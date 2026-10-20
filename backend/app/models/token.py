"""Revoked access tokens (logout). Rows can be purged once expires_at passes."""
from ..extensions import db
from ..utils.time import utcnow


class RevokedToken(db.Model):
    __tablename__ = "revoked_tokens"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @classmethod
    def purge_expired(cls) -> int:
        return cls.query.filter(cls.expires_at < utcnow()).delete()
