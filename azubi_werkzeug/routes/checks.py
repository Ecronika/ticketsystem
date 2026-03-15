"""
Check routes.

Handles check submissions, tool exchanges, history views,
session details, and session deletion.
"""
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from metrics import CHECKS_SUBMITTED_TOTAL, SCANS_TOTAL
from models import Azubi, Check, Examiner, SystemSettings, Werkzeug
from enums import CheckType
from exceptions import AzubiWerkzeugError, ValidationError
from app_state import is_migration_active
from routes.auth import admin_required
from routes.utils import get_data_dir, parse_migration_date
from services import CheckService, HistoryService, ExchangeService


def _parse_last_entry_status(last_entry):
    """Extract status, tech_val, manufacturer and incident_reason from a Check entry."""
    status, tech_val, manufacturer, incident_reason = 'ok', '', '', ''
    if last_entry:
        manufacturer = last_entry.manufacturer or ''
        incident_reason = last_entry.incident_reason or ''
        if last_entry.bemerkung:
            for p in last_entry.bemerkung.split('|'):
                if p.strip().startswith('Status:'):
                    status = p.replace('Status:', '').strip()
                    break
        if last_entry.tech_param_value:
            tech_val = last_entry.tech_param_value
    return status, tech_val, manufacturer, incident_reason


def _build_tool_status_list(azubi, werkzeuge, assigned_ids):
    """Build status list for tools."""
    subq = (
        db.session.query(
            Check.werkzeug_id,
            func.max(Check.datum).label('last_datum')
        )
        .filter_by(azubi_id=azubi.id)
        .group_by(Check.werkzeug_id)
        .subquery()
    )
    last_checks = {
        c.werkzeug_id: c
        for c in Check.query
        .join(subq, (Check.werkzeug_id == subq.c.werkzeug_id) &
              (Check.datum == subq.c.last_datum))
        .filter(Check.azubi_id == azubi.id)
        .all()
    }

    mapped_werkzeuge = []
    for w in werkzeuge:
        status, tech_val, manufacturer, incident_reason = _parse_last_entry_status(
            last_checks.get(w.id))
        mapped_werkzeuge.append({
            'obj': w,
            'is_assigned': w.id in assigned_ids,
            'last_status': status,
            'last_tech_val': tech_val,
            'last_manufacturer': manufacturer,
            'last_incident_reason': incident_reason
        })
    return mapped_werkzeuge


def check_azubi(azubi_id):
    """Page to perform a new check."""
    azubi = db.get_or_404(Azubi, azubi_id)
    werkzeuge = Werkzeug.query.all()
    examiners = Examiner.query.all()
    current_date = datetime.now(timezone.utc).strftime("%d. %b %Y")

    assigned_ids = CheckService.get_assigned_tools(azubi.id)

    last_check_global = Check.query.filter_by(
        azubi_id=azubi.id).order_by(
        Check.datum.desc()).first()

    if last_check_global:
        last_datum = last_check_global.datum
        if last_datum and last_datum.tzinfo is None:
            last_datum = last_datum.replace(tzinfo=timezone.utc)
        days_since_global = (datetime.now(timezone.utc) - last_datum).days
    else:
        days_since_global = 999

    is_overdue = days_since_global > 90

    presets_str = SystemSettings.get_setting(
        'manufacturer_presets',
        'Wera,Wiha,Knipex,Hazet,Stahlwille,Gedore,NWS')
    manufacturer_presets = [
        p.strip() for p in presets_str.split(',') if p.strip()]

    mapped_werkzeuge = _build_tool_status_list(azubi, werkzeuge, assigned_ids)

    # Track that a QR Code scan successfully landed on the check page
    SCANS_TOTAL.inc()

    return render_template(
        'check.html',
        azubi=azubi,
        werkzeuge=mapped_werkzeuge,
        examiners=examiners,
        current_date=current_date,
        current_date_iso=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        is_overdue=is_overdue,
        manufacturer_presets=manufacturer_presets)


