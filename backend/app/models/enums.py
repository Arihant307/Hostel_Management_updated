"""Domain enumerations. Values are what gets stored in the database and
returned by the API, so treat them as part of the public contract."""
from .base import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    WARDEN = "warden"
    STAFF = "staff"       # general hostel staff: limited, read-mostly access
    STUDENT = "student"


class ApprovalStatus(StrEnum):
    """Whether an account may be used. Self-registered accounts start PENDING."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TokenPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


class RoomType(StrEnum):
    SINGLE = "single"
    DOUBLE = "double"
    TRIPLE = "triple"
    DORMITORY = "dormitory"


class AllocationStatus(StrEnum):
    ACTIVE = "active"
    TRANSFERRED = "transferred"   # closed because the student moved to another room
    CHECKED_OUT = "checked_out"   # closed because the student left the hostel


class FeeType(StrEnum):
    HOSTEL_RENT = "hostel_rent"
    MESS = "mess"
    SECURITY_DEPOSIT = "security_deposit"
    FINE = "fine"
    OTHER = "other"


class FeeStatus(StrEnum):
    """Derived — never stored. See FeeRecord.status."""
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    CASH = "cash"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    CHEQUE = "cheque"


class PaymentSource(StrEnum):
    MANUAL = "manual"     # recorded by staff after receiving money offline
    GATEWAY = "gateway"   # online payment; only counts once verified server-side


class PaymentStatus(StrEnum):
    PENDING = "pending"       # gateway payment awaiting server-side verification
    COMPLETED = "completed"   # counts towards the fee balance
    FAILED = "failed"
    REVERSED = "reversed"     # voided / refunded after being completed


class ComplaintCategory(StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CLEANLINESS = "cleanliness"
    FURNITURE = "furniture"
    INTERNET = "internet"
    OTHER = "other"


class ComplaintPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComplaintStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class NoticeCategory(StrEnum):
    GENERAL = "general"
    MAINTENANCE = "maintenance"
    FEES = "fees"
    EVENT = "event"
    EMERGENCY = "emergency"


class NoticeAudience(StrEnum):
    ALL = "all"
    STUDENTS = "students"
    STAFF = "staff"
