"""Time helpers. All timestamps are stored as naive UTC datetimes."""
from datetime import date, datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return utcnow().date()


def isoformat(value):
    """Serialise date/datetime for JSON; datetimes are marked as UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat() + "Z"
    return value.isoformat()
