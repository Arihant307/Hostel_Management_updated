"""Database schema rules: constraints, derived values and relationships."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from app.models import (
    AllocationStatus, Complaint, ComplaintCategory, ComplaintStatus, FeeRecord, FeeStatus,
    FeeType, Notice, Payment, PaymentMethod, PaymentSource, PaymentStatus, Role,
    RoomAllocation, StudentProfile, User,
)
from app.utils.time import today, utcnow


def _expect_integrity_error(db):
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


# --- users -----------------------------------------------------------------

def test_password_is_hashed_and_verifiable(make_user):
    user = make_user(password="CorrectHorse9")
    assert "CorrectHorse9" not in user.password_hash
    assert user.password_hash.startswith("scrypt:")
    assert user.check_password("CorrectHorse9")
    assert not user.check_password("wrong-password")


def test_user_serialisation_hides_secrets(make_user):
    data = make_user().to_dict()
    assert "password_hash" not in data and "token_version" not in data


def test_duplicate_email_rejected(db, make_user):
    make_user(email="dup@example.com")
    db.session.add(User(email="dup@example.com", full_name="X", role=Role.WARDEN,
                        password_hash="x"))
    _expect_integrity_error(db)


def test_email_must_be_lowercase(db):
    db.session.add(User(email="Mixed@Example.com", full_name="X", role=Role.ADMIN,
                        password_hash="x"))
    _expect_integrity_error(db)


def test_invalid_role_rejected(db):
    with pytest.raises((StatementError, LookupError)):
        db.session.add(User(email="r@example.com", full_name="X", role="superuser",
                            password_hash="x"))
        db.session.flush()
    db.session.rollback()


def test_duplicate_student_code_rejected(db, make_student):
    make_student(code="STU-1")
    with pytest.raises(IntegrityError):
        make_student(code="STU-1")
    db.session.rollback()


def test_academic_year_range(db, make_student):
    with pytest.raises(IntegrityError):
        make_student(academic_year=9)
    db.session.rollback()


# --- rooms & allocations ---------------------------------------------------

def test_room_number_unique_within_block(db, make_room):
    make_room(block="A", number="101")
    make_room(block="B", number="101")  # same number, other block: fine
    with pytest.raises(IntegrityError):
        make_room(block="A", number="101")
    db.session.rollback()


def test_room_capacity_must_be_positive(db, make_room):
    with pytest.raises(IntegrityError):
        make_room(capacity=0)
    db.session.rollback()


def _allocate(db, student, room, **kwargs):
    alloc = RoomAllocation(student=student, room=room,
                           allocated_on=kwargs.pop("allocated_on", date(2026, 8, 1)), **kwargs)
    db.session.add(alloc)
    db.session.flush()
    return alloc


def test_occupancy_is_derived_from_active_allocations(db, make_room, make_student):
    room = make_room(capacity=2)
    db.session.refresh(room)
    assert (room.occupied_beds, room.available_beds, room.occupancy_status) == (0, 2, "available")

    first = _allocate(db, make_student(), room)
    db.session.refresh(room)
    assert (room.occupied_beds, room.occupancy_status) == (1, "partially_occupied")

    _allocate(db, make_student(), room)
    db.session.refresh(room)
    assert (room.occupied_beds, room.available_beds, room.occupancy_status) == (2, 0, "full")

    first.status = AllocationStatus.CHECKED_OUT
    first.checked_out_on = date(2026, 9, 1)
    db.session.flush()
    db.session.refresh(room)
    assert room.occupied_beds == 1


def test_one_active_allocation_per_student(db, make_room, make_student):
    student = make_student()
    _allocate(db, student, make_room())
    db.session.add(RoomAllocation(student=student, room=make_room(),
                                  allocated_on=date(2026, 8, 2)))
    _expect_integrity_error(db)


def test_allocation_history_allows_many_closed_stays(db, make_room, make_student):
    student = make_student()
    first = _allocate(db, student, make_room(), status=AllocationStatus.TRANSFERRED,
                      checked_out_on=date(2026, 8, 10))
    second = _allocate(db, student, make_room(), allocated_on=date(2026, 8, 10),
                       previous_allocation=first)
    db.session.refresh(student)
    assert student.current_allocation is second
    assert len(student.allocations) == 2
    assert second.previous_allocation_id == first.id


def test_active_allocation_cannot_have_checkout_date(db, make_room, make_student):
    db.session.add(RoomAllocation(student=make_student(), room=make_room(),
                                  allocated_on=date(2026, 8, 1),
                                  checked_out_on=date(2026, 8, 5)))
    _expect_integrity_error(db)


def test_checkout_cannot_precede_allocation(db, make_room, make_student):
    db.session.add(RoomAllocation(student=make_student(), room=make_room(),
                                  status=AllocationStatus.CHECKED_OUT,
                                  allocated_on=date(2026, 8, 1),
                                  checked_out_on=date(2026, 7, 1)))
    _expect_integrity_error(db)


def test_foreign_keys_are_enforced(db, make_student):
    db.session.add(RoomAllocation(student=make_student(), room_id=9999,
                                  allocated_on=date(2026, 8, 1)))
    _expect_integrity_error(db)


def test_room_with_history_cannot_be_deleted(db, make_room, make_student):
    room = make_room()
    _allocate(db, make_student(), room)
    with pytest.raises(IntegrityError):
        db.session.execute(db.text("DELETE FROM rooms WHERE id = :id"), {"id": room.id})
    db.session.rollback()


# --- fees & payments -------------------------------------------------------

def _fee(db, student, amount=600000, due=None, **kwargs):
    fee = FeeRecord(student=student, fee_type=kwargs.pop("fee_type", FeeType.HOSTEL_RENT),
                    period_start=kwargs.pop("period_start", date(2026, 10, 1)),
                    period_end=date(2026, 10, 31), due_date=due or today() + timedelta(days=10),
                    amount_due_minor=amount, **kwargs)
    db.session.add(fee)
    db.session.flush()
    return fee


_receipts = iter(range(1, 10_000))


def _pay(db, fee, amount, recorder, **kwargs):
    payment = Payment(fee_record=fee, receipt_number=f"RCPT-{next(_receipts):05d}",
                      amount_minor=amount, method=kwargs.pop("method", PaymentMethod.CASH),
                      source=kwargs.pop("source", PaymentSource.MANUAL),
                      status=kwargs.pop("status", PaymentStatus.COMPLETED),
                      paid_on=today(), recorded_by=recorder, **kwargs)
    db.session.add(payment)
    db.session.flush()
    db.session.refresh(fee)
    return payment


def test_fee_status_follows_completed_payments(db, make_student, make_user):
    staff = make_user(Role.WARDEN)
    fee = _fee(db, make_student(), amount=600000)
    db.session.refresh(fee)
    assert fee.status == FeeStatus.PENDING and fee.balance_minor == 600000

    _pay(db, fee, 200000, staff)
    assert fee.status == FeeStatus.PARTIALLY_PAID
    assert (fee.amount_paid_minor, fee.balance_minor) == (200000, 400000)

    # Pending / failed / reversed payments do not reduce the balance.
    _pay(db, fee, 400000, None, source=PaymentSource.GATEWAY,
         status=PaymentStatus.PENDING, gateway_transaction_id="gw_1")
    _pay(db, fee, 400000, staff, status=PaymentStatus.FAILED)
    assert fee.amount_paid_minor == 200000

    _pay(db, fee, 400000, staff)
    assert fee.status == FeeStatus.PAID and fee.balance_minor == 0


def test_fee_overdue_and_cancelled(db, make_student):
    fee = _fee(db, make_student(), due=today() - timedelta(days=1))
    db.session.refresh(fee)
    assert fee.status == FeeStatus.OVERDUE
    fee.cancelled_at = utcnow()
    assert fee.status == FeeStatus.CANCELLED


def test_fee_cannot_be_billed_twice_for_same_period(db, make_student):
    student = make_student()
    _fee(db, student)
    with pytest.raises(IntegrityError):
        _fee(db, student)
    db.session.rollback()


def test_fee_amount_must_be_positive(db, make_student):
    with pytest.raises(IntegrityError):
        _fee(db, make_student(), amount=0)
    db.session.rollback()


def test_gateway_payment_cannot_complete_without_verification(db, make_student):
    fee = _fee(db, make_student())
    with pytest.raises(IntegrityError):
        _pay(db, fee, 1000, None, source=PaymentSource.GATEWAY,
             status=PaymentStatus.COMPLETED, gateway_transaction_id="gw_unverified")
    db.session.rollback()


def test_verified_gateway_payment_counts(db, make_student):
    fee = _fee(db, make_student(), amount=1000)
    payment = _pay(db, fee, 1000, None, source=PaymentSource.GATEWAY,
                   status=PaymentStatus.COMPLETED, gateway_transaction_id="gw_ok",
                   verified_at=utcnow())
    assert payment.is_verified_online
    assert fee.status == FeeStatus.PAID


def test_manual_payment_requires_recorder(db, make_student):
    fee = _fee(db, make_student())
    with pytest.raises(IntegrityError):
        _pay(db, fee, 1000, None)
    db.session.rollback()


def test_payment_amount_must_be_positive(db, make_student, make_user):
    fee = _fee(db, make_student())
    with pytest.raises(IntegrityError):
        _pay(db, fee, -5, make_user(Role.ADMIN))
    db.session.rollback()


# --- complaints ------------------------------------------------------------

def test_complaint_resolution_timestamp_matches_status(db, make_student):
    complaint = Complaint(student=make_student(), category=ComplaintCategory.PLUMBING,
                          title="Leaking tap", description="Bathroom tap leaks.")
    db.session.add(complaint)
    db.session.flush()
    assert complaint.status == ComplaintStatus.OPEN

    complaint.status = ComplaintStatus.RESOLVED  # without resolved_at
    _expect_integrity_error(db)


def test_student_cannot_see_internal_comments(db, make_student, make_user):
    from app.models import ComplaintComment
    warden = make_user(Role.WARDEN)
    complaint = Complaint(student=make_student(), category=ComplaintCategory.ELECTRICAL,
                          title="Fan", description="Fan not working.")
    complaint.comments = [
        ComplaintComment(author=warden, body="Electrician visiting tomorrow."),
        ComplaintComment(author=warden, body="Vendor overcharges.", is_internal=True),
    ]
    db.session.add(complaint)
    db.session.flush()
    assert len(complaint.to_dict()["comments"]) == 1
    assert len(complaint.to_dict(include_internal=True)["comments"]) == 2


# --- notices ---------------------------------------------------------------

def test_notice_visibility_window(db):
    now = utcnow()
    db.session.add_all([
        Notice(title="Live", body="b", publish_at=now - timedelta(hours=1)),
        Notice(title="Scheduled", body="b", publish_at=now + timedelta(days=1)),
        Notice(title="Expired", body="b", publish_at=now - timedelta(days=5),
               expires_at=now - timedelta(days=1)),
    ])
    db.session.flush()
    visible = db.session.scalars(db.select(Notice).where(Notice.active_filter())).all()
    assert [n.title for n in visible] == ["Live"]


def test_notice_expiry_must_follow_publish(db):
    now = utcnow()
    db.session.add(Notice(title="Bad", body="b", publish_at=now, expires_at=now - timedelta(1)))
    _expect_integrity_error(db)


# --- cascade behaviour -----------------------------------------------------

def test_student_profile_deleted_with_user_when_no_history(db, make_student):
    profile = make_student()
    db.session.delete(profile.user)
    db.session.flush()
    assert db.session.get(StudentProfile, profile.id) is None
