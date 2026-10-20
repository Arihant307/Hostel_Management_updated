"""Rooms and room allocations (the allocation table is the history)."""
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, func, select, text
from sqlalchemy.orm import column_property

from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, enum_column
from .enums import AllocationStatus, RoomType


class RoomAllocation(TimestampMixin, db.Model):
    """One stay of one student in one room.

    Rules:
    * A student has at most ONE allocation with status ACTIVE — enforced by a
      partial unique index, so it holds even if application code is bypassed.
    * Closed allocations are never deleted; they are the allocation history.
    * A transfer closes the old allocation (status TRANSFERRED, checked_out_on
      set) and opens a new one whose previous_allocation_id points back.
    * Room occupancy is COUNT(active allocations); it is never stored.
    """

    __tablename__ = "room_allocations"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    room_id = db.Column(
        db.Integer, db.ForeignKey("rooms.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    status = db.Column(
        enum_column(AllocationStatus, "allocation_status"),
        nullable=False, default=AllocationStatus.ACTIVE, index=True,
    )
    allocated_on = db.Column(db.Date, nullable=False)
    expected_checkout_on = db.Column(db.Date)
    checked_out_on = db.Column(db.Date)
    previous_allocation_id = db.Column(
        db.Integer, db.ForeignKey("room_allocations.id", ondelete="SET NULL")
    )
    allocated_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    closed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    notes = db.Column(db.String(500))

    student = db.relationship("StudentProfile", back_populates="allocations",
                              foreign_keys=[student_id])
    room = db.relationship("Room", back_populates="allocations")
    previous_allocation = db.relationship("RoomAllocation", remote_side=[id])
    allocated_by = db.relationship("User", foreign_keys=[allocated_by_id])
    closed_by = db.relationship("User", foreign_keys=[closed_by_id])

    __table_args__ = (
        Index(
            "uq_room_allocations_one_active_per_student", "student_id", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint(
            "(status = 'active' AND checked_out_on IS NULL) OR "
            "(status != 'active' AND checked_out_on IS NOT NULL)",
            name="checkout_matches_status",
        ),
        CheckConstraint(
            "checked_out_on IS NULL OR checked_out_on >= allocated_on",
            name="checkout_after_allocation",
        ),
        CheckConstraint(
            "expected_checkout_on IS NULL OR expected_checkout_on >= allocated_on",
            name="expected_checkout_after_allocation",
        ),
    )

    def to_dict(self, include_student: bool = True, include_room: bool = True) -> dict:
        data = {
            "id": self.id,
            "student_id": self.student_id,
            "room_id": self.room_id,
            "status": self.status.value,
            "allocated_on": isoformat(self.allocated_on),
            "expected_checkout_on": isoformat(self.expected_checkout_on),
            "checked_out_on": isoformat(self.checked_out_on),
            "previous_allocation_id": self.previous_allocation_id,
            "notes": self.notes,
            "created_at": isoformat(self.created_at),
        }
        if include_room and self.room is not None:
            data["room"] = self.room.to_summary()
        if include_student and self.student is not None:
            data["student"] = {
                "id": self.student.id,
                "student_code": self.student.student_code,
                "full_name": self.student.user.full_name if self.student.user else None,
            }
        return data

    def __repr__(self) -> str:
        return f"<RoomAllocation {self.id} student={self.student_id} room={self.room_id} {self.status}>"


class Room(TimestampMixin, db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    block = db.Column(db.String(50), nullable=False, index=True)
    room_number = db.Column(db.String(20), nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    room_type = db.Column(enum_column(RoomType, "room_type"), nullable=False, index=True)
    capacity = db.Column(db.Integer, nullable=False)
    # Money is stored as integer minor units (paise for INR) to avoid float errors.
    monthly_fee_minor = db.Column(db.Integer, nullable=False)
    amenities = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    allocations = db.relationship("RoomAllocation", back_populates="room")

    # Derived, query-able occupancy: number of ACTIVE allocations.
    occupied_beds = column_property(
        select(func.count(RoomAllocation.id))
        .where(RoomAllocation.room_id == id,
               RoomAllocation.status == AllocationStatus.ACTIVE)
        .correlate_except(RoomAllocation)
        .scalar_subquery(),
        deferred=False,
    )

    __table_args__ = (
        UniqueConstraint("block", "room_number", name="uq_rooms_block_room_number"),
        CheckConstraint("capacity BETWEEN 1 AND 20", name="capacity_range"),
        CheckConstraint("monthly_fee_minor >= 0", name="fee_non_negative"),
        CheckConstraint("floor BETWEEN -2 AND 200", name="floor_range"),
    )

    @property
    def available_beds(self) -> int:
        return max(self.capacity - (self.occupied_beds or 0), 0)

    @property
    def occupancy_status(self) -> str:
        if not self.is_active:
            return "inactive"
        occupied = self.occupied_beds or 0
        if occupied == 0:
            return "available"
        if occupied >= self.capacity:
            return "full"
        return "partially_occupied"

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "block": self.block,
            "room_number": self.room_number,
            "floor": self.floor,
            "room_type": self.room_type.value,
            "monthly_fee_minor": self.monthly_fee_minor,
        }

    def to_dict(self) -> dict:
        return {
            **self.to_summary(),
            "capacity": self.capacity,
            "occupied_beds": self.occupied_beds or 0,
            "available_beds": self.available_beds,
            "occupancy_status": self.occupancy_status,
            "amenities": self.amenities,
            "is_active": self.is_active,
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }

    def __repr__(self) -> str:
        return f"<Room {self.block}-{self.room_number}>"
