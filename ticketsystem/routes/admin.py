"""
Admin Routes module.

Handles worker management and other administrative tasks.
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from .auth import admin_required
from services.worker_service import WorkerService

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
                flash(f"Mitarbeiter '{name}' wurde angelegt.", "success")
            
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
                
        except ValueError as e:
            flash(str(e), "danger")
        except Exception:
            flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")

    workers_list = WorkerService.get_all_workers()
    return render_template('workers.html', workers=workers_list)
