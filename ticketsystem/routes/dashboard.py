"""
Dashboard routes.

Handles the main dashboard, logo serving, health check,
and ingress path injection.
"""
import os
import time
from datetime import datetime, timezone

from flask import Blueprint, render_template, jsonify, current_app, session, request, Response

from extensions import db, Config
from utils import get_utc_now
from models import Ticket
from enums import TicketStatus, WorkerRole
from routes.auth import worker_required
_dash_start_time = time.time()

def register_routes(bp):
    """Register dashboard routes on the given blueprint."""

    @bp.route('/logo')
    def serve_logo():
        """Serve logo from DATA_DIR with ETag-based caching."""
        data_dir = Config.get_data_dir()
        logo_path = os.path.join(
            data_dir, 'static', 'img', 'logo.png')

        if not os.path.exists(logo_path):
            current_app.logger.warning(
                "Logo not found at %s", logo_path)
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
            current_app.logger.exception("Error reading logo")
            return "Error reading logo", 500

    @bp.route('/health')
    def health_check():
        """Lightweight healthcheck endpoint — returns JSON."""
        try:
            db.session.execute(db.text('SELECT 1')).fetchone()
            db_ok = True
        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.exception("Healthcheck DB failed")
            db_ok = False

        payload = {
            "status": "ok" if db_ok else "degraded",
            "version": current_app.config.get("VERSION", "1.29.0"),
            "uptime": round(time.time() - _dash_start_time, 2),
            "db_ok": db_ok,
        }
        status_code = 200 if db_ok else 503
        return jsonify(payload), status_code

    @bp.route('/api/dashboard/summary')
    @worker_required
    def dashboard_summary():
        """API endpoint for dashboard polling (summary only)."""
        from sqlalchemy import func
        
        try:
            query = db.session.query(Ticket.status, func.count(Ticket.id))\
                .filter(Ticket.is_deleted == False)
            
            # FIG-04: Filter confidential tickets for non-elevated roles
            user_role = session.get('role')
            if user_role not in [WorkerRole.ADMIN.value, WorkerRole.HR.value, WorkerRole.MANAGEMENT.value]:
                query = query.filter(Ticket.is_confidential == False)
                
            results = query.group_by(Ticket.status).all()
            
            count_map = {status: count for status, count in results}
            
            # BUG-2: Also return last_updated timestamp so frontend can detect status changes
            # that don't alter the total count (e.g. Offen -> In Bearbeitung)
            last_updated_query = db.session.query(func.max(Ticket.updated_at))\
                .filter(Ticket.is_deleted == False)
            if user_role not in [WorkerRole.ADMIN.value, WorkerRole.HR.value, WorkerRole.MANAGEMENT.value]:
                last_updated_query = last_updated_query.filter(Ticket.is_confidential == False)
            last_updated_result = last_updated_query.scalar()
            last_updated_iso = last_updated_result.isoformat() if last_updated_result else None

            counts = {
                TicketStatus.OFFEN.value: count_map.get(TicketStatus.OFFEN.value, 0),
                TicketStatus.IN_BEARBEITUNG.value: count_map.get(TicketStatus.IN_BEARBEITUNG.value, 0),
                TicketStatus.WARTET.value: count_map.get(TicketStatus.WARTET.value, 0),
                'summary': sum(count for status, count in count_map.items() if status != TicketStatus.ERLEDIGT.value)
            }
            return jsonify({
                'success': True,
                'counts': counts,
                'last_updated': last_updated_iso,
                'timestamp': get_utc_now().isoformat()
            })
        except Exception as e:
            current_app.logger.exception("Error in dashboard_summary")
            return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