def _validate_signatures(form, is_migration):
    """Return error tuple if signatures are missing and not in migration mode."""
    sig_azubi = form.get('signature_azubi_data')
    sig_examiner = form.get('signature_examiner_data')
    if (not sig_azubi or not sig_examiner) and not is_migration:
        return ('Fehler: Unterschriften fehlen.', 'error')
    return None


def _validate_check_submission(form):
    """Validate check submission form data."""
    azubi_id = form.get('azubi_id')
    check_type_str = form.get('check_type', CheckType.CHECK.value)
    examiner = form.get('examiner')

    try:
        CheckType(check_type_str)
    except ValueError:
        return None, ('Fehler: UngÃƒÂ¼ltiger PrÃƒÂ¼fungstyp.', 'error')

    if not azubi_id or not examiner:
        return None, ('Fehler: Azubi und PrÃƒÂ¼fer mÃƒÂ¼ssen angegeben werden.', 'error')

    sig_error = _validate_signatures(form, is_migration_active())
    if sig_error:
        return None, sig_error

    tool_ids = CheckService.collect_tool_ids(form)
    if not tool_ids:
        return None, ('Keine Werkzeuge ausgewÃƒÂ¤hlt', 'warning')

    return tool_ids, None


def submit_check():
    """Handle check submission."""
    # pylint: disable=too-many-locals,too-many-return-statements
    azubi_id = request.form.get('azubi_id')
    check_type_str = request.form.get(
        'check_type', CheckType.CHECK.value)
    examiner = request.form.get('examiner')
    ingress = request.headers.get('X-Ingress-Path', '')

    # Validation
    tool_ids, error = _validate_check_submission(request.form)
    if error:
        flash(error[0], error[1])
        # UX Fix: Redirect back to the check page if validation fails to keep context
        if azubi_id:
            return redirect(f"{ingress}{url_for('main.check_azubi', azubi_id=azubi_id)}")
        return redirect(f"{ingress}{url_for('main.index')}")

    try:
        check_date = datetime.now(timezone.utc)
        if is_migration_active():
            check_date, err = parse_migration_date(
                request.form, ingress)
            if err:
                return err

        try:
            safe_azubi_id = int(azubi_id)
        except (TypeError, ValueError):
            flash('UngÃƒÂ¼ltige Azubi ID.', 'error')
            return redirect(f"{ingress}{url_for('main.index')}")

        try:
            result = CheckService.process_check_submission(
                azubi_id=safe_azubi_id,
                examiner_name=examiner,
                tool_ids=tool_ids,
                form_data=request.form,
                check_date=check_date,
                check_type=CheckType(check_type_str)
            )

            # Track successful check submission in Prometheus
            CHECKS_SUBMITTED_TOTAL.labels(check_type=check_type_str).inc()

            flash(
                f'{check_type_str.capitalize()} erfolgreich '
                f'gespeichert! '
                f'(Session: {result["session_id"]})',
                'success')

            return redirect(
                f"{ingress}{url_for('main.index')}")
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(f"{ingress}{url_for('checks.submit_check', azubi_id=azubi_id, type=check_type_str)}")
        except AzubiWerkzeugError as e:
            flash(f"Fehler: {e}", "error")
            current_app.logger.error("Check submission error: %s", e)
            return redirect(f"{ingress}{url_for('main.index')}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            "Error in submit_check: %s", e,
            exc_info=True)
        flash(
            f'Fehler beim Speichern: {str(e)}',
            'danger')
        return redirect(
            f"{ingress}{url_for('main.index')}")


