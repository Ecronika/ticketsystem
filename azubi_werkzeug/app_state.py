"""
App State module.

Manages application-wide state (e.g. Migration Mode) in a request-context
safe way using flask.session.
"""
from datetime import datetime, timezone
from flask import session, current_app


def is_migration_active() -> bool:
    """
    Return True only if migration mode is enabled and has not yet expired.

    Migration mode auto-expires 8 hours after activation.
    Silently clears the session flags when the time has elapsed.
    """
    if not session.get('migration_mode', False):
        return False

    expires_str = session.get('migration_mode_expires')
    if expires_str:
        try:
            expires = datetime.fromisoformat(expires_str)
            if datetime.now(timezone.utc) > expires:
                session.pop('migration_mode', None)
                session.pop('migration_mode_expires', None)
                current_app.logger.info(
                    "Migration mode auto-expired and was cleared.")
                return False
        except (ValueError, TypeError):
            # Malformed timestamp â€” clear to be safe
            session.pop('migration_mode', None)
            session.pop('migration_mode_expires', None)
            return False
    return True
