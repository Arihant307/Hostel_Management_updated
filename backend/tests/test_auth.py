"""Authentication, session lifecycle and role-based permissions."""
from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.models import AuditLog, Role, User

PASSWORD = "Str0ngPassword!"


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- login -----------------------------------------------------------------

def test_login_success_returns_token_and_user(client, db, make_user):
    user = make_user(Role.WARDEN, email="warden@hostel.edu")
    db.session.commit()
    res = _login(client, "  WARDEN@hostel.edu ")  # normalised
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["access_token"] and data["token_type"] == "Bearer"
    assert data["user"]["role"] == "warden"
    assert "password_hash" not in data["user"]
    assert db.session.get(User, user.id).last_login_at is not None
    assert db.session.scalar(db.select(AuditLog).filter_by(action="auth.login"))


def test_student_login_includes_profile(client, db, make_student):
    profile = make_student(code="STU-77")
    db.session.commit()
    data = _login(client, profile.user.email).get_json()["data"]
    assert data["student_profile"]["student_code"] == "STU-77"


@pytest.mark.parametrize("email,password", [
    ("admin@hostel.edu", "WrongPassword1"),
    ("nobody@hostel.edu", PASSWORD),
])
def test_login_failures_are_indistinguishable(client, db, make_user, email, password):
    make_user(Role.ADMIN, email="admin@hostel.edu")
    db.session.commit()
    res = _login(client, email, password)
    assert res.status_code == 401
    assert res.get_json()["error"] == {"code": "invalid_credentials",
                                       "message": "Invalid email or password."}


def test_login_requires_fields(client):
    res = client.post("/api/auth/login", json={"email": ""})
    assert res.status_code == 422
    assert set(res.get_json()["error"]["details"]["fields"]) == {"email", "password"}


def test_login_rejects_non_json(client):
    res = client.post("/api/auth/login", data="email=x", content_type="text/plain")
    assert res.status_code == 422


def test_deactivated_user_cannot_login(client, db, make_user):
    make_user(Role.WARDEN, email="gone@hostel.edu", is_active=False)
    db.session.commit()
    res = _login(client, "gone@hostel.edu")
    assert res.status_code == 403
    assert res.get_json()["error"]["code"] == "account_disabled"


def test_login_is_throttled_after_repeated_failures(client, db, make_user):
    make_user(Role.ADMIN, email="admin@hostel.edu")
    db.session.commit()
    for _ in range(5):
        assert _login(client, "admin@hostel.edu", "WrongPassword1").status_code == 401
    res = _login(client, "admin@hostel.edu")  # even the right password is blocked now
    assert res.status_code == 429
    assert res.get_json()["error"]["code"] == "too_many_attempts"


# --- tokens & session ------------------------------------------------------

