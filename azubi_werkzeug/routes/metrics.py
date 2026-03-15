"""Metrics routes."""
from flask import Blueprint, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from routes.auth import admin_required

metrics_bp = Blueprint('metrics', __name__)


@metrics_bp.route('/metrics')
@admin_required
def metrics():
    """Expose Prometheus metrics."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
