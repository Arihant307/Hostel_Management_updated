"""Audit logging. Entries join the caller's transaction, so an action and its
log entry are committed (or rolled back) together."""
from flask import has_request_context
from flask_jwt_extended import current_user

from ..extensions import db
from ..models import AuditLog
from ..utils.request import client_ip

_SENSITIVE_KEYS = {"password", "new_password", "current_password", "password_hash", "token"}


def _client_ip() -> str | None:
    return client_ip()


def record(action: str, entity_type: str, entity_id: int | None = None,
           details: dict | None = None, actor=None) -> AuditLog:
    if actor is None and has_request_context():
        try:
            actor = current_user._get_current_object()
        except Exception:  # no verified JWT in this request
            actor = None
    clean = {k: v for k, v in (details or {}).items() if k not in _SENSITIVE_KEYS}
    entry = AuditLog(actor_id=getattr(actor, "id", None), action=action,
                     entity_type=entity_type, entity_id=entity_id,
                     details=clean or None, ip_address=_client_ip())
    db.session.add(entry)
    return entry
