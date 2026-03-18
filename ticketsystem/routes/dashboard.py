"""
Dashboard routes.

Handles the main dashboard, logo serving, health check,
and ingress path injection.
"""
import os
import time
from datetime import datetime


from flask import Response, current_app, jsonify, render_template, request
from sqlalchemy import func

from extensions import Config, db
from models import Ticket

_dash_start_time = time.time()



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
        return render_template('index.html')

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
            current_app.logger.error("Error reading logo: %s", e)
            return "Error reading logo", 500

    @bp.route('/health')
    def health_check():
        """Lightweight healthcheck endpoint — returns JSON."""
        try:
            db.session.execute(db.text('SELECT 1')).fetchone()
            db_ok = True
        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error("Healthcheck DB failed: %s", e)
            db_ok = False

        payload = {
            "status": "ok" if db_ok else "degraded",
            "version": current_app.config.get("VERSION", "2.11.0"),
            "uptime": round(time.time() - _dash_start_time, 2),
            "db_ok": db_ok,
        }
        status_code = 200 if db_ok else 503
        return jsonify(payload), status_code

