"""Account lifecycle: signup, email verification, password reset, invitations,
approvals and session revocation.

Account state machine (self-registration):

    signup ──> unverified + PENDING ──verify email──> PENDING ──staff approve──> APPROVED
                                                       └──────staff reject────> REJECTED

* Students skip the approval step when STUDENT_APPROVAL_REQUIRED is false.
* Staff who sign up with a valid invitation are APPROVED with the invitation's
  role once their email is verified (the invitation is the admin's approval).
* Staff who apply without an invitation get the lowest staff role and stay
  PENDING; an admin chooses their real role when approving.
* No public path can ever produce an admin.
"""
from datetime import timedelta

from flask import current_app

from ..extensions import db
from ..models import (
    AccountToken, ApprovalStatus, Role, StaffInvitation, StaffProfile, StudentProfile,
    TokenPurpose, User, hash_token, new_raw_token,
)
from ..utils.errors import APIError, ConflictError
from ..utils.time import today, utcnow
from . import audit, mailer

STAFF_ROLES_ASSIGNABLE = (Role.WARDEN, Role.STAFF)          # via invitation / approval
ROLE_CHANGE_ALLOWED = (Role.ADMIN, Role.WARDEN, Role.STAFF)   # by an admin, for staff accounts


def verification_required() -> bool:
    return current_app.config["EMAIL_VERIFICATION_REQUIRED"]


# --- sessions ----------------------------------------------------------------

def revoke_all_sessions(user: User) -> None:
    """Invalidate every access token issued to `user` (checked on each request)."""
    user.token_version = (user.token_version or 0) + 1


# --- one-time tokens ----------------------------------------------------------

def _issue(user: User, purpose: TokenPurpose, ttl: timedelta) -> str:
    """Create a token, invalidating any older unused token for the same purpose."""
    now = utcnow()
    db.session.execute(
        db.update(AccountToken)
        .where(AccountToken.user_id == user.id, AccountToken.purpose == purpose,
               AccountToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw = new_raw_token()
    db.session.add(AccountToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw),
                                expires_at=now + ttl))
    return raw


def _consume(raw: str, purpose: TokenPurpose) -> AccountToken:
    token = db.session.scalar(
        db.select(AccountToken).filter_by(token_hash=hash_token(raw or ""), purpose=purpose)
    )
    if token is None or token.used_at is not None:
        raise APIError("This link is invalid or has already been used.", 400, "token_invalid")
    if token.expires_at <= utcnow():
        raise APIError("This link has expired. Please request a new one.", 400, "token_expired")
    token.used_at = utcnow()
    return token


def send_verification(user: User) -> None:
    hours = current_app.config["EMAIL_VERIFICATION_TTL_HOURS"]
    raw = _issue(user, TokenPurpose.EMAIL_VERIFICATION, timedelta(hours=hours))
    mailer.send_verification_email(user, raw)


def send_password_reset(user: User) -> None:
    minutes = current_app.config["PASSWORD_RESET_TTL_MINUTES"]
    raw = _issue(user, TokenPurpose.PASSWORD_RESET, timedelta(minutes=minutes))
    mailer.send_password_reset_email(user, raw)


def verify_email(raw: str) -> User:
    token = _consume(raw, TokenPurpose.EMAIL_VERIFICATION)
    user = token.user
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    # An invited staff member is approved by the invitation itself.
    audit.record("auth.email_verified", "user", user.id, actor=user)
    return user


