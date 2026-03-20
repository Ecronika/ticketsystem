"""
Routes package.

Splits the monolithic routes.py into logical sub-modules while
keeping a single 'main' Blueprint to avoid template changes.
"""
from flask import Blueprint

main_bp = Blueprint('main', __name__)


# pylint: disable=wrong-import-position
from .auth import register_routes as register_auth  # noqa: E402
from .tickets import register_routes as register_tickets  # noqa: E402
from .dashboard import register_routes as register_dashboard  # noqa: E402

# pylint: enable=wrong-import-position

register_tickets(main_bp)
register_auth(main_bp)
register_dashboard(main_bp)

