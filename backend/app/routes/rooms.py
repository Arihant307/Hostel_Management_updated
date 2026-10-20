"""/api/rooms — room inventory.

Admins create, edit and deactivate rooms; wardens can view them (for
allocation). Occupancy is always derived from active allocations.
Safeguards: capacity can never be reduced below the current occupancy, and a
room with occupants cannot be deactivated.
"""
from flask import Blueprint
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import AllocationStatus, Room, RoomAllocation, RoomType, StudentProfile
from ..services import audit
from ..utils.auth import admin_required, any_staff_required
from ..utils.errors import APIError, ConflictError, NotFoundError
from ..utils.query import apply_sort, arg_bool, arg_choice, arg_int, arg_str
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success

bp = Blueprint("rooms", __name__)

AVAILABILITY = ("available", "partially_occupied", "full", "has_space")


def _validate(data: dict, partial: bool) -> dict:
    v = Validator(data, partial=partial)
    v.string("block", max_length=50)
    v.string("room_number", max_length=20)
    v.integer("floor", min_value=-2, max_value=200)
    v.choice("room_type", RoomType)
    v.integer("capacity", min_value=1, max_value=20)
    v.integer("monthly_fee_minor", min_value=0, max_value=100_000_000)
    v.string("amenities", required=False, max_length=255)
    v.raise_if_errors()
    clean = v.clean
    if "block" in clean:
        clean["block"] = clean["block"].upper()
    if "room_number" in clean:
        clean["room_number"] = clean["room_number"].upper()
    if "room_type" in clean:
        clean["room_type"] = RoomType(clean["room_type"])
    return clean


def _get_room(room_id: int) -> Room:
    room = db.session.get(Room, room_id)
    if room is None:
        raise NotFoundError("Room not found.")
    return room


def _check_duplicate(block: str, number: str, exclude_id=None) -> None:
    stmt = db.select(Room.id).filter_by(block=block, room_number=number)
    if exclude_id:
        stmt = stmt.where(Room.id != exclude_id)
    if db.session.scalar(stmt):
        raise ConflictError(f"Room {block}-{number} already exists.",
                            details={"fields": {"room_number": "This room number already exists in the block."}})


def room_detail(room: Room) -> dict:
    allocations = db.session.scalars(
        db.select(RoomAllocation).filter_by(room_id=room.id)
        .options(selectinload(RoomAllocation.student).selectinload(StudentProfile.user))
        .order_by(RoomAllocation.allocated_on.desc(), RoomAllocation.id.desc())
    ).all()
    return {
        **room.to_dict(),
        "occupants": [a.to_dict(include_room=False) for a in allocations
                      if a.status == AllocationStatus.ACTIVE],
        "history": [a.to_dict(include_room=False) for a in allocations
                    if a.status != AllocationStatus.ACTIVE][:50],
    }


def filtered_rooms_stmt():
    stmt = db.select(Room)
    if search := arg_str("search"):
        like = f"%{search}%"
        stmt = stmt.where(or_(Room.room_number.ilike(like), Room.block.ilike(like),
                              Room.amenities.ilike(like)))
    if block := arg_str("block"):
        stmt = stmt.where(Room.block == block.upper())
    if room_type := arg_choice("room_type", RoomType):
        stmt = stmt.where(Room.room_type == RoomType(room_type))
    if (floor := arg_int("floor")) is not None:
        stmt = stmt.where(Room.floor == floor)
    is_active = arg_bool("is_active")
    if is_active is not None:
        stmt = stmt.where(Room.is_active.is_(is_active))
    availability = arg_choice("availability", AVAILABILITY)
    occupied = Room.occupied_beds
    if availability == "available":
        stmt = stmt.where(occupied == 0)
    elif availability == "partially_occupied":
        stmt = stmt.where(occupied > 0, occupied < Room.capacity)
    elif availability == "full":
        stmt = stmt.where(occupied >= Room.capacity)
    elif availability == "has_space":
        stmt = stmt.where(occupied < Room.capacity)
    return stmt


@bp.get("")
@any_staff_required
def list_rooms():
    stmt = apply_sort(filtered_rooms_stmt(), {
        "room": Room.room_number, "block": Room.block, "floor": Room.floor,
        "capacity": Room.capacity, "monthly_fee": Room.monthly_fee_minor,
        "occupied": Room.occupied_beds, "created_at": Room.created_at,
    }, default="block", tiebreak=Room.room_number)
    return success(paginate(stmt, lambda r: r.to_dict()))


@bp.get("/blocks")
@any_staff_required
def list_blocks():
    return success(db.session.scalars(db.select(Room.block).distinct().order_by(Room.block)).all())


@bp.post("")
@admin_required
def create_room():
    data = _validate(json_body(), partial=False)
    _check_duplicate(data["block"], data["room_number"])
    room = Room(**data, is_active=True)
    db.session.add(room)
    db.session.flush()
    audit.record("room.create", "room", room.id,
                 {"room": f"{room.block}-{room.room_number}", "capacity": room.capacity})
    db.session.commit()
    db.session.refresh(room)
    return success(room_detail(room), 201, "Room created.")


@bp.get("/<int:room_id>")
@any_staff_required
def get_room(room_id: int):
    return success(room_detail(_get_room(room_id)))


@bp.patch("/<int:room_id>")
@admin_required
def update_room(room_id: int):
    room = _get_room(room_id)
    data = _validate(json_body(), partial=True)
    data = {k: v for k, v in data.items() if v is not None or k == "amenities"}
    block = data.get("block", room.block)
    number = data.get("room_number", room.room_number)
    if (block, number) != (room.block, room.room_number):
        _check_duplicate(block, number, exclude_id=room.id)
    if "capacity" in data and data["capacity"] < (room.occupied_beds or 0):
        raise APIError(f"Capacity cannot be lower than the current occupancy ({room.occupied_beds}).",
                       409, "capacity_below_occupancy",
                       {"fields": {"capacity": f"At least {room.occupied_beds} (current occupants)."}})

    changes = {}
    for field, value in data.items():
        old = getattr(room, field)
        if old != value:
            changes[field] = {"from": str(old), "to": str(value)}
            setattr(room, field, value)
    if changes:
        audit.record("room.update", "room", room.id, {"changes": changes})
    db.session.commit()
    db.session.refresh(room)
    return success(room_detail(room), message="Room updated.")


@bp.patch("/<int:room_id>/status")
@admin_required
def set_room_status(room_id: int):
    room = _get_room(room_id)
    v = Validator(json_body())
    v.boolean("is_active")
    v.raise_if_errors()
    active = v.clean["is_active"]
    if not active and (room.occupied_beds or 0) > 0:
        raise APIError("Move or check out all occupants before deactivating this room.",
                       409, "room_occupied")
    if room.is_active != active:
        room.is_active = active
        audit.record("room.activate" if active else "room.deactivate", "room", room.id)
        db.session.commit()
    return success(room_detail(room), message="Room activated." if active else "Room deactivated.")
