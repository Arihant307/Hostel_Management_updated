"""Shared model building blocks."""
import enum

from sqlalchemy import Enum as SAEnum

from ..extensions import db
from ..utils.time import utcnow


class StrEnum(str, enum.Enum):
    """String enum whose members compare equal to their stored values."""

    def __str__(self) -> str:
        return self.value

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


def enum_column(enum_cls: type[StrEnum], name: str):
    """Portable enum column: stored as VARCHAR + CHECK constraint (works on
    SQLite and PostgreSQL), persisting the enum *value* rather than its name."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=max(len(v) for v in enum_cls.values()),
        values_callable=lambda cls: [member.value for member in cls],
    )


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
