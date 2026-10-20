"""Student CRUD, validation, search and safeguards."""
from datetime import date

import pytest

from app.models import AllocationStatus, AuditLog, RoomAllocation, StudentProfile, User

NEW_STUDENT = {
    "full_name": "Ananya Iyer", "email": "ananya@college.edu", "phone": "+91 99887 76655",
    "student_code": "cs2026-014", "course": "B.Tech", "department": "Computer Science",
    "academic_year": 2, "gender": "female", "emergency_contact_name": "R. Iyer",
    "emergency_contact_phone": "9876543210", "emergency_contact_relation": "Father",
    "registration_date": "2026-07-15", "password": "Welcome2Hostel",
}


def _create(client, headers, **overrides):
    return client.post("/api/students", headers=headers, json={**NEW_STUDENT, **overrides})


def test_staff_registers_student_who_can_login(client, warden_headers):
    res = _create(client, warden_headers)
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert data["student_code"] == "CS2026-014"  # normalised
    assert data["email"] == "ananya@college.edu"
    assert data["current_allocation"] is None
    assert data["fee_summary"]["outstanding_minor"] == 0
    login = client.post("/api/auth/login",
                        json={"email": "ananya@college.edu", "password": "Welcome2Hostel"})
    assert login.status_code == 200
    assert login.get_json()["data"]["student_profile"]["student_code"] == "CS2026-014"


def test_student_creation_is_audited(client, db, admin_headers):
    _create(client, admin_headers)
    assert db.session.scalar(db.select(AuditLog).filter_by(action="student.create"))


@pytest.mark.parametrize("field,value", [
    ("email", "not-an-email"), ("academic_year", 9), ("emergency_contact_phone", "abc"),
    ("full_name", ""), ("password", "weak"), ("registration_date", "2099-01-01"),
    ("gender", "unknown"), ("date_of_birth", "15/08/2005"),
])
def test_student_validation(client, admin_headers, field, value):
    res = _create(client, admin_headers, **{field: value})
    assert res.status_code == 422
    assert field in res.get_json()["error"]["details"]["fields"]


def test_duplicate_email_and_student_id(client, admin_headers):
    assert _create(client, admin_headers).status_code == 201
    dup_email = _create(client, admin_headers, student_code="OTHER-1")
    assert dup_email.status_code == 409
    assert "email" in dup_email.get_json()["error"]["details"]["fields"]
    dup_code = _create(client, admin_headers, email="other@college.edu", student_code="CS2026-014")
    assert dup_code.status_code == 409
    assert "student_code" in dup_code.get_json()["error"]["details"]["fields"]


def test_students_cannot_manage_students(client, student_headers):
    assert client.get("/api/students", headers=student_headers).status_code == 403
    assert _create(client, student_headers).status_code == 403
    other = student_headers.profile.id
    assert client.get(f"/api/students/{other}", headers=student_headers).status_code == 403


def test_student_reads_own_profile(client, student_headers):
    res = client.get("/api/students/me", headers=student_headers)
    assert res.status_code == 200
    assert res.get_json()["data"]["id"] == student_headers.profile.id


def test_staff_cannot_use_me_endpoint(client, warden_headers):
    assert client.get("/api/students/me", headers=warden_headers).status_code == 403


def test_list_search_filter_sort_paginate(client, admin_headers, make_student, make_room, db):
    a = make_student(code="A-001", department="Physics", academic_year=1)
    a.user.full_name = "Zara Khan"
    b = make_student(code="B-002", department="Chemistry", academic_year=3)
    b.user.full_name = "Arjun Mehta"
    c = make_student(code="C-003", department="Physics", academic_year=3)
    c.user.is_active = False
    db.session.add(RoomAllocation(student=a, room=make_room(), allocated_on=date(2026, 8, 1)))
    db.session.commit()

    def get(qs):
        return client.get(f"/api/students?{qs}", headers=admin_headers).get_json()["data"]

    assert get("")["pagination"]["total"] == 3
    assert [s["student_code"] for s in get("search=arjun")["items"]] == ["B-002"]
    assert {s["student_code"] for s in get("department=Physics")["items"]} == {"A-001", "C-003"}
    assert [s["student_code"] for s in get("academic_year=1")["items"]] == ["A-001"]
    assert [s["student_code"] for s in get("status=inactive")["items"]] == ["C-003"]
    assert [s["student_code"] for s in get("has_room=true")["items"]] == ["A-001"]
    assert len(get("has_room=false")["items"]) == 2
    assert [s["full_name"] for s in get("sort=name&order=asc&status=active")["items"]] == \
        ["Arjun Mehta", "Zara Khan"]
    page = get("per_page=2&page=2")
    assert len(page["items"]) == 1 and page["pagination"]["pages"] == 2
    assert client.get("/api/students?status=bogus", headers=admin_headers).status_code == 422


