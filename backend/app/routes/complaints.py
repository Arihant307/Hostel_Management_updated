"""/api/complaints — maintenance complaints.

Students file complaints and see only their own (never internal notes).
Staff see all, assign them, change status, and add replies or internal notes.
Resolving or rejecting requires a resolution message for the student.
"""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    Complaint, ComplaintCategory, ComplaintComment, ComplaintPriority, ComplaintStatus,
    StudentProfile, User,
)
from ..services import audit
from ..utils.auth import any_staff_required, login_required
from ..utils.errors import APIError, ForbiddenError, NotFoundError
from ..utils.query import (
    apply_sort, arg_choice, arg_date, arg_int, arg_str, current_student_profile, is_student,
)
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success
from ..utils.time import utcnow

bp = Blueprint("complaints", __name__)
CLOSED = (ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED)


def _serialize(c: Complaint) -> dict:
    return c.to_dict(include_internal=not is_student())


def _get_complaint(complaint_id: int) -> Complaint:
    complaint = db.session.get(Complaint, complaint_id)
    if complaint is None or (is_student() and complaint.student_id != current_student_profile().id):
        raise NotFoundError("Complaint not found.")
    return complaint


@bp.get("")
@login_required
def list_complaints():
    stmt = (db.select(Complaint).join(Complaint.student).join(StudentProfile.user)
            .options(selectinload(Complaint.student).selectinload(StudentProfile.user),
                     selectinload(Complaint.room),
                     selectinload(Complaint.comments).selectinload(ComplaintComment.author)))
    if is_student():
        stmt = stmt.where(Complaint.student_id == current_student_profile().id)
    else:
        if (student_id := arg_int("student_id")) is not None:
            stmt = stmt.where(Complaint.student_id == student_id)
        if search := arg_str("search"):
            like = f"%{search}%"
            stmt = stmt.where(or_(Complaint.title.ilike(like), User.full_name.ilike(like),
                                  StudentProfile.student_code.ilike(like)))
    if status := arg_choice("status", [s.value for s in ComplaintStatus] + ["active"]):
        if status == "active":
            stmt = stmt.where(Complaint.status.in_([ComplaintStatus.OPEN, ComplaintStatus.IN_PROGRESS]))
        else:
            stmt = stmt.where(Complaint.status == ComplaintStatus(status))
    if category := arg_choice("category", ComplaintCategory):
        stmt = stmt.where(Complaint.category == ComplaintCategory(category))
    if priority := arg_choice("priority", ComplaintPriority):
        stmt = stmt.where(Complaint.priority == ComplaintPriority(priority))
    if date_from := arg_date("from"):
        stmt = stmt.where(db.func.date(Complaint.created_at) >= date_from.isoformat())
    if date_to := arg_date("to"):
        stmt = stmt.where(db.func.date(Complaint.created_at) <= date_to.isoformat())
    stmt = apply_sort(stmt, {
        "created_at": Complaint.created_at, "updated_at": Complaint.updated_at,
        "priority": Complaint.priority, "status": Complaint.status,
    }, default="created_at", default_order="desc", tiebreak=Complaint.id.desc())
    return success(paginate(stmt, _serialize))


@bp.post("")
@login_required
def create_complaint():
    if not is_student():
        raise ForbiddenError("Only students can file complaints.")
    student = current_student_profile()
    v = Validator(json_body())
    v.choice("category", ComplaintCategory)
    v.choice("priority", ComplaintPriority, required=False)
    v.string("title", min_length=4, max_length=150)
    v.string("description", min_length=10, max_length=4000)
    v.raise_if_errors()
    data = v.clean
    allocation = student.current_allocation
    complaint = Complaint(student=student, room_id=allocation.room_id if allocation else None,
                          category=ComplaintCategory(data["category"]),
                          priority=ComplaintPriority(data.get("priority") or "medium"),
                          title=data["title"], description=data["description"])
    db.session.add(complaint)
    db.session.flush()
    audit.record("complaint.create", "complaint", complaint.id, {"category": data["category"]})
    db.session.commit()
    return success(_serialize(complaint), 201, "Complaint submitted.")


@bp.get("/<int:complaint_id>")
@login_required
def get_complaint(complaint_id: int):
    return success(_serialize(_get_complaint(complaint_id)))


@bp.patch("/<int:complaint_id>")
@any_staff_required
def update_complaint(complaint_id: int):
    complaint = _get_complaint(complaint_id)
    v = Validator(json_body(), partial=True)
    v.choice("status", ComplaintStatus)
    v.choice("priority", ComplaintPriority)
    v.string("assigned_to", required=False, max_length=120)
    v.string("resolution", required=False, max_length=4000)
    v.raise_if_errors()
    data = v.clean

    new_status = ComplaintStatus(data["status"]) if "status" in data else complaint.status
    resolution = data["resolution"] if "resolution" in data else complaint.resolution
    if new_status in CLOSED and not resolution:
        raise APIError("Add a resolution message explaining the outcome to the student.", 422,
                       "validation_error",
                       {"fields": {"resolution": "Required when resolving or rejecting."}})

    changes = {}
    for field in ("priority", "assigned_to", "resolution"):
        if field in data:
            value = ComplaintPriority(data[field]) if field == "priority" else data[field]
            if getattr(complaint, field) != value:
                changes[field] = {"from": str(getattr(complaint, field)), "to": str(value)}
                setattr(complaint, field, value)
    if new_status != complaint.status:
        changes["status"] = {"from": complaint.status.value, "to": new_status.value}
        complaint.status = new_status
        complaint.resolved_at = utcnow() if new_status in CLOSED else None
    complaint.handled_by = current_user._get_current_object()
    if changes:
        audit.record("complaint.update", "complaint", complaint.id, {"changes": changes})
    db.session.commit()
    return success(_serialize(complaint), message="Complaint updated.")


@bp.post("/<int:complaint_id>/comments")
@login_required
def add_comment(complaint_id: int):
    complaint = _get_complaint(complaint_id)
    v = Validator(json_body())
    v.string("body", min_length=1, max_length=4000)
    v.boolean("is_internal", required=False)
    v.raise_if_errors()
    internal = bool(v.clean.get("is_internal"))
    if is_student() and internal:
        raise ForbiddenError("Students cannot add internal notes.")
    comment = ComplaintComment(complaint=complaint, author=current_user._get_current_object(),
                               body=v.clean["body"], is_internal=internal)
    db.session.add(comment)
    db.session.flush()
    audit.record("complaint.comment", "complaint", complaint.id, {"internal": internal})
    db.session.commit()
    return success(_serialize(complaint), 201, "Note added." if internal else "Reply posted.")
