"""
Dashboard routes.

Handles the main dashboard, logo serving, health check,
and ingress path injection.
"""
import os
import time
from datetime import datetime

from flask import (
    render_template, request, current_app, Response
)
from sqlalchemy import func

from extensions import db, Config
from models import Azubi, Check
from services import CheckService


def register_routes(bp):
    """Register dashboard routes on the given blueprint."""

    @bp.context_processor
    def inject_ingress_path():
        """Inject ingress path and logo version into templates."""
        ingress = request.headers.get('X-Ingress-Path', '')
        data_dir = Config.get_data_dir()
        logo_path = os.path.join(data_dir, 'static', 'img', 'logo.png')
        logo_version = 0
        if os.path.exists(logo_path):
            try:
                logo_version = int(os.path.getmtime(logo_path))
            except OSError:
                pass
        return {'ingress_path': ingress, 'logo_version': logo_version}

    @bp.route('/')
    def index():
        """Dashboard view."""
        start_time = time.time()

        subq = (
            db.session.query(
                Check.azubi_id,
                func.max(Check.datum).label('last_datum')
            )
            .group_by(Check.azubi_id)
            .subquery()
        )

        azubis_with_checks = (
            db.session.query(Azubi, subq.c.last_datum)
            .outerjoin(subq, Azubi.id == subq.c.azubi_id)
            .filter(Azubi.is_archived.is_(False))
            .order_by(Azubi.name)
            .all()
        )

        dashboard_data = []
        for azubi, last_datum in azubis_with_checks:
            status, status_class, last_check_str, sort_order = \
                azubi.get_dashboard_status(last_datum)
            assigned_count = len(
                CheckService.get_assigned_tools(azubi.id))
            dashboard_data.append({
                'id': azubi.id,
                'name': azubi.name,
                'lehrjahr': azubi.lehrjahr,
                'status': status,
                'status_class': status_class,
                'last_check': last_check_str,
                'assigned_count': assigned_count,
                'sort_order': sort_order
            })

        dashboard_data.sort(
            key=lambda x: (x['sort_order'], x['name']))

        duration = time.time() - start_time
        current_app.logger.info(
            f"Index route completed in {duration:.3f}s (Optimized)")

        return render_template('index.html', azubis=dashboard_data)

    @bp.route('/logo')
    def serve_logo():
        """Serve logo from DATA_DIR with ETag-based caching."""
        data_dir = Config.get_data_dir()
        logo_path = os.path.join(
            data_dir, 'static', 'img', 'logo.png')

        if not os.path.exists(logo_path):
            current_app.logger.warning(
                f"Logo not found at {logo_path}")
            return "Logo not found", 404

        try:
            mtime = os.path.getmtime(logo_path)
            etag = f'"{int(mtime)}"'

            if request.headers.get('If-None-Match') == etag:
                return Response(status=304)

            with open(logo_path, 'rb') as f:
                logo_data = f.read()

            return Response(
                logo_data,
                mimetype='image/png',
                headers={
                    'ETag': etag,
                    'Cache-Control': 'public, max-age=3600',
                    'Last-Modified': datetime.fromtimestamp(
                        mtime).strftime(
                        '%a, %d %b %Y %H:%M:%S GMT')
                }
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Error reading logo: {e}")
            return "Error reading logo", 500

    @bp.route('/health')
    def health_check():
        """Lightweight healthcheck endpoint."""
        try:
            db.session.execute(
                db.text('SELECT 1')).fetchone()
            return 'OK', 200
        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error(
                f"Healthcheck failed: {e}")
            return 'FAIL', 503
