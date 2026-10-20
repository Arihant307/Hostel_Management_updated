"""/api/students — student records (staff manage; students read their own via /me).

Safeguards:
* Email and student ID are unique (checked here for friendly errors, and by
  database constraints).
* A student with an active room allocation cannot be deactivated — check them
  out first so occupancy stays correct.
* Hard delete is admin-only and only allowed for records with no history
  (allocations, fees or complaints). Everything else is deactivated instead.
* The limited "staff" role can view students; only admins and wardens change them.
* Self-registered students appear with approval_status "pending" until staff
  approve or reject them here.
"""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import exists, or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    AllocationStatus, ApprovalStatus, AuditLog, Complaint, FeeRecord, FeeStatus, Role,
    RoomAllocation, StudentProfile, User,
)
from ..services import accounts, audit
from ..utils.auth import admin_required, any_staff_required, login_required, staff_required
from ..utils.errors import APIError, ConflictError, NotFoundError
from ..utils.query import apply_sort, arg_bool, arg_choice, arg_int, arg_str, current_student_profile
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success
from ..utils.time import today, utcnow

bp = Blueprint("students", __name__)

PROFILE_FIELDS = ("student_code", "course", "department", "academic_year", "gender",
                  "date_of_birth", "address", "emergency_contact_name",
                  "emergency_contact_phone", "emergency_contact_relation", "registration_date")
USER_FIELDS = ("full_name", "email", "phone")


def _validate(data: dict, partial: bool) -> dict:
    v = Validator(data, partial=partial)
    v.string("full_name", min_length=2, max_length=120)
    v.email("email")
    v.phone("phone", required=False)
    v.string("student_code", min_length=2, max_length=32)
    v.string("course", max_length=100)
    v.string("department", max_length=100)
    v.integer("academic_year", min_value=1, max_value=6)
    v.choice("gender", ["male", "female", "other"], required=False)
    v.date("date_of_birth", required=False)
    v.string("address", required=False, max_length=255)
    v.string("emergency_contact_name", min_length=2, max_length=120)
    v.phone("emergency_contact_phone")
    v.string("emergency_contact_relation", required=False, max_length=50)
    v.date("registration_date", required=False)
    if not partial:
        v.password("password")
    if v.clean.get("date_of_birth") and v.clean["date_of_birth"] >= today():
        v.errors["date_of_birth"] = "Date of birth must be in the past."
    if v.clean.get("registration_date") and v.clean["registration_date"] > today():
        v.errors["registration_date"] = "Registration date cannot be in the future."
    v.raise_if_errors()
    if "student_code" in v.clean:
        v.clean["student_code"] = v.clean["student_code"].upper()
    return v.clean


def _check_unique(data: dict, exclude_user_id=None, exclude_profile_id=None) -> None:
    fields = {}
    if "email" in data:
        stmt = db.select(User.id).filter_by(email=data["email"])
        if exclude_user_id:
            stmt = stmt.where(User.id != exclude_user_id)
        if db.session.scalar(stmt):
            fields["email"] = "Email is already in use."
    if "student_code" in data:
        stmt = db.select(StudentProfile.id).filter_by(student_code=data["student_code"])
        if exclude_profile_id:
            stmt = stmt.where(StudentProfile.id != exclude_profile_id)
        if db.session.scalar(stmt):
            fields["student_code"] = "Student ID is already in use."
    if fields:
        raise ConflictError("A student with these details already exists.", details={"fields": fields})


def _get_student(student_id: int) -> StudentProfile:
    student = db.session.get(StudentProfile, student_id)
    if student is None:
        raise NotFoundError("Student not found.")
    return student


def _fee_summary(student: StudentProfile) -> dict:
    fees = [f for f in student.fee_records if f.status != FeeStatus.CANCELLED]
    return {
        "total_billed_minor": sum(f.amount_due_minor for f in fees),
        "total_paid_minor": sum(f.amount_paid_minor or 0 for f in fees),
        "outstanding_minor": sum(f.balance_minor for f in fees),
        "overdue_count": sum(1 for f in fees if f.status == FeeStatus.OVERDUE),
    }


