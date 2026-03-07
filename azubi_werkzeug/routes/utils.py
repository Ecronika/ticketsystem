"""
Route utilities module.

Shared helpers used across route sub-modules.
"""
from datetime import datetime, timezone
from flask import current_app, flash, redirect, session, url_for
from extensions import db


def is_migration_active() -> bool:
    """Return True only if migration mode is enabled and has not yet expired.

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
            # Malformed timestamp — clear to be safe
            session.pop('migration_mode', None)
            session.pop('migration_mode_expires', None)
            return False
    return True


def handle_db_error(
        error,
        operation_name,
        redirect_route='main.index',
        custom_message=None):
    """
    Centralized database error handling with logging and user feedback.

    Args:
        error: The SQLAlchemyError exception
        operation_name: Description of the operation (for logging)
        redirect_route: Route to redirect to after error
        custom_message: Optional custom error message for user
    """
    db.session.rollback()

    current_app.logger.error(
        f"Database error during {operation_name}: {str(error)}")

    if custom_message:
        flash(custom_message, 'danger')
    else:
        flash(
            'Ein Datenbankfehler ist aufgetreten. '
            'Bitte versuchen Sie es später erneut.',
            'danger')

    return redirect(url_for(redirect_route))


def get_data_dir():
    """Retrieve data directory from config."""
    from extensions import Config  # pylint: disable=import-outside-toplevel
    return Config.get_data_dir()


def parse_migration_date(form_data, ingress):
    """Parse and validate custom date from migration mode form data.

    Returns:
        tuple: (check_date, error_redirect) — error_redirect is None
               on success.
    """
    c_date = form_data.get('custom_date')
    c_time = form_data.get('custom_time')
    if not c_date:
        return datetime.now(timezone.utc), None
    try:
        time_str = c_time if c_time else "12:00"
        check_date = datetime.strptime(
            f"{c_date} {time_str}", "%Y-%m-%d %H:%M")
        return check_date, None
    except ValueError:
        flash(
            'Fehler: Ungültiges Datumsformat im Migrations-Modus.',
            'error')
        current_app.logger.warning(
            f"Invalid migration date format: {c_date} {c_time}")
        return None, redirect(f"{ingress}{url_for('main.index')}")
