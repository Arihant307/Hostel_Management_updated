"""/api/auth — sign-in, sessions, self-registration, email verification,
password recovery and the signed-in user's own profile.

Public endpoints never reveal whether an email address is registered:
forgot-password and resend-verification always return the same response, and
login failures use one message for "no such user" and "wrong password".
Admin management of staff accounts lives in routes/staff_accounts.py.
"""
from datetime import datetime, timezone

from flask import Blueprint, current_app, request
from flask_jwt_extended import current_user, get_jwt
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import RevokedToken, Role, StaffInvitation, User
from ..services import accounts, audit
from ..utils.auth import issue_access_token, login_required
from ..utils.errors import APIError, ValidationError
from ..utils.rate_limit import (
    email_action_per_address, email_action_per_ip, login_throttle, signup_per_ip,
    token_attempts_per_ip,
)
from ..utils.request import Validator, client_ip, json_body
from ..utils.responses import success
from ..utils.time import isoformat, utcnow

bp = Blueprint("auth", __name__)

# Verified against when the email is unknown, so response time does not reveal
# whether an account exists.
_DUMMY_HASH = generate_password_hash("timing-equaliser-not-a-real-password", method="scrypt")

GENERIC_EMAIL_SENT = ("If an account exists for that email address, we have sent a message "
                      "with further instructions. Check your inbox and spam folder.")


def _client_ip() -> str:
    return client_ip() or "unknown"


def _limited(seconds: int):
    raise APIError(f"Too many requests. Try again in {seconds // 60 + 1} minute(s).",
                   429, "too_many_attempts", {"retry_after_seconds": seconds})


def _session_payload(user: User) -> dict:
    data = {"user": user.to_dict()}
    if user.role == Role.STUDENT and user.student_profile is not None:
        data["student_profile"] = user.student_profile.to_dict(include_user=False)
    return data


def _revoke_current_token() -> None:
    claims = get_jwt()
    db.session.add(RevokedToken(
        jti=claims["jti"], user_id=current_user.id,
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc).replace(tzinfo=None),
    ))


def _password_pair(v: Validator, data: dict, field="password", confirm="confirm_password"):
    v.password(field)
    if confirm in data and data.get(confirm) != data.get(field):
        v.errors[confirm] = "Passwords do not match."


# --- policy (public) -------------------------------------------------------

@bp.get("/signup-policy")
def signup_policy():
    cfg = current_app.config
    return success({
        "student_signup_enabled": cfg["STUDENT_SIGNUP_ENABLED"],
        "student_approval_required": cfg["STUDENT_APPROVAL_REQUIRED"],
        "staff_signup_enabled": cfg["STAFF_SIGNUP_ENABLED"],
        "email_verification_required": cfg["EMAIL_VERIFICATION_REQUIRED"],
        "hostel_name": cfg["HOSTEL_NAME"],
    })


# --- session ---------------------------------------------------------------

@bp.post("/login")
def login():
    data = json_body()
    email = User.normalize_email(data.get("email") if isinstance(data.get("email"), str) else "")
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    if not email or not password:
        raise ValidationError("Email and password are required.", details={"fields": {
            **({"email": "This field is required."} if not email else {}),
            **({"password": "This field is required."} if not password else {}),
        }})

    throttle_key = (_client_ip(), email)
    wait = login_throttle.retry_after(throttle_key)
    if wait:
        raise APIError(f"Too many failed sign-in attempts. Try again in {wait // 60 + 1} minute(s).",
                       429, "too_many_attempts", {"retry_after_seconds": wait})

    user = db.session.scalar(db.select(User).filter_by(email=email))
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        login_throttle.fail(throttle_key)
        raise APIError("Invalid email or password.", 401, "invalid_credentials")
    if not user.check_password(password):
        login_throttle.fail(throttle_key)
        audit.record("auth.login_failed", "user", user.id, actor=user)
        db.session.commit()
        raise APIError("Invalid email or password.", 401, "invalid_credentials")

    # Correct password: now it is safe to explain why access is refused.
    problem = user.access_problem(accounts.verification_required())
    if problem:
        code, message = problem
        raise APIError(message, 403, code, {"email": user.email} if code == "email_unverified" else None)

    login_throttle.reset(throttle_key)
    user.last_login_at = utcnow()
    audit.record("auth.login", "user", user.id, actor=user)
    db.session.commit()

    expires = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    return success({
        "access_token": issue_access_token(user),
        "token_type": "Bearer",
        "expires_in": int(expires.total_seconds()),
        **_session_payload(user),
    })


@bp.get("/me")
@login_required
def me():
    return success(_session_payload(current_user))


