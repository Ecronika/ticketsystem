"""
Routes module.

Defines the URL routes and view functions for the application.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, Response, jsonify, make_response, send_from_directory
from sqlalchemy.orm import joinedload
from sqlalchemy import func, select  # For optimized queries
from sqlalchemy.exc import SQLAlchemyError  # Issue #4: Error handling
from extensions import db, limiter, csrf, Config
from models import Azubi, Werkzeug, Examiner, Check, CheckType
from forms import AzubiForm, ExaminerForm, WerkzeugForm
from datetime import datetime, timedelta
import logging
import time
import os
import uuid
import base64
from pdf_utils import generate_handover_pdf, generate_qr_codes_pdf, generate_end_of_training_report
from services import CheckService, BackupService

main_bp = Blueprint('main', __name__)

@main_bp.context_processor
def inject_ingress_path():
    ingress = request.headers.get('X-Ingress-Path', '')

    # Add logo version for cache busting
    data_dir = Config.get_data_dir()
    logo_path = os.path.join(data_dir, 'static', 'img', 'logo.png')

    # Use file modification time as version (cache buster)
    logo_version = 0
    if os.path.exists(logo_path):
        try:
            logo_version = int(os.path.getmtime(logo_path))
        except:
            pass

    return {'ingress_path': ingress, 'logo_version': logo_version}

# Issue #4: Helper function for database error handling
def handle_db_error(error, operation_name, redirect_route='main.index', custom_message=None):
    """
    Centralized database error handling with logging and user feedback.

    Args:
        error: The SQLAlchemyError exception
        operation_name: Description of the operation (for logging)
        redirect_route: Route to redirect to after error
        custom_message: Optional custom error message for user
    """
    # Roll back the session
    db.session.rollback()

    # Log the error with context
    current_app.logger.error(f"Database error during {operation_name}: {str(error)}")

    # User-friendly error message
    if custom_message:
        flash(custom_message, 'danger')
    else:
        flash('Ein Datenbankfehler ist aufgetreten. Bitte versuchen Sie es später erneut.', 'danger')

    return redirect(url_for(redirect_route))

def generate_unique_session_id():
    """Generates a unique session ID, preventing collision."""
    # Combine timestamp and UUID for better uniqueness/ordering
    import time
    timestamp = int(time.time() * 1000)
    uid = str(uuid.uuid4()).split('-')[0] # Shorten UUID part
    return f"{timestamp}-{uid}"

def get_data_dir():
    # Retrieve data_dir from app config or calculate it
    return Config.get_data_dir()

# Helper: Assigned Tools Cache
# Simple in-memory cache to reduce DB load
from threading import Lock
_assigned_tools_cache = {}
_cache_lock = Lock()
_cache_timeout = timedelta(minutes=5)

def get_assigned_tools(azubi_id):
    """
    Returns a set of tool IDs currently assigned to the Azubi.
    Uses caching to improve performance.
    """
    cache_key = f"assigned_{azubi_id}"
    now = datetime.now()

    # Check cache
    with _cache_lock:
        if cache_key in _assigned_tools_cache:
            cached_data, timestamp = _assigned_tools_cache[cache_key]
            if now - timestamp < _cache_timeout:
                return cached_data

    # Calculate (Heavy DB Operation)
    checks = Check.query.filter_by(azubi_id=azubi_id).order_by(Check.datum.asc()).all()
    assigned = set()

    for c in checks:
        # Case-insensitive comparison for robustness
        c_type = (c.check_type or "").lower()
        if c_type == CheckType.ISSUE.value.lower():
            assigned.add(c.werkzeug_id)
        elif c_type == CheckType.RETURN.value.lower():
            if c.werkzeug_id in assigned:
                assigned.remove(c.werkzeug_id)

    result = assigned

    # Update cache
    with _cache_lock:
        _assigned_tools_cache[cache_key] = (result, now)

    return result

@main_bp.route('/logo')
def serve_logo():
    """Serve logo from DATA_DIR with ETag-based caching"""
    data_dir = get_data_dir()
    logo_path = os.path.join(data_dir, 'static', 'img', 'logo.png')

    if not os.path.exists(logo_path):
        current_app.logger.warning(f"Logo not found at {logo_path}")
        return "Logo not found", 404

    try:
        # Use file modification time as ETag for cache validation
        mtime = os.path.getmtime(logo_path)
        etag = f'"{int(mtime)}"'

        # Check if client has current version (HTTP 304 Not Modified)
        if request.headers.get('If-None-Match') == etag:
            return Response(status=304)

        # Read and serve logo with ETag
        with open(logo_path, 'rb') as f:
            logo_data = f.read()

        from datetime import datetime
        return Response(
            logo_data,
            mimetype='image/png',
            headers={
                'ETag': etag,
                'Cache-Control': 'public, max-age=3600',
                'Last-Modified': datetime.fromtimestamp(mtime).strftime('%a, %d %b %Y %H:%M:%S GMT')
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error reading logo: {e}")
        return "Error reading logo", 500

@main_bp.route('/debug/paths')
def debug_paths():
    """Debug endpoint to check paths"""
    import os
    data_dir = get_data_dir()
    logo_path = os.path.join(data_dir, 'static', 'img', 'logo.png')

    return {
        'DATA_DIR_env': os.environ.get('DATA_DIR', 'NOT SET'),
        'data_dir': data_dir,
        'logo_path': logo_path,
        'logo_exists': os.path.exists(logo_path),
        'logo_size': os.path.getsize(logo_path) if os.path.exists(logo_path) else 0,
        'cwd': os.getcwd(),
        'files_in_data_static_img': os.listdir(os.path.join(data_dir, 'static', 'img')) if os.path.exists(os.path.join(data_dir, 'static', 'img')) else []
    }

@main_bp.route('/health')
def health_check():
    """Lightweight healthcheck endpoint - no heavy DB operations"""
    try:
        # Simple DB connection check
        db.session.execute(db.text('SELECT 1')).fetchone()
        return 'OK', 200
    except Exception as e:
        current_app.logger.error(f"Healthcheck failed: {e}")
        return 'FAIL', 503

@main_bp.route('/')
def index():
    import time
    start_time = time.time()

    # OPTIMIERT: Single query with subquery for last check date (Fixes N+1 problem)
    # Subquery: Get latest check date per azubi
    subq = (
        db.session.query(
            Check.azubi_id,
            func.max(Check.datum).label('last_datum')
        )
        .group_by(Check.azubi_id)
        .subquery()
    )

    # Join azubis with their last check in ONE query
    azubis_with_checks = (
        db.session.query(Azubi, subq.c.last_datum)
        .outerjoin(subq, Azubi.id == subq.c.azubi_id)
        .filter(Azubi.is_archived == False)
        .order_by(Azubi.name)
        .all()
    )

    dashboard_data = []
    now = datetime.now()

    for azubi, last_datum in azubis_with_checks:
        start_loop = time.time()

        # Calculate status
        if last_datum:
            days_since = (now - last_datum).days
            last_check_str = last_datum.strftime("%d. %b %Y")

            if days_since >= 90:
                status, status_class, sort_order = "Überfällig (> 3 Mon.)", "danger", 1
                last_check_str = f"Vor {days_since} Tagen"
            elif days_since >= 62:
                status, status_class, sort_order = "Prüfung fällig (< 4 Wochen)", "warning", 2
                last_check_str = f"Vor {days_since} Tagen"
            else:
                status, status_class, sort_order = "Geprüft", "success", 3
        else:
            status, status_class = "Neu / Leer", "info"
            last_check_str, sort_order = "Noch nie", 4

        # Get assigned tools count (now using CACHED version)
        assigned_count = len(get_assigned_tools(azubi.id))

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

    dashboard_data.sort(key=lambda x: (x['sort_order'], x['name']))

    duration = time.time() - start_time
    current_app.logger.info(f"Index route completed in {duration:.3f}s (Optimized)")

    return render_template('index.html', azubis=dashboard_data)

@main_bp.route('/check/<int:azubi_id>', methods=['GET'])
def check_azubi(azubi_id):
    azubi = Azubi.query.get_or_404(azubi_id)
    werkzeuge = Werkzeug.query.all()
    examiners = Examiner.query.all()
    current_date = datetime.now().strftime("%d. %b %Y")

    assigned_ids = get_assigned_tools(azubi.id)

    last_check_global = Check.query.filter_by(azubi_id=azubi.id).order_by(Check.datum.desc()).first()
    days_since_global = (datetime.now() - last_check_global.datum).days if last_check_global else 999
    is_overdue = days_since_global > 90

    mapped_werkzeuge = []
    for w in werkzeuge:
        last_entry = Check.query.filter_by(azubi_id=azubi.id, werkzeug_id=w.id).order_by(Check.datum.desc()).first()
        status = 'ok'
        tech_val = ""

        if last_entry:
            if last_entry.bemerkung:
                 parts = last_entry.bemerkung.split('|')
                 for p in parts:
                     if p.strip().startswith("Status:"):
                         status = p.replace("Status:", "").strip()
                         break
            if last_entry.tech_param_value:
                tech_val = last_entry.tech_param_value

        mapped_werkzeuge.append({
            'obj': w,
            'is_assigned': w.id in assigned_ids,
            'last_status': status,
            'last_tech_val': tech_val
        })

    return render_template('check.html', azubi=azubi, werkzeuge=mapped_werkzeuge, examiners=examiners, current_date=current_date,
                           is_overdue=is_overdue)


@main_bp.route('/submit_check', methods=['POST'])
def submit_check():
    import time
    start_time = time.time()

    azubi_id = request.form.get('azubi_id')
    check_type_str = request.form.get('check_type', CheckType.CHECK.value)
    ingress = request.headers.get('X-Ingress-Path', '')

    # Validate CheckType
    try:
        CheckType(check_type_str)
    except ValueError:
        current_app.logger.warning(f"Invalid CheckType submitted: {check_type_str}")
        flash('Fehler: Ungültiger Prüfungstyp.', 'error')
        return redirect(f"{ingress}{url_for('main.index')}")

    examiner = request.form.get('examiner')

    if not azubi_id or not examiner:
        flash('Fehler: Azubi und Prüfer müssen angegeben werden.', 'error')
        return redirect(f"{ingress}{url_for('main.index')}")

    try:
        # --- Migration Mode Logic (Date Parsing) ---
        is_migration = session.get('migration_mode', False)
        check_date = datetime.now()

        if is_migration:
            c_date = request.form.get('custom_date')
            c_time = request.form.get('custom_time')
            if c_date:
                try:
                    time_str = c_time if c_time else "12:00"
                    check_date = datetime.strptime(f"{c_date} {time_str}", "%Y-%m-%d %H:%M")
                except ValueError:
                    flash('Fehler: Ungültiges Datumsformat im Migrations-Modus.', 'error')
                    current_app.logger.warning(f"Invalid migration date format: {c_date} {c_time}")
                    return redirect(f"{ingress}{url_for('main.index')}")

        # 2. Collect Tool IDs
        tool_ids = []
        for key in request.form:
            if key.startswith('tool_'):
                try:
                    tool_ids.append(int(key.split('_')[1]))
                except (IndexError, ValueError):
                    continue

        if not tool_ids:
            flash('Keine Werkzeuge ausgewählt', 'warning')
            return redirect(f"{ingress}{url_for('main.index')}")

        # Call Service
        result = CheckService.process_check_submission(
            azubi_id=int(azubi_id),
            examiner_name=examiner,
            tool_ids=tool_ids,
            form_data=request.form,
            check_date=check_date,
            check_type=CheckType(check_type_str)
        )

        flash(f'{check_type_str.capitalize()} erfolgreich gespeichert! (Session: {result["session_id"]})', 'success')

        # Invalidate Cache for this Azubi so the new state (issued/returned) is reflected immediately
        _assigned_tools_cache.pop(f"assigned_{azubi_id}", None)

        return redirect(f"{ingress}{url_for('main.index')}")

    except Exception as e:
        current_app.logger.error(f"Error in submit_check: {e}", exc_info=True)
        flash(f'Fehler beim Speichern: {str(e)}', 'danger')
        return redirect(f"{ingress}{url_for('main.index')}")

@main_bp.route('/exchange_tool', methods=['POST'])
def exchange_tool():
    """
    Handles One-Click Tool Exchange (Defective -> New).
    Creates two records (Return + Issue) with shared session_id.
    """
    import time
    start_time = time.time()

    azubi_id = request.form.get('azubi_id')
    tool_id = request.form.get('tool_id')
    reason = request.form.get('reason') # e.g. "Defekt", "Verloren"
    is_payable = request.form.get('is_payable') == 'on'
    signature_data = request.form.get('signature_azubi_data')
    ingress = request.headers.get('X-Ingress-Path', '')

    if not all([azubi_id, tool_id, reason, signature_data]):
        flash('Fehler: Unvollständige Daten für Austausch.', 'error')
        return redirect(f"{ingress}{url_for('main.index')}")

    try:
        result = CheckService.process_tool_exchange(
            azubi_id=int(azubi_id),
            tool_id=int(tool_id),
            reason=reason,
            is_payable=is_payable,
            signature_data=signature_data
        )

        # Invalidate Cache
        _assigned_tools_cache.pop(f"assigned_{azubi_id}", None)

        flash('Werkzeug erfolgreich ausgetauscht.', 'success')
        return redirect(f"{ingress}{url_for('main.index')}")

    except Exception as e:
        current_app.logger.error(f"Exchange failed: {e}", exc_info=True)
        flash(f'Fehler beim Austausch: {str(e)}', 'error')
        return redirect(f"{ingress}{url_for('main.index')}")

@main_bp.route('/api/assigned_tools/<int:azubi_id>')
def api_get_assigned_tools(azubi_id):
    """API to get assigned tools for dropdown"""
    # Use our cached function
    tool_ids = get_assigned_tools(azubi_id)

    # Fetch names
    tools = Werkzeug.query.filter(Werkzeug.id.in_(tool_ids)).order_by(Werkzeug.name).all()

    return jsonify([{'id': t.id, 'name': t.name} for t in tools])

@main_bp.route('/api/stats')
@limiter.limit("30 per minute")
@csrf.exempt
def api_stats():
    """Returns basic statistics for dashboard"""
    total_tools = Werkzeug.query.count()
    total_azubis = Azubi.query.filter_by(is_archived=False).count()

    # New metrics for v2.6.0-beta2
    start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    checks_today = Check.query.filter(Check.datum >= start_of_day).count()

    return jsonify({
        'total_tools': total_tools,
        'total_azubis': total_azubis,
        'checks_today': checks_today,
        'generated_at': datetime.now().isoformat()
    })

@main_bp.route('/history')
def history():
    import time
    start_time = time.time()

    azubi_id = request.args.get('azubi_id')

    try:
        query = Check.query.order_by(Check.datum.desc())

        if azubi_id and azubi_id != 'all':
            query = query.filter_by(azubi_id=int(azubi_id))

        # Load checks with eager loading
        query_start = time.time()
        all_checks = query.options(joinedload(Check.azubi)).limit(2000).all()
        query_duration = time.time() - query_start
        current_app.logger.info(f"History query loaded {len(all_checks)} checks in {query_duration:.3f}s")

        azubis = Azubi.query.order_by(Azubi.name).all()

        # OPTIMIZED: Group checks by session_id using dict (O(N) instead of O(N²))
        group_start = time.time()
        sessions_dict = {}

        for check in all_checks:
            # Generate session key
            if check.session_id:
                sid = check.session_id
            else:
                sid = f"LEGACY_{check.azubi_id}_{int(check.datum.timestamp())}"

            # Group by session
            if sid not in sessions_dict:
                sessions_dict[sid] = {
                    'session_id': check.session_id if check.session_id else sid,
                    'datum': check.datum,
                    'azubi_name': check.azubi.name,
                    'checks': [],
                    'is_ok': True
                }

            sessions_dict[sid]['checks'].append(check)

            # Check if any tool is missing/broken
            if "Status: missing" in (check.bemerkung or "") or "Status: broken" in (check.bemerkung or ""):
                sessions_dict[sid]['is_ok'] = False

        # Convert to list and add count
        sessions = []
        for sid, session_data in sessions_dict.items():
            sessions.append({
                'session_id': session_data['session_id'],
                'datum': session_data['datum'],
                'azubi_name': session_data['azubi_name'],
                'is_ok': session_data['is_ok'],
                'count': len(session_data['checks'])
            })

        group_duration = time.time() - group_start
        current_app.logger.info(f"History grouping completed in {group_duration:.3f}s ({len(sessions)} sessions)")

        total_duration = time.time() - start_time
        current_app.logger.info(f"History route completed in {total_duration:.3f}s (query:{query_duration:.3f}s, grouping:{group_duration:.3f}s)")

        return render_template('history.html', sessions=sessions, azubis=azubis,
                             selected_azubi_id=int(azubi_id) if azubi_id and azubi_id != 'all' else None)

    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error in history: {e}", exc_info=True)
        flash('Fehler beim Laden der Historie', 'danger')
        return redirect(url_for('main.index'))
    except Exception as e:
        current_app.logger.error(f"Error in history: {e}", exc_info=True)
        flash(f'Fehler: {str(e)}', 'danger')
        return redirect(url_for('main.index'))

@main_bp.route('/history_details/<path:session_id>')
def history_details(session_id):
    if session_id.startswith("LEGACY_"):
        _, azubi_id_str, timestamp_str = session_id.split('_')
        target_time = datetime.fromtimestamp(float(timestamp_str))
        checks = Check.query.filter_by(azubi_id=int(azubi_id_str), datum=target_time).all()
    else:
        checks = Check.query.filter_by(session_id=session_id).options(joinedload(Check.werkzeug), joinedload(Check.azubi)).all()

    if not checks:
        flash('Prüfung nicht gefunden.', 'error')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.history')}")

    azubi = checks[0].azubi
    datum = checks[0].datum.strftime("%d. %b %Y %H:%M")

    first_c = checks[0]
    check_type = first_c.check_type
    examiner = first_c.examiner
    report_path = first_c.report_path

    # Detect Exchange (Austausch)
    # Since exchange creates RETURN + ISSUE, we check if any item has "Austausch" in comments
    # or if we have mixed types in one session (Return + Issue)
    has_return = any(c.check_type == CheckType.RETURN for c in checks)
    has_issue = any(c.check_type == CheckType.ISSUE for c in checks)

    if has_return and has_issue and len(checks) >= 2:
        check_type = 'exchange'
    elif any('Austausch' in (c.bemerkung or '') for c in checks):
        check_type = 'exchange'

    parsed_checks = []
    global_bemerkung = ""

    for c in checks:
        status_code = "ok"
        parts = (c.bemerkung or "").split('|')
        for p in parts:
            p = p.strip()
            if p.startswith("Status:"):
                status_code = p.replace("Status:", "").strip()
            elif not p.startswith("Status:"):
                if p and not global_bemerkung:
                     global_bemerkung = p

        parsed_checks.append({
            'werkzeug': c.werkzeug.name,
            'status': status_code,
            'tech_label': c.werkzeug.tech_param_label,
            'tech_value': c.tech_param_value,
            'incident_reason': c.incident_reason
        })

    return render_template('history_details.html',
                         azubi=azubi,
                         datum=datum,
                         checks=parsed_checks,
                         global_bemerkung=global_bemerkung,
                         check_type=check_type,
                         examiner=examiner,
                         report_path=report_path,
                         session_id=session_id)

@main_bp.route('/download_report/<path:filename>')
def download_report(filename):
    data_dir = get_data_dir()
    reports_dir = os.path.join(data_dir, 'reports')
    return send_from_directory(reports_dir, filename, as_attachment=True)

@main_bp.route('/manage')
def manage():
    """Redirect old /manage to new /tools page for backward compatibility"""
    return redirect(url_for('main.tools'))

@main_bp.route('/tools')
def tools():
    """Tools management page"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    werkzeuge_pagination = Werkzeug.query.order_by(Werkzeug.name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    werkzeuge = werkzeuge_pagination.items

    return render_template('tools.html',
                          werkzeuge=werkzeuge,
                          werkzeuge_pagination=werkzeuge_pagination)