def exchange_tool():
    """Handle one-click tool exchange (Bulk mass processing)."""
    import json  # pylint: disable=import-outside-toplevel
    azubi_id = request.form.get('azubi_id')
    exchange_data_json = request.form.get('exchange_data')
    is_payable = request.form.get('is_payable') == 'on'
    signature_data = request.form.get('signature_azubi_data')
    ingress = request.headers.get('X-Ingress-Path', '')

    if not all([azubi_id, exchange_data_json, signature_data]):
        flash('Fehler: UnvollstÃƒÂ¤ndige Daten fÃƒÂ¼r Austausch.', 'error')
        return redirect(f"{ingress}{url_for('main.index')}")

    try:
        exchange_data = json.loads(exchange_data_json)
        if not exchange_data:
            flash('Fehler: Keine Werkzeuge ausgewÃƒÂ¤hlt.', 'error')
            return redirect(f"{ingress}{url_for('main.index')}")

        try:
            safe_azubi_id = int(azubi_id)
        except (TypeError, ValueError):
            flash('UngÃƒÂ¼ltige Azubi ID.', 'error')
            return redirect(f"{ingress}{url_for('main.index')}")

        try:
            result = ExchangeService.process_tool_exchange_batch(
                azubi_id=safe_azubi_id,
                exchange_data=exchange_data,
                is_payable=is_payable,
                signature_data=signature_data
            )

            # Track successful exchange in Prometheus for the batch
            CHECKS_SUBMITTED_TOTAL.labels(
                check_type='exchange').inc(amount=len(exchange_data))

            msg = f"{len(exchange_data)} Werkzeuge erfolgreich ausgetauscht."
            if result.get('total_price'):
                msg += f" (GeschÃƒÂ¤tzte Kosten: {result['total_price']:.2f} EUR)"

            flash(msg, 'success')
            return redirect(f"{ingress}{url_for('main.index')}")
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(f"{ingress}{url_for('main.index')}")
        except AzubiWerkzeugError as e:
            flash(f"Fehler beim Austausch: {e}", "error")
            current_app.logger.error("Exchange error: %s", e)
            return redirect(f"{ingress}{url_for('main.index')}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            f"Error in exchange_tool: {e}", exc_info=True)
        flash(
            f'Systemfehler beim Austausch: {str(e)}',
            'error')
        return redirect(
            f"{ingress}{url_for('main.index')}")


def history():
    """Show check history."""
    start_time = time.time()
    azubi_id = request.args.get('azubi_id')

    try:
        page = request.args.get('page', 1, type=int)

        query = Check.query.order_by(Check.datum.desc())
        if azubi_id and azubi_id != 'all':
            query = query.filter_by(
                azubi_id=int(azubi_id))

        query_start = time.time()

        # New server-side pagination (100 items per page)
        pagination = query.options(
            joinedload(Check.azubi),
            joinedload(Check.werkzeug)
        ).paginate(
            page=page, per_page=100, error_out=False
        )
        all_checks = pagination.items

        query_duration = time.time() - query_start
        current_app.logger.info(
            "History query (Page %s): %s checks in %.3fs",
            page, len(all_checks), query_duration)

        azubis = Azubi.query.order_by(Azubi.name).all()

        group_start = time.time()
        sessions = (
            HistoryService.group_checks_into_sessions(
                all_checks))
        group_duration = time.time() - group_start

        total_duration = time.time() - start_time
        current_app.logger.info(
            "History: %.3fs (q:%.3fs, g:%.3fs)",
            total_duration, query_duration, group_duration)

        safe_selected_id = None
        if azubi_id and azubi_id != 'all':
            try:
                safe_selected_id = int(azubi_id)
            except (ValueError, TypeError):
                safe_selected_id = None

        return render_template(
            'history.html',
            sessions=sessions,
            azubis=azubis,
            pagination=pagination,
            total_count=pagination.total,
            selected_azubi_id=safe_selected_id)

    except SQLAlchemyError as e:
        current_app.logger.error(
            "Error in tool exchange: %s", e,
            exc_info=True)
        flash('Fehler beim Laden der Historie',
              'danger')
        return redirect(url_for('main.index'))
    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            "Error in history: %s", e, exc_info=True)
        flash(f'Fehler: {str(e)}', 'danger')
        return redirect(url_for('main.index'))