@bp.patch("/me")
@login_required
def update_me():
    """Update the caller's own editable profile fields. Email, role and
    approval status are never editable here."""
    user = current_user._get_current_object()
    data = json_body()
    forbidden = {"email", "role", "approval_status", "is_active", "student_code",
                 "employee_id", "password"} & set(data)
    if forbidden:
        raise APIError("These fields can only be changed by the hostel office: "
                       + ", ".join(sorted(forbidden)) + ".", 403, "forbidden_fields")
    v = Validator(data, partial=True)
    v.string("full_name", min_length=2, max_length=120)
    v.phone("phone", required=False)
    if user.role == Role.STUDENT:
        v.string("address", required=False, max_length=255)
        v.string("emergency_contact_name", min_length=2, max_length=120)
        v.phone("emergency_contact_phone")
        v.string("emergency_contact_relation", required=False, max_length=50)
    v.raise_if_errors()
    changes = {}
    for field, value in v.clean.items():
        target = user if field in ("full_name", "phone") else user.student_profile
        if target is None:
            continue
        if getattr(target, field) != value:
            changes[field] = {"from": getattr(target, field), "to": value}
            setattr(target, field, value)
    if changes:
        audit.record("account.profile_update", "user", user.id, {"changes": changes})
    db.session.commit()
    return success(_session_payload(user), message="Profile updated.")


@bp.post("/logout")
@login_required
def logout():
    _revoke_current_token()
    audit.record("auth.logout", "user", current_user.id)
    db.session.commit()
    return success(None, message="Signed out.")


@bp.post("/logout-all")
@login_required
def logout_all():
    """Sign out every device, including this one."""
    user = current_user._get_current_object()
    accounts.revoke_all_sessions(user)
    _revoke_current_token()
    audit.record("auth.logout_all", "user", user.id)
    db.session.commit()
    return success(None, message="Signed out of all sessions.")


@bp.post("/change-password")
@login_required
def change_password():
    data = json_body()
    v = Validator(data)
    if not isinstance(data.get("current_password"), str) or not data.get("current_password"):
        v.errors["current_password"] = "This field is required."
    _password_pair(v, data, "new_password", "confirm_password")
    v.raise_if_errors()

    user = current_user._get_current_object()
    if not user.check_password(data["current_password"]):
        raise ValidationError("Current password is incorrect.",
                              details={"fields": {"current_password": "Current password is incorrect."}})
    if user.check_password(v.clean["new_password"]):
        raise ValidationError("New password must be different from the current one.",
                              details={"fields": {"new_password": "Choose a different password."}})

    user.set_password(v.clean["new_password"])
    accounts.revoke_all_sessions(user)  # signs out every other session
    _revoke_current_token()
    audit.record("auth.change_password", "user", user.id)
    db.session.commit()
    return success({"access_token": issue_access_token(user)}, message="Password updated.")


# --- self-registration -----------------------------------------------------

def _signup_rate_limit():
    wait = signup_per_ip.check_and_hit(_client_ip())
    if wait:
        _limited(wait)


def _signup_response(user: User, kind: str):
    verification = user.email_verified_at is None
    pending = user.approval_status.value == "pending"
    if verification:
        message = "Account created. Check your email to verify your address."
    elif pending:
        message = "Account created. It will be reviewed by the hostel office."
    else:
        message = "Account created. You can sign in now."
    return success({
        "account_type": kind,
        "email": user.email,
        "verification_required": verification,
        "approval_required": pending,
        "role": user.role.value,
    }, 201, message)


@bp.post("/signup/student")
def signup_student():
    if not current_app.config["STUDENT_SIGNUP_ENABLED"]:
        raise APIError("Student self-registration is closed. Contact the hostel office.",
                       403, "signup_disabled")
    data = json_body()
    v = Validator(data)
    v.string("full_name", min_length=2, max_length=120)
    v.string("student_code", min_length=2, max_length=32)
    v.email("email")
    v.phone("phone")
    v.string("course", max_length=100)
    v.string("department", max_length=100)
    v.integer("academic_year", min_value=1, max_value=6)
    v.string("emergency_contact_name", min_length=2, max_length=120)
    v.phone("emergency_contact_phone")
    v.string("emergency_contact_relation", required=False, max_length=50)
    _password_pair(v, data)
    if data.get("accept_terms") is not True:
        v.errors["accept_terms"] = "You must accept the terms and privacy policy."
    v.raise_if_errors()
    _signup_rate_limit()
    clean = {**v.clean, "student_code": v.clean["student_code"].upper()}
    user = accounts.signup_student(clean)
    db.session.commit()
    return _signup_response(user, "student")


