"""One-time account tokens (email verification, password reset) and staff invitations.

Security rules shared by every token here:
* The raw token is sent to the user once (by email / shown to the admin once)
  and NEVER stored. Only its SHA-256 hash is saved, so a database leak does not
  expose usable tokens.
* Every token expires and can be used once (used_at / revoked_at).
"""
import hashlib
import secrets

from sqlalchemy import CheckConstraint

from ..extensions import db
from ..utils.time import isoformat, utcnow
from .base import enum_column
from .enums import TokenPurpose


def new_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


class AccountToken(db.Model):
    __tablename__ = "account_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    purpose = db.Column(enum_column(TokenPurpose, "token_purpose"), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")

    __table_args__ = (
        db.Index("ix_account_tokens_user_purpose", "user_id", "purpose"),
    )

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.expires_at > utcnow()


class StaffInvitation(db.Model):
    """Admin-issued, single-use invitation that lets one email address register
    as staff with a role chosen by the admin (never admin)."""

    __tablename__ = "staff_invitations"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    note = db.Column(db.String(255))
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    used_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    revoked_at = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    used_by = db.relationship("User", foreign_keys=[used_by_id])

    __table_args__ = (
        # Invitations can never grant admin.
        CheckConstraint("role IN ('staff', 'warden')", name="role_allowed"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    @property
    def status(self) -> str:
        if self.revoked_at:
            return "revoked"
        if self.used_at:
            return "used"
        if self.expires_at <= utcnow():
            return "expired"
        return "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "note": self.note,
            "status": self.status,
            "expires_at": isoformat(self.expires_at),
            "used_at": isoformat(self.used_at),
            "used_by": self.used_by.full_name if self.used_by else None,
            "revoked_at": isoformat(self.revoked_at),
            "created_by": self.created_by.full_name if self.created_by else None,
            "created_at": isoformat(self.created_at),
        }