def reset_password(raw: str, new_password: str) -> User:
    token = _consume(raw, TokenPurpose.PASSWORD_RESET)
    user = token.user
    user.set_password(new_password)
    revoke_all_sessions(user)
    # Clicking the emailed link proves control of the address.
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    # Any other outstanding reset links for this user die with this one.
    db.session.execute(
        db.update(AccountToken)
        .where(AccountToken.user_id == user.id,
               AccountToken.purpose == TokenPurpose.PASSWORD_RESET,
               AccountToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    audit.record("auth.password_reset", "user", user.id, actor=user)
    return user


# --- uniqueness helpers -------------------------------------------------------

def check_unique(email: str | None = None, student_code: str | None = None,
                 employee_id: str | None = None) -> None:
    fields = {}
    if email and db.session.scalar(db.select(User.id).filter_by(email=email)):
        fields["email"] = "An account with this email already exists."
    if student_code and db.session.scalar(
            db.select(StudentProfile.id).filter_by(student_code=student_code)):
        fields["student_code"] = "This student ID is already registered."
    if employee_id and db.session.scalar(
            db.select(StaffProfile.id).filter_by(employee_id=employee_id)):
        fields["employee_id"] = "This employee ID is already registered."
    if fields:
        raise ConflictError("Some details are already registered.", details={"fields": fields})


# --- signup -------------------------------------------------------------------

def signup_student(data: dict) -> User:
    cfg = current_app.config
    check_unique(email=data["email"], student_code=data["student_code"])
    needs_approval = cfg["STUDENT_APPROVAL_REQUIRED"]
    user = User(email=data["email"], full_name=data["full_name"], phone=data["phone"],
                role=Role.STUDENT, is_active=True, created_via="signup",
                approval_status=ApprovalStatus.PENDING if needs_approval else ApprovalStatus.APPROVED,
                email_verified_at=None if cfg["EMAIL_VERIFICATION_REQUIRED"] else utcnow())
    user.set_password(data["password"])
    profile = StudentProfile(
        user=user, student_code=data["student_code"], course=data["course"],
        department=data["department"], academic_year=data["academic_year"],
        emergency_contact_name=data["emergency_contact_name"],
        emergency_contact_phone=data["emergency_contact_phone"],
        emergency_contact_relation=data.get("emergency_contact_relation"),
        registration_date=today(),
    )
    db.session.add(profile)
    db.session.flush()
    audit.record("auth.signup_student", "student", profile.id,
                 {"student_code": profile.student_code, "email": user.email}, actor=user)
    if user.email_verified_at is None:
        send_verification(user)
    return user


def find_invitation(raw_code: str) -> StaffInvitation:
    inv = db.session.scalar(db.select(StaffInvitation).filter_by(token_hash=hash_token(raw_code or "")))
    if inv is None or inv.status in ("revoked", "used"):
        raise APIError("This invitation code is invalid or has already been used.", 400,
                       "invitation_invalid", {"fields": {"invitation_code": "Invalid or already used."}})
    if inv.status == "expired":
        raise APIError("This invitation has expired. Ask an administrator for a new one.", 400,
                       "invitation_expired", {"fields": {"invitation_code": "This invitation has expired."}})
    return inv


def signup_staff(data: dict) -> tuple[User, StaffInvitation | None]:
    cfg = current_app.config
    invitation = None
    code = data.get("invitation_code")
    if code:
        invitation = find_invitation(code)
        if invitation.email != data["email"]:
            raise APIError("This invitation was issued for a different email address.", 400,
                           "invitation_email_mismatch",
                           {"fields": {"email": "Use the email address the invitation was sent to."}})
    elif not cfg["STAFF_SIGNUP_ENABLED"]:
        raise APIError("Staff accounts can only be created with an invitation code.", 403,
                       "invitation_required",
                       {"fields": {"invitation_code": "An invitation code is required."}})

    check_unique(email=data["email"], employee_id=data["employee_id"])

    # The role is decided by the server: the invitation's role, or the lowest
    # staff role while an admin reviews the application. Never admin.
    granted_role = Role(invitation.role) if invitation else Role.STAFF
    user = User(email=data["email"], full_name=data["full_name"], phone=data["phone"],
                role=granted_role, is_active=True,
                created_via="invitation" if invitation else "signup",
                approval_status=ApprovalStatus.APPROVED if invitation else ApprovalStatus.PENDING,
                email_verified_at=None if cfg["EMAIL_VERIFICATION_REQUIRED"] else utcnow())
    user.set_password(data["password"])
    user.staff_profile = StaffProfile(employee_id=data["employee_id"],
                                      department=data["department"],
                                      requested_role=data["requested_role"])
    db.session.add(user)
    db.session.flush()
    if invitation:
        invitation.used_at = utcnow()
        invitation.used_by_id = user.id
        user.reviewed_at = utcnow()
        user.reviewed_by_id = invitation.created_by_id
    audit.record("auth.signup_staff", "user", user.id, {
        "email": user.email, "requested_role": data["requested_role"],
        "granted_role": granted_role.value, "invitation_id": invitation.id if invitation else None,
    }, actor=user)
    if user.email_verified_at is None:
        send_verification(user)
    return user, invitation


# --- invitations ------------------------------------------------------------

def create_invitation(email: str, role: str, note: str | None, actor: User) -> tuple[StaffInvitation, str]:
    if Role(role) not in STAFF_ROLES_ASSIGNABLE:
        raise APIError("Invitations can only be for staff or warden.", 422, "validation_error",
                       {"fields": {"role": "Choose staff or warden."}})
    if db.session.scalar(db.select(User.id).filter_by(email=email)):
        raise ConflictError("An account with this email already exists.",
                            details={"fields": {"email": "Already registered."}})
    now = utcnow()
    # A new invitation replaces any still-active one for the same address.
    db.session.execute(
        db.update(StaffInvitation)
        .where(StaffInvitation.email == email, StaffInvitation.used_at.is_(None),
               StaffInvitation.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    raw = new_raw_token()
    inv = StaffInvitation(email=email, role=role, note=note, token_hash=hash_token(raw),
                          expires_at=now + timedelta(days=current_app.config["STAFF_INVITATION_TTL_DAYS"]),
                          created_by_id=actor.id)
    db.session.add(inv)
    db.session.flush()
    audit.record("staff.invite", "invitation", inv.id, {"email": email, "role": role}, actor=actor)
    mailer.send_staff_invitation_email(inv, raw)
    return inv, raw


def revoke_invitation(inv: StaffInvitation, actor: User) -> None:
    if inv.status != "active":
        raise ConflictError(f"This invitation is already {inv.status}.", code="invitation_not_active")
    inv.revoked_at = utcnow()
    audit.record("staff.invitation_revoke", "invitation", inv.id, {"email": inv.email}, actor=actor)


# --- approvals ----------------------------------------------------------------

def approve(user: User, actor: User, role: Role | None = None) -> None:
    if user.approval_status == ApprovalStatus.APPROVED:
        raise ConflictError("This account is already approved.", code="already_approved")
    if role is not None:
        if role not in STAFF_ROLES_ASSIGNABLE:
            raise APIError("Approved staff can be given the staff or warden role only.", 422,
                           "validation_error", {"fields": {"role": "Choose staff or warden."}})
        user.role = role
    user.approval_status = ApprovalStatus.APPROVED
    user.approval_note = None
    user.reviewed_at = utcnow()
    user.reviewed_by_id = actor.id
    audit.record("account.approve", "user", user.id,
                 {"role": user.role.value, "email": user.email}, actor=actor)
    mailer.send_account_decision_email(user, approved=True)


def reject(user: User, actor: User, reason: str) -> None:
    if user.approval_status == ApprovalStatus.REJECTED:
        raise ConflictError("This account is already rejected.", code="already_rejected")
    if user.approval_status == ApprovalStatus.APPROVED and user.role == Role.ADMIN:
        raise APIError("Administrator accounts cannot be rejected.", 400, "cannot_reject_admin")
    user.approval_status = ApprovalStatus.REJECTED
    user.approval_note = reason
    user.reviewed_at = utcnow()
    user.reviewed_by_id = actor.id
    revoke_all_sessions(user)
    audit.record("account.reject", "user", user.id, {"reason": reason, "email": user.email}, actor=actor)
    mailer.send_account_decision_email(user, approved=False, reason=reason)
