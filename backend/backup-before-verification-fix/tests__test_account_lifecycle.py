"""Self-registration, email verification, password recovery, invitations,
approvals, role changes and session revocation."""
import re
from datetime import timedelta

import pytest

from app.models import (
    AccountToken, ApprovalStatus, AuditLog, Role, StaffInvitation, StudentProfile, User,
)
from app.utils.time import utcnow

PASSWORD = "Str0ngPassword!"
NEW_PASSWORD = "BrandNewPass9"

STUDENT = {
    "full_name": "Ananya Iyer", "student_code": "cs2026-099", "email": "Ananya@College.edu",
    "phone": "+91 99887 76655", "course": "B.Tech", "department": "Computer Science",
    "academic_year": 2, "emergency_contact_name": "R. Iyer",
    "emergency_contact_phone": "9876543210", "password": PASSWORD,
    "confirm_password": PASSWORD, "accept_terms": True,
}
STAFF = {
    "full_name": "Vikram Rao", "email": "vikram@hostel.edu", "phone": "9123456780",
    "employee_id": "emp-101", "department": "Maintenance", "requested_role": "warden",
    "password": PASSWORD, "confirm_password": PASSWORD, "accept_terms": True,
}


# --- helpers -------------------------------------------------------------

def outbox(app):
    return app.extensions.setdefault("mail_outbox", [])


def last_link_token(app, to=None):
    msgs = [m for m in outbox(app) if to is None or m["To"] == to]
    assert msgs, "no email was sent"
    body = msgs[-1].get_body(preferencelist=("plain",)).get_content()
    return re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)


def login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def signup_student(client, **overrides):
    return client.post("/api/auth/signup/student", json={**STUDENT, **overrides})


def signup_staff(client, **overrides):
    return client.post("/api/auth/signup/staff", json={**STAFF, **overrides})


def get_user(db, email):
    db.session.expire_all()
    return db.session.scalar(db.select(User).filter_by(email=email))


# --- policy --------------------------------------------------------------

def test_signup_policy_is_public(client):
    data = client.get("/api/auth/signup-policy").get_json()["data"]
    assert data["student_signup_enabled"] and data["email_verification_required"]


# --- student signup ------------------------------------------------------

def test_student_signup_creates_pending_unverified_account(app, client, db):
    res = signup_student(client)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()["data"]
    assert body == {"account_type": "student", "email": "ananya@college.edu",
                    "verification_required": True, "approval_required": True, "role": "student"}

    user = get_user(db, "ananya@college.edu")
    assert user.role == Role.STUDENT
    assert user.approval_status == ApprovalStatus.PENDING
    assert user.email_verified_at is None
    assert user.password_hash.startswith("scrypt:") and PASSWORD not in user.password_hash
    profile = user.student_profile
    assert profile.student_code == "CS2026-099"
    assert profile.current_allocation is None          # no room allocated
    assert profile.fee_records == []                    # no fees created or paid
    assert len(outbox(app)) == 1 and outbox(app)[0]["To"] == "ananya@college.edu"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="auth.signup_student"))


def test_student_signup_ignores_client_supplied_role_and_status(client, db):
    res = signup_student(client, role="admin", approval_status="approved",
                         email_verified_at="2026-01-01T00:00:00", is_active=True)
    assert res.status_code == 201
    user = get_user(db, "ananya@college.edu")
    assert user.role == Role.STUDENT and user.approval_status == ApprovalStatus.PENDING
    assert user.email_verified_at is None


@pytest.mark.parametrize("field,value", [
    ("email", "not-an-email"), ("phone", "abc"), ("academic_year", 0), ("full_name", ""),
    ("password", "weak"), ("confirm_password", "Different123"), ("accept_terms", False),
    ("emergency_contact_phone", "12"),
])
def test_student_signup_validation(client, field, value):
    res = signup_student(client, **{field: value})
    assert res.status_code == 422
    assert field in res.get_json()["error"]["details"]["fields"]


def test_student_signup_duplicates(client, make_student, db):
    existing = make_student(code="CS2026-099")
    db.session.commit()
    dup_code = signup_student(client)
    assert dup_code.status_code == 409
    assert "student_code" in dup_code.get_json()["error"]["details"]["fields"]
    dup_email = signup_student(client, student_code="OTHER-1", email=existing.user.email)
    assert dup_email.status_code == 409
    assert "email" in dup_email.get_json()["error"]["details"]["fields"]


