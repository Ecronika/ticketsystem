"""
Check routes.

Handles check submissions, tool exchanges, history views,
session details, and session deletion.
"""
import os
import time
from datetime import datetime

from flask import (
    render_template, request, redirect, url_for,
    flash, current_app, session, send_from_directory, abort
)
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Azubi, Werkzeug, Examiner, Check, CheckType, SystemSettings
from services import CheckService
from routes.utils import get_data_dir, parse_migration_date
from routes.auth import admin_required


def _build_tool_status_list(azubi, werkzeuge, assigned_ids):
    """Build status list for tools."""
    mapped_werkzeuge = []
    for w in werkzeuge:
        last_entry = Check.query.filter_by(
            azubi_id=azubi.id,
            werkzeug_id=w.id).order_by(
            Check.datum.desc()).first()
        status = 'ok'
        tech_val = ""
        manufacturer = ""

        if last_entry:
            manufacturer = last_entry.manufacturer or ""
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
            'last_tech_val': tech_val,
            'last_manufacturer': manufacturer
        })
    return mapped_werkzeuge


def check_azubi(azubi_id):
    """Page to perform a new check."""
    azubi = Azubi.query.get_or_404(azubi_id)
    werkzeuge = Werkzeug.query.all()
    examiners = Examiner.query.all()
    current_date = datetime.now().strftime("%d. %b %Y")

    assigned_ids = CheckService.get_assigned_tools(azubi.id)

    last_check_global = Check.query.filter_by(
        azubi_id=azubi.id).order_by(
        Check.datum.desc()).first()
    days_since_global = (
        datetime.now()
        - last_check_global.datum
    ).days if last_check_global else 999
    is_overdue = days_since_global > 90

    is_overdue = days_since_global > 90

    presets_str = SystemSettings.get_setting(
        'manufacturer_presets',
        'Wera,Wiha,Knipex,Hazet,Stahlwille,Gedore,NWS')
    manufacturer_presets = [
        p.strip() for p in presets_str.split(',') if p.strip()]

    mapped_werkzeuge = _build_tool_status_list(azubi, werkzeuge, assigned_ids)

    return render_template(
        'check.html',
        azubi=azubi,
        werkzeuge=mapped_werkzeuge,
        examiners=examiners,
        current_date=current_date,
        is_overdue=is_overdue,
        manufacturer_presets=manufacturer_presets)


def submit_check():
    """Handle check submission."""
    # pylint: disable=too-many-locals,too-many-return-statements
    azubi_id = request.form.get('azubi_id')
    check_type_str = request.form.get(
        'check_type', CheckType.CHECK.value)
    ingress = request.headers.get('X-Ingress-Path', '')

    try:
        CheckType(check_type_str)
    except ValueError:
        current_app.logger.warning(
            f"Invalid CheckType: {check_type_str}")
        flash('Fehler: Ungültiger Prüfungstyp.', 'error')
        return redirect(
            f"{ingress}{url_for('main.index')}")

    examiner = request.form.get('examiner')

    if not azubi_id or not examiner:
        flash(
            'Fehler: Azubi und Prüfer müssen '
            'angegeben werden.', 'error')
        return redirect(
            f"{ingress}{url_for('main.index')}")

    sig_azubi = request.form.get('signature_azubi_data')
    sig_examiner = request.form.get(
        'signature_examiner_data')
    if not sig_azubi or not sig_examiner:
        flash('Fehler: Unterschriften fehlen.', 'error')
        return redirect(
            f"{ingress}{url_for('main.index')}")

    try:
        check_date = datetime.now()
        if session.get('migration_mode', False):
            check_date, err = parse_migration_date(
                request.form, ingress)
            if err:
                return err

        tool_ids = CheckService.collect_tool_ids(
            request.form)
        if not tool_ids:
            flash('Keine Werkzeuge ausgewählt', 'warning')
            return redirect(
                f"{ingress}{url_for('main.index')}")

        result = CheckService.process_check_submission(
            azubi_id=int(azubi_id),
            examiner_name=examiner,
            tool_ids=tool_ids,
            form_data=request.form,
            check_date=check_date,
            check_type=CheckType(check_type_str)
        )

        flash(
            f'{check_type_str.capitalize()} erfolgreich '
            f'gespeichert! '
            f'(Session: {result["session_id"]})',
            'success')

        CheckService.invalidate_cache(int(azubi_id))
        return redirect(
            f"{ingress}{url_for('main.index')}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            f"Error in submit_check: {e}",
            exc_info=True)
        flash(
            f'Fehler beim Speichern: {str(e)}',
            'danger')
        return redirect(
            f"{ingress}{url_for('main.index')}")


def exchange_tool():
    """Handle one-click tool exchange."""
    azubi_id = request.form.get('azubi_id')
    tool_id = request.form.get('tool_id')
    reason = request.form.get('reason')
    is_payable = request.form.get('is_payable') == 'on'
    signature_data = request.form.get(
        'signature_azubi_data')
    ingress = request.headers.get('X-Ingress-Path', '')

    if not all([azubi_id, tool_id, reason,
                signature_data]):
        flash(
            'Fehler: Unvollständige Daten '
            'für Austausch.', 'error')
        return redirect(
            f"{ingress}{url_for('main.index')}")

    try:
        result = CheckService.process_tool_exchange(
            azubi_id=int(azubi_id),
            tool_id=int(tool_id),
            reason=reason,
            is_payable=is_payable,
            signature_data=signature_data
        )
        CheckService.invalidate_cache(int(azubi_id))

        msg = 'Werkzeug erfolgreich ausgetauscht.'
        if result.get('price'):
            msg += f" (Geschätzte Kosten: {result['price']:.2f} €)"

        flash(msg, 'success')
        return redirect(
            f"{ingress}{url_for('main.index')}")

    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            f"Exchange failed: {e}", exc_info=True)
        flash(
            f'Fehler beim Austausch: {str(e)}',
            'error')
        return redirect(
            f"{ingress}{url_for('main.index')}")


