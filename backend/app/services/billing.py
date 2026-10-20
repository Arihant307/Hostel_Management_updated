"""Fee and payment business rules.

* Fee status is never stored. status_clause() is the SQL twin of
  FeeRecord.status so lists can be filtered by status in the database.
* Payments are recorded against one fee, under a write lock on that fee row,
  and may never exceed the remaining balance (no overpayment).
* Only staff record MANUAL payments. Online (GATEWAY) payments are not
  integrated; the schema requires server-side verification before such a
  payment can ever count (see models/finance.py).
* Payments are corrected by reversal, never deletion.
"""
import calendar
import secrets
from datetime import date

from sqlalchemy import and_, case, func, update

from ..extensions import db
from ..models import (
    AllocationStatus, FeeRecord, FeeStatus, FeeType, Payment, PaymentMethod, PaymentSource,
    PaymentStatus, RoomAllocation, StudentProfile, User,
)
from ..utils.errors import APIError, ConflictError
from ..utils.time import today, utcnow
from . import audit

_paid = FeeRecord.amount_paid_minor
_not_cancelled = FeeRecord.cancelled_at.is_(None)


def status_clause(status: str, on: date | None = None):
    on = on or today()
    return {
        FeeStatus.CANCELLED.value: FeeRecord.cancelled_at.is_not(None),
        FeeStatus.PAID.value: and_(_not_cancelled, _paid >= FeeRecord.amount_due_minor),
        FeeStatus.OVERDUE.value: and_(_not_cancelled, _paid < FeeRecord.amount_due_minor,
                                      FeeRecord.due_date < on),
        FeeStatus.PARTIALLY_PAID.value: and_(_not_cancelled, _paid > 0,
                                             _paid < FeeRecord.amount_due_minor,
                                             FeeRecord.due_date >= on),
        FeeStatus.PENDING.value: and_(_not_cancelled, _paid == 0, FeeRecord.due_date >= on),
        "outstanding": and_(_not_cancelled, _paid < FeeRecord.amount_due_minor),
    }[status]


def outstanding_expr():
    """Remaining balance of a fee row as a SQL expression (0 if cancelled/paid)."""
    return case((and_(_not_cancelled, _paid < FeeRecord.amount_due_minor),
                 FeeRecord.amount_due_minor - _paid), else_=0)


def totals_for(stmt) -> dict:
    """Sum billed / paid / outstanding over the fees selected by `stmt`."""
    ids = stmt.with_only_columns(FeeRecord.id).order_by(None)
    billed, paid, outstanding = db.session.execute(
        db.select(
            func.coalesce(func.sum(case((_not_cancelled, FeeRecord.amount_due_minor), else_=0)), 0),
            func.coalesce(func.sum(case((_not_cancelled, _paid), else_=0)), 0),
            func.coalesce(func.sum(outstanding_expr()), 0),
        ).where(FeeRecord.id.in_(ids))
    ).one()
    return {"billed_minor": int(billed), "paid_minor": int(paid),
            "outstanding_minor": int(outstanding)}


def _lock_fee(fee_id: int) -> FeeRecord:
    db.session.execute(update(FeeRecord).where(FeeRecord.id == fee_id)
                       .values(updated_at=FeeRecord.updated_at))
    fee = db.session.scalar(db.select(FeeRecord).where(FeeRecord.id == fee_id).with_for_update())
    if fee is None:
        raise APIError("Fee record not found.", 404, "not_found")
    db.session.refresh(fee)  # make sure amount_paid_minor reflects committed payments
    return fee


def _new_receipt_number(paid_on: date) -> str:
    while True:
        number = f"RCPT-{paid_on:%Y%m%d}-{secrets.token_hex(3).upper()}"
        if not db.session.scalar(db.select(Payment.id).filter_by(receipt_number=number)):
            return number


def create_fee(*, student: StudentProfile, fee_type: str, period_start: date, period_end: date,
               due_date: date, amount_due_minor: int, description: str | None = None,
               allocation_id: int | None = None, actor=None) -> FeeRecord:
    if period_end < period_start:
        raise APIError("Period end must be on or after period start.", 422, "validation_error",
                       {"fields": {"period_end": "Must be on or after the period start."}})
    if db.session.scalar(db.select(FeeRecord.id).filter_by(
            student_id=student.id, fee_type=FeeType(fee_type), period_start=period_start)):
        raise ConflictError("This student is already billed for this fee type and period.",
                            code="duplicate_fee")
    fee = FeeRecord(student=student, fee_type=FeeType(fee_type), description=description,
                    period_start=period_start, period_end=period_end, due_date=due_date,
                    amount_due_minor=amount_due_minor, allocation_id=allocation_id,
                    created_by=actor)
    db.session.add(fee)
    db.session.flush()
    audit.record("fee.create", "fee", fee.id, {"student_id": student.id, "fee_type": fee_type,
                                               "amount_due_minor": amount_due_minor}, actor=actor)
    return fee


