"""/api/dashboard — figures for the staff and student dashboards.

Every number is computed from current database rows at request time.
"""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    AllocationStatus, Complaint, FeeRecord, FeeStatus, Notice, NoticeAudience, Role,
    RoomAllocation, StudentProfile,
)
from ..services import stats
from ..utils.auth import any_staff_required, login_required
from ..utils.query import current_student_profile
from ..utils.responses import success
from ..utils.time import isoformat, today, utcnow

bp = Blueprint("dashboard", __name__)


@bp.get("/summary")
@any_staff_required
def staff_summary():
    on = today()
    recent_students = db.session.scalars(
        db.select(StudentProfile).options(selectinload(StudentProfile.user))
        .order_by(StudentProfile.created_at.desc(), StudentProfile.id.desc()).limit(5)).all()
    recent_allocations = db.session.scalars(
        db.select(RoomAllocation)
        .options(selectinload(RoomAllocation.room),
                 selectinload(RoomAllocation.student).selectinload(StudentProfile.user))
        .order_by(RoomAllocation.created_at.desc(), RoomAllocation.id.desc()).limit(5)).all()
    data = {
        "as_of": isoformat(utcnow()),
        "students": stats.student_totals(on),
        "rooms": stats.bed_totals(),
        "fees": stats.fee_totals(on),
        "payments": stats.payment_totals(on),
        "complaints": stats.complaint_totals(),
        "payment_trend": stats.payment_trend(on, 12),
        "occupancy_by_block": stats.occupancy_by_block(),
        "complaints_by_category": stats.complaints_by_category(),
        "recent_students": [{
            "id": s.id, "student_code": s.student_code, "full_name": s.user.full_name,
            "department": s.department, "registration_date": isoformat(s.registration_date),
            "created_at": isoformat(s.created_at),
        } for s in recent_students],
        "recent_allocations": [a.to_dict() for a in recent_allocations],
    }
    if current_user.role == Role.STAFF:  # no financial figures for the limited role
        for key in ("fees", "payments", "payment_trend"):
            data.pop(key)
    return success(data)


@bp.get("/student")
@login_required
def student_summary():
    student = current_student_profile()
    allocation = student.current_allocation
    roommates = []
    if allocation:
        roommates = [a.student.user.full_name for a in db.session.scalars(
            db.select(RoomAllocation).filter_by(room_id=allocation.room_id,
                                                status=AllocationStatus.ACTIVE)
            .where(RoomAllocation.student_id != student.id)).all()]

    fees = db.session.scalars(db.select(FeeRecord).filter_by(student_id=student.id)
                              .order_by(FeeRecord.due_date.desc())).all()
    open_fees = [f for f in fees if f.status in (FeeStatus.PENDING, FeeStatus.PARTIALLY_PAID,
                                                 FeeStatus.OVERDUE)]
    next_due = min(open_fees, key=lambda f: f.due_date, default=None)
    complaints = db.session.scalars(db.select(Complaint).filter_by(student_id=student.id)
                                    .order_by(Complaint.created_at.desc()).limit(3)).all()
    notices = db.session.scalars(
        db.select(Notice).where(Notice.active_filter(),
                                Notice.audience.in_([NoticeAudience.ALL, NoticeAudience.STUDENTS]))
        .order_by(Notice.is_pinned.desc(), Notice.publish_at.desc()).limit(5)).all()

    return success({
        "profile": student.to_dict(),
        "room": {**allocation.room.to_dict(), "allocation": allocation.to_dict(include_student=False),
                 "roommates": roommates} if allocation else None,
        "fees": {
            "outstanding_minor": sum(f.balance_minor for f in open_fees),
            "overdue_count": sum(1 for f in open_fees if f.status == FeeStatus.OVERDUE),
            "next_due": next_due.to_dict() if next_due else None,
            "recent": [f.to_dict() for f in fees[:3]],
        },
        "complaints": [c.to_dict() for c in complaints],
        "notices": [n.to_dict() for n in notices],
    })