def history():
    """Show check history."""
    start_time = time.time()
    azubi_id = request.args.get('azubi_id')

    try:
        query = Check.query.order_by(Check.datum.desc())
        if azubi_id and azubi_id != 'all':
            query = query.filter_by(
                azubi_id=int(azubi_id))

        query_start = time.time()
        all_checks = query.options(
            joinedload(Check.azubi)).limit(2000).all()
        query_duration = time.time() - query_start
        current_app.logger.info(
            f"History query: {len(all_checks)} checks "
            f"in {query_duration:.3f}s")

        azubis = Azubi.query.order_by(Azubi.name).all()

        group_start = time.time()
        sessions = (
            CheckService.group_checks_into_sessions(
                all_checks))
        group_duration = time.time() - group_start

        total_duration = time.time() - start_time
        current_app.logger.info(
            f"History: {total_duration:.3f}s "
            f"(q:{query_duration:.3f}s, "
            f"g:{group_duration:.3f}s)")

        return render_template(
            'history.html',
            sessions=sessions,
            azubis=azubis,
            selected_azubi_id=(
                int(azubi_id)
                if azubi_id and azubi_id != 'all'
                else None))

    except SQLAlchemyError as e:
        current_app.logger.error(
            f"DB error in history: {e}",
            exc_info=True)
        flash('Fehler beim Laden der Historie',
              'danger')
        return redirect(url_for('main.index'))
    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            f"Error in history: {e}", exc_info=True)
        flash(f'Fehler: {str(e)}', 'danger')
        return redirect(url_for('main.index'))


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
        flash('Prüfung nicht gefunden.', 'error')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.history')}")

    first_c = checks[0]
    check_type = (
        CheckService.detect_exchange_type(checks)
        or first_c.check_type)

    parsed_checks = []
    global_bemerkung = ""

    for c in checks:
        status_code, comment = (
            CheckService.parse_check_bemerkung(
                c.bemerkung))
        if comment and not global_bemerkung:
            global_bemerkung = comment

        parsed_checks.append({
            'werkzeug': c.werkzeug.name,
            'status': status_code,
            'tech_label': c.werkzeug.tech_param_label,
            'tech_value': c.tech_param_value,
            'incident_reason': c.incident_reason
        })

    return render_template(
        'history_details.html',
        azubi=first_c.azubi,
        datum=first_c.datum.strftime(
            "%d. %b %Y %H:%M"),
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


@admin_required
def delete_session(session_id):
    """Delete a check session (migration mode only)."""
    ingress = request.headers.get('X-Ingress-Path', '')

    if not session.get('migration_mode', False):
        current_app.logger.warning(
            f"Delete session attempted WITHOUT "
            f"migration mode: {session_id}")
        flash(
            '⚠️ Session-Löschung nur im '
            'Migration-Modus erlaubt!', 'danger')
        return redirect(
            f"{ingress}{url_for('main.history')}")

    try:
        if session_id.startswith("LEGACY_"):
            flash(
                'Legacy-Sessions können noch nicht '
                'gelöscht werden.', 'warning')
            return redirect(
                f"{ingress}{url_for('main.history')}")

        checks = Check.query.filter_by(
            session_id=session_id).all()

        if not checks:
            current_app.logger.warning(
                f"Delete session not found: "
                f"{session_id}")
            flash('Session nicht gefunden.', 'warning')
            return redirect(
                f"{ingress}{url_for('main.history')}")

        first = checks[0]
        azubi_name = first.azubi.name
        azubi_id_val = first.azubi_id
        datum = first.datum
        examiner = first.examiner or 'Unbekannt'
        check_count = len(checks)

        files_to_delete = [
            p for p in [
                first.report_path,
                first.signature_azubi,
                first.signature_examiner] if p
        ]

        for check_entry in checks:
            db.session.delete(check_entry)
        CheckService.invalidate_cache(azubi_id_val)
        db.session.commit()

        deleted_count = (
            CheckService.cleanup_session_files(
                files_to_delete))

        current_app.logger.warning(
            f"SESSION DELETED | sid={session_id} | "
            f"azubi={azubi_name}(id:{azubi_id_val}) | "
            f"datum="
            f"{datum.strftime('%Y-%m-%d %H:%M')} | "
            f"examiner={examiner} | "
            f"checks={check_count} | "
            f"files={deleted_count}")

        flash(
            f'Session gelöscht. {check_count} Einträge '
            f'entfernt. {deleted_count} Dateien '
            f'bereinigt.', 'success')
        return redirect(
            f"{ingress}{url_for('main.history')}")

    except SQLAlchemyError as e:
        db.session.rollback()
        db.session.remove()
        current_app.logger.error(
            f"DB error deleting session "
            f"{session_id}: {e}", exc_info=True)
        flash(
            'Datenbankfehler beim Löschen.',
            'danger')
        return redirect(
            f"{ingress}{url_for('main.history_details', session_id=session_id)}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        db.session.remove()
        current_app.logger.error(
            f"Error deleting session "
            f"{session_id}: {e}", exc_info=True)
        flash(
            f'❌ Fehler beim Löschen: {str(e)}',
            'danger')
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
        '/history_details/<path:session_id>',
        view_func=history_details)
    bp.add_url_rule(
        '/download_report/<path:filename>',
        view_func=download_report)
    bp.add_url_rule(
        '/delete_session/<path:session_id>',
        view_func=delete_session,
        methods=['POST'])
