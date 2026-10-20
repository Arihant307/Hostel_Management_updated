"""Append-only audit trail of important administrative actions."""
from ..extensions import db
from ..utils.time import isoformat, utcnow


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    # Nullable so logs survive if the acting user is ever removed.
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(64), nullable=False, index=True)  # e.g. "room.create"
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer)
    # Small structured context. Never put passwords, tokens or hashes here.
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    actor = db.relationship("User")

    __table_args__ = (
        db.Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "actor": {"id": self.actor.id, "full_name": self.actor.full_name,
                      "role": self.actor.role.value} if self.actor else None,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details or {},
            "ip_address": self.ip_address,
            "created_at": isoformat(self.created_at),
        }
