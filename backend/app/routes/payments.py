"""/api/payments — payment records and receipts.

Only admins record or reverse payments. Recording a payment here always means
"staff received the money" (source = manual); a client can never mark a fee
paid by itself. Students can list their own payments and view their receipts.
"""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    FeeRecord, Payment, PaymentMethod, PaymentSource, PaymentStatus, StudentProfile, User,
)
from ..services import billing
from ..utils.auth import admin_required, login_required
from ..utils.errors import NotFoundError
from ..utils.query import (
    apply_sort, arg_choice, arg_date, arg_int, arg_str, current_student_profile, deny_limited_staff,
    is_student,
)
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success
from ..utils.time import isoformat, today, utcnow

bp = Blueprint("payments", __name__)

HOSTEL_NAME = "HostelHub Residence"


def payment_row(p: Payment) -> dict:
    fee = p.fee_record
    student = fee.student
    return {
        **p.to_dict(),
        "fee": {"id": fee.id, "fee_type": fee.fee_type.value, "description": fee.description,
                "period_start": isoformat(fee.period_start), "period_end": isoformat(fee.period_end)},
        "student": {"id": student.id, "student_code": student.student_code,
                    "full_name": student.user.full_name},
    }


def filtered_payments_stmt():
    deny_limited_staff()
    stmt = (db.select(Payment).join(Payment.fee_record).join(FeeRecord.student)
            .join(StudentProfile.user)
            .options(selectinload(Payment.fee_record).selectinload(FeeRecord.student)
                     .selectinload(StudentProfile.user),
                     selectinload(Payment.recorded_by)))
    if is_student():
        stmt = stmt.where(FeeRecord.student_id == current_student_profile().id)
    else:
        if (student_id := arg_int("student_id")) is not None:
            stmt = stmt.where(FeeRecord.student_id == student_id)
        if search := arg_str("search"):
            like = f"%{search}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), StudentProfile.student_code.ilike(like),
                                  Payment.receipt_number.ilike(like), Payment.reference.ilike(like)))
    if (fee_id := arg_int("fee_record_id")) is not None:
        stmt = stmt.where(Payment.fee_record_id == fee_id)
    if status := arg_choice("status", PaymentStatus):
        stmt = stmt.where(Payment.status == PaymentStatus(status))
    if method := arg_choice("method", PaymentMethod):
        stmt = stmt.where(Payment.method == PaymentMethod(method))
    if source := arg_choice("source", PaymentSource):
        stmt = stmt.where(Payment.source == PaymentSource(source))
    if date_from := arg_date("from"):
        stmt = stmt.where(Payment.paid_on >= date_from)
    if date_to := arg_date("to"):
        stmt = stmt.where(Payment.paid_on <= date_to)
    return stmt


@bp.get("")
@login_required
def list_payments():
    stmt = filtered_payments_stmt()
    total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(Payment.amount_minor), 0))
        .where(Payment.id.in_(stmt.with_only_columns(Payment.id).order_by(None)),
               Payment.status == PaymentStatus.COMPLETED))
    stmt = apply_sort(stmt, {
        "paid_on": Payment.paid_on, "amount": Payment.amount_minor, "student": User.full_name,
        "created_at": Payment.created_at,
    }, default="paid_on", default_order="desc", tiebreak=Payment.id.desc())
    return success({**paginate(stmt, payment_row), "totals": {"completed_minor": int(total)}})


@bp.post("")
@admin_required
def record_payment():
    v = Validator(json_body())
    v.integer("fee_record_id", min_value=1)
    v.integer("amount_minor", min_value=1, max_value=100_000_000)
    v.choice("method", PaymentMethod)
    v.date("paid_on", required=False)
    v.string("reference", required=False, max_length=100)
    v.string("notes", required=False, max_length=500)
    data = v.clean
    if data.get("method") and data["method"] != PaymentMethod.CASH.value and not data.get("reference"):
        v.errors["reference"] = "A transaction or cheque reference is required for non-cash payments."
    if data.get("paid_on") and data["paid_on"] > today():
        v.errors["paid_on"] = "Payment date cannot be in the future."
    v.raise_if_errors()
    payment = billing.record_manual_payment(
        fee_id=data["fee_record_id"], amount_minor=data["amount_minor"], method=data["method"],
        paid_on=data.get("paid_on") or today(), reference=data.get("reference"),
        notes=data.get("notes"), actor=current_user,
    )
    db.session.commit()
    return success(payment_row(payment), 201, f"Payment recorded. Receipt {payment.receipt_number}.")


def _get_payment(payment_id: int) -> Payment:
    deny_limited_staff()
    payment = db.session.get(Payment, payment_id)
    if payment is None or (is_student()
                           and payment.fee_record.student_id != current_student_profile().id):
        raise NotFoundError("Payment not found.")
    return payment


@bp.get("/<int:payment_id>")
@login_required
def get_payment(payment_id: int):
    return success(payment_row(_get_payment(payment_id)))


@bp.post("/<int:payment_id>/reverse")
@admin_required
def reverse_payment(payment_id: int):
    payment = _get_payment(payment_id)
    v = Validator(json_body())
    v.string("reason", min_length=3, max_length=255)
    v.raise_if_errors()
    billing.reverse_payment(payment, v.clean["reason"], current_user)
    db.session.commit()
    return success(payment_row(payment), message="Payment reversed.")


@bp.get("/<int:payment_id>/receipt")
@login_required
def receipt(payment_id: int):
    payment = _get_payment(payment_id)
    fee = payment.fee_record
    student = fee.student
    allocation = fee.allocation or student.current_allocation
    return success({
        "hostel_name": HOSTEL_NAME,
        "generated_at": isoformat(utcnow()),
        "payment": payment.to_dict(),
        "fee": {**fee.to_dict(), "student": None},
        "student": {"full_name": student.user.full_name, "student_code": student.student_code,
                    "email": student.user.email, "course": student.course,
                    "department": student.department},
        "room": allocation.room.to_summary() if allocation else None,
    })