def test_student_signup_can_be_disabled(app, client):
    app.config["STUDENT_SIGNUP_ENABLED"] = False
    res = signup_student(client)
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "signup_disabled"


def test_signup_is_rate_limited_per_ip(client):
    for i in range(10):
        signup_student(client, email=f"s{i}@college.edu", student_code=f"RL-{i}")
    res = signup_student(client, email="late@college.edu", student_code="RL-LATE")
    assert res.status_code == 429


# --- email verification --------------------------------------------------

def test_full_student_journey(app, client, db, auth_headers, make_user):
    signup_student(client)
    # Unverified: login refused with a specific code (password was correct).
    blocked = login(client, "ananya@college.edu")
    assert blocked.status_code == 403
    assert blocked.get_json()["error"]["code"] == "email_unverified"

    token = last_link_token(app)
    verified = client.post("/api/auth/verify-email", json={"token": token})
    assert verified.status_code == 200
    assert verified.get_json()["data"]["approval_required"] is True

    pending = login(client, "ananya@college.edu")
    assert pending.status_code == 403
    assert pending.get_json()["error"]["code"] == "account_pending"

    warden = auth_headers(make_user(Role.WARDEN))
    student_id = get_user(db, "ananya@college.edu").student_profile.id
    pending_list = client.get("/api/students?approval=pending", headers=warden).get_json()["data"]
    assert [s["id"] for s in pending_list["items"]] == [student_id]
    approved = client.post(f"/api/students/{student_id}/approve", headers=warden)
    assert approved.status_code == 200
    assert approved.get_json()["data"]["approval_status"] == "approved"

    ok = login(client, "ananya@college.edu")
    assert ok.status_code == 200
    assert ok.get_json()["data"]["user"]["role"] == "student"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="auth.email_verified"))
    assert db.session.scalar(db.select(AuditLog).filter_by(action="account.approve"))


def test_student_without_approval_policy_can_login_after_verifying(app, client):
    app.config["STUDENT_APPROVAL_REQUIRED"] = False
    res = signup_student(client)
    assert res.get_json()["data"]["approval_required"] is False
    client.post("/api/auth/verify-email", json={"token": last_link_token(app)})
    assert login(client, "ananya@college.edu").status_code == 200


def test_verification_token_is_single_use(app, client):
    signup_student(client)
    token = last_link_token(app)
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    reused = client.post("/api/auth/verify-email", json={"token": token})
    assert reused.status_code == 400 and reused.get_json()["error"]["code"] == "token_invalid"


def test_expired_verification_token(app, client, db):
    signup_student(client)
    token = last_link_token(app)
    for t in db.session.scalars(db.select(AccountToken)):
        t.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    res = client.post("/api/auth/verify-email", json={"token": token})
    assert res.status_code == 400 and res.get_json()["error"]["code"] == "token_expired"


def test_garbage_verification_token(client):
    res = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    assert res.status_code == 400


def test_resend_verification_invalidates_old_link(app, client):
    signup_student(client)
    first = last_link_token(app)
    res = client.post("/api/auth/resend-verification", json={"email": "ananya@college.edu"})
    assert res.status_code == 200
    second = last_link_token(app)
    assert first != second
    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200


def test_resend_verification_does_not_reveal_accounts(app, client):
    signup_student(client)
    before = len(outbox(app))
    known = client.post("/api/auth/resend-verification", json={"email": "ananya@college.edu"})
    unknown = client.post("/api/auth/resend-verification", json={"email": "nobody@college.edu"})
    assert known.status_code == unknown.status_code == 200
    assert known.get_json()["message"] == unknown.get_json()["message"]
    assert len(outbox(app)) == before + 1  # only the real account got an email


def test_resend_verification_rate_limited(client):
    for _ in range(3):
        client.post("/api/auth/resend-verification", json={"email": "x@college.edu"})
    assert client.post("/api/auth/resend-verification",
                       json={"email": "x@college.edu"}).status_code == 429


def test_tokens_are_stored_hashed(app, client, db):
    signup_student(client)
    raw = last_link_token(app)
    stored = db.session.scalars(db.select(AccountToken.token_hash)).all()
    assert raw not in stored and all(len(h) == 64 for h in stored)


# --- forgot / reset password ---------------------------------------------

def test_forgot_password_generic_response(app, client, make_user, db):
    make_user(Role.STUDENT, email="known@college.edu")
    db.session.commit()
    known = client.post("/api/auth/forgot-password", json={"email": "known@college.edu"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "ghost@college.edu"})
    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert [m["To"] for m in outbox(app)] == ["known@college.edu"]
    assert "token" not in str(known.get_json())  # never leaked in the API response


