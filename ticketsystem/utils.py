from datetime import datetime, timezone

def get_utc_now():
    """
    Returns the current UTC time as an unaware datetime object (naive).
    This is the standard timestamp format used across the system.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
