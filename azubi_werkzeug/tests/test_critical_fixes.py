# pylint: disable=line-too-long,wrong-import-order,too-many-lines,unnecessary-pass,too-many-locals,broad-exception-caught,import-outside-toplevel,mixed-line-endings,unused-import
"""
Tests for critical bug fixes.
"""
from extensions import db
from models import CheckType
from services import CheckService
from pdf_utils import parse_check_type


def test_check_type_normalization(test_app):
    """Test C4: CheckType normalization"""
    with test_app.app_context():
        assert parse_check_type(CheckType.ISSUE) == CheckType.ISSUE
        assert parse_check_type('issue') == CheckType.ISSUE
        assert parse_check_type('IsSuE') == CheckType.ISSUE
        assert parse_check_type('return') == CheckType.RETURN
        assert parse_check_type('unknown_type') == CheckType.CHECK
        assert parse_check_type(None) == CheckType.CHECK


# Cache tests removed as In-Memory cache was intentionally removed in v2.10.2


# Global Cache invalidation test removed along with the cache in v2.10.2


# ---------------------------------------------------------------------------
# B-01 regression: migration expiry check must use datetime, not Unix float
# ---------------------------------------------------------------------------

def test_is_migration_active_expired(test_app):
    """is_migration_active() returns False when the timestamp has elapsed."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    from routes.utils import is_migration_active  # noqa: PLC0415

    with test_app.test_request_context():
        from flask import session  # noqa: PLC0415
        # Timestamp one hour in the past
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        session['migration_mode'] = True
        session['migration_mode_expires'] = past
        assert not is_migration_active(), (
            "is_migration_active() should return False for an expired timestamp")


def test_is_migration_active_valid(test_app):
    """is_migration_active() returns True when the timestamp is in the future."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    from routes.utils import is_migration_active  # noqa: PLC0415

    with test_app.test_request_context():
        from flask import session  # noqa: PLC0415
        future = (datetime.now(timezone.utc) + timedelta(hours=7)).isoformat()
        session['migration_mode'] = True
        session['migration_mode_expires'] = future
        assert is_migration_active(), (
            "is_migration_active() should return True for a future timestamp")


def test_is_migration_active_malformed(test_app):
    """is_migration_active() returns False for a malformed expiry string."""
    from routes.utils import is_migration_active  # noqa: PLC0415

    with test_app.test_request_context():
        from flask import session  # noqa: PLC0415
        session['migration_mode'] = True
        session['migration_mode_expires'] = 'not-a-date'
        assert not is_migration_active(), (
            "is_migration_active() should return False for a malformed timestamp")


def test_is_migration_active_missing(test_app):
    """is_migration_active() returns False when the flag is not set at all."""
    from routes.utils import is_migration_active  # noqa: PLC0415

    with test_app.test_request_context():
        from flask import session  # noqa: PLC0415
        session.clear()
        assert not is_migration_active(), (
            "is_migration_active() should return False when flag is absent")
