"""
Route utilities module.

Shared helpers used across route sub-modules.
"""
from flask import current_app, flash, redirect, url_for
from extensions import db


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
    from datetime import datetime  # pylint: disable=import-outside-toplevel

    c_date = form_data.get('custom_date')
    c_time = form_data.get('custom_time')
    if not c_date:
        return datetime.now(), None
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
