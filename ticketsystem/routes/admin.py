"""
Admin Routes module.

Handles worker management and other administrative tasks.
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from .auth import admin_required
from services.worker_service import WorkerService
from models import SystemSettings

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/workers', methods=['GET', 'POST'])
@admin_required
def workers():
    """List and manage workers."""
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'create':
                name = request.form.get('name')
                pin = request.form.get('pin')
                is_admin = request.form.get('is_admin') == 'on'
                WorkerService.create_worker(name, pin, is_admin)
                
                if pin:
                    flash(f"Mitarbeiter '{name}' wurde angelegt. Erster Login mit PIN: {pin}.", "success")
                else:
                    flash(f"Mitarbeiter '{name}' wurde ohne PIN angelegt. Standard-PIN ist '0000' (muss beim ersten Login geändert werden).", "success")
            
            elif action == 'toggle_status':
                worker_id = request.form.get('worker_id')
                worker = WorkerService.toggle_status(worker_id)
                status_str = "aktiviert" if worker.is_active else "deaktiviert"
                flash(f"Mitarbeiter '{worker.name}' wurde {status_str}.", "success")

            elif action == 'update':
                worker_id = request.form.get('worker_id')
                name = request.form.get('name')
                is_admin = request.form.get('is_admin') == 'on'
                WorkerService.update_worker(worker_id, name, is_admin)
                flash(f"Mitarbeiter '{name}' wurde aktualisiert.", "success")
            
            elif action == 'reset_pin':
                worker_id = request.form.get('worker_id')
                worker = WorkerService.admin_reset_pin(worker_id)
                flash(f"PIN für '{worker.name}' wurde auf '0000' zurückgesetzt. Der Mitarbeiter muss diesen beim nächsten Login ändern.", "warning")

            elif action == 'generate_tokens':
                from services.system_service import SystemService
                SystemService.generate_recovery_tokens()
                flash("Neue Notfall-Codes wurden generiert. Bitte sofort sicher verwahren!", "warning")
                return redirect(url_for('admin.show_tokens'))
                
        except ValueError as e:
            flash(str(e), "danger")
        except Exception:
            flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")

    workers_list = WorkerService.get_all_workers()
    return render_template('workers.html', workers=workers_list)


@admin_bp.route('/workers/tokens')
@admin_required
def show_tokens():
    """Display the generated recovery tokens."""
    tokens_json = SystemSettings.get_setting('recovery_tokens_raw', '[]')
    import json
    tokens = json.loads(tokens_json)
    return render_template('show_recovery_tokens.html', tokens=tokens)
