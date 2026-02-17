"""
Admin routes.

Handles personnel management, tool management, settings,
backups, migration mode, logo upload, QR codes, and reports.
"""
import os
import time

from flask import (
    render_template, request, redirect, url_for,
    flash, current_app, session, make_response,
    send_from_directory
)
from werkzeug.utils import secure_filename

from extensions import db, limiter
from models import Azubi, Werkzeug, Examiner, Check, SystemSettings
from forms import AzubiForm, ExaminerForm, WerkzeugForm
from services import CheckService, BackupService
from routes.utils import get_data_dir
from pdf_utils import (
    generate_qr_codes_pdf, generate_end_of_training_report
)


def manage():
    """Redirect /manage → /tools for backward compat."""
    return redirect(url_for('main.tools'))


def tools():
    """Tools management page."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    werkzeuge_pagination = Werkzeug.query.order_by(
        Werkzeug.name).paginate(
        page=page, per_page=per_page, error_out=False)
    werkzeuge = werkzeuge_pagination.items
    return render_template(
        'tools.html',
        werkzeuge=werkzeuge,
        werkzeuge_pagination=werkzeuge_pagination)


def personnel():
    """Personnel management page."""
    azubi_page = request.args.get(
        'azubi_page', 1, type=int)
    show_archived = (
        request.args.get('show_archived', '0') == '1')
    per_page = 20
    query = Azubi.query.order_by(Azubi.name)

    if not show_archived:
        query = query.filter_by(is_archived=False)

    try:
        azubi_pagination = query.paginate(
            page=azubi_page, per_page=per_page,
            error_out=False)

        if (azubi_pagination.pages > 0
                and azubi_page > azubi_pagination.pages):
            flash(
                'Seite existiert nicht, leite zur '
                'letzten Seite um.', 'info')
            args = request.args.copy()
            args['azubi_page'] = azubi_pagination.pages
            return redirect(
                url_for(request.endpoint, **args))

    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            f"Pagination failed: {e}")
        azubi_pagination = None

    azubis = (
        azubi_pagination.items
        if azubi_pagination else [])
    examiners = Examiner.query.order_by(
        Examiner.name).all()

    return render_template(
        'personnel.html',
        azubis=azubis,
        azubi_pagination=azubi_pagination,
        examiners=examiners,
        show_archived=show_archived)


def settings():
    """System settings page."""
    data_dir = get_data_dir()
    logo_path = os.path.join(
        data_dir, 'static', 'img', 'logo.png')
    logo_exists = os.path.exists(logo_path)
    backups = BackupService.list_backups()
    backup_interval = SystemSettings.get_setting(
        'backup_interval', 'daily')
    backup_time = SystemSettings.get_setting(
        'backup_time', '03:00')
    retention_days = SystemSettings.get_setting(
        'backup_retention_days', '30')

    return render_template(
        'settings.html',
        logo_exists=logo_exists,
        logo_version=time.time(),
        backups=backups,
        backup_interval=backup_interval,
        backup_time=backup_time,
        retention_days=retention_days)


def save_backup_config():
    """Save backup schedule settings."""
    interval = request.form.get('interval')
    time_str = request.form.get('time')
    retention = request.form.get('retention')
    SystemSettings.set_setting(
        'backup_interval', interval)
    SystemSettings.set_setting('backup_time', time_str)
    SystemSettings.set_setting(
        'backup_retention_days', retention)
    # pylint: disable=protected-access
    BackupService.schedule_backup_job(
        current_app._get_current_object())
    flash('Backup-Einstellungen gespeichert.',
          'success')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.settings')}")


def restore_backup():
    """Handle backup restore from upload."""
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    if 'backup_file' not in request.files:
        flash('Keine Datei ausgewählt.', 'error')
        return redirect(
            f"{ingress}{url_for('main.settings')}")

    file = request.files['backup_file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'error')
        return redirect(
            f"{ingress}{url_for('main.settings')}")

    if file and file.filename.endswith('.zip'):
        try:
            data_dir = CheckService.get_data_dir()
            temp_path = os.path.join(
                data_dir, 'restore_upload.zip')
            try:
                file.save(temp_path)
                BackupService.restore_backup(temp_path)
                flash(
                    'Backup erfolgreich '
                    'wiederhergestellt.',
                    'success')
                return redirect(
                    f"{ingress}"
                    f"{url_for('main.index')}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                flash(
                    f'Fehler bei Wiederherstellung: '
                    f'{str(e)}', 'error')
                return redirect(
                    f"{ingress}"
                    f"{url_for('main.settings')}")
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
        except Exception as e:  # pylint: disable=broad-exception-caught
            flash(
                f'Fehler bei Wiederherstellung: '
                f'{str(e)}', 'error')
            return redirect(
                f"{ingress}"
                f"{url_for('main.settings')}")

    flash(
        'Ungültiges Dateiformat. Nur .zip erlaubt.',
        'error')
    return redirect(
        f"{ingress}{url_for('main.settings')}")


def create_backup():
    """Create a new backup."""
    try:
        filename = BackupService.create_backup()
        flash(
            f'Backup erfolgreich erstellt: {filename}',
            'success')
    except Exception as e:  # pylint: disable=broad-exception-caught
        flash(f'Backup fehlgeschlagen: {e}', 'error')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.settings')}")


def download_backup(filename):
    """Download a backup file."""
    try:
        backup_dir = BackupService.get_backup_dir()
        return send_from_directory(
            backup_dir, filename,
            as_attachment=True)
    except Exception as e:  # pylint: disable=broad-exception-caught
        flash(
            f'Download fehlgeschlagen: {e}', 'error')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.settings')}")


def toggle_migration_mode():
    """Toggle migration mode."""
    current_mode = session.get(
        'migration_mode', False)
    session['migration_mode'] = not current_mode
    status = ("aktiviert"
              if session['migration_mode']
              else "deaktiviert")
    flash(
        f'Migration Modus wurde {status}.', 'info')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.settings')}")


def add_examiner():
    """Add a new examiner."""
    form = ExaminerForm(request.form)
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    if form.validate():
        new_examiner = Examiner(
            name=form.name.data)
        db.session.add(new_examiner)
        db.session.commit()
        flash(
            f'Prüfer {form.name.data} hinzugefügt.',
            'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(
                    f"Fehler bei {field}: {error}",
                    'error')
    return redirect(
        f"{ingress}{url_for('main.personnel')}")


def delete_examiner(examiner_id):
    """Delete an examiner."""
    examiner = Examiner.query.get_or_404(
        examiner_id)
    db.session.delete(examiner)
    db.session.commit()
    flash(
        f'Prüfer {examiner.name} gelöscht.',
        'success')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.personnel')}")


def add_azubi():
    """Add a new azubi."""
    form = AzubiForm(request.form)
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    if form.validate():
        new_azubi = Azubi(
            name=form.name.data,
            lehrjahr=form.lehrjahr.data)
        db.session.add(new_azubi)
        db.session.commit()
        flash(
            f'Azubi {form.name.data} hinzugefügt.',
            'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(
                    f"Fehler bei {field}: {error}",
                    'error')
    return redirect(
        f"{ingress}{url_for('main.personnel')}")


def edit_azubi(azubi_id):
    """Edit an azubi."""
    azubi = Azubi.query.get_or_404(azubi_id)
    form = AzubiForm(request.form)
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    if form.validate():
        azubi.name = form.name.data
        azubi.lehrjahr = form.lehrjahr.data
        db.session.commit()
        flash(
            f'Azubi {azubi.name} aktualisiert.',
            'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(
                    f"Fehler bei {field}: {error}",
                    'error')
    return redirect(
        f"{ingress}{url_for('main.personnel')}")


def delete_azubi(azubi_id):
    """Delete an azubi."""
    azubi = Azubi.query.get_or_404(azubi_id)
    if azubi.checks:
        flash(
            f'Fehler: Azubi "{azubi.name}" hat '
            'Historie und kann nicht gelöscht '
            'werden.', 'error')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.personnel')}")
    db.session.delete(azubi)
    db.session.commit()
    flash(
        f'Azubi {azubi.name} gelöscht.', 'success')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.personnel')}")


def archive_azubi(azubi_id):
    """Archive an azubi."""
    azubi = Azubi.query.get_or_404(azubi_id)
    assigned = CheckService.get_assigned_tools(
        azubi.id)
    if assigned:
        flash(
            f'Warnung: {azubi.name} hat noch '
            f'{len(assigned)} Werkzeuge im Besitz! '
            'Bitte erst zurückgeben.', 'danger')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.personnel')}")
    azubi.is_archived = True
    db.session.commit()
    flash(
        f'{azubi.name} wurde archiviert.',
        'success')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.personnel')}")


def unarchive_azubi(azubi_id):
    """Unarchive an azubi."""
    azubi = Azubi.query.get_or_404(azubi_id)
    azubi.is_archived = False
    db.session.commit()
    flash(
        f'{azubi.name} wurde wiederhergestellt.',
        'success')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.personnel')}")


def add_werkzeug():
    """Add a new tool."""
    form = WerkzeugForm(request.form)
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    if form.validate():
        new_werkzeug = Werkzeug(
            name=form.name.data,
            material_category=(
                form.material_category.data),
            tech_param_label=(
                form.tech_param_label.data))
        db.session.add(new_werkzeug)
        db.session.commit()
        flash(
            f'Werkzeug {form.name.data} hinzugefügt.',
            'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(
                    f"Fehler bei {field}: {error}",
                    'error')
    return redirect(
        f"{ingress}{url_for('main.tools')}")


def edit_werkzeug(werkzeug_id):
    """Edit a tool."""
    werkzeug = Werkzeug.query.get_or_404(
        werkzeug_id)
    form = WerkzeugForm(request.form)
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    if form.validate():
        werkzeug.name = form.name.data
        werkzeug.material_category = (
            form.material_category.data)
        werkzeug.tech_param_label = (
            form.tech_param_label.data)
        db.session.commit()
        flash(
            f'Werkzeug {werkzeug.name} aktualisiert.',
            'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(
                    f"Fehler bei {field}: {error}",
                    'error')
    return redirect(
        f"{ingress}{url_for('main.tools')}")


def delete_werkzeug(werkzeug_id):
    """Delete a tool."""
    werkzeug = Werkzeug.query.get_or_404(
        werkzeug_id)
    if werkzeug.checks:
        flash(
            f'Fehler: Werkzeug "{werkzeug.name}" '
            'wird in Protokollen verwendet und '
            'kann nicht gelöscht werden.', 'error')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.tools')}")
    db.session.delete(werkzeug)
    CheckService.invalidate_cache()
    db.session.commit()
    flash(
        f'Werkzeug {werkzeug.name} gelöscht.',
        'success')
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    return redirect(
        f"{ingress}{url_for('main.tools')}")


@limiter.limit("5 per minute")
def upload_logo():
    """Upload a custom logo."""
    ingress = request.headers.get(
        'X-Ingress-Path', '')
    if 'logo' not in request.files:
        flash('Keine Datei ausgewählt', 'danger')
        return redirect(
            f"{ingress}{url_for('main.settings')}")

    file = request.files['logo']
    if file.filename == '':
        flash('Keine Datei ausgewählt', 'danger')
        return redirect(
            f"{ingress}{url_for('main.settings')}")

    if file:
        ext = file.filename.rsplit(
            '.', 1)[-1].lower()
        if ext not in ['png', 'jpg', 'jpeg']:
            flash(
                'Ungültige Dateiendung '
                '(Nur .png, .jpg, .jpeg).', 'error')
            return redirect(
                f"{ingress}"
                f"{url_for('main.settings')}")

        header = file.read(1024)
        file.seek(0)
        is_png = header.startswith(
            b'\x89PNG\r\n\x1a\n')
        is_jpeg = header.startswith(b'\xff\xd8\xff')

        if not (is_png or is_jpeg):
            flash(
                'Ungültiges Format '
                '(Nur PNG/JPG erlaubt).', 'error')
            return redirect(
                f"{ingress}"
                f"{url_for('main.settings')}")

        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > 2 * 1024 * 1024:
            flash(
                'Datei zu groß (max. 2MB).', 'error')
            return redirect(
                f"{ingress}"
                f"{url_for('main.settings')}")

        filename = secure_filename('logo.png')
        data_dir = get_data_dir()
        img_folder = os.path.join(
            data_dir, 'static', 'img')
        os.makedirs(img_folder, exist_ok=True)
        file.save(
            os.path.join(img_folder, filename))
        flash(
            'Logo erfolgreich hochgeladen',
            'success')

    return redirect(
        f"{ingress}{url_for('main.settings')}")


def generate_qr_codes():
    """Generate PDF with QR codes for all tools."""
    all_tools = Werkzeug.query.order_by(
        Werkzeug.name).all()
    if not all_tools:
        flash('Keine Werkzeuge vorhanden.',
              'warning')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.settings')}")

    try:
        pdf = generate_qr_codes_pdf(all_tools)
        # pylint: disable=unexpected-keyword-arg
        pdf_bytes = bytes(pdf.output(dest='S'))
        response = make_response(pdf_bytes)
        response.headers[
            'Content-Type'] = 'application/pdf'
        response.headers[
            'Content-Disposition'] = (
            'attachment; '
            'filename=Werkzeug_QRCodes.pdf')
        return response
    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            f"Error generating QR Codes: {e}")
        flash(
            f'Fehler beim Erstellen der '
            f'QR-Codes: {e}', 'danger')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.settings')}")


def end_of_training_report(azubi_id):
    """Generate end of training report."""
    azubi = Azubi.query.get_or_404(azubi_id)
    assigned = CheckService.get_assigned_tools(
        azubi.id)
    is_clear = len(assigned) == 0
    check_history = Check.query.filter_by(
        azubi_id=azubi_id).order_by(
        Check.datum.desc()).all()

    try:
        pdf = generate_end_of_training_report(
            azubi, check_history, is_clear)
        # pylint: disable=unexpected-keyword-arg
        pdf_bytes = bytes(pdf.output(dest='S'))
        response = make_response(pdf_bytes)
        response.headers[
            'Content-Type'] = 'application/pdf'
        response.headers[
            'Content-Disposition'] = (
            'attachment; '
            f'filename=Ausbildungsende_'
            f'{azubi.name}.pdf')
        return response
    except Exception as e:  # pylint: disable=broad-exception-caught
        current_app.logger.error(
            f"Error generating Report: {e}")
        flash(
            f'Fehler beim Erstellen des '
            f'Berichts: {e}', 'danger')
        ingress = request.headers.get(
            'X-Ingress-Path', '')
        return redirect(
            f"{ingress}{url_for('main.manage')}")


def register_routes(bp):
    """Register admin routes on the given blueprint."""
    bp.add_url_rule('/manage', view_func=manage)
    bp.add_url_rule('/tools', view_func=tools)
    bp.add_url_rule('/personnel', view_func=personnel)
    bp.add_url_rule('/settings', view_func=settings)
    bp.add_url_rule(
        '/settings/backup/config',
        view_func=save_backup_config, methods=['POST'])
    bp.add_url_rule(
        '/settings/restore',
        view_func=restore_backup, methods=['POST'])
    bp.add_url_rule(
        '/settings/backup/create',
        view_func=create_backup, methods=['POST'])
    bp.add_url_rule(
        '/settings/backup/download/<filename>',
        view_func=download_backup)
    bp.add_url_rule(
        '/toggle_migration_mode',
        view_func=toggle_migration_mode, methods=['POST'])

    # Examiner CRUD
    bp.add_url_rule(
        '/add_examiner',
        view_func=add_examiner, methods=['POST'])
    bp.add_url_rule(
        '/delete_examiner/<int:examiner_id>',
        view_func=delete_examiner, methods=['POST'])

    # Azubi CRUD
    bp.add_url_rule(
        '/add_azubi',
        view_func=add_azubi, methods=['POST'])
    bp.add_url_rule(
        '/edit_azubi/<int:azubi_id>',
        view_func=edit_azubi, methods=['POST'])
    bp.add_url_rule(
        '/delete_azubi/<int:azubi_id>',
        view_func=delete_azubi, methods=['POST'])
    bp.add_url_rule(
        '/archive_azubi/<int:azubi_id>',
        view_func=archive_azubi, methods=['POST'])
    bp.add_url_rule(
        '/unarchive_azubi/<int:azubi_id>',
        view_func=unarchive_azubi, methods=['POST'])

    # Werkzeug CRUD
    bp.add_url_rule(
        '/add_werkzeug',
        view_func=add_werkzeug, methods=['POST'])
    bp.add_url_rule(
        '/edit_werkzeug/<int:werkzeug_id>',
        view_func=edit_werkzeug, methods=['POST'])
    bp.add_url_rule(
        '/delete_werkzeug/<int:werkzeug_id>',
        view_func=delete_werkzeug, methods=['POST'])

    # Uploads & Reports
    bp.add_url_rule(
        '/upload_logo',
        view_func=upload_logo, methods=['POST'])
    bp.add_url_rule(
        '/generate_qr_codes',
        view_func=generate_qr_codes)
    bp.add_url_rule(
        '/report/end_of_training/<int:azubi_id>',
        view_func=end_of_training_report)