def test_me_requires_token(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "authorization_required"


def test_me_with_token(client, make_user, auth_headers):
    user = make_user(Role.ADMIN)
    res = client.get("/api/auth/me", headers=auth_headers(user))
    assert res.status_code == 200
    assert res.get_json()["data"]["user"]["email"] == user.email


def test_garbage_token_rejected(client):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "invalid_token"


def test_expired_token_rejected(client, db, make_user):
    user = make_user(Role.ADMIN)
    db.session.commit()
    token = create_access_token(identity=user, additional_claims={"ver": 0},
                                expires_delta=timedelta(seconds=-1))
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "token_expired"


def test_logout_revokes_token(client, make_user, auth_headers):
    headers = auth_headers(make_user(Role.WARDEN))
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "token_revoked"


def test_deactivation_invalidates_existing_tokens(client, db, make_user, auth_headers):
    user = make_user(Role.WARDEN)
    headers = auth_headers(user)
    user.is_active = False
    db.session.commit()
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "session_invalid"


# --- change password -------------------------------------------------------

def test_change_password_flow(client, db, make_user, auth_headers):
    user = make_user(Role.STUDENT, email="stu@hostel.edu")
    old_headers = auth_headers(user)

    res = client.post("/api/auth/change-password", headers=old_headers,
                      json={"current_password": PASSWORD, "new_password": "BrandNewPass9"})
    assert res.status_code == 200
    new_token = res.get_json()["data"]["access_token"]

    assert client.get("/api/auth/me", headers=old_headers).status_code == 401
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
    assert _login(client, "stu@hostel.edu", PASSWORD).status_code == 401
    assert _login(client, "stu@hostel.edu", "BrandNewPass9").status_code == 200


@pytest.mark.parametrize("body,field", [
    ({"current_password": "WrongPass123", "new_password": "BrandNewPass9"}, "current_password"),
    ({"current_password": PASSWORD, "new_password": "weak"}, "new_password"),
    ({"current_password": PASSWORD, "new_password": PASSWORD}, "new_password"),
])
def test_change_password_validation(client, make_user, auth_headers, body, field):
    res = client.post("/api/auth/change-password",
                      headers=auth_headers(make_user(Role.WARDEN)), json=body)
    assert res.status_code == 422
    assert field in res.get_json()["error"]["details"]["fields"]


# --- staff management & role permissions -----------------------------------

NEW_WARDEN = {"full_name": "Asha Rao", "email": "asha@hostel.edu", "phone": "+91 98765 43210",
              "role": "warden", "password": "WardenPass123"}


def test_admin_creates_warden_who_can_login(client, make_user, auth_headers):
    res = client.post("/api/auth/staff", headers=auth_headers(make_user(Role.ADMIN)),
                      json=NEW_WARDEN)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["data"]["role"] == "warden"
    assert _login(client, "asha@hostel.edu", "WardenPass123").status_code == 200


@pytest.mark.parametrize("role", [Role.WARDEN, Role.STUDENT])
def test_non_admins_cannot_manage_staff(client, make_user, auth_headers, role):
    headers = auth_headers(make_user(role))
    assert client.post("/api/auth/staff", headers=headers, json=NEW_WARDEN).status_code == 403
    assert client.get("/api/auth/staff", headers=headers).status_code == 403
    assert client.patch("/api/auth/staff/1", headers=headers,
                        json={"is_active": False}).status_code == 403


def test_staff_endpoints_require_authentication(client):
    assert client.get("/api/auth/staff").status_code == 401
    assert client.post("/api/auth/staff", json=NEW_WARDEN).status_code == 401


def test_create_staff_validation_and_duplicates(client, make_user, auth_headers):
    headers = auth_headers(make_user(Role.ADMIN, email="taken@hostel.edu"))
    bad = client.post("/api/auth/staff", headers=headers,
                      json={"full_name": "", "email": "nope", "role": "student",
                            "password": "short"})
    assert bad.status_code == 422
    assert set(bad.get_json()["error"]["details"]["fields"]) == {
        "full_name", "email", "role", "password"}

    dup = client.post("/api/auth/staff", headers=headers,
                      json={**NEW_WARDEN, "email": "TAKEN@hostel.edu"})
    assert dup.status_code == 409


def test_cannot_create_student_through_staff_endpoint(client, make_user, auth_headers):
    res = client.post("/api/auth/staff", headers=auth_headers(make_user(Role.ADMIN)),
                      json={**NEW_WARDEN, "role": "student"})
    assert res.status_code == 422


def test_list_staff_filters_and_paginates(client, make_user, auth_headers):
    admin = make_user(Role.ADMIN, full_name="Main Admin")
    make_user(Role.WARDEN, full_name="Asha Rao")
    make_user(Role.WARDEN, full_name="Vikram Singh", is_active=False)
    make_user(Role.STUDENT, full_name="A Student")
    headers = auth_headers(admin)

    everyone = client.get("/api/auth/staff", headers=headers).get_json()["data"]
    assert everyone["pagination"]["total"] == 3  # students excluded

    wardens = client.get("/api/auth/staff?role=warden&status=active",
                         headers=headers).get_json()["data"]["items"]
    assert [w["full_name"] for w in wardens] == ["Asha Rao"]

    found = client.get("/api/auth/staff?search=vikram", headers=headers).get_json()["data"]
    assert found["pagination"]["total"] == 1

    page = client.get("/api/auth/staff?per_page=2&page=2", headers=headers).get_json()["data"]
    assert len(page["items"]) == 1 and page["pagination"]["pages"] == 2


def test_admin_deactivates_warden(client, db, make_user, auth_headers):
    admin = make_user(Role.ADMIN)
    warden = make_user(Role.WARDEN)
    warden_headers = auth_headers(warden)
    res = client.patch(f"/api/auth/staff/{warden.id}", headers=auth_headers(admin),
                       json={"is_active": False})
    assert res.status_code == 200 and res.get_json()["data"]["is_active"] is False
    assert client.get("/api/auth/me", headers=warden_headers).status_code == 401
    entry = db.session.scalar(db.select(AuditLog).filter_by(action="staff.update"))
    assert entry.actor_id == admin.id and entry.entity_id == warden.id


def test_admin_cannot_deactivate_self_or_last_admin(client, make_user, auth_headers):
    admin = make_user(Role.ADMIN)
    res = client.patch(f"/api/auth/staff/{admin.id}", headers=auth_headers(admin),
                       json={"is_active": False})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "self_deactivation"


def test_last_active_admin_is_protected(client, db, make_user, auth_headers):
    acting = make_user(Role.ADMIN)
    other = make_user(Role.ADMIN)
    headers = auth_headers(acting)
    # Deactivating the other admin is allowed while two are active...
    assert client.patch(f"/api/auth/staff/{other.id}", headers=headers,
                        json={"is_active": False}).status_code == 200
    # ...the acting admin now cannot be deactivated by anyone (self + last admin).
    assert client.patch(f"/api/auth/staff/{acting.id}", headers=headers,
                        json={"is_active": False}).status_code == 400


def test_staff_endpoint_does_not_expose_students(client, make_user, auth_headers):
    student = make_user(Role.STUDENT)
    res = client.patch(f"/api/auth/staff/{student.id}",
                       headers=auth_headers(make_user(Role.ADMIN)), json={"is_active": False})
    assert res.status_code == 404


def test_admin_resets_staff_password(client, make_user, auth_headers):
    warden = make_user(Role.WARDEN, email="w@hostel.edu")
    warden_headers = auth_headers(warden)
    res = client.post(f"/api/auth/staff/{warden.id}/reset-password",
                      headers=auth_headers(make_user(Role.ADMIN)),
                      json={"password": "ResetPass1234"})
    assert res.status_code == 200
    assert client.get("/api/auth/me", headers=warden_headers).status_code == 401
    assert _login(client, "w@hostel.edu", "ResetPass1234").status_code == 200


def test_audit_log_never_stores_passwords(client, db, make_user, auth_headers):
    client.post("/api/auth/staff", headers=auth_headers(make_user(Role.ADMIN)), json=NEW_WARDEN)
    for entry in db.session.scalars(db.select(AuditLog)):
        assert "WardenPass123" not in str(entry.details)
