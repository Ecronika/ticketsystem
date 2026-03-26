"""
Route utilities module.

Shared helpers used across route sub-modules.
"""
from datetime import datetime, timezone

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

    current_app.logger.exception(
        "Database error during %s", operation_name)

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
