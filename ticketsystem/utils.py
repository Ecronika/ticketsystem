"""Utility functions shared across the application."""

from datetime import datetime, timezone


def get_utc_now() -> datetime:
    """Return the current UTC time as a naive (timezone-unaware) datetime.

    This is the standard timestamp format used across the system because
    SQLite stores datetimes as text without timezone information.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