def generate_monthly_rent(year: int, month: int, due_date: date, actor=None) -> dict:
    """Bill one month's rent to every student with an active allocation.

    Students already billed for that month are skipped, so the operation is
    safe to run more than once.
    """
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    allocations = db.session.scalars(
        db.select(RoomAllocation).join(RoomAllocation.student).join(StudentProfile.user)
        .where(RoomAllocation.status == AllocationStatus.ACTIVE, User.is_active.is_(True))
    ).all()
    already = set(db.session.scalars(
        db.select(FeeRecord.student_id).filter_by(fee_type=FeeType.HOSTEL_RENT, period_start=start)
    ).all())
    created, skipped = [], 0
    for allocation in allocations:
        if allocation.student_id in already or allocation.room.monthly_fee_minor <= 0:
            skipped += 1
            continue
        fee = FeeRecord(student_id=allocation.student_id, allocation_id=allocation.id,
                        fee_type=FeeType.HOSTEL_RENT,
                        description=f"Hostel rent {start:%B %Y} — room "
                                    f"{allocation.room.block}-{allocation.room.room_number}",
                        period_start=start, period_end=end, due_date=due_date,
                        amount_due_minor=allocation.room.monthly_fee_minor, created_by=actor)
        db.session.add(fee)
        created.append(fee)
    db.session.flush()
    audit.record("fee.generate_rent", "fee", None,
                 {"period": f"{start:%Y-%m}", "created": len(created), "skipped": skipped},
                 actor=actor)
    return {"created": len(created), "skipped": skipped, "period": f"{start:%Y-%m}"}


def record_manual_payment(*, fee_id: int, amount_minor: int, method: str, paid_on: date,
                          reference: str | None, notes: str | None, actor) -> Payment:
    fee = _lock_fee(fee_id)
    if fee.cancelled_at is not None:
        raise ConflictError("Payments cannot be recorded against a cancelled fee.",
                            code="fee_cancelled")
    if fee.balance_minor <= 0:
        raise ConflictError("This fee is already fully paid.", code="fee_paid")
    if amount_minor > fee.balance_minor:
        raise APIError(f"Amount exceeds the outstanding balance ({fee.balance_minor / 100:.2f}).",
                       422, "overpayment",
                       {"fields": {"amount_minor": "Cannot exceed the outstanding balance."},
                        "balance_minor": fee.balance_minor})
    payment = Payment(fee_record=fee, receipt_number=_new_receipt_number(paid_on),
                      amount_minor=amount_minor, method=PaymentMethod(method),
                      source=PaymentSource.MANUAL, status=PaymentStatus.COMPLETED,
                      paid_on=paid_on, reference=reference, notes=notes, recorded_by=actor)
    db.session.add(payment)
    db.session.flush()
    audit.record("payment.record", "payment", payment.id,
                 {"fee_id": fee.id, "amount_minor": amount_minor, "method": method,
                  "receipt": payment.receipt_number}, actor=actor)
    return payment


def reverse_payment(payment: Payment, reason: str, actor) -> Payment:
    if payment.status != PaymentStatus.COMPLETED:
        raise ConflictError("Only completed payments can be reversed.", code="not_completed")
    _lock_fee(payment.fee_record_id)
    payment.status = PaymentStatus.REVERSED
    payment.reversed_at = utcnow()
    payment.reversal_reason = reason
    db.session.flush()
    audit.record("payment.reverse", "payment", payment.id,
                 {"receipt": payment.receipt_number, "reason": reason}, actor=actor)
    return payment


def cancel_fee(fee: FeeRecord, reason: str, actor) -> FeeRecord:
    if fee.cancelled_at is not None:
        raise ConflictError("This fee is already cancelled.", code="already_cancelled")
    if (fee.amount_paid_minor or 0) > 0:
        raise ConflictError("Reverse the recorded payments before cancelling this fee.",
                            code="has_payments")
    fee.cancelled_at = utcnow()
    fee.cancellation_reason = reason
    db.session.flush()
    audit.record("fee.cancel", "fee", fee.id, {"reason": reason}, actor=actor)
    return fee
