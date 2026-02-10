from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, Response, jsonify
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError  # Issue #4: Error handling
from extensions import db, limiter
from models import Azubi, Werkzeug, Examiner, Check
from forms import AzubiForm, ExaminerForm, WerkzeugForm
from datetime import datetime, timedelta
import os
import uuid
import base64
from pdf_utils import generate_handover_pdf, generate_qr_codes_pdf, generate_end_of_training_report

main_bp = Blueprint('main', __name__)

@main_bp.context_processor
def inject_ingress_path():
    ingress = request.headers.get('X-Ingress-Path', '')
    
    # Add logo version for cache busting
    data_dir = current_app.config.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
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

def get_data_dir():
    # Retrieve data_dir from app config or calculate it
    return current_app.config.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))

def get_assigned_tools(azubi_id):
    """Calculates currently assigned tools for an Azubi based on history."""
    checks = Check.query.filter_by(azubi_id=azubi_id).order_by(Check.datum.asc()).all()
    assigned = set()
    
    for c in checks:
        if c.check_type == 'issue':
            assigned.add(c.werkzeug_id)
        elif c.check_type == 'return':
            if c.werkzeug_id in assigned:
                assigned.remove(c.werkzeug_id)
    return list(assigned)

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

@main_bp.route('/')
def index():
    azubis = Azubi.query.filter_by(is_archived=False).order_by(Azubi.name).all()
    
    dashboard_data = []
    
    for azubi in azubis:
        last_check = Check.query.filter_by(azubi_id=azubi.id).order_by(Check.datum.desc()).first()
        
        status = "Unbekannt"
        status_class = "secondary"
        last_check_str = "Noch nie"
        sort_order = 4
        
        if last_check:
            last_check_str = last_check.datum.strftime("%d. %b %Y")
            days_since = (datetime.now() - last_check.datum).days
            
            if days_since >= 90:
                status = "Überfällig (> 3 Mon.)"
                status_class = "danger"
                last_check_str = f"Vor {days_since} Tagen"
                sort_order = 1
            elif days_since >= 62:
                status = "Prüfung fällig (< 4 Wochen)"
                status_class = "warning"
                last_check_str = f"Vor {days_since} Tagen"
                sort_order = 2
            else:
                status = "Geprüft"
                status_class = "success"
                sort_order = 3
        else:
            status = "Neu / Leer"
            status_class = "info"
            sort_order = 4
        
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
    azubi_id = request.form.get('azubi_id')
    bemerkung_global = request.form.get('bemerkung')
    check_type = request.form.get('check_type', 'check')
    examiner = request.form.get('examiner')
    ingress = request.headers.get('X-Ingress-Path', '')
    
    if not azubi_id or not examiner:
        flash('Fehler: Azubi und Prüfer müssen angegeben werden.', 'error')
        return redirect(f"{ingress}{url_for('main.index')}")

    sig_azubi_data = request.form.get('signature_azubi_data')
    sig_examiner_data = request.form.get('signature_examiner_data')
    
    data_dir = get_data_dir()
    session_id = str(uuid.uuid4())
    sig_azubi_path = None
    sig_examiner_path = None
    
    # --- Migration Mode Logic ---
    is_migration = session.get('migration_mode', False)
    check_date = datetime.now()
    skip_sig = False

    if is_migration:
        c_date = request.form.get('custom_date')
        c_time = request.form.get('custom_time')
        skip_sig = request.form.get('skip_signature') == 'yes'
        
        if c_date and c_time:
            try:
                check_date = datetime.strptime(f"{c_date} {c_time}", "%Y-%m-%d %H:%M")
            except ValueError:
                pass # Fallback to now
        elif c_date:
             try:
                check_date = datetime.strptime(f"{c_date} 12:00", "%Y-%m-%d %H:%M")
             except ValueError:
                pass

    # Save Signatures (if not skipped and data present)
    if not skip_sig:
        if sig_azubi_data and ',' in sig_azubi_data:
            header, encoded = sig_azubi_data.split(",", 1)
            data = base64.b64decode(encoded)
            path = os.path.join(data_dir, 'signatures', f"{session_id}_azubi.png")
            with open(path, "wb") as f:
                f.write(data)
            sig_azubi_path = path

        if sig_examiner_data and ',' in sig_examiner_data:
            header, encoded = sig_examiner_data.split(",", 1)
            data = base64.b64decode(encoded)
            path = os.path.join(data_dir, 'signatures', f"{session_id}_examiner.png")
            with open(path, "wb") as f:
                f.write(data)
            sig_examiner_path = path
    selected_tools = []
    werkzeuge = Werkzeug.query.all()
    reports_to_create = []

    for werkzeug in werkzeuge:
        status = request.form.get(f'tool_{werkzeug.id}')
        
        if status:
            tech_val = request.form.get(f'tech_param_{werkzeug.id}')
            incident_reason = request.form.get(f'incident_reason_{werkzeug.id}') 
            
            full_bemerkung = f"Status: {status}"
            if bemerkung_global:
                full_bemerkung += f" | {bemerkung_global}"
            
            new_check = Check(
                session_id=session_id,
                azubi_id=azubi_id, 
                werkzeug_id=werkzeug.id, 
                bemerkung=full_bemerkung,
                tech_param_value=tech_val,
                incident_reason=incident_reason,
                datum=check_date,
                check_type=check_type,
                examiner=examiner,
                signature_azubi=sig_azubi_path,
                signature_examiner=sig_examiner_path
            )
            db.session.add(new_check)
            reports_to_create.append(new_check)
            
            selected_tools.append({
                'id': werkzeug.id,
                'name': werkzeug.name,
                'category': werkzeug.material_category,
                'status': status
            })

    if selected_tools:
        azubi = Azubi.query.get(azubi_id)
        pdf_filename = f"Protokoll_{check_type}_{azubi.name.replace(' ', '_')}_{check_date.strftime('%Y%m%d_%H%M')}.pdf"
        pdf_path = os.path.join(data_dir, 'reports', pdf_filename)
        
        generate_handover_pdf(
            azubi_name=azubi.name, 
            examiner_name=examiner, 
            tools=selected_tools, 
            check_type=check_type, 
            signature_paths={'azubi': sig_azubi_path, 'examiner': sig_examiner_path},
            output_path=pdf_path
        )
        
        for record in reports_to_create:
            record.report_path = pdf_path

    db.session.commit()
    flash(f'{check_type.capitalize()} erfolgreich gespeichert! PDF erstellt.', 'success')
    return redirect(f"{ingress}{url_for('main.index')}")

