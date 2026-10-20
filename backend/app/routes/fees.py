"""/api/fees — fee records.

Admins assign, edit and cancel fees and generate monthly rent. Wardens can
view fees. Students can view only their own.
"""
from datetime import date

from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import FeeRecord, FeeStatus, FeeType, StudentProfile, User
from ..services import audit, billing
from ..utils.auth import admin_required, login_required
from ..utils.errors import APIError, NotFoundError
from ..utils.query import (
    apply_sort, arg_choice, arg_date, arg_int, arg_str, current_student_profile, deny_limited_staff,
    is_student,
)
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success

bp = Blueprint("fees", __name__)

STATUS_FILTERS = [s.value for s in FeeStatus] + ["outstanding"]


def filtered_fees_stmt():
    deny_limited_staff()
    stmt = (db.select(FeeRecord).join(FeeRecord.student).join(StudentProfile.user)
            .options(selectinload(FeeRecord.student).selectinload(StudentProfile.user)))
    if is_student():
        stmt = stmt.where(FeeRecord.student_id == current_student_profile().id)
    else:
        if (student_id := arg_int("student_id")) is not None:
            stmt = stmt.where(FeeRecord.student_id == student_id)
        if search := arg_str("search"):
            like = f"%{search}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), StudentProfile.student_code.ilike(like),
                                  FeeRecord.description.ilike(like)))
    if status := arg_choice("status", STATUS_FILTERS):
        stmt = stmt.where(billing.status_clause(status))
    if fee_type := arg_choice("fee_type", FeeType):
        stmt = stmt.where(FeeRecord.fee_type == FeeType(fee_type))
    if due_from := arg_date("due_from"):
        stmt = stmt.where(FeeRecord.due_date >= due_from)
    if due_to := arg_date("due_to"):
        stmt = stmt.where(FeeRecord.due_date <= due_to)
    return stmt


def _get_fee(fee_id: int) -> FeeRecord:
    deny_limited_staff()
    fee = db.session.get(FeeRecord, fee_id)
    if fee is None or (is_student() and fee.student_id != current_student_profile().id):
        raise NotFoundError("Fee record not found.")
    return fee


@bp.get("")
@login_required
def list_fees():
    stmt = filtered_fees_stmt()
    totals = billing.totals_for(stmt)
    stmt = apply_sort(stmt, {
        "due_date": FeeRecord.due_date, "amount": FeeRecord.amount_due_minor,
        "student": User.full_name, "period_start": FeeRecord.period_start,
        "created_at": FeeRecord.created_at,
    }, default="due_date", default_order="desc", tiebreak=FeeRecord.id.desc())
    return success({**paginate(stmt, lambda f: f.to_dict()), "totals": totals})


@bp.post("")
@admin_required
def create_fee():
    v = Validator(json_body())
    v.integer("student_id", min_value=1)
    v.choice("fee_type", FeeType)
    v.string("description", required=False, max_length=255)
    v.date("period_start")
    v.date("period_end")
    v.date("due_date")
    v.integer("amount_due_minor", min_value=1, max_value=100_000_000)
    v.raise_if_errors()
    data = v.clean
    student = db.session.get(StudentProfile, data["student_id"])
    if student is None:
        raise NotFoundError("Student not found.")
    allocation = student.current_allocation
    fee = billing.create_fee(
        student=student, fee_type=data["fee_type"], description=data.get("description"),
        period_start=data["period_start"], period_end=data["period_end"],
        due_date=data["due_date"], amount_due_minor=data["amount_due_minor"],
        allocation_id=allocation.id if allocation else None, actor=current_user,
    )
    db.session.commit()
    db.session.refresh(fee)
    return success(fee.to_dict(include_payments=True), 201, "Fee assigned.")


@bp.post("/generate-rent")
@admin_required
def generate_rent():
    v = Validator(json_body())
    v.string("month", min_length=7, max_length=7)
    v.date("due_date")
    v.raise_if_errors()
    try:
        year, month = (int(p) for p in v.clean["month"].split("-"))
        date(year, month, 1)
    except ValueError:
        raise APIError("Month must be in YYYY-MM format.", 422, "validation_error",
                       {"fields": {"month": "Use the format YYYY-MM."}})
    result = billing.generate_monthly_rent(year, month, v.clean["due_date"], actor=current_user)
    db.session.commit()
    return success(result, 201,
                   f"Generated {result['created']} rent fee(s); skipped {result['skipped']}.")


@bp.get("/<int:fee_id>")
@login_required
def get_fee(fee_id: int):
    return success(_get_fee(fee_id).to_dict(include_payments=True))


@bp.patch("/<int:fee_id>")
@admin_required
def update_fee(fee_id: int):
    fee = _get_fee(fee_id)
    if fee.cancelled_at is not None:
        raise APIError("Cancelled fees cannot be edited.", 409, "fee_cancelled")
    v = Validator(json_body(), partial=True)
    v.string("description", required=False, max_length=255)
    v.date("due_date")
    v.integer("amount_due_minor", min_value=1, max_value=100_000_000)
    v.raise_if_errors()
    data = v.clean
    if "amount_due_minor" in data and data["amount_due_minor"] < (fee.amount_paid_minor or 0):
        raise APIError("Amount due cannot be less than what has already been paid.", 409,
                       "below_paid", {"fields": {"amount_due_minor": "Must be at least the amount paid."}})
    changes = {}
    for field, value in data.items():
        if getattr(fee, field) != value:
            changes[field] = {"from": str(getattr(fee, field)), "to": str(value)}
            setattr(fee, field, value)
    if changes:
        audit.record("fee.update", "fee", fee.id, {"changes": changes})
    db.session.commit()
    db.session.refresh(fee)
    return success(fee.to_dict(include_payments=True), message="Fee updated.")


@bp.post("/<int:fee_id>/cancel")
@admin_required
def cancel_fee(fee_id: int):
    fee = _get_fee(fee_id)
    v = Validator(json_body())
    v.string("reason", min_length=3, max_length=255)
    v.raise_if_errors()
    billing.cancel_fee(fee, v.clean["reason"], current_user)
    db.session.commit()
    return success(fee.to_dict(include_payments=True), message="Fee cancelled.")
