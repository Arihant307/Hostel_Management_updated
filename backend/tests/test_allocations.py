"""Room allocation, capacity enforcement, transfer, checkout and history."""
import threading
from datetime import date

from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.models import AllocationStatus, AuditLog, Role, Room, RoomAllocation, RoomType, StudentProfile, User


def _allocate(client, headers, student, room, **extra):
    return client.post("/api/allocations", headers=headers,
                       json={"student_id": student.id, "room_id": room.id,
                             "allocated_on": "2026-08-01", **extra})


def test_allocate_student(client, db, warden_headers, make_student, make_room):
    student, room = make_student(), make_room(capacity=2)
    db.session.commit()
    res = _allocate(client, warden_headers, student, room, expected_checkout_on="2027-05-31")
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert data["status"] == "active" and data["room"]["id"] == room.id
    detail = client.get(f"/api/rooms/{room.id}", headers=warden_headers).get_json()["data"]
    assert (detail["occupied_beds"], detail["available_beds"]) == (1, 1)
    assert db.session.scalar(db.select(AuditLog).filter_by(action="allocation.create"))


def test_capacity_enforced_on_backend(client, db, admin_headers, make_student, make_room):
    room = make_room(capacity=1)
    first, second = make_student(), make_student()
    db.session.commit()
    assert _allocate(client, admin_headers, first, room).status_code == 201
    res = _allocate(client, admin_headers, second, room)
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "room_full"


def test_no_duplicate_active_allocation(client, db, admin_headers, make_student, make_room):
    student = make_student()
    r1, r2 = make_room(), make_room()
    db.session.commit()
    assert _allocate(client, admin_headers, student, r1).status_code == 201
    res = _allocate(client, admin_headers, student, r2)
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "already_allocated"


def test_inactive_room_or_student_rejected(client, db, admin_headers, make_student, make_room):
    inactive_room = make_room(is_active=False)
    student = make_student()
    db.session.commit()
    assert _allocate(client, admin_headers, student, inactive_room).get_json()["error"]["code"] \
        == "room_inactive"
    student.user.is_active = False
    db.session.commit()
    assert _allocate(client, admin_headers, student, make_room()).get_json()["error"]["code"] \
        == "student_inactive"


def test_allocation_validation(client, db, admin_headers, make_student, make_room):
    student, room = make_student(), make_room()
    db.session.commit()
    bad_dates = _allocate(client, admin_headers, student, room, expected_checkout_on="2026-01-01")
    assert bad_dates.status_code == 422
    missing = client.post("/api/allocations", headers=admin_headers, json={"room_id": room.id})
    assert missing.status_code == 422
    assert "student_id" in missing.get_json()["error"]["details"]["fields"]
    unknown = client.post("/api/allocations", headers=admin_headers,
                          json={"student_id": 999, "room_id": room.id})
    assert unknown.status_code == 404


def test_students_cannot_allocate(client, db, student_headers, make_room):
    room = make_room()
    db.session.commit()
    res = _allocate(client, student_headers, student_headers.profile, room)
    assert res.status_code == 403


def test_transfer_preserves_history(client, db, admin_headers, make_student, make_room):
    student = make_student()
    old_room, new_room = make_room(capacity=1), make_room(capacity=1)
    db.session.commit()
    alloc_id = _allocate(client, admin_headers, student, old_room,
                         expected_checkout_on="2027-05-31").get_json()["data"]["id"]
    res = client.post(f"/api/allocations/{alloc_id}/transfer", headers=admin_headers,
                      json={"room_id": new_room.id, "transfer_date": "2026-09-15",
                            "notes": "Requested quieter floor"})
    assert res.status_code == 201, res.get_json()
    new = res.get_json()["data"]
    assert new["previous_allocation_id"] == alloc_id
    assert new["room"]["id"] == new_room.id
    assert new["expected_checkout_on"] == "2027-05-31"

    db.session.expire_all()
    old = db.session.get(RoomAllocation, alloc_id)
    assert old.status == AllocationStatus.TRANSFERRED
    assert old.checked_out_on == date(2026, 9, 15)
    assert db.session.get(Room, old_room.id).occupied_beds == 0
    assert db.session.get(Room, new_room.id).occupied_beds == 1

    history = client.get(f"/api/allocations?student_id={student.id}",
                         headers=admin_headers).get_json()["data"]["items"]
    assert [h["status"] for h in history] == ["active", "transferred"]


def test_transfer_rules(client, db, admin_headers, make_student, make_room):
    student, blocker = make_student(), make_student()
    room, full_room = make_room(capacity=2), make_room(capacity=1)
    db.session.commit()
    alloc_id = _allocate(client, admin_headers, student, room).get_json()["data"]["id"]
    _allocate(client, admin_headers, blocker, full_room)

    def transfer(**body):
        return client.post(f"/api/allocations/{alloc_id}/transfer", headers=admin_headers,
                           json=body)

    assert transfer(room_id=room.id).get_json()["error"]["code"] == "same_room"
    assert transfer(room_id=full_room.id).get_json()["error"]["code"] == "room_full"
    assert transfer(room_id=make_room().id, transfer_date="2026-07-01").status_code == 422
    # A failed transfer leaves the original allocation untouched.
    db.session.expire_all()
    assert db.session.get(RoomAllocation, alloc_id).status == AllocationStatus.ACTIVE


