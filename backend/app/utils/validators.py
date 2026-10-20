"""Reusable input validation helpers."""
import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-]{6,18}[0-9]$")

PASSWORD_MIN_LENGTH = 10


def is_valid_email(value: str) -> bool:
    return bool(value) and len(value) <= 254 and bool(EMAIL_RE.match(value))


def is_valid_phone(value: str) -> bool:
    return bool(value) and bool(PHONE_RE.match(value))


def password_problems(password: str) -> list[str]:
    """Return a list of reasons the password is too weak (empty list = OK)."""
    problems = []
    if len(password or "") < PASSWORD_MIN_LENGTH:
        problems.append(f"must be at least {PASSWORD_MIN_LENGTH} characters long")
    if len(password or "") > 128:
        problems.append("must be at most 128 characters long")
    if not re.search(r"[a-z]", password or ""):
        problems.append("must contain a lowercase letter")
    if not re.search(r"[A-Z]", password or ""):
        problems.append("must contain an uppercase letter")
    if not re.search(r"[0-9]", password or ""):
        problems.append("must contain a digit")
    return problems