def student_detail(student: StudentProfile) -> dict:
    return {
        **student.to_dict(),
        "allocation_history": [a.to_dict(include_student=False) for a in student.allocations],
        "fee_summary": _fee_summary(student),
        "complaint_count": len(student.complaints),
    }


# --- endpoints -------------------------------------------------------------

@bp.get("")
@any_staff_required
def list_students():
    active_alloc = exists().where(RoomAllocation.student_id == StudentProfile.id,
                                  RoomAllocation.status == AllocationStatus.ACTIVE)
    stmt = (db.select(StudentProfile).join(StudentProfile.user)
            .options(selectinload(StudentProfile.user),
                     selectinload(StudentProfile.allocations).selectinload(RoomAllocation.room)))

    search = arg_str("search")
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like),
                              StudentProfile.student_code.ilike(like), User.phone.ilike(like)))
    if department := arg_str("department"):
        stmt = stmt.where(StudentProfile.department == department)
    if (year := arg_int("academic_year")) is not None:
        stmt = stmt.where(StudentProfile.academic_year == year)
    status = arg_choice("status", ["active", "inactive"])
    if status:
        stmt = stmt.where(User.is_active.is_(status == "active"))
    if approval := arg_choice("approval", ApprovalStatus):
        stmt = stmt.where(User.approval_status == ApprovalStatus(approval))
    verified = arg_bool("verified")
    if verified is not None:
        stmt = stmt.where(User.email_verified_at.is_not(None) if verified
                          else User.email_verified_at.is_(None))
    has_room = arg_bool("has_room")
    if has_room is not None:
        stmt = stmt.where(active_alloc if has_room else ~active_alloc)

    stmt = apply_sort(stmt, {
        "name": User.full_name, "student_code": StudentProfile.student_code,
        "department": StudentProfile.department, "academic_year": StudentProfile.academic_year,
        "registration_date": StudentProfile.registration_date, "created_at": StudentProfile.created_at,
    }, default="created_at", default_order="desc", tiebreak=StudentProfile.id)
    return success(paginate(stmt, lambda s: s.to_dict()))


@bp.get("/departments")
@any_staff_required
def list_departments():
    rows = db.session.scalars(db.select(StudentProfile.department).distinct()
                              .order_by(StudentProfile.department)).all()
    return success(rows)


@bp.get("/me")
@login_required
def my_profile():
    return success(student_detail(current_student_profile()))


@bp.post("")
@staff_required
def create_student():
    data = _validate(json_body(), partial=False)
    _check_unique(data)

    # Registered by staff: trusted, so approved and treated as verified.
    user = User(email=data["email"], full_name=data["full_name"], phone=data.get("phone"),
                role=Role.STUDENT, is_active=True, created_via="staff",
                approval_status=ApprovalStatus.APPROVED, email_verified_at=utcnow(),
                reviewed_at=utcnow(), reviewed_by_id=current_user.id)
    user.set_password(data["password"])
    profile = StudentProfile(user=user, registration_date=data.get("registration_date") or today(),
                             **{f: data.get(f) for f in PROFILE_FIELDS if f != "registration_date"})
    db.session.add(profile)
    db.session.flush()
    audit.record("student.create", "student", profile.id,
                 {"student_code": profile.student_code, "email": user.email})
    db.session.commit()
    return success(student_detail(profile), 201, "Student registered.")


@bp.get("/<int:student_id>")
@any_staff_required
def get_student(student_id: int):
    return success(student_detail(_get_student(student_id)))


@bp.patch("/<int:student_id>")
@staff_required
def update_student(student_id: int):
    student = _get_student(student_id)
    data = _validate(json_body(), partial=True)
    data.pop("password", None)
    for required in ("full_name", "email", "student_code", "course", "department",
                     "academic_year", "emergency_contact_name", "emergency_contact_phone",
                     "registration_date"):
        if required in data and data[required] is None:
            data.pop(required)
    _check_unique(data, exclude_user_id=student.user_id, exclude_profile_id=student.id)

    changes = {}
    for field, value in data.items():
        target = student.user if field in USER_FIELDS else student
        old = getattr(target, field)
        if old != value:
            changes[field] = {"from": str(old) if old is not None else None,
                              "to": str(value) if value is not None else None}
            setattr(target, field, value)
    if changes:
        audit.record("student.update", "student", student.id, {"changes": changes})
    db.session.commit()
    return success(student_detail(student), message="Student updated.")


