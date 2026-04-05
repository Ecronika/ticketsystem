"""Routes package.

Splits the monolithic routes into logical sub-modules while keeping a
single ``main`` Blueprint to avoid template changes.

The sub-module imports **must** appear after ``main_bp`` is created
because each ``register_routes`` function receives the blueprint instance.
"""

from flask import Blueprint

main_bp: Blueprint = Blueprint("main", __name__)


def _register_all(bp: Blueprint) -> None:
    """Import and register every route sub-module on *bp*."""
    from .auth import register_routes as register_auth  # noqa: E402
    from .dashboard import register_routes as register_dashboard  # noqa: E402
    from .tickets import register_routes as register_tickets  # noqa: E402

    register_tickets(bp)
    register_auth(bp)
    register_dashboard(bp)


_register_all(main_bp)