@main_bp.route('/personnel')
def personnel():
    """Personnel management page (Azubis + Examiners)"""
    azubi_page = request.args.get('azubi_page', 1, type=int)
    show_archived = request.args.get('show_archived', '0') == '1'
    per_page = 20
    query = Azubi.query.order_by(Azubi.name)

    if not show_archived:
        query = query.filter_by(is_archived=False)

    try:
        azubi_pagination = query.paginate(page=azubi_page, per_page=per_page, error_out=False)

        # FIX: Edge Case - If page > max_pages, redirect to last page
        # Add check for pages > 0 to prevent redirect loops if no items exist
        if azubi_pagination.pages > 0 and azubi_page > azubi_pagination.pages:
           flash('Seite existiert nicht, leite zur letzten Seite um.', 'info')
           # We need to rebuild the current URL but with modified page
           args = request.args.copy()
           args['azubi_page'] = azubi_pagination.pages
           return redirect(url_for(request.endpoint, **args))

    except Exception as e:
        current_app.logger.error(f"Pagination failed: {e}")
        azubi_pagination = None # Handle pagination error gracefully

    azubis = azubi_pagination.items if azubi_pagination else []

    # Query examiners (not paginated, typically few items)
    examiners = Examiner.query.order_by(Examiner.name).all()

    return render_template('personnel.html',
                          azubis=azubis,
                          azubi_pagination=azubi_pagination,
                          examiners=examiners,
                          show_archived=show_archived)

