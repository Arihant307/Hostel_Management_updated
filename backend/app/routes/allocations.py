"""/api/allocations — allocate, transfer, check out, and allocation history.

Staff (admins and wardens) run the workflow; students may read only their own
allocation history. All capacity rules are enforced in services.allocation.
"""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import AllocationStatus, Room, RoomAllocation, StudentProfile, User
from ..services import allocation as allocation_service
from ..utils.auth import login_required, staff_required
from ..utils.errors import NotFoundError
from ..utils.query import (
    apply_sort, arg_choice, arg_date, arg_int, arg_str, current_student_profile, is_student,
)
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success
from ..utils.time import today
from .rooms import filtered_rooms_stmt

bp = Blueprint("allocations", __name__)


def _get_allocation(allocation_id: int) -> RoomAllocation:
    allocation = db.session.get(RoomAllocation, allocation_id)
    if allocation is None:
        raise NotFoundError("Allocation not found.")
    return allocation


@bp.get("")
@login_required
def list_allocations():
    stmt = (db.select(RoomAllocation)
            .join(RoomAllocation.student).join(StudentProfile.user).join(RoomAllocation.room)
            .options(selectinload(RoomAllocation.room),
                     selectinload(RoomAllocation.student).selectinload(StudentProfile.user)))
    if is_student():
        stmt = stmt.where(RoomAllocation.student_id == current_student_profile().id)
    else:
        if (student_id := arg_int("student_id")) is not None:
            stmt = stmt.where(RoomAllocation.student_id == student_id)
        if (room_id := arg_int("room_id")) is not None:
            stmt = stmt.where(RoomAllocation.room_id == room_id)
        if search := arg_str("search"):
            like = f"%{search}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), StudentProfile.student_code.ilike(like),
                                  Room.room_number.ilike(like)))
    if status := arg_choice("status", AllocationStatus):
        stmt = stmt.where(RoomAllocation.status == AllocationStatus(status))
    if block := arg_str("block"):
        stmt = stmt.where(Room.block == block.upper())
    if date_from := arg_date("from"):
        stmt = stmt.where(RoomAllocation.allocated_on >= date_from)
    if date_to := arg_date("to"):
        stmt = stmt.where(RoomAllocation.allocated_on <= date_to)
    stmt = apply_sort(stmt, {
        "allocated_on": RoomAllocation.allocated_on, "student": User.full_name,
        "room": Room.room_number, "checked_out_on": RoomAllocation.checked_out_on,
        "expected_checkout_on": RoomAllocation.expected_checkout_on,
    }, default="allocated_on", default_order="desc", tiebreak=RoomAllocation.id.desc())
    return success(paginate(stmt, lambda a: a.to_dict()))


@bp.get("/eligible-rooms")
@staff_required
def eligible_rooms():
    """Active rooms with at least one free bed (accepts the /api/rooms filters)."""
    stmt = (filtered_rooms_stmt()
            .where(Room.is_active.is_(True), Room.occupied_beds < Room.capacity)
            .order_by(Room.block, Room.room_number))
    return success(paginate(stmt, lambda r: r.to_dict()))


@bp.post("")
@staff_required
def create_allocation():
    v = Validator(json_body())
    v.integer("student_id", min_value=1)
    v.integer("room_id", min_value=1)
    v.date("allocated_on", required=False)
    v.date("expected_checkout_on", required=False)
    v.string("notes", required=False, max_length=500)
    v.raise_if_errors()
    data = v.clean
    student = db.session.get(StudentProfile, data["student_id"])
    if student is None:
        raise NotFoundError("Student not found.")
    allocation = allocation_service.allocate(
        student, data["room_id"], data.get("allocated_on") or today(),
        data.get("expected_checkout_on"), data.get("notes"), actor=current_user,
    )
    db.session.commit()
    return success(allocation.to_dict(), 201, "Room allocated.")


@bp.get("/<int:allocation_id>")
@login_required
def get_allocation(allocation_id: int):
    allocation = _get_allocation(allocation_id)
    if is_student() and allocation.student_id != current_student_profile().id:
        raise NotFoundError("Allocation not found.")
    return success(allocation.to_dict())


@bp.post("/<int:allocation_id>/transfer")
@staff_required
def transfer_allocation(allocation_id: int):
    allocation = _get_allocation(allocation_id)
    v = Validator(json_body())
    v.integer("room_id", min_value=1)
    v.date("transfer_date", required=False)
    v.string("notes", required=False, max_length=500)
    v.raise_if_errors()
    new_allocation = allocation_service.transfer(
        allocation, v.clean["room_id"], v.clean.get("transfer_date") or today(),
        v.clean.get("notes"), actor=current_user,
    )
    db.session.commit()
    return success(new_allocation.to_dict(), 201, "Student transferred.")


@bp.post("/<int:allocation_id>/checkout")
@staff_required
def checkout_allocation(allocation_id: int):
    allocation = _get_allocation(allocation_id)
    v = Validator(json_body())
    v.date("checkout_date", required=False)
    v.string("notes", required=False, max_length=500)
    v.raise_if_errors()
    allocation_service.checkout(allocation, v.clean.get("checkout_date") or today(),
                                v.clean.get("notes"), actor=current_user)
    db.session.commit()
    return success(allocation.to_dict(), message="Student checked out.")
