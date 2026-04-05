"""Route utilities module.

Shared helpers used across route sub-modules.
"""

from flask import current_app, flash, redirect, url_for
from werkzeug.wrappers import Response as WerkzeugResponse

from extensions import Config, db


def handle_db_error(
    error: Exception,
    operation_name: str,
    redirect_route: str = "main.index",
    custom_message: str | None = None,
) -> WerkzeugResponse:
    """Centralised database error handling with logging and user feedback.

    Args:
        error: The SQLAlchemy exception.
        operation_name: Description of the operation (for logging).
        redirect_route: Route to redirect to after the error.
        custom_message: Optional custom error message for the user.

    Returns:
        A redirect response to *redirect_route*.
    """
    db.session.rollback()
    current_app.logger.exception("Database error during %s", operation_name)

    if custom_message:
        flash(custom_message, "danger")
    else:
        flash(
            "Ein Datenbankfehler ist aufgetreten. "
            "Bitte versuchen Sie es später erneut.",
            "danger",
        )

    return redirect(url_for(redirect_route))


def get_data_dir() -> str:
    """Return the application data directory path."""
    return Config.get_data_dir()