@main_bp.route('/settings')
def settings():
    """System settings page"""
    data_dir = get_data_dir()
    logo_path = os.path.join(data_dir, 'static', 'img', 'logo.png')
    logo_exists = os.path.exists(logo_path)
    logo_version = int(os.path.getmtime(logo_path)) if logo_exists else 0
    ingress = request.headers.get('X-Ingress-Path', '')

    # Fetch backups
    backups = BackupService.list_backups()

    # Get System Settings
    from models import SystemSettings
    backup_interval = SystemSettings.get_setting('backup_interval', 'daily')
    backup_time = SystemSettings.get_setting('backup_time', '03:00')
    retention_days = SystemSettings.get_setting('backup_retention_days', '30')

    return render_template('settings.html',
                             logo_exists=logo_exists,
                             logo_version=time.time(),
                             backups=backups,
                             backup_interval=backup_interval,
                             backup_time=backup_time,
                             retention_days=retention_days)

@main_bp.route('/settings/backup/config', methods=['POST'])
def save_backup_config():
    """Saves backup schedule settings"""
    from models import SystemSettings

    interval = request.form.get('interval')
    time_str = request.form.get('time')
    retention = request.form.get('retention')

    # Save settings
    SystemSettings.set_setting('backup_interval', interval)
    SystemSettings.set_setting('backup_time', time_str)
    SystemSettings.set_setting('backup_retention_days', retention)

    # Update Job
    BackupService.schedule_backup_job(current_app._get_current_object())

    flash('Backup-Einstellungen gespeichert.', 'success')
    return redirect(f"{request.headers.get('X-Ingress-Path', '')}{url_for('main.settings')}")

