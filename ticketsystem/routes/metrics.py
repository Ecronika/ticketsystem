"""Metrics routes — Prometheus endpoint."""

from flask import Blueprint, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from routes.auth import admin_required

metrics_bp: Blueprint = Blueprint("metrics", __name__)


@metrics_bp.route("/metrics")
@admin_required
def metrics() -> Response:
    """Expose Prometheus metrics (admin-only)."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
