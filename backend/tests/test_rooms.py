"""Room CRUD, filters and occupancy safeguards."""
from datetime import date

import pytest

from app.models import RoomAllocation

NEW_ROOM = {"block": "a", "room_number": "101", "floor": 1, "room_type": "double",
            "capacity": 2, "monthly_fee_minor": 450000, "amenities": "Attached bath, Wi-Fi"}


def _create(client, headers, **overrides):
    return client.post("/api/rooms", headers=headers, json={**NEW_ROOM, **overrides})


def test_admin_creates_room(client, admin_headers):
    res = _create(client, admin_headers)
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert (data["block"], data["room_number"]) == ("A", "101")
    assert (data["occupied_beds"], data["available_beds"], data["occupancy_status"]) == \
        (0, 2, "available")
    assert data["occupants"] == []


def test_wardens_view_but_cannot_edit_rooms(client, warden_headers, admin_headers):
    room_id = _create(client, admin_headers).get_json()["data"]["id"]
    assert client.get("/api/rooms", headers=warden_headers).status_code == 200
    assert client.get(f"/api/rooms/{room_id}", headers=warden_headers).status_code == 200
    assert _create(client, warden_headers, room_number="102").status_code == 403
    assert client.patch(f"/api/rooms/{room_id}", headers=warden_headers,
                        json={"capacity": 3}).status_code == 403


def test_students_cannot_access_rooms(client, student_headers):
    assert client.get("/api/rooms", headers=student_headers).status_code == 403


def test_duplicate_room_rejected(client, admin_headers):
    _create(client, admin_headers)
    res = _create(client, admin_headers, block="A", room_number="101")
    assert res.status_code == 409
    assert _create(client, admin_headers, block="B").status_code == 201


@pytest.mark.parametrize("field,value", [
    ("capacity", 0), ("capacity", 25), ("monthly_fee_minor", -1), ("room_type", "suite"),
    ("block", ""), ("floor", "abc"),
])
def test_room_validation(client, admin_headers, field, value):
    res = _create(client, admin_headers, **{field: value})
    assert res.status_code == 422
    assert field in res.get_json()["error"]["details"]["fields"]


def _occupy(db, room, make_student, n):
    for _ in range(n):
        db.session.add(RoomAllocation(student=make_student(), room=room,
                                      allocated_on=date(2026, 8, 1)))
    db.session.commit()


def test_capacity_cannot_drop_below_occupancy(client, db, admin_headers, make_room, make_student):
    room = make_room(capacity=3)
    _occupy(db, room, make_student, 2)
    res = client.patch(f"/api/rooms/{room.id}", headers=admin_headers, json={"capacity": 1})
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "capacity_below_occupancy"
    ok = client.patch(f"/api/rooms/{room.id}", headers=admin_headers,
                      json={"capacity": 2, "monthly_fee_minor": 500000})
    assert ok.status_code == 200
    assert ok.get_json()["data"]["occupancy_status"] == "full"


def test_occupied_room_cannot_be_deactivated(client, db, admin_headers, make_room, make_student):
    room = make_room()
    _occupy(db, room, make_student, 1)
    res = client.patch(f"/api/rooms/{room.id}/status", headers=admin_headers,
                       json={"is_active": False})
    assert res.status_code == 409
    empty = make_room()
    db.session.commit()
    ok = client.patch(f"/api/rooms/{empty.id}/status", headers=admin_headers,
                      json={"is_active": False})
    assert ok.get_json()["data"]["occupancy_status"] == "inactive"


def test_room_detail_lists_occupants(client, db, admin_headers, make_room, make_student):
    room = make_room(capacity=2)
    _occupy(db, room, make_student, 1)
    data = client.get(f"/api/rooms/{room.id}", headers=admin_headers).get_json()["data"]
    assert len(data["occupants"]) == 1
    assert data["occupants"][0]["student"]["student_code"]


def test_room_filters(client, db, admin_headers, make_room, make_student):
    empty = make_room(block="A", number="1", capacity=2)
    partial = make_room(block="A", number="2", capacity=2)
    full = make_room(block="B", number="3", capacity=1)
    from app.models import RoomType
    single = make_room(block="B", number="4", capacity=1, room_type=RoomType.SINGLE,
                       is_active=False)
    _occupy(db, partial, make_student, 1)
    _occupy(db, full, make_student, 1)

    def numbers(qs):
        items = client.get(f"/api/rooms?{qs}", headers=admin_headers).get_json()["data"]["items"]
        return sorted(r["room_number"] for r in items)

    assert numbers("availability=available") == ["1", "4"]
    assert numbers("availability=partially_occupied") == ["2"]
    assert numbers("availability=full") == ["3"]
    assert numbers("availability=has_space&is_active=true") == ["1", "2"]
    assert numbers("block=b") == ["3", "4"]
    assert numbers("room_type=single") == ["4"]
    assert numbers("search=3") == ["3"]
    blocks = client.get("/api/rooms/blocks", headers=admin_headers).get_json()["data"]
    assert blocks == ["A", "B"]
    assert empty and single