@main_bp.route('/history')
def history():
    azubi_id = request.args.get('azubi_id')
    query = Check.query.order_by(Check.datum.desc())
    
    if azubi_id and azubi_id != 'all':
        query = query.filter_by(azubi_id=int(azubi_id))
        
    all_checks = query.options(joinedload(Check.azubi)).limit(2000).all()
    azubis = Azubi.query.order_by(Azubi.name).all()
    
    sessions = []
    seen_sessions = set()
    
    for check in all_checks:
        sid = check.session_id
        if not sid:
            sid = f"{check.azubi_id}_{check.datum.timestamp()}"
            
        if sid not in seen_sessions:
            seen_sessions.add(sid)
            
            if check.session_id:
                session_checks = [c for c in all_checks if c.session_id == sid]
            else:
                session_checks = [c for c in all_checks if c.azubi_id == check.azubi_id and c.datum == check.datum]
            
            is_ok = True
            for c in session_checks:
                if "Status: missing" in (c.bemerkung or "") or "Status: broken" in (c.bemerkung or ""):
                    is_ok = False
                    break
            
            sessions.append({
                'session_id': check.session_id if check.session_id else "LEGACY_" + sid,
                'datum': check.datum,
                'azubi_name': check.azubi.name,
                'is_ok': is_ok,
                'count': len(session_checks)
            })
            
    return render_template('history.html', sessions=sessions, azubis=azubis, selected_azubi_id=int(azubi_id) if azubi_id and azubi_id != 'all' else None)

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

    return render_template('history_details.html', azubi=azubi, datum=datum, checks=parsed_checks, global_bemerkung=global_bemerkung, check_type=check_type, examiner=examiner, report_path=report_path)

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
    
    # Query azubis
    query = Azubi.query.order_by(Azubi.name)
    if not show_archived:
        query = query.filter_by(is_archived=False)
    
    azubi_pagination = query.paginate(page=azubi_page, per_page=per_page, error_out=False)
    azubis = azubi_pagination.items
    
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
    
    return render_template('settings.html', logo_exists=logo_exists)

@main_bp.route('/toggle_migration_mode', methods=['POST'])
def toggle_migration_mode():
    current_mode = session.get('migration_mode', False)
    session['migration_mode'] = not current_mode
    status = "aktiviert" if session['migration_mode'] else "deaktiviert"
    flash(f'Migration Modus wurde {status}.', 'info')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.settings')}")

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
        return jsonify({'success': False, 'error': str(e)}), 500

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
        return jsonify({'success': False, 'error': str(e)}), 500

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
        return jsonify({'success': False, 'error': str(e)}), 500


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
