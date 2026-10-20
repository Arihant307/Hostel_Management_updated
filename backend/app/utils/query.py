"""Helpers for reading list-endpoint query parameters safely."""
from datetime import date

from flask import request
from flask_jwt_extended import current_user

from ..models import Role
from .errors import ForbiddenError, ValidationError


def arg_str(name: str, max_length: int = 100) -> str | None:
    value = (request.args.get(name) or "").strip()
    return value[:max_length] or None


def arg_choice(name: str, choices) -> str | None:
    value = arg_str(name)
    allowed = [getattr(c, "value", c) for c in choices]
    if value is None:
        return None
    if value not in allowed:
        raise ValidationError(f"Invalid '{name}' filter. Use one of: {', '.join(allowed)}.")
    return value


def arg_int(name: str) -> int | None:
    value = arg_str(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValidationError(f"'{name}' must be a whole number.")


def arg_date(name: str) -> date | None:
    value = arg_str(name)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"'{name}' must be a date in YYYY-MM-DD format.")


def arg_bool(name: str) -> bool | None:
    value = arg_str(name)
    if value is None:
        return None
    if value.lower() in ("1", "true", "yes"):
        return True
    if value.lower() in ("0", "false", "no"):
        return False
    raise ValidationError(f"'{name}' must be true or false.")


def apply_sort(stmt, columns: dict, default: str, default_order: str = "asc", tiebreak=None):
    """Order by ?sort=<key>&order=asc|desc using a whitelist of columns."""
    key = request.args.get("sort") if request.args.get("sort") in columns else default
    order = request.args.get("order") or default_order
    column = columns[key]
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
    return stmt.order_by(tiebreak) if tiebreak is not None else stmt


def deny_limited_staff(area: str = "financial records") -> None:
    """The general "staff" role has no access to finance (enforced server-side)."""
    if current_user.role == Role.STAFF:
        raise ForbiddenError(f"Your role does not have access to {area}.")


def is_student() -> bool:
    return current_user.role == Role.STUDENT


def current_student_profile():
    """The signed-in student's profile (403 for accounts without one)."""
    profile = current_user.student_profile
    if profile is None:
        raise ForbiddenError("This action is only available to students.")
    return profile
