"""/api/auth/staff and /api/auth/invitations — admin-only staff account management.

Rules enforced here (never only in the UI):
* Only admins reach these endpoints.
* An admin cannot deactivate or demote themselves, and the last active admin
  can never be deactivated or demoted.
* Deactivation, rejection and any role change revoke the user's sessions.
* Invitations and approvals can grant staff or warden only; promotion to admin
  is a separate, explicit role change by an existing admin.
"""
from flask import Blueprint, request
from flask_jwt_extended import current_user
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import ApprovalStatus, AuditLog, Role, StaffInvitation, User
from ..services import accounts, audit
from ..utils.auth import admin_required
from ..utils.errors import APIError, ConflictError, NotFoundError
from ..utils.query import arg_choice, arg_str
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success
from ..utils.time import utcnow

bp = Blueprint("staff_accounts", __name__)

STAFF_ROLES = (Role.ADMIN, Role.WARDEN, Role.STAFF)


def _get_staff(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None or user.role not in STAFF_ROLES:
        raise NotFoundError("Staff account not found.")
    return user


def _active_admin_count() -> int:
    return db.session.scalar(
        db.select(func.count(User.id)).filter_by(role=Role.ADMIN, is_active=True,
                                                 approval_status=ApprovalStatus.APPROVED))


def _guard_admin_loss(user: User, action: str) -> None:
    """Block actions that would remove admin access from self or the last admin."""
    if user.id == current_user.id:
        code = "self_deactivation" if action == "deactivate" else "self_change"
        raise APIError(f"You cannot {action} your own account.", 400, code)
    if user.role == Role.ADMIN and user.is_active and _active_admin_count() <= 1:
        raise APIError("At least one active administrator is required.", 400, "last_admin")


# --- staff accounts --------------------------------------------------------

@bp.get("/staff")
@admin_required
def list_staff():
    stmt = db.select(User).where(User.role.in_(STAFF_ROLES)).options(selectinload(User.staff_profile))
    if role := arg_choice("role", ["admin", "warden", "staff"]):
        stmt = stmt.where(User.role == Role(role))
    status = arg_choice("status", ["active", "inactive"])
    if status:
        stmt = stmt.where(User.is_active.is_(status == "active"))
    if approval := arg_choice("approval", ApprovalStatus):
        stmt = stmt.where(User.approval_status == ApprovalStatus(approval))
    if search := arg_str("search"):
        like = f"%{search}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))

    sort_columns = {"name": User.full_name, "email": User.email,
                    "created_at": User.created_at, "last_login_at": User.last_login_at}
    column = sort_columns.get(request.args.get("sort"), User.created_at)
    stmt = stmt.order_by(column.desc() if request.args.get("order") == "desc" else column.asc(),
                         User.id)
    counts = dict(db.session.execute(
        db.select(User.approval_status, func.count(User.id))
        .where(User.role.in_(STAFF_ROLES)).group_by(User.approval_status)).all())
    return success({**paginate(stmt, lambda u: u.to_dict()),
                    "counts": {s.value: counts.get(s, 0) for s in ApprovalStatus}})


@bp.post("/staff")
@admin_required
def create_staff():
    v = Validator(json_body())
    v.string("full_name", min_length=2, max_length=120)
    v.email("email")
    v.phone("phone", required=False)
    v.choice("role", STAFF_ROLES)
    v.password("password")
    v.raise_if_errors()
    data = v.clean

    if db.session.scalar(db.select(User.id).filter_by(email=data["email"])):
        raise ConflictError("An account with this email already exists.",
                            details={"fields": {"email": "Email is already in use."}})

    # Created directly by an admin: trusted, approved and verified.
    user = User(full_name=data["full_name"], email=data["email"], phone=data.get("phone"),
                role=Role(data["role"]), is_active=True, created_via="admin",
                approval_status=ApprovalStatus.APPROVED, email_verified_at=utcnow(),
                reviewed_at=utcnow(), reviewed_by_id=current_user.id)
    user.set_password(data["password"])
    db.session.add(user)
    db.session.flush()
    audit.record("staff.create", "user", user.id, {"email": user.email, "role": user.role.value})
    db.session.commit()
    return success(user.to_dict(), 201, "Staff account created.")


@bp.get("/staff/<int:user_id>")
@admin_required
def get_staff(user_id: int):
    return success(_get_staff(user_id).to_dict())


@bp.patch("/staff/<int:user_id>")
@admin_required
def update_staff(user_id: int):
    user = _get_staff(user_id)
    v = Validator(json_body(), partial=True)
    v.string("full_name", min_length=2, max_length=120)
    v.phone("phone", required=False)
    v.boolean("is_active")
    v.choice("role", STAFF_ROLES)
    v.raise_if_errors()
    data = v.clean

    revoke = False
    if data.get("is_active") is False and user.is_active:
        _guard_admin_loss(user, "deactivate")
        revoke = True
    if "role" in data and Role(data["role"]) != user.role:
        if user.approval_status != ApprovalStatus.APPROVED:
            raise APIError("Approve the application before changing its role.", 409, "not_approved")
        if user.role == Role.ADMIN:
            _guard_admin_loss(user, "change the role of")
        elif user.id == current_user.id:
            raise APIError("You cannot change your own role.", 400, "self_change")
        data["role"] = Role(data["role"])
        revoke = True  # new privileges take effect on next sign-in

    changes = {}
    for field in ("full_name", "phone", "is_active", "role"):
        if field in data and getattr(user, field) != data[field]:
            old = getattr(user, field)
            changes[field] = {"from": getattr(old, "value", old), "to": getattr(data[field], "value", data[field])}
            setattr(user, field, data[field])
    if revoke:
        accounts.revoke_all_sessions(user)
    if changes:
        action = "staff.role_change" if "role" in changes else "staff.update"
        audit.record(action, "user", user.id, {"changes": changes})
    db.session.commit()
    return success(user.to_dict(), message="Staff account updated.")


@bp.post("/staff/<int:user_id>/approve")
@admin_required
def approve_staff(user_id: int):
    user = _get_staff(user_id)
    v = Validator(json_body())
    v.choice("role", [Role.WARDEN, Role.STAFF])
    v.raise_if_errors()
    accounts.approve(user, current_user._get_current_object(), role=Role(v.clean["role"]))
    db.session.commit()
    return success(user.to_dict(), message="Staff application approved.")


@bp.post("/staff/<int:user_id>/reject")
@admin_required
def reject_staff(user_id: int):
    user = _get_staff(user_id)
    if user.id == current_user.id:
        raise APIError("You cannot reject your own account.", 400, "self_change")
    v = Validator(json_body())
    v.string("reason", min_length=3, max_length=255)
    v.raise_if_errors()
    accounts.reject(user, current_user._get_current_object(), v.clean["reason"])
    db.session.commit()
    return success(user.to_dict(), message="Staff application rejected.")


@bp.post("/staff/<int:user_id>/reset-password")
@admin_required
def reset_staff_password(user_id: int):
    user = _get_staff(user_id)
    if user.id == current_user.id:
        raise APIError("Use 'Change password' to change your own password.", 400, "use_change_password")
    v = Validator(json_body())
    v.password("password")
    v.raise_if_errors()
    user.set_password(v.clean["password"])
    accounts.revoke_all_sessions(user)
    audit.record("staff.reset_password", "user", user.id)
    db.session.commit()
    return success(None, message="Password reset. The user must sign in again.")


@bp.post("/staff/<int:user_id>/send-password-reset")
@admin_required
def send_staff_password_reset(user_id: int):
    """Email the user a secure reset link. The admin never sees the token."""
    user = _get_staff(user_id)
    if not user.is_active:
        raise APIError("Reactivate the account before sending a reset link.", 409, "account_disabled")
    accounts.send_password_reset(user)
    audit.record("staff.password_reset_link_sent", "user", user.id)
    db.session.commit()
    return success(None, message=f"A password reset link was emailed to {user.email}.")


@bp.get("/staff/<int:user_id>/history")
@admin_required
def staff_history(user_id: int):
    user = _get_staff(user_id)
    stmt = (db.select(AuditLog).options(selectinload(AuditLog.actor))
            .where(AuditLog.entity_type == "user", AuditLog.entity_id == user.id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()))
    return success(paginate(stmt, lambda a: a.to_dict()))


# --- invitations ----------------------------------------------------------

@bp.get("/invitations")
@admin_required
def list_invitations():
    stmt = db.select(StaffInvitation).options(selectinload(StaffInvitation.created_by),
                                              selectinload(StaffInvitation.used_by))
    now = utcnow()
    status = arg_choice("status", ["active", "used", "revoked", "expired"])
    if status == "active":
        stmt = stmt.where(StaffInvitation.used_at.is_(None), StaffInvitation.revoked_at.is_(None),
                          StaffInvitation.expires_at > now)
    elif status == "used":
        stmt = stmt.where(StaffInvitation.used_at.is_not(None))
    elif status == "revoked":
        stmt = stmt.where(StaffInvitation.revoked_at.is_not(None))
    elif status == "expired":
        stmt = stmt.where(StaffInvitation.used_at.is_(None), StaffInvitation.revoked_at.is_(None),
                          StaffInvitation.expires_at <= now)
    if search := arg_str("search"):
        stmt = stmt.where(StaffInvitation.email.ilike(f"%{search}%"))
    stmt = stmt.order_by(StaffInvitation.created_at.desc(), StaffInvitation.id.desc())
    return success(paginate(stmt, lambda i: i.to_dict()))


@bp.post("/invitations")
@admin_required
def create_invitation():
    v = Validator(json_body())
    v.email("email")
    v.choice("role", [Role.WARDEN, Role.STAFF])
    v.string("note", required=False, max_length=255)
    v.raise_if_errors()
    inv, raw = accounts.create_invitation(v.clean["email"], v.clean["role"], v.clean.get("note"),
                                          current_user._get_current_object())
    db.session.commit()
    # The code is returned once so the admin can share it if email is not set up.
    return success({**inv.to_dict(), "code": raw}, 201,
                   f"Invitation created for {inv.email}. The code is shown only once.")


@bp.post("/invitations/<int:invitation_id>/revoke")
@admin_required
def revoke_invitation(invitation_id: int):
    inv = db.session.get(StaffInvitation, invitation_id)
    if inv is None:
        raise NotFoundError("Invitation not found.")
    accounts.revoke_invitation(inv, current_user._get_current_object())
    db.session.commit()
    return success(inv.to_dict(), message="Invitation revoked.")
