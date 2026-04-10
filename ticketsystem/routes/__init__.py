"""Routes package.

Splits the monolithic routes into logical sub-modules while keeping a
single ``main`` Blueprint to avoid template changes.

Each sub-module provides a ``register_routes(bp)`` function that binds
its endpoints to the blueprint.
"""

from flask import Blueprint

main_bp: Blueprint = Blueprint("main", __name__)


def _register_all(bp: Blueprint) -> None:
    """Import and register every route sub-module on *bp*."""
    from .auth import register_routes as register_auth
    from .dashboard import register_routes as register_dashboard
    from .ticket_api import register_routes as register_api
    from .ticket_checklists import register_routes as register_checklists
    from .ticket_export import register_routes as register_export
    from .ticket_misc import register_routes as register_misc
    from .ticket_views import register_routes as register_views

    register_auth(bp)
    register_dashboard(bp)
    register_views(bp)
    register_api(bp)
    register_checklists(bp)
    register_export(bp)
    register_misc(bp)


_register_all(main_bp)