def test_forgot_password_not_sent_to_disabled_accounts(app, client, make_user, db):
    make_user(Role.STUDENT, email="gone@college.edu", is_active=False)
    db.session.commit()
    res = client.post("/api/auth/forgot-password", json={"email": "gone@college.edu"})
    assert res.status_code == 200 and outbox(app) == []


def test_password_reset_flow_revokes_sessions(app, client, make_user, auth_headers, db):
    user = make_user(Role.WARDEN, email="w@hostel.edu")
    old_session = auth_headers(user)
    client.post("/api/auth/forgot-password", json={"email": "w@hostel.edu"})
    token = last_link_token(app, "w@hostel.edu")

    mismatch = client.post("/api/auth/reset-password",
                           json={"token": token, "password": NEW_PASSWORD, "confirm_password": "nope"})
    assert mismatch.status_code == 422
    weak = client.post("/api/auth/reset-password", json={"token": token, "password": "weak"})
    assert weak.status_code == 422

    ok = client.post("/api/auth/reset-password",
                     json={"token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert ok.status_code == 200
    assert client.get("/api/auth/me", headers=old_session).status_code == 401
    assert login(client, "w@hostel.edu").status_code == 401
    assert login(client, "w@hostel.edu", NEW_PASSWORD).status_code == 200

    reused = client.post("/api/auth/reset-password", json={"token": token, "password": "Another123Pass"})
    assert reused.status_code == 400 and reused.get_json()["error"]["code"] == "token_invalid"
    entry = db.session.scalar(db.select(AuditLog).filter_by(action="auth.password_reset"))
    assert entry and NEW_PASSWORD not in str(entry.details) and token not in str(entry.details)


def test_expired_reset_token(app, client, make_user, db):
    make_user(Role.STUDENT, email="s@college.edu")
    db.session.commit()
    client.post("/api/auth/forgot-password", json={"email": "s@college.edu"})
    token = last_link_token(app)
    for t in db.session.scalars(db.select(AccountToken)):
        t.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    res = client.post("/api/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})
    assert res.status_code == 400 and res.get_json()["error"]["code"] == "token_expired"


def test_reset_token_only_changes_its_own_account(app, client, make_user, db):
    make_user(Role.STUDENT, email="a@college.edu")
    make_user(Role.STUDENT, email="b@college.edu")
    db.session.commit()
    client.post("/api/auth/forgot-password", json={"email": "a@college.edu"})
    token = last_link_token(app, "a@college.edu")
    client.post("/api/auth/reset-password",
                json={"token": token, "password": NEW_PASSWORD, "email": "b@college.edu", "user_id": 2})
    assert login(client, "a@college.edu", NEW_PASSWORD).status_code == 200
    assert login(client, "b@college.edu").status_code == 200  # unchanged


def test_new_reset_request_invalidates_previous_link(app, client, make_user, db):
    make_user(Role.STUDENT, email="s@college.edu")
    db.session.commit()
    client.post("/api/auth/forgot-password", json={"email": "s@college.edu"})
    first = last_link_token(app)
    client.post("/api/auth/forgot-password", json={"email": "s@college.edu"})
    assert client.post("/api/auth/reset-password",
                       json={"token": first, "password": NEW_PASSWORD}).status_code == 400


def test_forgot_password_rate_limited(client):
    for _ in range(3):
        client.post("/api/auth/forgot-password", json={"email": "x@college.edu"})
    res = client.post("/api/auth/forgot-password", json={"email": "x@college.edu"})
    assert res.status_code == 429


# --- staff signup & invitations ------------------------------------------

def _invite(client, headers, email="vikram@hostel.edu", role="warden"):
    return client.post("/api/auth/invitations", headers=headers, json={"email": email, "role": role})


def test_staff_application_without_invitation_is_pending_low_role(app, client, db, admin_headers):
    res = signup_staff(client)
    assert res.status_code == 201
    assert res.get_json()["data"]["role"] == "staff"   # NOT the requested "warden"
    client.post("/api/auth/verify-email", json={"token": last_link_token(app)})
    blocked = login(client, "vikram@hostel.edu")
    assert blocked.get_json()["error"]["code"] == "account_pending"

    pending = client.get("/api/auth/staff?approval=pending", headers=admin_headers).get_json()["data"]
    assert pending["counts"]["pending"] == 1
    applicant = pending["items"][0]
    assert applicant["staff_profile"]["requested_role"] == "warden"

    approved = client.post(f"/api/auth/staff/{applicant['id']}/approve", headers=admin_headers,
                           json={"role": "warden"})
    assert approved.status_code == 200 and approved.get_json()["data"]["role"] == "warden"
    assert login(client, "vikram@hostel.edu").status_code == 200


def test_staff_approval_cannot_grant_admin(app, client, admin_headers, db):
    signup_staff(client)
    user = get_user(db, "vikram@hostel.edu")
    res = client.post(f"/api/auth/staff/{user.id}/approve", headers=admin_headers, json={"role": "admin"})
    assert res.status_code == 422
    assert get_user(db, "vikram@hostel.edu").role == Role.STAFF


def test_staff_signup_never_creates_admin(client, db):
    res = signup_staff(client, requested_role="admin", role="admin")
    assert res.status_code == 422  # "admin" is not a requestable role
    res = signup_staff(client, role="admin")
    assert res.status_code == 201
    assert get_user(db, "vikram@hostel.edu").role == Role.STAFF


def test_staff_signup_with_invitation(app, client, db, admin_headers):
    created = _invite(client, admin_headers, role="warden")
    assert created.status_code == 201
    code = created.get_json()["data"]["code"]
    assert len(outbox(app)) == 1  # invitation emailed
    assert code not in str(db.session.scalars(db.select(StaffInvitation.token_hash)).all())

    check = client.post("/api/auth/invitations/validate", json={"code": code}).get_json()["data"]
    assert check["email"] == "vikram@hostel.edu" and check["role"] == "warden"

    # Requested role is ignored; the invitation decides.
    res = signup_staff(client, invitation_code=code, requested_role="staff")
    assert res.status_code == 201
    assert res.get_json()["data"] == {"account_type": "staff", "email": "vikram@hostel.edu",
                                      "verification_required": True, "approval_required": False,
                                      "role": "warden"}
    client.post("/api/auth/verify-email", json={"token": last_link_token(app, "vikram@hostel.edu")})
    assert login(client, "vikram@hostel.edu").status_code == 200

    # Single use.
    again = signup_staff(client, invitation_code=code, email="vikram@hostel.edu",
                         employee_id="EMP-999")
    assert again.status_code == 400
    assert again.get_json()["error"]["code"] == "invitation_invalid"


def test_invitation_bound_to_email(client, admin_headers):
    code = _invite(client, admin_headers).get_json()["data"]["code"]
    res = signup_staff(client, invitation_code=code, email="someone.else@hostel.edu")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "invitation_email_mismatch"


def test_expired_and_revoked_invitations(client, admin_headers, db):
    expired_code = _invite(client, admin_headers, email="old@hostel.edu").get_json()["data"]["code"]
    inv = db.session.scalar(db.select(StaffInvitation).filter_by(email="old@hostel.edu"))
    inv.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    res = signup_staff(client, invitation_code=expired_code, email="old@hostel.edu")
    assert res.get_json()["error"]["code"] == "invitation_expired"

    created = _invite(client, admin_headers, email="new@hostel.edu").get_json()["data"]
    assert client.post(f"/api/auth/invitations/{created['id']}/revoke",
                       headers=admin_headers).status_code == 200
    res = signup_staff(client, invitation_code=created["code"], email="new@hostel.edu",
                       employee_id="EMP-2")
    assert res.get_json()["error"]["code"] == "invitation_invalid"
    listed = client.get("/api/auth/invitations?status=revoked", headers=admin_headers).get_json()["data"]
    assert [i["email"] for i in listed["items"]] == ["new@hostel.edu"]


def test_invitation_cannot_grant_admin(client, admin_headers):
    res = _invite(client, admin_headers, role="admin")
    assert res.status_code == 422


def test_staff_signup_requires_invitation_when_open_signup_disabled(app, client):
    app.config["STAFF_SIGNUP_ENABLED"] = False
    res = signup_staff(client)
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "invitation_required"


def test_duplicate_employee_id(client, admin_headers):
    signup_staff(client)
    res = signup_staff(client, email="other@hostel.edu")
    assert res.status_code == 409
    assert "employee_id" in res.get_json()["error"]["details"]["fields"]


def test_only_admins_manage_invitations_and_approvals(client, warden_headers, student_headers, db):
    signup_staff(client)
    uid = get_user(db, "vikram@hostel.edu").id
    for headers in (warden_headers, student_headers):
        assert _invite(client, headers).status_code == 403
        assert client.get("/api/auth/invitations", headers=headers).status_code == 403
        assert client.post(f"/api/auth/staff/{uid}/approve", headers=headers,
                           json={"role": "warden"}).status_code == 403


def test_reject_staff_application(app, client, db, admin_headers):
    signup_staff(client)
    client.post("/api/auth/verify-email", json={"token": last_link_token(app)})
    uid = get_user(db, "vikram@hostel.edu").id
    assert client.post(f"/api/auth/staff/{uid}/reject", headers=admin_headers,
                       json={"reason": ""}).status_code == 422
    res = client.post(f"/api/auth/staff/{uid}/reject", headers=admin_headers,
                      json={"reason": "Not on the employee roster"})
    assert res.status_code == 200 and res.get_json()["data"]["approval_status"] == "rejected"
    blocked = login(client, "vikram@hostel.edu")
    assert blocked.get_json()["error"]["code"] == "account_rejected"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="account.reject"))


# --- role changes & admin safeguards -------------------------------------

def test_admin_role_changes_revoke_sessions(client, make_user, auth_headers, admin_headers):
    warden = make_user(Role.WARDEN)
    warden_session = auth_headers(warden)
    res = client.patch(f"/api/auth/staff/{warden.id}", headers=admin_headers, json={"role": "staff"})
    assert res.status_code == 200 and res.get_json()["data"]["role"] == "staff"
    assert client.get("/api/auth/me", headers=warden_session).status_code == 401


def test_warden_cannot_promote_self(client, make_user, auth_headers):
    warden = make_user(Role.WARDEN)
    headers = auth_headers(warden)
    assert client.patch(f"/api/auth/staff/{warden.id}", headers=headers,
                        json={"role": "admin"}).status_code == 403
    assert client.patch("/api/auth/me", headers=headers, json={"role": "admin"}).status_code == 403


def test_admin_cannot_demote_self_or_last_admin(client, make_user, auth_headers):
    admin = make_user(Role.ADMIN)
    headers = auth_headers(admin)
    res = client.patch(f"/api/auth/staff/{admin.id}", headers=headers, json={"role": "warden"})
    assert res.status_code == 400
    other = make_user(Role.ADMIN)
    # Demoting another admin is fine while two are active...
    assert client.patch(f"/api/auth/staff/{other.id}", headers=headers,
                        json={"role": "warden"}).status_code == 200


def test_admin_sends_password_reset_link(app, client, make_user, admin_headers):
    warden = make_user(Role.WARDEN, email="w2@hostel.edu")
    res = client.post(f"/api/auth/staff/{warden.id}/send-password-reset", headers=admin_headers)
    assert res.status_code == 200
    assert "token" not in str(res.get_json())
    assert outbox(app)[-1]["To"] == "w2@hostel.edu"


# --- student account management ------------------------------------------

def test_staff_reject_student_and_history(app, client, db, warden_headers):
    signup_student(client)
    sid = get_user(db, "ananya@college.edu").student_profile.id
    res = client.post(f"/api/students/{sid}/reject", headers=warden_headers,
                      json={"reason": "Not enrolled this semester"})
    assert res.status_code == 200 and res.get_json()["data"]["approval_status"] == "rejected"
    history = client.get(f"/api/students/{sid}/history", headers=warden_headers).get_json()["data"]
    actions = [h["action"] for h in history["items"]]
    assert "account.reject" in actions and "auth.signup_student" in actions


def test_cannot_approve_unverified_student(client, db, warden_headers):
    signup_student(client)
    sid = get_user(db, "ananya@college.edu").student_profile.id
    res = client.post(f"/api/students/{sid}/approve", headers=warden_headers)
    assert res.status_code == 409 and res.get_json()["error"]["code"] == "email_unverified"


def test_student_filters_by_verification(client, db, warden_headers, make_student):
    make_student(code="OLD-1")
    db.session.commit()
    signup_student(client)
    unverified = client.get("/api/students?verified=false", headers=warden_headers).get_json()["data"]
    assert [s["student_code"] for s in unverified["items"]] == ["CS2026-099"]


def test_students_cannot_manage_accounts(client, student_headers, db):
    signup_student(client)
    sid = get_user(db, "ananya@college.edu").student_profile.id
    assert client.post(f"/api/students/{sid}/approve", headers=student_headers).status_code == 403
    assert client.get(f"/api/students/{sid}/history", headers=student_headers).status_code == 403


def test_deactivation_revokes_sessions_immediately(client, make_student, auth_headers, warden_headers, db):
    student = make_student()
    session = auth_headers(student.user)
    client.patch(f"/api/students/{student.id}/status", headers=warden_headers, json={"is_active": False})
    assert client.get("/api/auth/me", headers=session).status_code == 401


# --- profile & sessions --------------------------------------------------

def test_profile_update_limited_fields(client, make_student, auth_headers, db):
    student = make_student()
    headers = auth_headers(student.user)
    res = client.patch("/api/auth/me", headers=headers,
                       json={"phone": "9000011111", "emergency_contact_name": "New Contact"})
    assert res.status_code == 200
    assert res.get_json()["data"]["student_profile"]["emergency_contact"]["name"] == "New Contact"
    for field in ("email", "role", "approval_status", "student_code"):
        blocked = client.patch("/api/auth/me", headers=headers, json={field: "x"})
        assert blocked.status_code == 403, field


def test_logout_all_sessions(client, make_user, auth_headers):
    user = make_user(Role.WARDEN)
    first, second = auth_headers(user), auth_headers(user)
    assert client.post("/api/auth/logout-all", headers=first).status_code == 200
    assert client.get("/api/auth/me", headers=first).status_code == 401
    assert client.get("/api/auth/me", headers=second).status_code == 401


def test_change_password_requires_matching_confirmation(client, make_user, auth_headers):
    headers = auth_headers(make_user(Role.WARDEN))
    res = client.post("/api/auth/change-password", headers=headers,
                      json={"current_password": PASSWORD, "new_password": NEW_PASSWORD,
                            "confirm_password": "Mismatch123"})
    assert res.status_code == 422
    assert "confirm_password" in res.get_json()["error"]["details"]["fields"]


# --- the limited "staff" role --------------------------------------------

def test_staff_role_permissions(client, make_user, auth_headers, make_student, db):
    headers = auth_headers(make_user(Role.STAFF))
    student = make_student()
    db.session.commit()
    assert client.get("/api/students", headers=headers).status_code == 200
    assert client.get(f"/api/students/{student.id}", headers=headers).status_code == 200
    assert client.get("/api/rooms", headers=headers).status_code == 200
    assert client.get("/api/complaints", headers=headers).status_code == 200
    summary = client.get("/api/dashboard/summary", headers=headers).get_json()["data"]
    assert "fees" not in summary and "payments" not in summary
    # Not allowed:
    assert client.get("/api/fees", headers=headers).status_code == 403
    assert client.get("/api/payments", headers=headers).status_code == 403
    assert client.post("/api/allocations", headers=headers, json={}).status_code == 403
    assert client.patch(f"/api/students/{student.id}", headers=headers,
                        json={"course": "X"}).status_code == 403
    assert client.post("/api/rooms", headers=headers, json={}).status_code == 403
    assert client.get("/api/auth/staff", headers=headers).status_code == 403
    assert client.get("/api/reports/summary", headers=headers).status_code == 403


# --- existing users & login hardening -------------------------------------

def test_unverified_legacy_style_user_without_requirement(app, client, db, make_user):
    """If verification is switched off, unverified accounts may sign in."""
    make_user(Role.STUDENT, email="nv@college.edu", email_verified_at=None)
    db.session.commit()
    assert login(client, "nv@college.edu").get_json()["error"]["code"] == "email_unverified"
    app.config["EMAIL_VERIFICATION_REQUIRED"] = False
    assert login(client, "nv@college.edu").status_code == 200


def test_wrong_password_never_reveals_account_state(client, db, make_user):
    make_user(Role.STUDENT, email="p@college.edu", approval_status=ApprovalStatus.PENDING)
    db.session.commit()
    res = login(client, "p@college.edu", "WrongPass999")
    assert res.status_code == 401 and res.get_json()["error"]["code"] == "invalid_credentials"


def test_existing_tokens_stop_working_when_account_state_changes(client, make_user, auth_headers, db):
    """Defence in depth: every request re-checks approval and verification,
    even if no session revocation happened."""
    user = make_user(Role.WARDEN)
    headers = auth_headers(user)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    user.approval_status = ApprovalStatus.PENDING
    db.session.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    user.approval_status = ApprovalStatus.APPROVED
    user.email_verified_at = None
    db.session.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