@bp.patch("/<int:student_id>/status")
@staff_required
def set_student_status(student_id: int):
    student = _get_student(student_id)
    v = Validator(json_body())
    v.boolean("is_active")
    v.raise_if_errors()
    active = v.clean["is_active"]
    if active == student.user.is_active:
        return success(student_detail(student))
    if not active and student.current_allocation is not None:
        raise APIError("Check the student out of their room before deactivating the account.",
                       409, "has_active_allocation")
    student.user.is_active = active
    if not active:
        student.user.token_version += 1
    audit.record("student.activate" if active else "student.deactivate", "student", student.id)
    db.session.commit()
    return success(student_detail(student),
                   message="Student reactivated." if active else "Student deactivated.")


@bp.post("/<int:student_id>/reset-password")
@staff_required
def reset_student_password(student_id: int):
    student = _get_student(student_id)
    v = Validator(json_body())
    v.password("password")
    v.raise_if_errors()
    student.user.set_password(v.clean["password"])
    student.user.token_version += 1
    audit.record("student.reset_password", "student", student.id)
    db.session.commit()
    return success(None, message="Password reset.")


@bp.delete("/<int:student_id>")
@admin_required
def delete_student(student_id: int):
    student = _get_student(student_id)
    has_history = (
        db.session.scalar(db.select(RoomAllocation.id).filter_by(student_id=student.id).limit(1))
        or db.session.scalar(db.select(FeeRecord.id).filter_by(student_id=student.id).limit(1))
        or db.session.scalar(db.select(Complaint.id).filter_by(student_id=student.id).limit(1))
    )
    if has_history:
        raise APIError("This student has allocation, fee or complaint history and cannot be "
                       "deleted. Deactivate the account instead.", 409, "has_history")
    details = {"student_code": student.student_code, "email": student.user.email}
    user = student.user
    audit.record("student.delete", "student", student.id, details)
    db.session.delete(user)  # cascades to the profile
    db.session.commit()
    return success(None, message="Student deleted.")


# --- account management ------------------------------------------------------

@bp.post("/<int:student_id>/approve")
@staff_required
def approve_student(student_id: int):
    student = _get_student(student_id)
    if student.user.email_verified_at is None and accounts.verification_required():
        raise APIError("This student has not verified their email address yet.", 409,
                       "email_unverified")
    accounts.approve(student.user, current_user._get_current_object())
    db.session.commit()
    return success(student_detail(student), message="Registration approved.")


@bp.post("/<int:student_id>/reject")
@staff_required
def reject_student(student_id: int):
    student = _get_student(student_id)
    if student.current_allocation is not None:
        raise APIError("Check the student out of their room before rejecting the account.",
                       409, "has_active_allocation")
    v = Validator(json_body())
    v.string("reason", min_length=3, max_length=255)
    v.raise_if_errors()
    accounts.reject(student.user, current_user._get_current_object(), v.clean["reason"])
    db.session.commit()
    return success(student_detail(student), message="Registration rejected.")


@bp.post("/<int:student_id>/send-password-reset")
@staff_required
def send_student_password_reset(student_id: int):
    """Email the student a secure reset link; staff never see the token."""
    student = _get_student(student_id)
    if not student.user.is_active:
        raise APIError("Reactivate the account before sending a reset link.", 409,
                       "account_disabled")
    accounts.send_password_reset(student.user)
    audit.record("student.password_reset_link_sent", "student", student.id)
    db.session.commit()
    return success(None, message=f"A password reset link was emailed to {student.user.email}.")


@bp.get("/<int:student_id>/history")
@any_staff_required
def student_history(student_id: int):
    """Account creation and status changes for this student (audit trail)."""
    student = _get_student(student_id)
    stmt = (db.select(AuditLog).options(selectinload(AuditLog.actor))
            .where(or_((AuditLog.entity_type == "student") & (AuditLog.entity_id == student.id),
                       (AuditLog.entity_type == "user") & (AuditLog.entity_id == student.user_id)))
            .where(~AuditLog.action.in_(["auth.login", "auth.logout", "auth.login_failed"]))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()))
    return success(paginate(stmt, lambda a: a.to_dict()))
