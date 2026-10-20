"""Notice board announcements."""
from sqlalchemy import CheckConstraint, and_, or_

from ..extensions import db
from ..utils.time import isoformat, utcnow
from .base import TimestampMixin, enum_column
from .enums import NoticeAudience, NoticeCategory


class Notice(TimestampMixin, db.Model):
    __tablename__ = "notices"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = db.Column(enum_column(NoticeCategory, "notice_category"),
                         nullable=False, default=NoticeCategory.GENERAL, index=True)
    audience = db.Column(enum_column(NoticeAudience, "notice_audience"),
                         nullable=False, default=NoticeAudience.ALL)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    # A future publish_at schedules the notice; it is hidden until then.
    publish_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    expires_at = db.Column(db.DateTime, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    created_by = db.relationship("User")

    __table_args__ = (
        CheckConstraint("expires_at IS NULL OR expires_at > publish_at",
                        name="expiry_after_publish"),
    )

    @classmethod
    def active_filter(cls, now=None):
        """SQL filter for notices that are currently visible."""
        now = now or utcnow()
        return and_(cls.publish_at <= now,
                    or_(cls.expires_at.is_(None), cls.expires_at > now))

    @property
    def is_active(self) -> bool:
        now = utcnow()
        return self.publish_at <= now and (self.expires_at is None or self.expires_at > now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "category": self.category.value,
            "audience": self.audience.value,
            "is_pinned": self.is_pinned,
            "is_active": self.is_active,
            "publish_at": isoformat(self.publish_at),
            "expires_at": isoformat(self.expires_at),
            "created_by": self.created_by.full_name if self.created_by else None,
            "created_at": isoformat(self.created_at),
        }