def api_history():
    """Serve history 'Load More' data via API."""
    azubi_id = request.args.get('azubi_id')
    page = request.args.get('page', 1, type=int)

    try:
        query = Check.query.order_by(Check.datum.desc())
        if azubi_id and azubi_id != 'all':
            try:
                query = query.filter_by(azubi_id=int(azubi_id))
            except (ValueError, TypeError):
                pass

        pagination = query.options(
            joinedload(Check.azubi),
        ).paginate(
            page=page, per_page=100, error_out=False
        )
        all_checks = pagination.items
        sessions = HistoryService.group_checks_into_sessions(all_checks)

        is_admin = session.get('is_admin', False)

        for session_item in sessions:
            # RBAC: Remove price if not admin
            if not is_admin:
                session_item['total_price'] = 0.0
                session_item['is_payable'] = False  # Optional: hide flag too

        for session_item in sessions:
            dt = session_item['datum']
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_local = dt.astimezone(ZoneInfo('Europe/Berlin'))
            session_item['datum_formatted'] = dt_local.strftime('%d.%m.%Y')
            session_item['time_formatted'] = dt_local.strftime('%H:%M')
            session_item['datum'] = dt_local.isoformat()  # JSON serialization

        return jsonify({
            'success': True,
            'sessions': sessions,
            'has_next': pagination.has_next,
            'next_page': pagination.next_num,
            'total': pagination.total
        })

    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(f"Error in api_history: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


def _parse_session_checks(checks):
    """Parse a list of Check records into display dicts."""
    parsed, global_bemerkung = [], ''
    for c in checks:
        status_code, comment = CheckService.parse_check_bemerkung(c.bemerkung)
        if comment and not global_bemerkung:
            global_bemerkung = comment
        parsed.append({
            'werkzeug': c.werkzeug.name,
            'status': status_code,
            'tech_label': c.werkzeug.tech_param_label,
            'tech_value': c.tech_param_value,
            'incident_reason': c.incident_reason
        })
    return parsed, global_bemerkung


def history_details(session_id):
    """Show details of a specific check session."""
    # DoS Protection: Limit session_id length
    if len(session_id) > 64:
        abort(400, "Session ID too long")

    if session_id.startswith("LEGACY_"):
        _, azubi_id_str, timestamp_str = (
            session_id.split('_'))
        target_time = datetime.fromtimestamp(
            float(timestamp_str))
        checks = Check.query.filter_by(
            azubi_id=int(azubi_id_str),
            datum=target_time).all()
    else:
        checks = Check.query.filter_by(
            session_id=session_id).options(
            joinedload(Check.werkzeug),
            joinedload(Check.azubi)).all()

    if not checks:
        flash('PrÃƒÂ¼fung nicht gefunden.', 'error')
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.history')}")

    first_c = checks[0]
    raw_type = CheckService.detect_exchange_type(checks) or first_c.check_type
    check_type = raw_type.value if hasattr(raw_type, 'value') else raw_type
    parsed_checks, global_bemerkung = _parse_session_checks(checks)

    # Localize datum for template
    dt = first_c.datum
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone(ZoneInfo('Europe/Berlin'))

    return render_template(
        'history_details.html',
        azubi=first_c.azubi,
        datum=dt_local.strftime("%d. %b %Y %H:%M"),
        checks=parsed_checks,
        global_bemerkung=global_bemerkung,
        check_type=check_type,
        examiner=first_c.examiner,
        report_path=first_c.report_path,
        session_id=session_id)


def download_report(filename):
    """Download a PDF report."""
    data_dir = get_data_dir()
    reports_dir = os.path.join(data_dir, 'reports')
    return send_from_directory(
        reports_dir, filename, as_attachment=True)


def _collect_session_files(first_check):
    """Collect file paths associated with a session for deletion."""
    return [p for p in [
        first_check.report_path,
        first_check.signature_azubi,
        first_check.signature_examiner
    ] if p]


def _log_session_deleted(session_id, azubi_name, azubi_id_val,
                         datum, examiner, check_count, deleted_count):
    """Emit a structured WARNING for a deleted check session."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    current_app.logger.warning(
        "SESSION DELETED | sid=%s | azubi=%s(id:%s) | datum=%s |"
        " examiner=%s | checks=%s | files=%s",
        session_id, azubi_name, azubi_id_val,
        datum.strftime('%Y-%m-%d %H:%M'),
        examiner, check_count, deleted_count,
    )


@admin_required
def delete_session(session_id):
    """Delete a check session (migration mode only)."""
    ingress = request.headers.get('X-Ingress-Path', '')

    if not is_migration_active():
        current_app.logger.warning(
            "Delete session attempted WITHOUT migration mode: %s", session_id)
        flash('Ã¢Å¡Â Ã¯Â¸Â Session-LÃƒÂ¶schung nur im Migration-Modus erlaubt!', 'danger')
        return redirect(f"{ingress}{url_for('main.history')}")

    try:
        if session_id.startswith("LEGACY_"):
            flash('Legacy-Sessions kÃƒÂ¶nnen noch nicht gelÃƒÂ¶scht werden.', 'warning')
            return redirect(f"{ingress}{url_for('main.history')}")

        checks = Check.query.filter_by(session_id=session_id).all()

        if not checks:
            current_app.logger.warning(
                "Delete session not found: %s", session_id)
            flash('Session nicht gefunden.', 'warning')
            return redirect(f"{ingress}{url_for('main.history')}")

        first = checks[0]
        azubi_name = first.azubi.name
        azubi_id_val = first.azubi_id
        datum = first.datum
        examiner = first.examiner or 'Unbekannt'
        check_count = len(checks)
        files_to_delete = _collect_session_files(first)

        for check_entry in checks:
            db.session.delete(check_entry)
        db.session.commit()

        deleted_count = CheckService.cleanup_session_files(files_to_delete)
        _log_session_deleted(
            session_id, azubi_name, azubi_id_val,
            datum, examiner, check_count, deleted_count)

        flash(
            f'Session gelÃƒÂ¶scht. {check_count} EintrÃƒÂ¤ge '
            f'entfernt. {deleted_count} Dateien bereinigt.', 'success')
        return redirect(f"{ingress}{url_for('main.history')}")

    except SQLAlchemyError as e:
        db.session.rollback()
        db.session.remove()
        current_app.logger.error(
            "DB error deleting session %s: %s", session_id, e, exc_info=True)
        flash('Datenbankfehler beim LÃƒÂ¶schen.', 'danger')
        return redirect(
            f"{ingress}{url_for('main.history_details', session_id=session_id)}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        db.session.remove()
        current_app.logger.error(
            "Error deleting session %s: %s", session_id, e, exc_info=True)
        flash(f'Ã¢ÂÅ’ Fehler beim LÃƒÂ¶schen: {str(e)}', 'danger')
        return redirect(
            f"{ingress}{url_for('main.history_details', session_id=session_id)}")


def register_routes(bp):
    """Register check-related routes on the given blueprint."""
    bp.add_url_rule(
        '/check/<int:azubi_id>',
        view_func=check_azubi,
        methods=['GET'])
    bp.add_url_rule(
        '/submit_check',
        view_func=submit_check,
        methods=['POST'])
    bp.add_url_rule(
        '/exchange_tool',
        view_func=exchange_tool,
        methods=['POST'])
    bp.add_url_rule(
        '/history',
        view_func=history)
    bp.add_url_rule(
        '/api/history',
        view_func=api_history,
        methods=['GET'])
    bp.add_url_rule(
        '/history_details/<path:session_id>',
        view_func=history_details)
    bp.add_url_rule(
        '/download_report/<path:filename>',
        view_func=download_report)
    bp.add_url_rule(
        '/delete_session/<path:session_id>',
        view_func=delete_session,
        methods=['POST'])
