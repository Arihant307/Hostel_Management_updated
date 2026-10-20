"""JWT wiring and role-based access control.

Every protected endpoint uses @login_required or @roles_required(...). A token
is accepted only if:
  * its signature and expiry are valid,
  * its jti is not in the revoked_tokens table (logout),
  * the user still exists, is active, approved and (if required) verified,
  * its "ver" claim equals user.token_version (bumped on password change,
    password reset and deactivation, which invalidates every older token).
"""
from functools import wraps

from flask import current_app
from flask_jwt_extended import (
    create_access_token, current_user, get_jwt, verify_jwt_in_request,
)

from ..extensions import db, jwt
from ..models import RevokedToken, Role, User
from .errors import ForbiddenError, error_response


def issue_access_token(user: User) -> str:
    return create_access_token(
        identity=user,
        additional_claims={"role": user.role.value, "ver": user.token_version},
    )


def roles_required(*roles: Role):
    """Require a valid token and (if roles are given) one of those roles."""
    allowed = {Role(r) for r in roles}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if allowed and current_user.role not in allowed:
                raise ForbiddenError("You do not have permission to perform this action.")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def login_required(fn):
    return roles_required()(fn)


# Admins and wardens: manage students, rooms, allocations, notices, complaints.
staff_required = roles_required(Role.ADMIN, Role.WARDEN)
# Any staff member including the limited "staff" role (read-mostly access).
any_staff_required = roles_required(Role.ADMIN, Role.WARDEN, Role.STAFF)
admin_required = roles_required(Role.ADMIN)


def current_token_claims() -> dict:
    return get_jwt()


@jwt.user_identity_loader
def _identity(user):
    return str(user.id if isinstance(user, User) else user)


@jwt.user_lookup_loader
def _load_user(_jwt_header, jwt_data):
    try:
        user = db.session.get(User, int(jwt_data["sub"]))
    except (TypeError, ValueError):
        return None
    if user is None:
        return None
    if user.access_problem(current_app.config["EMAIL_VERIFICATION_REQUIRED"]):
        return None
    if jwt_data.get("ver") != user.token_version:
        return None
    return user


@jwt.token_in_blocklist_loader
def _is_revoked(_jwt_header, jwt_payload) -> bool:
    return db.session.scalar(
        db.select(RevokedToken.id).filter_by(jti=jwt_payload["jti"])
    ) is not None


@jwt.expired_token_loader
def _expired(_h, _p):
    return error_response("Your session has expired. Please sign in again.", 401, "token_expired")


@jwt.invalid_token_loader
def _invalid(reason):
    return error_response("Invalid authentication token.", 401, "invalid_token")


@jwt.unauthorized_loader
def _missing(reason):
    return error_response("Authentication is required.", 401, "authorization_required")


@jwt.revoked_token_loader
def _revoked(_h, _p):
    return error_response("This session has been signed out. Please sign in again.",
                          401, "token_revoked")


@jwt.user_lookup_error_loader
def _lookup_failed(_h, _p):
    return error_response("Your session is no longer valid. Please sign in again.",
                          401, "session_invalid")
