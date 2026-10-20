"""Aggregate statistics computed from live database records (no stored totals)."""
from collections import OrderedDict
from datetime import date

from sqlalchemy import func

from ..extensions import db
from ..models import (
    AllocationStatus, Complaint, ComplaintStatus, FeeRecord, Payment, PaymentStatus, Room,
    RoomAllocation, StudentProfile, User,
)
from .billing import outstanding_expr, status_clause


def month_keys(end: date, count: int) -> list[date]:
    """First day of each of the `count` months ending with `end`'s month, oldest first."""
    months, year, month = [], end.year, end.month
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def payment_trend(end: date, months: int = 12) -> list[dict]:
    keys = month_keys(end, months)
    start = keys[0]
    rows = db.session.execute(
        db.select(Payment.paid_on, Payment.amount_minor)
        .where(Payment.status == PaymentStatus.COMPLETED, Payment.paid_on >= start,
               Payment.paid_on <= end)
    ).all()
    buckets = OrderedDict((k.strftime("%Y-%m"), {"amount_minor": 0, "count": 0}) for k in keys)
    for paid_on, amount in rows:
        bucket = buckets.get(paid_on.strftime("%Y-%m"))
        if bucket is not None:
            bucket["amount_minor"] += amount
            bucket["count"] += 1
    return [{"month": k, "label": date.fromisoformat(k + "-01").strftime("%b %Y"), **v}
            for k, v in buckets.items()]


def occupancy_by_block() -> list[dict]:
    occupied = (db.select(RoomAllocation.room_id, func.count(RoomAllocation.id).label("n"))
                .where(RoomAllocation.status == AllocationStatus.ACTIVE)
                .group_by(RoomAllocation.room_id).subquery())
    rows = db.session.execute(
        db.select(Room.block, func.count(Room.id), func.sum(Room.capacity),
                  func.coalesce(func.sum(occupied.c.n), 0))
        .outerjoin(occupied, occupied.c.room_id == Room.id)
        .where(Room.is_active.is_(True)).group_by(Room.block).order_by(Room.block)
    ).all()
    return [{"block": block, "rooms": rooms, "beds": int(beds or 0), "occupied": int(occ or 0),
             "available": int((beds or 0) - (occ or 0))} for block, rooms, beds, occ in rows]


def bed_totals() -> dict:
    blocks = occupancy_by_block()
    beds = sum(b["beds"] for b in blocks)
    occupied = sum(b["occupied"] for b in blocks)
    return {
        "rooms": sum(b["rooms"] for b in blocks),
        "beds_total": beds,
        "beds_occupied": occupied,
        "beds_available": beds - occupied,
        "occupancy_percent": round(occupied * 100 / beds, 1) if beds else 0.0,
    }


def fee_totals(on: date) -> dict:
    outstanding = db.session.scalar(db.select(func.coalesce(func.sum(outstanding_expr()), 0)))
    overdue_count, overdue_amount = db.session.execute(
        db.select(func.count(FeeRecord.id), func.coalesce(func.sum(outstanding_expr()), 0))
        .where(status_clause("overdue", on))
    ).one()
    open_count = db.session.scalar(
        db.select(func.count(FeeRecord.id)).where(status_clause("outstanding", on)))
    return {"outstanding_minor": int(outstanding), "overdue_count": overdue_count,
            "overdue_minor": int(overdue_amount), "unpaid_count": open_count}


def payment_totals(on: date) -> dict:
    month_start = on.replace(day=1)
    completed = Payment.status == PaymentStatus.COMPLETED
    total, count = db.session.execute(
        db.select(func.coalesce(func.sum(Payment.amount_minor), 0), func.count(Payment.id))
        .where(completed)).one()
    month_total, month_count = db.session.execute(
        db.select(func.coalesce(func.sum(Payment.amount_minor), 0), func.count(Payment.id))
        .where(completed, Payment.paid_on >= month_start, Payment.paid_on <= on)).one()
    return {"total_minor": int(total), "total_count": count,
            "this_month_minor": int(month_total), "this_month_count": month_count}


def complaint_totals() -> dict:
    rows = dict(db.session.execute(
        db.select(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status)).all())
    counts = {s.value: rows.get(s, 0) for s in ComplaintStatus}
    counts["active"] = counts["open"] + counts["in_progress"]
    return counts


def complaints_by_category() -> list[dict]:
    active = Complaint.status.in_([ComplaintStatus.OPEN, ComplaintStatus.IN_PROGRESS])
    rows = db.session.execute(
        db.select(Complaint.category, func.count(Complaint.id),
                  func.sum(db.case((active, 1), else_=0)))
        .group_by(Complaint.category).order_by(func.count(Complaint.id).desc())
    ).all()
    return [{"category": c.value, "total": t, "active": int(a or 0)} for c, t, a in rows]


def student_totals(on: date) -> dict:
    total, active = db.session.execute(
        db.select(func.count(StudentProfile.id),
                  func.sum(db.case((User.is_active.is_(True), 1), else_=0)))
        .join(StudentProfile.user)).one()
    new = db.session.scalar(db.select(func.count(StudentProfile.id))
                            .where(StudentProfile.registration_date >= on.replace(day=1)))
    housed = db.session.scalar(db.select(func.count(RoomAllocation.id))
                               .where(RoomAllocation.status == AllocationStatus.ACTIVE))
    return {"total": total, "active": int(active or 0), "new_this_month": new,
            "with_room": housed, "without_room": int(active or 0) - housed}
