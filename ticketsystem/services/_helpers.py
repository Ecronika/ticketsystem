"""Service-layer helper utilities."""

import functools
import os
import shutil
import time

from flask import current_app, flash as _flask_flash, jsonify
from sqlalchemy.exc import SQLAlchemyError

from exceptions import DomainError
from extensions import db


# ---------------------------------------------------------------------------
# Database / API decorators
# ---------------------------------------------------------------------------

def db_transaction(func):
    """Decorator: rollback + log + reraise on database errors.

    Wraps a service method so that any ``SQLAlchemyError`` triggers an
    automatic ``db.session.rollback()``, logs the error, and re-raises.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError as exc:
            db.session.rollback()
            current_app.logger.error(
                "Database error in %s: %s", func.__qualname__, exc,
            )
            raise
    return wrapper


def api_ok(**extra):
    """Return a JSON success response."""
    return jsonify({"success": True, **extra})


def api_error(msg: str, status: int = 500, *, errors: list | None = None):
    """Return a JSON error response with the given *status* code.

    If *errors* is provided, it is included as an ``errors`` array in the
    payload to support structured field-level error rendering on the client.
    """
    payload: dict = {"success": False, "error": msg}
    if errors:
        payload["errors"] = errors
    return jsonify(payload), status


def api_endpoint(func):
    """Decorator: catch domain / validation / DB errors for API routes.

    Maps ``DomainError`` to its ``status_code`` with the curated
    ``user_message`` in the response, ``ValueError`` to 400 with a generic
    message (the raw exception string is logged server-side only to avoid
    leaking internals), and ``SQLAlchemyError`` to 500.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DomainError as exc:
            # exc.user_message is curated per DomainError's contract (see
            # exceptions.py) and is safe to return to the client.
            msg = exc.user_message
            current_app.logger.info(
                "Domain error in %s: %s", func.__name__, msg,
            )
            field = getattr(exc, 'field', None)
            errors = [{"field": field, "message": msg}] if field else None
            return api_error(msg, exc.status_code, errors=errors)
        except ValueError:
            # Do not expose the raw ValueError message — it may carry
            # internal detail. Log server-side, return a generic hint.
            current_app.logger.info(
                "Validation error in %s", func.__name__, exc_info=True,
            )
            return api_error("Ungültige Eingabe.", 400)
        except SQLAlchemyError:
            current_app.logger.exception(
                "API error in %s", func.__name__,
            )
            return api_error("Ein interner Fehler ist aufgetreten.")
    return wrapper


def _remove_with_retry(path: str, retries: int = 3, delay: float = 0.5) -> bool:
    """Remove a file or directory with retries for locked resources.

    Args:
        path: Filesystem path to remove.
        retries: Maximum number of attempts.
        delay: Seconds to wait between retries.

    Returns:
        ``True`` on success.

    Raises:
        OSError: If removal fails after all retries.
    """
    for attempt in range(retries):
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            return True
        except OSError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
    return False


# ---------------------------------------------------------------------------
# Flash helpers
# ---------------------------------------------------------------------------

def flash_with_undo(message: str, undo_url: str, undo_label: str = "Rückgängig",
                    category: str = "success") -> None:
    """Flash a message accompanied by an inline undo-action button.

    The payload is a dict; ``base.html`` detects the mapping shape and renders
    the undo button with data-attributes that ``base_ui.js`` handles.
    """
    _flask_flash(
        {"message": message, "undo_url": undo_url, "undo_label": undo_label},
        category,
    )