@main_bp.route('/settings/restore', methods=['POST'])
def restore_backup():
    """Handles backup restore from upload"""
    if 'backup_file' not in request.files:
        flash('Keine Datei ausgewählt.', 'error')
        return redirect(f"{request.headers.get('X-Ingress-Path', '')}{url_for('main.settings')}")

    file = request.files['backup_file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'error')
        return redirect(f"{request.headers.get('X-Ingress-Path', '')}{url_for('main.settings')}")

    if file and file.filename.endswith('.zip'):
        ingress = request.headers.get('X-Ingress-Path', '')
        try:
            # Save upload to temp
            data_dir = CheckService.get_data_dir()
            temp_path = os.path.join(data_dir, 'restore_upload.zip')

            try:
                file.save(temp_path)

                # Restore
                BackupService.restore_backup(temp_path)

                # Trigger Restart
                flash('System wird wiederhergestellt. Neustart in 5 Sekunden...', 'success')

                # In a container, sys.exit(0) effectively restarts the app
                import threading
                def restart():
                    import time, sys
                    time.sleep(2)
                    sys.exit(0)

                threading.Thread(target=restart).start()

                return redirect(f"{ingress}{url_for('main.index')}")

            except Exception as e:
                flash(f'Fehler bei Wiederherstellung: {str(e)}', 'error')
                return redirect(f"{ingress}{url_for('main.settings')}")
            finally:
                # Cleanup upload - ALWAYS executed
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

        except Exception as e:
            flash(f'Fehler bei Wiederherstellung: {str(e)}', 'error')
            return redirect(f"{ingress}{url_for('main.settings')}")

    flash('Ungültiges Dateiformat. Nur .zip erlaubt.', 'error')
    return redirect(f"{request.headers.get('X-Ingress-Path', '')}{url_for('main.settings')}")

@main_bp.route('/settings/backup/create', methods=['POST'])
def create_backup():
    try:
        filename = BackupService.create_backup()
        flash(f'Backup erfolgreich erstellt: {filename}', 'success')
    except Exception as e:
        flash(f'Backup fehlgeschlagen: {e}', 'error')

    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.settings')}")

@main_bp.route('/settings/backup/download/<filename>')
def download_backup(filename):
    try:
        backup_dir = BackupService.get_backup_dir()
        return send_from_directory(backup_dir, filename, as_attachment=True)
    except Exception as e:
        flash(f'Download fehlgeschlagen: {e}', 'error')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.settings')}")

@main_bp.route('/toggle_migration_mode', methods=['POST'])
def toggle_migration_mode():
    current_mode = session.get('migration_mode', False)
    session['migration_mode'] = not current_mode
    status = "aktiviert" if session['migration_mode'] else "deaktiviert"
    flash(f'Migration Modus wurde {status}.', 'info')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.settings')}")

@main_bp.route('/delete_session/<path:session_id>', methods=['POST'])
def delete_session(session_id):
    """Delete an entire check session (only in migration mode).

    Safety features:
    - Only works in migration mode
    - Confirmation modal required (UI)
    - Deletes all associated files (PDF, signatures)
    - Comprehensive audit logging
    """
    import time
    start_time = time.time()

    ingress = request.headers.get('X-Ingress-Path', '')

    # SAFETY CHECK: Only allow deletion in migration mode
    if not session.get('migration_mode', False):
        current_app.logger.warning(f"Delete session attempted WITHOUT migration mode: session_id={session_id}")
        flash('⚠️ Session-Löschung nur im Migration-Modus erlaubt!', 'danger')
        return redirect(f"{ingress}{url_for('main.history')}")

    try:
        # Check for legacy sessions (can't delete without real session_id)
        if session_id.startswith('LEGACY_'):
            current_app.logger.warning(f"Attempted to delete legacy session: {session_id}")
            flash('Legacy-Sessions ohne UUID können nicht gelöscht werden.', 'warning')
            return redirect(f"{ingress}{url_for('main.history')}")

        # Find all checks in this session
        checks = Check.query.filter_by(session_id=session_id).all()

        if not checks:
            current_app.logger.warning(f"Delete session not found: {session_id}")
            flash('Session nicht gefunden.', 'warning')
            return redirect(f"{ingress}{url_for('main.history')}")

        # Collect session info for logging
        azubi_name = checks[0].azubi.name
        azubi_id = checks[0].azubi_id
        datum = checks[0].datum
        examiner = checks[0].examiner or 'Unbekannt'
        check_count = len(checks)

        # File cleanup
        data_dir = get_data_dir()
        files_deleted = []

        # Delete PDF report
        if checks[0].report_path and os.path.exists(checks[0].report_path):
            try:
                os.remove(checks[0].report_path)
                pdf_filename = os.path.basename(checks[0].report_path)
                files_deleted.append(f'PDF:{pdf_filename}')
            except OSError as e:
                current_app.logger.error(f"Failed to delete PDF {checks[0].report_path}: {e}")

        # Delete azubi signature
        sig_azubi = checks[0].signature_azubi
        if sig_azubi and os.path.exists(sig_azubi):
            try:
                os.remove(sig_azubi)
                files_deleted.append('Sig_Azubi')
            except OSError as e:
                current_app.logger.error(f"Failed to delete azubi signature {sig_azubi}: {e}")

        # Delete examiner signature
        sig_examiner = checks[0].signature_examiner
        if sig_examiner and os.path.exists(sig_examiner):
            try:
                os.remove(sig_examiner)
                files_deleted.append('Sig_Examiner')
            except OSError as e:
                current_app.logger.error(f"Failed to delete examiner signature {sig_examiner}: {e}")

        # Delete all check records from database
        for check in checks:
            db.session.delete(check)

        db.session.commit()

        duration = time.time() - start_time

        # CRITICAL AUDIT LOG
        current_app.logger.warning(
            f"🗑️ SESSION DELETED | session_id={session_id} | "
            f"azubi={azubi_name}(id:{azubi_id}) | datum={datum.strftime('%Y-%m-%d %H:%M')} | "
            f"examiner={examiner} | checks_deleted={check_count} | "
            f"files={', '.join(files_deleted) if files_deleted else 'none'} | "
            f"duration={duration:.3f}s | migration_mode=True"
        )

        flash(
            f'✅ Session erfolgreich gelöscht: {azubi_name} - {datum.strftime("%d.%m.%Y %H:%M")} '
            f'({check_count} Checks, {len(files_deleted)} Dateien)',
            'success'
        )
        return redirect(f"{ingress}{url_for('main.history')}")

    except SQLAlchemyError as e:
        db.session.rollback()
        db.session.remove()  # Explicit cleanup to prevent connection leaks
        current_app.logger.error(f"Database error deleting session {session_id}: {e}", exc_info=True)
        flash('❌ Datenbankfehler beim Löschen der Session.', 'danger')
        return redirect(f"{ingress}{url_for('main.history_details', session_id=session_id)}")
    except Exception as e:
        db.session.rollback()
        db.session.remove()  # Explicit cleanup to prevent connection leaks
        current_app.logger.error(f"Unexpected error deleting session {session_id}: {e}", exc_info=True)
        flash(f'❌ Fehler beim Löschen: {str(e)}', 'danger')
        return redirect(f"{ingress}{url_for('main.history_details', session_id=session_id)}")

@main_bp.route('/add_examiner', methods=['POST'])
def add_examiner():
    form = ExaminerForm(request.form)
    ingress = request.headers.get('X-Ingress-Path', '')
    if form.validate():
        new_examiner = Examiner(name=form.name.data)
        db.session.add(new_examiner)
        db.session.commit()
        flash(f'Prüfer {form.name.data} hinzugefügt.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler bei {field}: {error}", 'error')
    return redirect(f"{ingress}{url_for('main.personnel')}")

@main_bp.route('/delete_examiner/<int:id>', methods=['POST'])
def delete_examiner(id):
    examiner = Examiner.query.get_or_404(id)
    db.session.delete(examiner)
    db.session.commit()
    flash(f'Prüfer {examiner.name} gelöscht.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.personnel')}")

@main_bp.route('/add_azubi', methods=['POST'])
def add_azubi():
    form = AzubiForm(request.form)
    ingress = request.headers.get('X-Ingress-Path', '')
    if form.validate():
        new_azubi = Azubi(name=form.name.data, lehrjahr=form.lehrjahr.data)
        db.session.add(new_azubi)
        db.session.commit()
        flash(f'Azubi {form.name.data} hinzugefügt.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler bei {field}: {error}", 'error')
    return redirect(f"{ingress}{url_for('main.personnel')}")

@main_bp.route('/edit_azubi/<int:id>', methods=['POST'])
def edit_azubi(id):
    azubi = Azubi.query.get_or_404(id)
    form = AzubiForm(request.form)
    ingress = request.headers.get('X-Ingress-Path', '')
    if form.validate():
        azubi.name = form.name.data
        azubi.lehrjahr = form.lehrjahr.data
        db.session.commit()
        flash(f'Azubi {azubi.name} aktualisiert.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler bei {field}: {error}", 'error')
    return redirect(f"{ingress}{url_for('main.personnel')}")

@main_bp.route('/delete_azubi/<int:id>', methods=['POST'])
def delete_azubi(id):
    azubi = Azubi.query.get_or_404(id)
    if azubi.checks:
        flash(f'Fehler: Azubi "{azubi.name}" hat Historie und kann nicht gelöscht werden.', 'error')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.personnel')}")

    db.session.delete(azubi)
    db.session.commit()
    flash(f'Azubi {azubi.name} gelöscht.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.personnel')}")

@main_bp.route('/add_werkzeug', methods=['POST'])
def add_werkzeug():
    form = WerkzeugForm(request.form)
    ingress = request.headers.get('X-Ingress-Path', '')
    if form.validate():
        new_werkzeug = Werkzeug(
            name=form.name.data,
            material_category=form.material_category.data,
            tech_param_label=form.tech_param_label.data
        )
        db.session.add(new_werkzeug)
        db.session.commit()
        flash(f'Werkzeug {form.name.data} hinzugefügt.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler bei {field}: {error}", 'error')
    return redirect(f"{ingress}{url_for('main.tools')}")

@main_bp.route('/api/werkzeug', methods=['POST'])
def api_add_werkzeug():
    """AJAX endpoint for adding werkzeug without page reload"""
    try:
        form = WerkzeugForm(request.form)
        if not form.validate():
            return jsonify({'success': False, 'errors': form.errors}), 400

        new_werkzeug = Werkzeug(
            name=form.name.data,
            material_category=form.material_category.data,
            tech_param_label=form.tech_param_label.data
        )
        db.session.add(new_werkzeug)
        db.session.commit()

        return jsonify({
            'success': True,
            'werkzeug': {
                'id': new_werkzeug.id,
                'name': new_werkzeug.name,
                'category': new_werkzeug.material_category,
                'param': new_werkzeug.tech_param_label or ''
            }
        })
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API add werkzeug error: {e}")
        return jsonify({'success': False, 'error': 'Datenbankfehler beim Hinzufügen des Werkzeugs'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API add werkzeug unexpected error: {e}")
        return jsonify({'success': False, 'error': 'Ein unbekannter Fehler ist aufgetreten.'}), 500

@main_bp.route('/api/azubi', methods=['POST'])
def api_add_azubi():
    """AJAX endpoint for adding azubi without page reload"""
    try:
        form = AzubiForm(request.form)
        if not form.validate():
            return jsonify({'success': False, 'errors': form.errors}), 400

        new_azubi = Azubi(
            name=form.name.data,
            lehrjahr=form.lehrjahr.data
        )
        db.session.add(new_azubi)
        db.session.commit()

        return jsonify({
            'success': True,
            'azubi': {
                'id': new_azubi.id,
                'name': new_azubi.name,
                'lehrjahr': new_azubi.lehrjahr,
                'is_archived': new_azubi.is_archived
            }
        })
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API add azubi error: {e}")
        return jsonify({'success': False, 'error': 'Datenbankfehler beim Hinzufügen des Azubis'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API add azubi unexpected error: {e}")
        return jsonify({'success': False, 'error': 'Ein unbekannter Fehler ist aufgetreten.'}), 500

@main_bp.route('/api/examiner', methods=['POST'])
def api_add_examiner():
    """AJAX endpoint for adding examiner without page reload"""
    try:
        form = ExaminerForm(request.form)
        if not form.validate():
            return jsonify({'success': False, 'errors': form.errors}), 400

        new_examiner = Examiner(
            name=form.name.data
        )
        db.session.add(new_examiner)
        db.session.commit()

        return jsonify({
            'success': True,
            'examiner': {
                'id': new_examiner.id,
                'name': new_examiner.name
            }
        })
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API add examiner error: {e}")
        return jsonify({'success': False, 'error': 'Datenbankfehler beim Hinzufügen des Prüfers'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API add examiner unexpected error: {e}")
        return jsonify({'success': False, 'error': 'Ein unbekannter Fehler ist aufgetreten.'}), 500


@main_bp.route('/edit_werkzeug/<int:id>', methods=['POST'])
def edit_werkzeug(id):
    werkzeug = Werkzeug.query.get_or_404(id)
    form = WerkzeugForm(request.form)
    ingress = request.headers.get('X-Ingress-Path', '')
    if form.validate():
        werkzeug.name = form.name.data
        werkzeug.material_category = form.material_category.data
        werkzeug.tech_param_label = form.tech_param_label.data
        db.session.commit()
        flash(f'Werkzeug {werkzeug.name} aktualisiert.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler bei {field}: {error}", 'error')
    return redirect(f"{ingress}{url_for('main.tools')}")

@main_bp.route('/delete_werkzeug/<int:id>', methods=['POST'])
def delete_werkzeug(id):
    werkzeug = Werkzeug.query.get_or_404(id)
    if werkzeug.checks:
        flash(f'Fehler: Werkzeug "{werkzeug.name}" wird in Protokollen verwendet und kann nicht gelöscht werden.', 'error')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.tools')}")

    db.session.delete(werkzeug)
    db.session.commit()
    flash(f'Werkzeug {werkzeug.name} gelöscht.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.tools')}")

@main_bp.route('/upload_logo', methods=['POST'])
@limiter.limit("5 per minute")
def upload_logo():
    ingress = request.headers.get('X-Ingress-Path', '')
    if 'logo' not in request.files:
        flash('Keine Datei ausgewählt', 'danger')
        return redirect(f"{ingress}{url_for('main.settings')}")

    file = request.files['logo']
    if file.filename == '':
        flash('Keine Datei ausgewählt', 'danger')
        return redirect(f"{ingress}{url_for('main.settings')}")

    if file:
        filename_ext = file.filename.rsplit('.', 1)[-1].lower()
        if filename_ext not in ['png', 'jpg', 'jpeg']:
             flash('Ungültige Dateiendung (Nur .png, .jpg, .jpeg).', 'error')
             return redirect(f"{ingress}{url_for('main.settings')}")

        header = file.read(1024)
        file.seek(0)
        is_png = header.startswith(b'\x89PNG\r\n\x1a\n')
        is_jpeg = header.startswith(b'\xff\xd8\xff')

        if not (is_png or is_jpeg):
            flash('Ungültiges Format (Nur PNG/JPG erlaubt).', 'error')
            return redirect(f"{ingress}{url_for('main.settings')}")

        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > 2 * 1024 * 1024:
             flash('Datei zu groß (max. 2MB).', 'error')
             return redirect(f"{ingress}{url_for('main.settings')}")

        # SECURITY FIX #2: Use secure_filename() to prevent path traversal
        from werkzeug.utils import secure_filename

        # Always save as 'logo.png' but sanitize for safety
        filename = secure_filename('logo.png')

        # Use get_data_dir() for consistency with logo display check
        data_dir = get_data_dir()
        img_folder = os.path.join(data_dir, 'static', 'img')
        os.makedirs(img_folder, exist_ok=True)
        file.save(os.path.join(img_folder, filename))

        flash('Logo erfolgreich hochgeladen', 'success')

    return redirect(f"{ingress}{url_for('main.settings')}")


@main_bp.route('/generate_qr_codes')
def generate_qr_codes():
    tools = Werkzeug.query.order_by(Werkzeug.name).all()
    if not tools:
        flash('Keine Werkzeuge vorhanden.', 'warning')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.settings')}")

    try:
        pdf = generate_qr_codes_pdf(tools)
        response = make_response(bytes(pdf.output(dest='S')))
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=Werkzeug_QRCodes.pdf'
        return response
    except Exception as e:
        current_app.logger.error(f"Error generating QR Codes: {e}")
        flash(f'Fehler beim Erstellen der QR-Codes: {e}', 'danger')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.settings')}")

@main_bp.route('/archive_azubi/<int:id>', methods=['POST'])
def archive_azubi(id):
    azubi = Azubi.query.get_or_404(id)
    assigned_cards = get_assigned_tools(azubi.id)
    if assigned_cards:
        flash(f'Warnung: {azubi.name} hat noch {len(assigned_cards)} Werkzeuge im Besitz! Bitte erst zurückgeben.', 'danger')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.personnel')}")

    azubi.is_archived = True
    db.session.commit()
    flash(f'{azubi.name} wurde archiviert.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.personnel')}")

@main_bp.route('/unarchive_azubi/<int:id>', methods=['POST'])
def unarchive_azubi(id):
    azubi = Azubi.query.get_or_404(id)
    azubi.is_archived = False
    db.session.commit()
    flash(f'{azubi.name} wurde wiederhergestellt.', 'success')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.personnel')}")

@main_bp.route('/report/end_of_training/<int:id>')
def end_of_training_report(id):
    azubi = Azubi.query.get_or_404(id)
    assigned = get_assigned_tools(azubi.id)
    is_clear = (len(assigned) == 0)
    history = Check.query.filter_by(azubi_id=id).order_by(Check.datum.desc()).all()

    try:
        pdf = generate_end_of_training_report(azubi, history, is_clear)
        response = make_response(bytes(pdf.output(dest='S')))
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=Ausbildungsende_{azubi.name}.pdf'
        return response
    except Exception as e:
        current_app.logger.error(f"Error generating Report: {e}")
        flash(f'Fehler beim Erstellen des Berichts: {e}', 'danger')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.manage')}")