def test_get_student_includes_allocation_history(client, admin_headers, make_student, make_room, db):
    s = make_student()
    db.session.add(RoomAllocation(student=s, room=make_room(), allocated_on=date(2026, 8, 1),
                                  status=AllocationStatus.CHECKED_OUT,
                                  checked_out_on=date(2026, 8, 20)))
    db.session.commit()
    data = client.get(f"/api/students/{s.id}", headers=admin_headers).get_json()["data"]
    assert len(data["allocation_history"]) == 1
    assert data["allocation_history"][0]["status"] == "checked_out"
    assert client.get("/api/students/9999", headers=admin_headers).status_code == 404


def test_update_student(client, db, admin_headers, make_student):
    s = make_student(code="UPD-1")
    other = make_student(code="UPD-2")
    db.session.commit()
    res = client.patch(f"/api/students/{s.id}", headers=admin_headers,
                       json={"full_name": "New Name", "academic_year": 4, "phone": "9123456780"})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert (data["full_name"], data["academic_year"], data["phone"]) == ("New Name", 4, "9123456780")
    clash = client.patch(f"/api/students/{s.id}", headers=admin_headers,
                         json={"student_code": "upd-2"})
    assert clash.status_code == 409
    assert client.patch(f"/api/students/{s.id}", headers=admin_headers,
                        json={"email": other.user.email}).status_code == 409
    assert client.patch(f"/api/students/{s.id}", headers=admin_headers,
                        json={"course": ""}).status_code == 422
    entry = db.session.scalar(db.select(AuditLog).filter_by(action="student.update"))
    assert "full_name" in entry.details["changes"]


def test_deactivation_requires_checkout_and_revokes_sessions(
        client, db, admin_headers, make_student, make_room, auth_headers):
    s = make_student()
    alloc = RoomAllocation(student=s, room=make_room(), allocated_on=date(2026, 8, 1))
    db.session.add(alloc)
    student_token = auth_headers(s.user)

    blocked = client.patch(f"/api/students/{s.id}/status", headers=admin_headers,
                           json={"is_active": False})
    assert blocked.status_code == 409
    assert blocked.get_json()["error"]["code"] == "has_active_allocation"

    alloc.status = AllocationStatus.CHECKED_OUT
    alloc.checked_out_on = date(2026, 9, 1)
    db.session.commit()
    ok = client.patch(f"/api/students/{s.id}/status", headers=admin_headers,
                      json={"is_active": False})
    assert ok.status_code == 200 and ok.get_json()["data"]["is_active"] is False
    assert client.get("/api/auth/me", headers=student_token).status_code == 401

    again = client.patch(f"/api/students/{s.id}/status", headers=admin_headers,
                         json={"is_active": True})
    assert again.get_json()["data"]["is_active"] is True


def test_delete_only_without_history_and_admin_only(
        client, db, admin_headers, warden_headers, make_student, make_room):
    clean = make_student()
    with_history = make_student()
    db.session.add(RoomAllocation(student=with_history, room=make_room(),
                                  allocated_on=date(2026, 8, 1)))
    db.session.commit()
    clean_id, user_id = clean.id, clean.user_id

    assert client.delete(f"/api/students/{clean_id}", headers=warden_headers).status_code == 403
    blocked = client.delete(f"/api/students/{with_history.id}", headers=admin_headers)
    assert blocked.status_code == 409 and blocked.get_json()["error"]["code"] == "has_history"

    assert client.delete(f"/api/students/{clean_id}", headers=admin_headers).status_code == 200
    db.session.expire_all()
    assert db.session.get(StudentProfile, clean_id) is None
    assert db.session.get(User, user_id) is None


def test_reset_student_password(client, db, warden_headers, make_student):
    s = make_student()
    db.session.commit()
    res = client.post(f"/api/students/{s.id}/reset-password", headers=warden_headers,
                      json={"password": "FreshStart2026"})
    assert res.status_code == 200
    assert client.post("/api/auth/login", json={"email": s.user.email,
                                                "password": "FreshStart2026"}).status_code == 200


def test_departments_endpoint(client, admin_headers, make_student, db):
    make_student(department="Physics")
    make_student(department="Biology")
    db.session.commit()
    assert client.get("/api/students/departments",
                      headers=admin_headers).get_json()["data"] == ["Biology", "Physics"]
