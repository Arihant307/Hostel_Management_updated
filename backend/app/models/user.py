"""User accounts (admins, wardens, staff and students), student and staff profiles."""
from sqlalchemy import CheckConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, enum_column
from .enums import AllocationStatus, ApprovalStatus, Role

PASSWORD_HASH_METHOD = "scrypt"


class User(TimestampMixin, db.Model):
    """Login identity. Name, email and phone live here (not on StudentProfile)
    so they are stored once for every role."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    role = db.Column(enum_column(Role, "user_role"), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)
    # Bumped on password change / deactivation to invalidate issued tokens.
    token_version = db.Column(db.Integer, nullable=False, default=0)

    # --- account lifecycle -------------------------------------------------
    # NULL = email address not yet verified. Accounts created by staff or the
    # CLI are trusted and marked verified when created.
    email_verified_at = db.Column(db.DateTime)
    # Self-registered accounts start PENDING until staff approve them.
    approval_status = db.Column(enum_column(ApprovalStatus, "approval_status"), nullable=False,
                                default=ApprovalStatus.APPROVED, server_default="approved",
                                index=True)
    approval_note = db.Column(db.String(255))      # e.g. rejection reason
    reviewed_at = db.Column(db.DateTime)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    # How the account was created: cli | admin | staff | signup | invitation
    created_via = db.Column(db.String(20))

    student_profile = db.relationship(
        "StudentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    staff_profile = db.relationship(
        "StaffProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    reviewed_by = db.relationship("User", remote_side="User.id", foreign_keys=[reviewed_by_id])

    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    # --- password handling -------------------------------------------------
    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password, method=PASSWORD_HASH_METHOD)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    @staticmethod
    def normalize_email(email: str) -> str:
        return (email or "").strip().lower()

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.ADMIN, Role.WARDEN, Role.STAFF)

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def access_problem(self, verification_required: bool) -> tuple[str, str] | None:
        """Why this account may not sign in, as (code, message), or None if it may.

        Checked at login and on every authenticated request."""
        if not self.is_active:
            return ("account_disabled",
                    "This account has been deactivated. Contact the hostel office.")
        if self.approval_status == ApprovalStatus.REJECTED:
            return ("account_rejected",
                    "This registration was not approved. Contact the hostel office.")
        if verification_required and not self.is_email_verified:
            return ("email_unverified",
                    "Please verify your email address before signing in.")
        if self.approval_status == ApprovalStatus.PENDING:
            return ("account_pending",
                    "Your account is waiting for approval by the hostel office.")
        return None

    def to_dict(self) -> dict:
        # password_hash and token_version are deliberately never serialised.
        data = {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "phone": self.phone,
            "role": self.role.value,
            "is_active": self.is_active,
            "email_verified": self.is_email_verified,
            "email_verified_at": isoformat(self.email_verified_at),
            "approval_status": self.approval_status.value if self.approval_status else None,
            "approval_note": self.approval_note,
            "reviewed_at": isoformat(self.reviewed_at),
            "created_via": self.created_via,
            "last_login_at": isoformat(self.last_login_at),
            "created_at": isoformat(self.created_at),
        }
        if self.staff_profile is not None:
            data["staff_profile"] = self.staff_profile.to_dict()
        return data

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email} ({self.role})>"


class StudentProfile(TimestampMixin, db.Model):
    """Student-specific data. Account status is User.is_active; the current
    room is derived from the student's single ACTIVE RoomAllocation."""

    __tablename__ = "student_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    student_code = db.Column(db.String(32), nullable=False, unique=True, index=True)
    course = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False, index=True)
    academic_year = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    address = db.Column(db.String(255))
    emergency_contact_name = db.Column(db.String(120), nullable=False)
    emergency_contact_phone = db.Column(db.String(20), nullable=False)
    emergency_contact_relation = db.Column(db.String(50))
    registration_date = db.Column(db.Date, nullable=False)

    user = db.relationship("User", back_populates="student_profile")
    allocations = db.relationship(
        "RoomAllocation", back_populates="student",
        order_by="[RoomAllocation.allocated_on.desc(), RoomAllocation.id.desc()]",
        foreign_keys="RoomAllocation.student_id",
    )
    fee_records = db.relationship("FeeRecord", back_populates="student")
    complaints = db.relationship("Complaint", back_populates="student")

    __table_args__ = (
        CheckConstraint("academic_year BETWEEN 1 AND 6", name="academic_year_range"),
    )

    @property
    def current_allocation(self):
        return next(
            (a for a in self.allocations if a.status == AllocationStatus.ACTIVE), None
        )

    def to_dict(self, include_user: bool = True) -> dict:
        allocation = self.current_allocation
        data = {
            "id": self.id,
            "student_code": self.student_code,
            "course": self.course,
            "department": self.department,
            "academic_year": self.academic_year,
            "gender": self.gender,
            "date_of_birth": isoformat(self.date_of_birth),
            "address": self.address,
            "emergency_contact": {
                "name": self.emergency_contact_name,
                "phone": self.emergency_contact_phone,
                "relation": self.emergency_contact_relation,
            },
            "registration_date": isoformat(self.registration_date),
            "current_allocation": allocation.to_dict(include_student=False) if allocation else None,
        }
        if include_user and self.user is not None:
            data.update({
                "user_id": self.user.id,
                "full_name": self.user.full_name,
                "email": self.user.email,
                "phone": self.user.phone,
                "is_active": self.user.is_active,
                "email_verified": self.user.is_email_verified,
                "approval_status": self.user.approval_status.value if self.user.approval_status else None,
                "approval_note": self.user.approval_note,
                "created_via": self.user.created_via,
            })
        return data

    def __repr__(self) -> str:
        return f"<StudentProfile {self.student_code}>"


class StaffProfile(TimestampMixin, db.Model):
    """Employment details captured when staff self-register or accept an invite."""

    __tablename__ = "staff_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, unique=True)
    employee_id = db.Column(db.String(40), nullable=False, unique=True, index=True)
    department = db.Column(db.String(100), nullable=False)
    # What the applicant asked for. The granted role is User.role, set by an admin.
    requested_role = db.Column(db.String(20), nullable=False)

    user = db.relationship("User", back_populates="staff_profile")

    __table_args__ = (
        CheckConstraint("requested_role IN ('staff', 'warden')", name="requested_role_allowed"),
    )

    def to_dict(self) -> dict:
        return {"employee_id": self.employee_id, "department": self.department,
                "requested_role": self.requested_role}
