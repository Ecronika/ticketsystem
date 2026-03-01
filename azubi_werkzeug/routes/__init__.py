"""
Routes package.

Splits the monolithic routes.py into logical sub-modules while
keeping a single 'main' Blueprint to avoid template changes.
"""
from flask import Blueprint

main_bp = Blueprint('main', __name__)

# Import registration functions AFTER Blueprint is created
# to prevent circular imports between __init__ and sub-modules.
# pylint: disable=wrong-import-position
from .dashboard import register_routes as register_dashboard  # noqa: E402
from .checks import register_routes as register_checks  # noqa: E402
from .admin import register_routes as register_admin  # noqa: E402
from .api import register_routes as register_api  # noqa: E402
from .auth import register_routes as register_auth  # noqa: E402
# pylint: enable=wrong-import-position

register_dashboard(main_bp)
register_checks(main_bp)
register_admin(main_bp)
register_api(main_bp)
register_auth(main_bp)