def test_checkout(client, db, warden_headers, make_student, make_room):
    student, room = make_student(), make_room(capacity=1)
    db.session.commit()
    alloc_id = _allocate(client, warden_headers, student, room).get_json()["data"]["id"]

    early = client.post(f"/api/allocations/{alloc_id}/checkout", headers=warden_headers,
                        json={"checkout_date": "2026-07-01"})
    assert early.status_code == 422

    res = client.post(f"/api/allocations/{alloc_id}/checkout", headers=warden_headers,
                      json={"checkout_date": "2026-12-20", "notes": "Semester ended"})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert (data["status"], data["checked_out_on"]) == ("checked_out", "2026-12-20")

    again = client.post(f"/api/allocations/{alloc_id}/checkout", headers=warden_headers, json={})
    assert again.status_code == 409
    # The freed bed can be allocated again.
    assert _allocate(client, warden_headers, make_student(), room).status_code == 201


def test_student_sees_only_own_allocations(client, db, student_headers, make_student, make_room):
    room_a, room_b, other_student = make_room(), make_room(), make_student()
    mine = RoomAllocation(student=student_headers.profile, room=room_a,
                          allocated_on=date(2026, 8, 1))
    other = RoomAllocation(student=other_student, room=room_b, allocated_on=date(2026, 8, 1))
    db.session.add_all([mine, other])
    db.session.commit()
    items = client.get("/api/allocations?student_id=" + str(other.student_id),
                       headers=student_headers).get_json()["data"]["items"]
    assert [i["id"] for i in items] == [mine.id]
    assert client.get(f"/api/allocations/{other.id}", headers=student_headers).status_code == 404
    assert client.get(f"/api/allocations/{mine.id}", headers=student_headers).status_code == 200


def test_eligible_rooms_lists_only_rooms_with_space(client, db, admin_headers, make_student, make_room):
    open_room = make_room(block="E", capacity=2)
    full_room = make_room(block="E", capacity=1)
    make_room(block="E", is_active=False)
    db.session.add(RoomAllocation(student=make_student(), room=full_room,
                                  allocated_on=date(2026, 8, 1)))
    db.session.commit()
    items = client.get("/api/allocations/eligible-rooms?block=E",
                       headers=admin_headers).get_json()["data"]["items"]
    assert [r["id"] for r in items] == [open_room.id]


def test_concurrent_allocations_never_exceed_capacity(tmp_path, monkeypatch):
    """Many simultaneous requests for one remaining bed: exactly one wins."""
    db_file = tmp_path / "concurrency.db"
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{db_file.as_posix()}")
    app = create_app("testing")
    contenders = 6
    with app.app_context():
        _db.create_all()
        from app.utils.time import utcnow
        admin = User(email="admin@hostel.test", full_name="Admin", role=Role.ADMIN,
                     email_verified_at=utcnow())
        admin.set_password("Str0ngPassword!")
        room = Room(block="Z", room_number="1", floor=1, room_type=RoomType.SINGLE,
                    capacity=1, monthly_fee_minor=1000)
        _db.session.add_all([admin, room])
        students = []
        for i in range(contenders):
            user = User(email=f"s{i}@hostel.test", full_name=f"S{i}", role=Role.STUDENT)
            user.set_password("Str0ngPassword!")
            students.append(StudentProfile(user=user, student_code=f"Z{i}", course="B.Sc",
                                           department="Maths", academic_year=1,
                                           emergency_contact_name="P",
                                           emergency_contact_phone="9876543210",
                                           registration_date=date(2026, 7, 1)))
        _db.session.add_all(students)
        _db.session.commit()
        from app.utils.auth import issue_access_token
        headers = {"Authorization": f"Bearer {issue_access_token(admin)}"}
        student_ids, room_id = [s.id for s in students], room.id

    barrier = threading.Barrier(contenders)
    results = []

    def attempt(student_id):
        client = app.test_client()
        barrier.wait()
        res = client.post("/api/allocations", headers=headers,
                          json={"student_id": student_id, "room_id": room_id})
        results.append(res.status_code)

    threads = [threading.Thread(target=attempt, args=(sid,)) for sid in student_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [201] + [409] * (contenders - 1), results
    with app.app_context():
        active = _db.session.scalar(
            _db.select(_db.func.count(RoomAllocation.id)).filter_by(status=AllocationStatus.ACTIVE))
        assert active == 1
        _db.session.remove()
        _db.engine.dispose()
