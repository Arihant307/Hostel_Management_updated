"""Request parsing and declarative field validation.

Usage:
    v = Validator(json_body())
    v.string("full_name", max_length=120)
    v.email("email")
    v.raise_if_errors()
    data = v.clean
"""
from datetime import date

from flask import current_app, has_request_context, request

from .errors import ValidationError
from .validators import is_valid_email, is_valid_phone, password_problems

_MISSING = object()


def client_ip() -> str | None:
    """The caller's IP address, used for rate limiting and the audit log.

    Behind a hosting proxy (Render) every request arrives from the proxy's own
    address, so `request.remote_addr` would put all users in one bucket. When
    CLIENT_IP_HEADER is configured (Render: True-Client-IP), that header is
    used instead. Locally it is unset and remote_addr is used.
    """
    if not has_request_context():
        return None
    header = current_app.config.get("CLIENT_IP_HEADER")
    if header:
        value = (request.headers.get(header) or "").split(",")[0].strip()
        if value:
            return value[:45]
    return (request.remote_addr or "")[:45] or None


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    return data


class Validator:
    def __init__(self, data: dict, partial: bool = False):
        self.data = data
        # partial=True (PATCH): absent fields are skipped instead of "required".
        self.partial = partial
        self.errors: dict[str, str] = {}
        self.clean: dict = {}

    # -- internals ---------------------------------------------------------
    def _get(self, field, required):
        value = self.data.get(field, _MISSING)
        if isinstance(value, str):
            value = value.strip()
        if value is _MISSING or value is None or value == "":
            if required and not (self.partial and value is _MISSING):
                self.errors[field] = "This field is required."
            elif not (self.partial and value is _MISSING):
                self.clean[field] = None
            return _MISSING
        return value

    # -- field types -------------------------------------------------------
    def string(self, field, required=True, min_length=1, max_length=255):
        value = self._get(field, required)
        if value is _MISSING:
            return
        if not isinstance(value, str):
            self.errors[field] = "Must be text."
        elif len(value) < min_length:
            self.errors[field] = f"Must be at least {min_length} characters."
        elif len(value) > max_length:
            self.errors[field] = f"Must be at most {max_length} characters."
        else:
            self.clean[field] = value

    def email(self, field="email", required=True):
        value = self._get(field, required)
        if value is _MISSING:
            return
        value = str(value).lower()
        if not is_valid_email(value):
            self.errors[field] = "Enter a valid email address."
        else:
            self.clean[field] = value

    def phone(self, field, required=True):
        value = self._get(field, required)
        if value is _MISSING:
            return
        if not isinstance(value, str) or not is_valid_phone(value):
            self.errors[field] = "Enter a valid phone number (digits, optional +, spaces or dashes)."
        else:
            self.clean[field] = value

    def password(self, field="password", required=True):
        value = self.data.get(field)
        if value is None or value == "":
            if required:
                self.errors[field] = "This field is required."
            return
        if not isinstance(value, str):
            self.errors[field] = "Must be text."
            return
        problems = password_problems(value)
        if problems:
            self.errors[field] = "Password " + "; ".join(problems) + "."
        else:
            self.clean[field] = value  # never stripped: spaces are significant

    def choice(self, field, choices, required=True):
        value = self._get(field, required)
        if value is _MISSING:
            return
        allowed = [getattr(c, "value", c) for c in choices]
        if value not in allowed:
            self.errors[field] = f"Must be one of: {', '.join(allowed)}."
        else:
            self.clean[field] = value

    def boolean(self, field, required=True):
        value = self.data.get(field, _MISSING)
        if value is _MISSING:
            if required and not self.partial:
                self.errors[field] = "This field is required."
            return
        if not isinstance(value, bool):
            self.errors[field] = "Must be true or false."
        else:
            self.clean[field] = value

    def integer(self, field, required=True, min_value=None, max_value=None):
        value = self._get(field, required)
        if value is _MISSING:
            return
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            self.errors[field] = "Must be a whole number."
            return
        try:
            value = int(value)
        except ValueError:
            self.errors[field] = "Must be a whole number."
            return
        if min_value is not None and value < min_value:
            self.errors[field] = f"Must be at least {min_value}."
        elif max_value is not None and value > max_value:
            self.errors[field] = f"Must be at most {max_value}."
        else:
            self.clean[field] = value

    def date(self, field, required=True):
        value = self._get(field, required)
        if value is _MISSING:
            return
        try:
            self.clean[field] = date.fromisoformat(str(value))
        except ValueError:
            self.errors[field] = "Must be a date in YYYY-MM-DD format."

    def raise_if_errors(self):
        if self.errors:
            raise ValidationError("Please correct the highlighted fields.",
                                  details={"fields": self.errors})
