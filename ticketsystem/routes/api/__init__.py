"""Public REST API Blueprint.

Strictly isolated from main_bp:
- No session cookies (cleared in before_request)
- JSON-only error responses
- Own decorator chain (@api_key_required, not @worker_required)
"""

from __future__ import annotations

import time
import uuid

from flask import Blueprint, Flask, current_app, g, request, session

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


@api_bp.before_request
def _isolate_session():
    """Clear any session state — API is stateless."""
    session.clear()
    g.api_request_id = str(uuid.uuid4())
    g.api_request_start = None  # set by auth decorator for latency measurement


@api_bp.after_request
def _write_audit_log(response):
    """Write audit log entry for every API request (except /health)."""
    # Skip audit log for liveness probes (endpoint "api._health")
    if request.endpoint == "api._health":
        return response
    start = getattr(g, "api_request_start", None)
    latency_ms = int((time.perf_counter() - start) * 1000) if start else 0
    try:
        from services.api_key_service import ApiKeyService
        ApiKeyService.log_audit(
            api_key=getattr(g, "api_key", None),
            key_prefix=getattr(g, "api_key_prefix", None),
            source_ip=(
                request.headers.get("CF-Connecting-IP")
                or request.headers.get("X-Real-IP")
                or request.remote_addr
                or ""
            ),
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            outcome=getattr(g, "api_outcome", "success"),
            request_id=getattr(g, "api_request_id", "unknown"),
            external_ref=getattr(g, "api_external_ref", None),
            assignment_method=getattr(g, "api_assignment_method", None),
            error_detail=getattr(g, "api_error_detail", None),
        )
    except Exception:
        current_app.logger.exception("Audit log write failed")
    return response


def register_api(app: Flask) -> None:
    """Register the api_bp on *app* with all sub-modules loaded."""
    from .health_routes import register_routes as register_health
    from .webhook_routes import register_routes as register_webhook
    # Phase b/c: from .ticket_routes import register_routes as register_tickets
    from ._errors import register_error_handlers

    register_health(api_bp)
    register_webhook(api_bp)
    register_error_handlers(api_bp)

    app.register_blueprint(api_bp)
