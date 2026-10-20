"""Fee records (what a student owes) and payments (money received).

Reconciliation rules:
* FeeRecord.amount_paid_minor = SUM(Payment.amount_minor) over that fee's
  payments with status COMPLETED. It is derived, never stored.
* Fee status is derived from amount due, amount paid, due date and
  cancellation (see FeeRecord.status); there is no status column to drift.
* A MANUAL payment is recorded by staff and is COMPLETED immediately — it is
  marked as manual so it is never confused with a verified online payment.
* A GATEWAY payment starts PENDING and becomes COMPLETED only after the server
  verifies the gateway confirmation (verified_at is then required by a CHECK).
* Payments are never deleted; mistakes are corrected by marking them REVERSED.
"""
from sqlalchemy import CheckConstraint, UniqueConstraint, func, select
from sqlalchemy.orm import column_property

from ..extensions import db
from ..utils.time import isoformat, today
from .base import TimestampMixin, enum_column
from .enums import FeeStatus, FeeType, PaymentMethod, PaymentSource, PaymentStatus


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    fee_record_id = db.Column(
        db.Integer, db.ForeignKey("fee_records.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    receipt_number = db.Column(db.String(40), nullable=False, unique=True)
    amount_minor = db.Column(db.Integer, nullable=False)
    method = db.Column(enum_column(PaymentMethod, "payment_method"), nullable=False)
    source = db.Column(enum_column(PaymentSource, "payment_source"), nullable=False)
    status = db.Column(enum_column(PaymentStatus, "payment_status"), nullable=False, index=True)
    paid_on = db.Column(db.Date, nullable=False, index=True)
    # Bank / UPI reference for manual payments.
    reference = db.Column(db.String(100))
    # Gateway transaction id; unique so the same confirmation cannot be applied twice.
    gateway_transaction_id = db.Column(db.String(100), unique=True)
    verified_at = db.Column(db.DateTime)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reversed_at = db.Column(db.DateTime)
    reversal_reason = db.Column(db.String(255))
    notes = db.Column(db.String(500))

    fee_record = db.relationship("FeeRecord", back_populates="payments")
    recorded_by = db.relationship("User")

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint(
            "source != 'gateway' OR status != 'completed' OR verified_at IS NOT NULL",
            name="gateway_completed_requires_verification",
        ),
        CheckConstraint(
            "source != 'gateway' OR gateway_transaction_id IS NOT NULL",
            name="gateway_requires_transaction_id",
        ),
        CheckConstraint(
            "source != 'manual' OR recorded_by_id IS NOT NULL OR status = 'reversed'",
            name="manual_requires_recorder",
        ),
    )

    @property
    def is_verified_online(self) -> bool:
        return (self.source == PaymentSource.GATEWAY
                and self.status == PaymentStatus.COMPLETED
                and self.verified_at is not None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fee_record_id": self.fee_record_id,
            "receipt_number": self.receipt_number,
            "amount_minor": self.amount_minor,
            "method": self.method.value,
            "source": self.source.value,
            "status": self.status.value,
            "is_verified_online": self.is_verified_online,
            "paid_on": isoformat(self.paid_on),
            "reference": self.reference,
            "verified_at": isoformat(self.verified_at),
            "recorded_by": self.recorded_by.full_name if self.recorded_by else None,
            "reversed_at": isoformat(self.reversed_at),
            "reversal_reason": self.reversal_reason,
            "notes": self.notes,
            "created_at": isoformat(self.created_at),
        }

    def __repr__(self) -> str:
        return f"<Payment {self.receipt_number} {self.amount_minor} {self.status}>"


class FeeRecord(TimestampMixin, db.Model):
    __tablename__ = "fee_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    # Optional link to the stay this rent was billed for.
    allocation_id = db.Column(
        db.Integer, db.ForeignKey("room_allocations.id", ondelete="SET NULL"), index=True
    )
    fee_type = db.Column(enum_column(FeeType, "fee_type"), nullable=False)
    description = db.Column(db.String(255))
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False, index=True)
    amount_due_minor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    cancelled_at = db.Column(db.DateTime)
    cancellation_reason = db.Column(db.String(255))

    student = db.relationship("StudentProfile", back_populates="fee_records")
    allocation = db.relationship("RoomAllocation")
    created_by = db.relationship("User")
    payments = db.relationship("Payment", back_populates="fee_record",
                               order_by="Payment.paid_on")

    amount_paid_minor = column_property(
        select(func.coalesce(func.sum(Payment.amount_minor), 0))
        .where(Payment.fee_record_id == id,
               Payment.status == PaymentStatus.COMPLETED)
        .correlate_except(Payment)
        .scalar_subquery(),
        deferred=False,
    )

    __table_args__ = (
        # Prevents billing the same student twice for the same fee and period.
        UniqueConstraint("student_id", "fee_type", "period_start",
                         name="uq_fee_records_student_type_period"),
        CheckConstraint("amount_due_minor > 0", name="amount_due_positive"),
        CheckConstraint("period_end >= period_start", name="period_valid"),
    )

    @property
    def balance_minor(self) -> int:
        return max(self.amount_due_minor - (self.amount_paid_minor or 0), 0)

    @property
    def status(self) -> FeeStatus:
        paid = self.amount_paid_minor or 0
        if self.cancelled_at is not None:
            return FeeStatus.CANCELLED
        if paid >= self.amount_due_minor:
            return FeeStatus.PAID
        if self.due_date < today():
            return FeeStatus.OVERDUE
        if paid > 0:
            return FeeStatus.PARTIALLY_PAID
        return FeeStatus.PENDING

    def to_dict(self, include_payments: bool = False) -> dict:
        data = {
            "id": self.id,
            "student_id": self.student_id,
            "allocation_id": self.allocation_id,
            "fee_type": self.fee_type.value,
            "description": self.description,
            "period_start": isoformat(self.period_start),
            "period_end": isoformat(self.period_end),
            "due_date": isoformat(self.due_date),
            "amount_due_minor": self.amount_due_minor,
            "amount_paid_minor": self.amount_paid_minor or 0,
            "balance_minor": self.balance_minor,
            "status": self.status.value,
            "cancelled_at": isoformat(self.cancelled_at),
            "cancellation_reason": self.cancellation_reason,
            "created_at": isoformat(self.created_at),
        }
        if self.student is not None:
            data["student"] = {
                "id": self.student.id,
                "student_code": self.student.student_code,
                "full_name": self.student.user.full_name if self.student.user else None,
            }
        if include_payments:
            data["payments"] = [p.to_dict() for p in self.payments]
        return data

    def __repr__(self) -> str:
        return f"<FeeRecord {self.id} student={self.student_id} {self.fee_type}>"