@bp.post("/signup/staff")
def signup_staff():
    data = json_body()
    v = Validator(data)
    v.string("full_name", min_length=2, max_length=120)
    v.email("email")
    v.phone("phone")
    v.string("employee_id", min_length=2, max_length=40)
    v.string("department", max_length=100)
    # What the applicant asks for; the server decides what is granted.
    v.choice("requested_role", ["staff", "warden"])
    v.string("invitation_code", required=False, min_length=10, max_length=100)
    _password_pair(v, data)
    if data.get("accept_terms") is not True:
        v.errors["accept_terms"] = "You must accept the terms and privacy policy."
    v.raise_if_errors()
    _signup_rate_limit()
    if v.clean.get("invitation_code"):
        wait = token_attempts_per_ip.check_and_hit(_client_ip())
        if wait:
            _limited(wait)
    clean = {**v.clean, "employee_id": v.clean["employee_id"].upper()}
    user, invitation = accounts.signup_staff(clean)
    db.session.commit()
    return _signup_response(user, "staff")


@bp.post("/invitations/validate")
def validate_invitation():
    """Let an invitee confirm their code before filling the form. Returns only
    what the invitation holder already knows (their email and role)."""
    wait = token_attempts_per_ip.check_and_hit(_client_ip())
    if wait:
        _limited(wait)
    data = json_body()
    code = data.get("code") if isinstance(data.get("code"), str) else ""
    inv: StaffInvitation = accounts.find_invitation(code.strip())
    return success({"email": inv.email, "role": inv.role, "expires_at": isoformat(inv.expires_at)})


# --- email verification ----------------------------------------------------

@bp.post("/verify-email")
def verify_email():
    wait = token_attempts_per_ip.check_and_hit(_client_ip())
    if wait:
        _limited(wait)
    data = json_body()
    token = data.get("token") if isinstance(data.get("token"), str) else ""
    if not token:
        raise ValidationError("The verification link is incomplete.",
                              details={"fields": {"token": "Missing token."}})
    user, already = accounts.verify_email(token.strip())
    db.session.commit()
    pending = user.approval_status.value == "pending"
    lead = "Your email address is already verified." if already else "Email verified."
    return success({"approval_required": pending, "role": user.role.value,
                    "already_verified": already},
                   message=lead + (" Your account is waiting for approval."
                                   if pending else " You can sign in now."))


@bp.post("/resend-verification")
def resend_verification():
    data = json_body()
    email = User.normalize_email(data.get("email") if isinstance(data.get("email"), str) else "")
    v = Validator({"email": email})
    v.email("email")
    v.raise_if_errors()
    for limiter, key in ((email_action_per_ip, _client_ip()),
                         (email_action_per_address, (_client_ip(), email))):
        wait = limiter.check_and_hit(key)
        if wait:
            _limited(wait)
    user = db.session.scalar(db.select(User).filter_by(email=email))
    if user is not None and user.email_verified_at is None and user.is_active:
        accounts.send_verification(user)
        audit.record("auth.verification_resent", "user", user.id, actor=user)
        db.session.commit()
    return success(None, message=GENERIC_EMAIL_SENT)


# --- password recovery -----------------------------------------------------

@bp.post("/forgot-password")
def forgot_password():
    data = json_body()
    email = User.normalize_email(data.get("email") if isinstance(data.get("email"), str) else "")
    v = Validator({"email": email})
    v.email("email")
    v.raise_if_errors()
    for limiter, key in ((email_action_per_ip, _client_ip()),
                         (email_action_per_address, (_client_ip(), email))):
        wait = limiter.check_and_hit(key)
        if wait:
            _limited(wait)
    user = db.session.scalar(db.select(User).filter_by(email=email))
    # Deactivated or rejected accounts get no email; the response is identical.
    if user is not None and user.is_active and user.approval_status.value != "rejected":
        accounts.send_password_reset(user)
        audit.record("auth.password_reset_requested", "user", user.id, actor=user)
        db.session.commit()
    return success(None, message=GENERIC_EMAIL_SENT)


@bp.post("/reset-password")
def reset_password():
    wait = token_attempts_per_ip.check_and_hit(_client_ip())
    if wait:
        _limited(wait)
    data = json_body()
    v = Validator(data)
    if not isinstance(data.get("token"), str) or not data.get("token"):
        v.errors["token"] = "The reset link is incomplete."
    _password_pair(v, data)
    v.raise_if_errors()
    accounts.reset_password(data["token"].strip(), v.clean["password"])
    db.session.commit()
    return success(None, message="Your password has been reset. You can sign in now.")
