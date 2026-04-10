"""Ticket routes -- thin coordinator.

All route implementations have been split into focused sub-modules:

* ``ticket_views``      -- HTML view endpoints (dashboard, detail, queue, etc.)
* ``ticket_api``        -- JSON API endpoints (status, assign, meta, etc.)
* ``ticket_checklists`` -- checklist API endpoints
* ``ticket_export``     -- CSV exports and bulk actions
* ``ticket_misc``       -- notifications, push, theme, worker names

This module only wires them together via ``register_routes``.
"""

from flask import Blueprint


def register_routes(bp: Blueprint) -> None:
    """Import and register every ticket route sub-module on *bp*."""
    from .ticket_views import register_routes as register_views
    from .ticket_api import register_routes as register_api
    from .ticket_checklists import register_routes as register_checklists
    from .ticket_export import register_routes as register_export
    from .ticket_misc import register_routes as register_misc

    register_views(bp)
    register_api(bp)
    register_checklists(bp)
    register_export(bp)
    register_misc(bp)
