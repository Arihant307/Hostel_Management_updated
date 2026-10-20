"""Complaints / maintenance requests and their comment thread."""
from sqlalchemy import CheckConstraint

from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, enum_column
from .enums import ComplaintCategory, ComplaintPriority, ComplaintStatus


class Complaint(TimestampMixin, db.Model):
    __tablename__ = "complaints"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    # Room at the time of filing (the student may move later).
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="SET NULL"))
    category = db.Column(enum_column(ComplaintCategory, "complaint_category"),
                         nullable=False, index=True)
    priority = db.Column(enum_column(ComplaintPriority, "complaint_priority"),
                         nullable=False, default=ComplaintPriority.MEDIUM)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(enum_column(ComplaintStatus, "complaint_status"),
                       nullable=False, default=ComplaintStatus.OPEN, index=True)
    # Maintenance staff are usually not system users, so this is a name.
    assigned_to = db.Column(db.String(120))
    # Visible to the student once the complaint is resolved or rejected.
    resolution = db.Column(db.Text)
    resolved_at = db.Column(db.DateTime)
    handled_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    student = db.relationship("StudentProfile", back_populates="complaints")
    room = db.relationship("Room")
    handled_by = db.relationship("User")
    comments = db.relationship("ComplaintComment", back_populates="complaint",
                               cascade="all, delete-orphan",
                               order_by="ComplaintComment.created_at")

    __table_args__ = (
        CheckConstraint(
            "(status IN ('resolved', 'rejected')) = (resolved_at IS NOT NULL)",
            name="resolved_at_matches_status",
        ),
    )

    def to_dict(self, include_internal: bool = False) -> dict:
        comments = [c for c in self.comments if include_internal or not c.is_internal]
        return {
            "id": self.id,
            "student_id": self.student_id,
            "student": {
                "student_code": self.student.student_code,
                "full_name": self.student.user.full_name if self.student.user else None,
            } if self.student else None,
            "room": self.room.to_summary() if self.room else None,
            "category": self.category.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "resolution": self.resolution,
            "resolved_at": isoformat(self.resolved_at),
            "comments": [c.to_dict() for c in comments],
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }


class ComplaintComment(TimestampMixin, db.Model):
    """A response visible to the student, or an internal staff-only note."""

    __tablename__ = "complaint_comments"

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(
        db.Integer, db.ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    body = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, nullable=False, default=False)

    complaint = db.relationship("Complaint", back_populates="comments")
    author = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "body": self.body,
            "is_internal": self.is_internal,
            "author": {"full_name": self.author.full_name, "role": self.author.role.value}
            if self.author else None,
            "created_at": isoformat(self.created_at),
        }
