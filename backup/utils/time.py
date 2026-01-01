"""UTC time helpers to keep timezone-aware timestamps consistent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware and normalized to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_isoformat(value: Optional[datetime]) -> Optional[str]:
    """Return an ISO8601 UTC string with a trailing Z."""
    if value is None:
        return None
    return ensure_utc(value).isoformat().replace("+00:00", "Z")
