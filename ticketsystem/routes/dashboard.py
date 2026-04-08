"""Dashboard routes.

Handles the main dashboard, logo serving, health check, and the
lightweight polling endpoint used by the frontend.
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, Tuple

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    session,
)
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from enums import TicketStatus, WorkerRole
from extensions import Config, db
from models import Team, Ticket
from routes.auth import worker_required
from services.ticket_service import _confidential_filter
from utils import get_utc_now

_dash_start_time: float = time.time()

_ELEVATED_ROLES = frozenset({
    WorkerRole.ADMIN.value,
    WorkerRole.HR.value,
    WorkerRole.MANAGEMENT.value,
})


# ------------------------------------------------------------------
# View functions
# ------------------------------------------------------------------

def _serve_logo() -> Response | tuple[str, int]:
    """Serve the logo from ``DATA_DIR`` with ETag-based caching."""
    data_dir = Config.get_data_dir()
    logo_path = os.path.join(data_dir, "static", "img", "logo.png")

    if not os.path.exists(logo_path):
        current_app.logger.warning("Logo not found at %s", logo_path)
        return "Logo not found", 404

    try:
        return _logo_response(logo_path)
    except OSError:
        current_app.logger.exception("Error reading logo")
        return "Error reading logo", 500


def _health_check() -> tuple[Response, int]:
    """Lightweight healthcheck — returns JSON with DB status."""
    db_ok = _probe_database()
    payload: Dict[str, Any] = {
        "status": "ok" if db_ok else "degraded",
        "version": current_app.config.get("VERSION", "1.29.1"),
        "uptime": round(time.time() - _dash_start_time, 2),
        "db_ok": db_ok,
    }
    return jsonify(payload), 200 if db_ok else 503


@worker_required
def _dashboard_summary() -> tuple[Response, int]:
    """API polling endpoint — return ticket status counts."""
    try:
        counts, last_updated_iso = _compute_summary_counts()
        return jsonify({
            "success": True,
            "counts": counts,
            "last_updated": last_updated_iso,
            "timestamp": get_utc_now().isoformat(),
        }), 200
    except SQLAlchemyError:
        current_app.logger.exception("Error in dashboard_summary")
        return jsonify({
            "success": False,
            "error": "Ein interner Fehler ist aufgetreten.",
        }), 500


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _logo_response(logo_path: str) -> Response:
    """Build a cacheable ``Response`` for the logo file at *logo_path*."""
    mtime = os.path.getmtime(logo_path)
    etag = f'"{int(mtime)}"'

    if request.headers.get("If-None-Match") == etag:
        return Response(status=304)

    with open(logo_path, "rb") as fh:
        logo_data = fh.read()

    return Response(
        logo_data,
        mimetype="image/png",
        headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=3600",
            "Last-Modified": datetime.fromtimestamp(mtime).strftime(
                "%a, %d %b %Y %H:%M:%S GMT",
            ),
        },
    )


def _probe_database() -> bool:
    """Return ``True`` if the database responds to a trivial query."""
    try:
        db.session.execute(db.text("SELECT 1")).fetchone()
        return True
    except SQLAlchemyError:
        current_app.logger.exception("Healthcheck DB failed")
        return False


def _is_elevated_role() -> bool:
    """Return ``True`` if the current session has an elevated role."""
    return session.get("role") in _ELEVATED_ROLES


def _compute_summary_counts() -> Tuple[Dict[str, int], str | None]:
    """Query ticket status counts and last-updated timestamp.

    Returns:
        A tuple of ``(counts_dict, last_updated_iso)``.
    """
    base = db.session.query(Ticket.status, func.count(Ticket.id)).filter(
        Ticket.is_deleted == False,  # noqa: E712
    )
    if not _is_elevated_role():
        worker_id = session.get("worker_id")
        team_ids = Team.team_ids_for_worker(worker_id) if worker_id else []
        base = base.filter(
            db.or_(*_confidential_filter(worker_id, team_ids))
        )

    results = base.group_by(Ticket.status).all()
    count_map: Dict[str, int] = dict(results)

    last_q = db.session.query(func.max(Ticket.updated_at)).filter(
        Ticket.is_deleted == False,  # noqa: E712
    )
    if not _is_elevated_role():
        worker_id = session.get("worker_id")
        team_ids = Team.team_ids_for_worker(worker_id) if worker_id else []
        last_q = last_q.filter(
            db.or_(*_confidential_filter(worker_id, team_ids))
        )

    last_updated = last_q.scalar()
    last_iso: str | None = last_updated.isoformat() if last_updated else None

    counts: Dict[str, Any] = {
        TicketStatus.OFFEN.value: count_map.get(TicketStatus.OFFEN.value, 0),
        TicketStatus.IN_BEARBEITUNG.value: count_map.get(
            TicketStatus.IN_BEARBEITUNG.value, 0,
        ),
        TicketStatus.WARTET.value: count_map.get(TicketStatus.WARTET.value, 0),
        "summary": sum(
            cnt for status, cnt in count_map.items()
            if status != TicketStatus.ERLEDIGT.value
        ),
    }
    return counts, last_iso


# ------------------------------------------------------------------
# Route registration
# ------------------------------------------------------------------

def register_routes(bp: Blueprint) -> None:
    """Register dashboard routes on *bp*."""
    bp.add_url_rule("/logo", "serve_logo", view_func=_serve_logo)
    bp.add_url_rule("/health", "health_check", view_func=_health_check)
    bp.add_url_rule(
        "/api/dashboard/summary", "dashboard_summary",
        view_func=_dashboard_summary,
    )
