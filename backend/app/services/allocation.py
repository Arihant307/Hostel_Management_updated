"""Room allocation, transfer and checkout — all capacity rules live here.

Consistency strategy
--------------------
Occupancy is COUNT(active allocations), so the risk is two requests both
seeing a free bed and both allocating it. Before counting, each operation
takes a write lock on the target room row:

* PostgreSQL / MySQL: SELECT ... FOR UPDATE on the room.
* SQLite: a no-op UPDATE on the room. SQLite allows one writer at a time, so
  the first write upgrades the transaction to a RESERVED lock and any
  concurrent allocator waits until this transaction commits or rolls back.

The count and the insert therefore happen inside one serialised transaction.
On top of that, the partial unique index on room_allocations guarantees a
student never has two active allocations, even under concurrency.
"""
from datetime import date

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import AllocationStatus, Room, RoomAllocation, StudentProfile
from ..utils.errors import APIError, ConflictError
from . import audit


def _lock_room(room_id: int) -> Room:
    db.session.execute(update(Room).where(Room.id == room_id).values(updated_at=Room.updated_at))
    room = db.session.scalar(db.select(Room).where(Room.id == room_id).with_for_update())
    if room is None:
        raise APIError("Room not found.", 404, "not_found")
    return room


def _active_count(room_id: int) -> int:
    return db.session.scalar(
        db.select(func.count(RoomAllocation.id))
        .where(RoomAllocation.room_id == room_id,
               RoomAllocation.status == AllocationStatus.ACTIVE)
    )


def _ensure_bed_available(room: Room) -> None:
    if not room.is_active:
        raise ConflictError(f"Room {room.block}-{room.room_number} is inactive.",
                            code="room_inactive")
    if _active_count(room.id) >= room.capacity:
        raise ConflictError(f"Room {room.block}-{room.room_number} has no available beds.",
                            code="room_full")


def _flush_or_conflict() -> None:
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ConflictError("This student already has an active room allocation.",
                            code="already_allocated")


def allocate(student: StudentProfile, room_id: int, allocated_on: date,
             expected_checkout_on: date | None = None, notes: str | None = None,
             actor=None) -> RoomAllocation:
    if not student.user.is_active:
        raise ConflictError("Inactive students cannot be allocated a room.", code="student_inactive")
    if student.current_allocation is not None:
        raise ConflictError("This student already has an active room allocation. "
                            "Use transfer instead.", code="already_allocated")
    if expected_checkout_on and expected_checkout_on < allocated_on:
        raise APIError("Expected checkout must be on or after the allocation date.", 422,
                       "validation_error",
                       {"fields": {"expected_checkout_on": "Must be on or after the allocation date."}})

    room = _lock_room(room_id)
    _ensure_bed_available(room)
    allocation = RoomAllocation(student=student, room=room, status=AllocationStatus.ACTIVE,
                                allocated_on=allocated_on, expected_checkout_on=expected_checkout_on,
                                notes=notes, allocated_by=actor)
    db.session.add(allocation)
    _flush_or_conflict()
    audit.record("allocation.create", "allocation", allocation.id,
                 {"student_id": student.id, "room": f"{room.block}-{room.room_number}"}, actor=actor)
    return allocation


def transfer(allocation: RoomAllocation, new_room_id: int, transfer_date: date,
             notes: str | None = None, actor=None) -> RoomAllocation:
    if allocation.status != AllocationStatus.ACTIVE:
        raise ConflictError("Only an active allocation can be transferred.", code="not_active")
    if new_room_id == allocation.room_id:
        raise ConflictError("The student is already in this room.", code="same_room")
    if transfer_date < allocation.allocated_on:
        raise APIError("Transfer date cannot be before the current allocation date.", 422,
                       "validation_error",
                       {"fields": {"transfer_date": "Must be on or after the allocation date."}})

    new_room = _lock_room(new_room_id)
    _ensure_bed_available(new_room)
    old_room = allocation.room

    allocation.status = AllocationStatus.TRANSFERRED
    allocation.checked_out_on = transfer_date
    allocation.closed_by = actor
    db.session.flush()  # frees the "one active allocation" slot before the new row

    expected = allocation.expected_checkout_on
    new_allocation = RoomAllocation(
        student=allocation.student, room=new_room, status=AllocationStatus.ACTIVE,
        allocated_on=transfer_date,
        expected_checkout_on=expected if expected and expected >= transfer_date else None,
        previous_allocation=allocation, notes=notes, allocated_by=actor,
    )
    db.session.add(new_allocation)
    _flush_or_conflict()
    audit.record("allocation.transfer", "allocation", new_allocation.id, {
        "student_id": allocation.student_id,
        "from": f"{old_room.block}-{old_room.room_number}",
        "to": f"{new_room.block}-{new_room.room_number}",
    }, actor=actor)
    return new_allocation


def checkout(allocation: RoomAllocation, checkout_date: date, notes: str | None = None,
             actor=None) -> RoomAllocation:
    if allocation.status != AllocationStatus.ACTIVE:
        raise ConflictError("This allocation is already closed.", code="not_active")
    if checkout_date < allocation.allocated_on:
        raise APIError("Checkout date cannot be before the allocation date.", 422,
                       "validation_error",
                       {"fields": {"checkout_date": "Must be on or after the allocation date."}})
    _lock_room(allocation.room_id)
    allocation.status = AllocationStatus.CHECKED_OUT
    allocation.checked_out_on = checkout_date
    allocation.closed_by = actor
    if notes:
        allocation.notes = f"{allocation.notes}\n{notes}" if allocation.notes else notes
    db.session.flush()
    audit.record("allocation.checkout", "allocation", allocation.id,
                 {"student_id": allocation.student_id,
                  "room": f"{allocation.room.block}-{allocation.room.room_number}"}, actor=actor)
    return allocation
