"""
Admin Routes module.

Handles worker management and other administrative tasks.
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from .auth import admin_required, redirect_to
from services.worker_service import WorkerService
from models import SystemSettings, Team
from enums import WorkerRole

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
                role = request.form.get('role')
                is_admin = (role == WorkerRole.ADMIN.value)
                WorkerService.create_worker(name, pin, is_admin, role)
                
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
                role = request.form.get('role')
                is_admin = (role == WorkerRole.ADMIN.value)
                WorkerService.update_worker(worker_id, name, is_admin, role)
                flash(f"Mitarbeiter '{name}' wurde aktualisiert.", "success")
            
            elif action == 'reset_pin':
                worker_id = request.form.get('worker_id')
                worker = WorkerService.admin_reset_pin(worker_id)
                flash(f"PIN für '{worker.name}' wurde auf '0000' zurückgesetzt. Der Mitarbeiter muss diesen beim nächsten Login ändern.", "warning")

            elif action == 'generate_tokens':
                from services.system_service import SystemService
                SystemService.generate_recovery_tokens()
                flash("Neue Notfall-Codes wurden generiert. Bitte sofort sicher verwahren!", "warning")
                return redirect_to('admin.show_tokens')
                
        except ValueError as e:
            flash(str(e), "danger")
        except Exception:
            flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")

    workers_list = WorkerService.get_all_workers()
    return render_template('workers.html', workers=workers_list)


@admin_bp.route('/templates', methods=['GET', 'POST'])
@admin_required
def templates():
    """List and manage checklist templates."""
    from extensions import db
    from models import ChecklistTemplate, ChecklistTemplateItem
    
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'create':
                title = request.form.get('title')
                desc = request.form.get('description')
                t = ChecklistTemplate(title=title, description=desc)
                db.session.add(t)
                db.session.flush()
                
                # Items are sent as list of strings
                items = request.form.getlist('items[]')
                for item_title in items:
                    if item_title.strip():
                        db.session.add(ChecklistTemplateItem(template_id=t.id, title=item_title.strip()))
                db.session.commit()
                flash("Vorlage erfolgreich erstellt.", "success")
                
            elif action == 'delete':
                t_id = request.form.get('template_id')
                t = db.session.get(ChecklistTemplate, t_id)
                if t:
                    db.session.delete(t)
                    db.session.commit()
                    flash("Vorlage gelöscht.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler: {str(e)}", "danger")

    templates_list = ChecklistTemplate.query.all()
    return render_template('admin_templates.html', templates=templates_list)


@admin_bp.route('/teams', methods=['GET', 'POST'])
@admin_required
def teams():
    """List and manage teams."""
    from extensions import db
    from models import Team, Worker

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'create':
                name = request.form.get('name', '').strip()
                if not name:
                    flash("Teamname ist erforderlich.", "warning")
                elif Team.query.filter_by(name=name).first():
                    flash(f"Team '{name}' existiert bereits.", "danger")
                else:
                    team = Team(name=name)
                    member_ids = request.form.getlist('member_ids')
                    for mid in member_ids:
                        worker = db.session.get(Worker, int(mid))
                        if worker:
                            team.members.append(worker)
                    db.session.add(team)
                    db.session.commit()
                    flash(f"Team '{name}' wurde erstellt.", "success")

            elif action == 'update':
                team_id = request.form.get('team_id')
                team = db.session.get(Team, team_id)
                if team:
                    new_name = request.form.get('name', '').strip()
                    if new_name and new_name != team.name:
                        if Team.query.filter_by(name=new_name).first():
                            flash(f"Team '{new_name}' existiert bereits.", "danger")
                            return redirect_to('admin.teams')
                        team.name = new_name
                    member_ids = request.form.getlist('member_ids')
                    team.members = []
                    for mid in member_ids:
                        worker = db.session.get(Worker, int(mid))
                        if worker:
                            team.members.append(worker)
                    db.session.commit()
                    flash(f"Team '{team.name}' wurde aktualisiert.", "success")

            elif action == 'delete':
                team_id = request.form.get('team_id')
                team = db.session.get(Team, team_id)
                if team:
                    db.session.delete(team)
                    db.session.commit()
                    flash(f"Team '{team.name}' wurde gelöscht.", "success")

        except Exception as e:
            db.session.rollback()
            flash(f"Fehler: {str(e)}", "danger")

    teams_list = Team.query.order_by(Team.name).all()
    active_workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    return render_template('admin_teams.html', teams=teams_list, active_workers=active_workers)


@admin_bp.route('/workers/tokens')
@admin_required
def show_tokens():
    """Display the generated recovery tokens."""
    import json
    from datetime import datetime, timezone

    tokens_json = SystemSettings.get_setting('recovery_tokens_raw', '[]')
    tokens_ts = SystemSettings.get_setting('recovery_tokens_generated_at', '')

    # SEC-02: Time-based expiry (5 minutes) instead of immediate deletion on read.
    # This prevents accidental loss if the admin refreshes the page.
    tokens = []
    expired = False
    if tokens_json and tokens_json != '[]':
        try:
            if tokens_ts:
                generated_at = datetime.fromisoformat(tokens_ts)
                from utils import get_utc_now
                now = get_utc_now()
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
                if generated_at.tzinfo is None:
                    generated_at = generated_at.replace(tzinfo=timezone.utc)
                elapsed = (now - generated_at).total_seconds()
                if elapsed > 300:  # 5 minutes
                    expired = True
                    SystemSettings.set_setting('recovery_tokens_raw', '[]')
                    SystemSettings.set_setting('recovery_tokens_generated_at', '')
            if not expired:
                tokens = json.loads(tokens_json)
        except (ValueError, json.JSONDecodeError):
            tokens = []

    return render_template('show_recovery_tokens.html', tokens=tokens, expired=expired)
