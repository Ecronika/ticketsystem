"""
Ticket routes.

Handles ticket CRUD, public ticket view, queue, approvals, and project views.
"""
import os
from datetime import datetime, timezone, timedelta

from flask import (
    flash, redirect, render_template, request, session, url_for, 
    jsonify, send_from_directory, current_app
)
from markupsafe import Markup
# from flask_limiter import Limiter (unused import)

from extensions import db, limiter
from utils import get_utc_now
from services import TicketService
from enums import TicketStatus, TicketPriority, WorkerRole, ApprovalStatus
from models import Worker, Attachment, Ticket
from .auth import worker_required, redirect_to, admin_required, admin_or_management_required

def _dashboard_view():
    """Handle the main dashboard view."""
    worker_id = session.get('worker_id')
    search = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    assigned_to_me = request.args.get('assigned_to_me') == '1'
    unassigned_only = request.args.get('unassigned') == '1'
    callback_pending = request.args.get('callback_pending') == '1'

    # Feature: Direct jump via #ID
    if search.startswith('#') and search[1:].isdigit():
        return redirect_to('main.ticket_detail', ticket_id=int(search[1:]))

    tickets_data = TicketService.get_dashboard_tickets(
        worker_id=worker_id,
        search=search,
        status_filter=status_filter,
        page=page,
        per_page=10,
        assigned_to_me=assigned_to_me,
        unassigned_only=unassigned_only,
        callback_pending=callback_pending,
        worker_role=session.get('role')
    )
    
    return render_template('index.html', 
                          pagination=tickets_data['focus_pagination'], 
                          focus_tickets=tickets_data['focus_pagination'].items,
                          self_tickets=tickets_data['self'],
                          self_total=tickets_data['self_total'],
                          summary_counts=tickets_data['summary_counts'],
                          query=search,
                          current_status=status_filter,
                          assigned_to_me=assigned_to_me,
                          unassigned_only=unassigned_only,
                          callback_pending=callback_pending,
                          today=get_utc_now())


def _archive_view():
    """Handle the ticket archive view (completed tickets)."""
    search = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    author = request.args.get('author', '').strip()
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')

    start_date = None
    end_date = None
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        if end_date_str:
            # Set end_date to end of the day
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        pass

    tickets_data = TicketService.get_dashboard_tickets(
        worker_id=session.get('worker_id'),
        search=search,
        status_filter=TicketStatus.ERLEDIGT.value,
        page=page,
        per_page=15,
        start_date=start_date,
        end_date=end_date,
        author_name=author,
        worker_role=session.get('role')
    )
    
    return render_template('archive.html', 
                          pagination=tickets_data['focus_pagination'], 
                          tickets=tickets_data['focus_pagination'].items,
                          query=search,
                          author=author,
                          start_date=start_date_str,
                          end_date=end_date_str,
                          current_status=TicketStatus.ERLEDIGT.value)

@admin_required
def _approvals_view():
    """GF/Prokurist Dashboard for specific ticket approvals."""
    page = request.args.get('page', 1, type=int)
    pagination = TicketService.get_pending_approvals(page=page)
    return render_template('approvals.html', pagination=pagination, tickets=pagination.items)

def _projects_view():
    """Project/Baustellen Dashboard."""
    projects = TicketService.get_projects_summary()
    return render_template('projects.html', projects=projects)

def _new_ticket_view():
    """Handle new ticket creation (v1.12.0: includes optional assignment)."""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        priority_val = request.form.get('priority', 2)
        author_name = request.form.get('author_name') or "Anonym"
        attachments = request.files.getlist('attachments')
        due_date_str = request.form.get('due_date')
        order_reference = request.form.get('order_reference')
        tags_raw = request.form.get('tags', '')
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
        is_confidential = request.form.get('is_confidential') == 'True' or request.form.get('is_confidential') == 'on'
        recurrence_rule = request.form.get('recurrence_rule')
        contact_name = request.form.get('contact_name') or None
        contact_phone = request.form.get('contact_phone') or None
        contact_channel = request.form.get('contact_channel') or None
        callback_requested = request.form.get('callback_requested') == 'on'
        callback_due_str = request.form.get('callback_due')
        callback_due = None
        if callback_due_str:
            try:
                callback_due = datetime.strptime(callback_due_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    callback_due = datetime.strptime(callback_due_str, '%Y-%m-%d')
                except ValueError:
                    pass

        # C-2 Fix: assigned_to_id selects can contain 'team_X' prefixed values
        # assigned_team_id is handled via the same select with 'team_' prefix
        assigned_to_id_raw = request.form.get('assigned_to_id')
        assigned_team_id_raw = request.form.get('assigned_team_id')
        assigned_to_id = None
        assigned_team_id = None

        if assigned_to_id_raw and assigned_to_id_raw.startswith('team_'):
            # Team selected via combined dropdown
            try:
                assigned_team_id = int(assigned_to_id_raw[5:])
            except ValueError:
                pass
        elif assigned_to_id_raw and assigned_to_id_raw.isdigit():
            assigned_to_id = int(assigned_to_id_raw)
        elif session.get('worker_id'):
            # Fallback: Ersteller ist Worker -> Auto-Zuweisung
            assigned_to_id = session.get('worker_id')

        template_id = request.form.get('template_id')
        if template_id:
            try:
                template_id = int(template_id)
            except ValueError:
                template_id = None

        if assigned_team_id_raw and not assigned_team_id:
            try:
                if assigned_team_id_raw.startswith('team_'):
                    assigned_team_id = int(assigned_team_id_raw[5:])
                elif assigned_team_id_raw.isdigit():
                    assigned_team_id = int(assigned_team_id_raw)
            except ValueError:
                pass

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            except ValueError:
                pass

        if not title:
            flash('Bitte einen Titel angeben.', 'warning')
            return render_template('ticket_new.html')

        try:
            priority = TicketPriority(int(priority_val))
            ticket = TicketService.create_ticket(
                title=title,
                description=description,
                priority=priority,
                author_name=author_name,
                author_id=session.get('worker_id'),
                attachments=attachments,
                due_date=due_date,
                assigned_to_id=assigned_to_id,
                assigned_team_id=assigned_team_id,
                is_confidential=is_confidential,
                recurrence_rule=recurrence_rule,
                order_reference=order_reference,
                tags=tags,
                checklist_template_id=template_id,
                contact_name=contact_name,
                contact_phone=contact_phone,
                contact_channel=contact_channel,
                callback_requested=callback_requested,
                callback_due=callback_due,
            )
            session['last_created_ticket_id'] = ticket.id
            ticket_url = f"{request.headers.get('X-Ingress-Path', '')}{url_for('main.ticket_detail', ticket_id=ticket.id)}"
            link_html = f' <a href="{ticket_url}" class="alert-link">Ticket #{ticket.id} ansehen →</a>'
            
            if not session.get('worker_id'):
                return redirect_to('main.ticket_new', created=ticket.id)
            
            flash(Markup(f'Ticket {link_html} erfolgreich erstellt!'), 'success')
            return redirect_to('main.index')
        except Exception:
            current_app.logger.exception("Fehler beim Erstellen des Tickets (worker=%s)", session.get('worker_id'))
            flash('Fehler beim Erstellen des Tickets.', 'error')

    from models import Worker, Team, ChecklistTemplate
    workers = Worker.query.filter_by(is_active=True).all()
    teams = Team.query.all()
    templates = ChecklistTemplate.query.all()
    return render_template('ticket_new.html', workers=workers, teams=teams, templates=templates)

@worker_required
def _ticket_detail_view(ticket_id):
    """Handle ticket detail view."""
    # FIX: Expire all to ensure we don't have stale data from a different session (e.g. in tests)
    db.session.expire_all()
    
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        flash('Ticket nicht gefunden.', 'error')
        return redirect_to('main.index')
    
    # Security Check: Confidentiality IDOR protection
    user_role = session.get('role')
    user_id = session.get('worker_id')
    
    if not ticket.is_accessible_by(user_id, user_role):
        flash('Keine Berechtigung für dieses Ticket.', 'danger')
        return redirect_to('main.index')
        
    has_full_access = True # Default for authorized users
            
    workers = Worker.query.filter_by(is_active=True).all()
    from models import Team, ChecklistTemplate
    teams = Team.query.all()
    templates = ChecklistTemplate.query.all()
    return render_template('ticket_detail.html', ticket=ticket, workers=workers, teams=teams, templates=templates, has_full_access=has_full_access, now=get_utc_now())

@limiter.limit("30 per minute")
def _public_ticket_view(ticket_id):
    """Public read-only status page (P0-1)."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.is_deleted or ticket.is_confidential:
        return render_template('404.html'), 404
        
    return render_template('ticket_public.html', ticket=ticket)

def check_approval_lock(ticket_id=None, item_id=None):
    from models import Ticket, ChecklistItem
    if item_id:
        item = db.session.get(ChecklistItem, item_id)
        if not item: return None
        ticket = item.ticket
    elif ticket_id:
        ticket = db.session.get(Ticket, ticket_id)
    else:
        return None
        
    if ticket and ticket.approval_status == ApprovalStatus.PENDING.value:
        return jsonify({'success': False, 'error': 'Ticket ist für die Freigabe gesperrt.'}), 403
    return None

@worker_required
@limiter.limit("20 per minute")
def _add_comment_view(ticket_id):
    """Handle adding a comment."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.is_deleted:
        flash('Ticket nicht gefunden.', 'error')
        return redirect_to('main.index')
    
    # IDOR fix: confidential tickets must be accessible by the caller
    worker_id = session.get('worker_id')
    worker_role = session.get('role')
    if not ticket.is_accessible_by(worker_id, worker_role):
        flash('Keine Berechtigung für dieses Ticket.', 'danger')
        return redirect_to('main.index')

    text = request.form.get('text')
    author_name = session.get('worker_name', 'System')
    if text:
        TicketService.add_comment(ticket_id, author_name, worker_id, text)
        flash('Kommentar hinzugefügt.', 'success')
    return redirect_to('main.ticket_detail', ticket_id=ticket_id, _anchor='comment-form')

@worker_required
@limiter.limit("20 per minute")
def _update_status_api(ticket_id):
    """Handle AJAX status update."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or not ticket.is_accessible_by(session.get('worker_id'), session.get('role')):
        return jsonify({'error': 'Keine Berechtigung'}), 403

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err: return lock_err

    data = request.get_json(silent=True) or {}
    new_status_val = data.get('status')
    
    if not new_status_val:
        return jsonify({'success': False, 'error': 'Kein Status angegeben'}), 400
        
    # FIG-05: Strict Enum Validation in Route Layer
    if new_status_val not in [s.value for s in TicketStatus]:
         return jsonify({'success': False, 'error': f'Ungültiger Status: {new_status_val}'}), 400

    author_name = session.get('worker_name', 'System')
    try:
        TicketService.update_status(ticket_id, new_status_val, author_name, session.get('worker_id'))
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("API Error in _update_status_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@worker_required
@limiter.limit("20 per minute")
def _assign_ticket_api(ticket_id):
    """Handle AJAX ticket assignment."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or not ticket.is_accessible_by(session.get('worker_id'), session.get('role')):
        return jsonify({'error': 'Keine Berechtigung'}), 403

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err: return lock_err

    data = request.get_json(silent=True) or {}
    worker_id = data.get('worker_id')
    
    if worker_id is not None:
        try:
            worker_id = int(worker_id)
        except (ValueError, TypeError):
             return jsonify({'success': False, 'error': 'Ungültige Worker ID'}), 400

    author_name = session.get('worker_name', 'System')
    try:
        TicketService.assign_ticket(ticket_id, worker_id, author_name, session.get('worker_id'))
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("API Error in _update_status_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@worker_required
def _assign_to_me_view(ticket_id):
    """Assign the ticket to the current logged-in worker."""
    from models import Ticket
    from enums import WorkerRole
    ticket = db.session.get(Ticket, ticket_id)
    
    if not ticket:
         return render_template('404.html'), 404

    # SEC-01: Check if user has access to this ticket (e.g. if it's confidential)
    worker_id = session.get('worker_id')
    worker_role = session.get('role')
    if not ticket.is_accessible_by(worker_id, worker_role):
        flash('Zugriff verweigert.', 'error')
        return redirect(url_for('main.index'))

    if ticket.approval_status == ApprovalStatus.PENDING.value:
        flash('Ticket ist für die Freigabe gesperrt.', 'error')
        return redirect_to('main.ticket_detail', ticket_id=ticket_id)

    worker_name = session.get('worker_name', 'System')
    
    if worker_id:
        TicketService.assign_ticket(ticket_id, worker_id, worker_name, worker_id)
        flash('Ticket wurde Ihnen zugewiesen.', 'success')
    
    return redirect_to('main.ticket_detail', ticket_id=ticket_id)

@worker_required
def _serve_attachment(attachment_id):
    """Securely serve uploaded attachments."""
    attachment = db.session.get(Attachment, attachment_id)
    if not attachment:
        return "Not Found", 404
        
    ticket = attachment.ticket
    user_role = session.get('role')
    user_id = session.get('worker_id')
    if ticket and ticket.is_confidential:
        # DRY: use Ticket.is_accessible_by() — same logic as _ticket_detail_view
        if not ticket.is_accessible_by(user_id, user_role):
            return "Forbidden", 403

    from extensions import Config
    data_dir = current_app.config.get('DATA_DIR', Config.get_data_dir())
    attachments_dir = os.path.join(data_dir, 'attachments')
    
    # Path-Traversal protection: only use basename and ensure it's not empty
    safe_filename = os.path.basename(attachment.path)
    if not safe_filename or safe_filename in ['.', '..']:
        return "Invalid Path", 400
        
    return send_from_directory(attachments_dir, safe_filename)

@worker_required
@limiter.limit("20 per minute")
def _update_ticket_api(ticket_id):
    """Handle ticket meta updates (title/priority/due_date)."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or not ticket.is_accessible_by(session.get('worker_id'), session.get('role')):
        return jsonify({'error': 'Keine Berechtigung'}), 403

    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err: return lock_err

    data = request.get_json(silent=True) or {}
    new_title = data.get('title')
    new_prio = data.get('priority')
    new_due_str = data.get('due_date')
    order_reference = data.get('order_reference')
    reminder_date_str = data.get('reminder_date')
    tags = data.get('tags') # List of strings expected
    author_name = session.get('worker_name', 'System')
    
    if not new_title:
        return jsonify({'success': False, 'error': 'Titel fehlt'}), 400

    if new_prio is None:
        return jsonify({'success': False, 'error': 'Priorität fehlt'}), 400

    # Strict Priority Validation
    try:
        priority_enum = TicketPriority(int(new_prio))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': f'Ungültige Priorität: {new_prio}'}), 400
        
    due_date = None
    if new_due_str:
        try:
            due_date = datetime.fromisoformat(new_due_str.split('T')[0])
        except (ValueError, TypeError):
            due_date = None

    reminder_date = None
    if reminder_date_str:
        try:
            reminder_date = datetime.fromisoformat(reminder_date_str.split('T')[0])
        except (ValueError, TypeError):
            reminder_date = None

    try:
        TicketService.update_ticket_meta(
            ticket_id, new_title, new_prio, author_name, session.get('worker_id'), 
            due_date=due_date, order_reference=order_reference, reminder_date=reminder_date,
            tags=tags
        )
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("API Error in _update_ticket_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@worker_required
@limiter.limit("20 per minute")
def _request_approval_api(ticket_id):
    author_name = session.get('worker_name', 'System')
    try:
        TicketService.request_approval(ticket_id, session.get('worker_id'), author_name)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("API Error in _request_approval_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@admin_required
@limiter.limit("20 per minute")
def _approve_ticket_api(ticket_id):
    author_name = session.get('worker_name', 'System')
    try:
        TicketService.approve_ticket(ticket_id, session.get('worker_id'), author_name)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("API Error in _approve_ticket_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@admin_required
@limiter.limit("20 per minute")
def _reject_ticket_api(ticket_id):
    data = request.get_json(silent=True) or {}
    reason = data.get('reason')
    if not reason:
        return jsonify({'success': False, 'error': 'Ablehnungsgrund fehlt.'}), 400
        
    author_name = session.get('worker_name', 'System')
    try:
        TicketService.reject_ticket(ticket_id, session.get('worker_id'), author_name, reason)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("API Error in _reject_ticket_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@worker_required
@limiter.limit("20 per minute")
def _add_checklist_api(ticket_id):
    lock_err = check_approval_lock(ticket_id=ticket_id)
    if lock_err: return lock_err
    
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    assigned_to_id_raw = data.get('assigned_to_id')
    assigned_to_id = int(assigned_to_id_raw) if assigned_to_id_raw else None
    
    assigned_team_id_raw = data.get('assigned_team_id')
    assigned_team_id = int(assigned_team_id_raw) if assigned_team_id_raw else None
    
    depends_on_item_id_raw = data.get('depends_on_item_id')
    depends_on_item_id = int(depends_on_item_id_raw) if depends_on_item_id_raw else None
    
    due_date_str = data.get('due_date')
    due_date = None
    if due_date_str:
        from datetime import datetime
        try:
            due_date = datetime.fromisoformat(due_date_str.split('T')[0])
        except (ValueError, TypeError):
            pass
    
    if not title:
        return jsonify({'success': False, 'error': 'Titel fehlt'}), 400
        
    try:
        item = TicketService.add_checklist_item(
            ticket_id, title, assigned_to_id, 
            assigned_team_id=assigned_team_id, 
            due_date=due_date, 
            depends_on_item_id=depends_on_item_id
        )
        return jsonify({'success': True, 'item_id': item.id})
    except Exception as e:
        current_app.logger.exception("API Error in _add_checklist_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@worker_required
@limiter.limit("40 per minute")
def _toggle_checklist_api(item_id):
    lock_err = check_approval_lock(item_id=item_id)
    if lock_err: return lock_err
    
    try:
        worker_name = session.get('worker_name', 'System')
        worker_id = session.get('worker_id')
        item = TicketService.toggle_checklist_item(item_id, worker_name=worker_name, worker_id=worker_id)
        return jsonify({'success': True, 'is_completed': item.is_completed if item else False})
    except Exception as e:
        current_app.logger.exception("API Error in _toggle_checklist_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

@worker_required
@limiter.limit("20 per minute")
def _delete_checklist_api(item_id):
    lock_err = check_approval_lock(item_id=item_id)
    if lock_err: return lock_err
    
    try:
        TicketService.delete_checklist_item(item_id)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("API Error in _delete_checklist_api")
        return jsonify({'success': False, 'error': 'Ein interner Fehler ist aufgetreten.'}), 500

def _my_queue_view():
    """Persönliche Aufgaben-Queue, gruppiert nach Dringlichkeit (v1.11.3)."""
    worker_id = session.get('worker_id')
    days_horizon = request.args.get('days', 7, type=int)
    
    now = get_utc_now()
    
    from models import ChecklistItem
    query = Ticket.query.filter(
        Ticket.is_deleted == False,
        Ticket.status != TicketStatus.ERLEDIGT.value
    ).filter(
        db.or_(
            Ticket.assigned_to_id == worker_id,
            Ticket.checklists.any(
                db.and_(
                    ChecklistItem.assigned_to_id == worker_id,
                    ChecklistItem.is_completed == False
                )
            )
        )
    )
      
    # Sortieren nach Urgency Score (Service Layer handling)
    tickets_list = query.all()
    tickets_list.sort(key=lambda t: TicketService._urgency_score(t, now))
    
    # Gruppierung (v1.11.3: Verbesserte Logik für 'upcoming' bei horizon=0)
    effective_horizon = days_horizon if days_horizon > 0 else 999
    
    groups = {
        'overdue':    [t for t in tickets_list if t.due_date and t.due_date.date() < now.date()],
        'today':      [t for t in tickets_list if t.due_date and t.due_date.date() == now.date()],
        'this_week':  [t for t in tickets_list if t.due_date and 0 < (t.due_date.date() - now.date()).days <= 7],
        'upcoming':   [t for t in tickets_list if t.due_date and 7 < (t.due_date.date() - now.date()).days <= effective_horizon],
        'later':      [t for t in tickets_list if not t.due_date or (t.due_date and (t.due_date.date() - now.date()).days > effective_horizon)],
    }
    
    urgent_count = len(groups['overdue']) + len(groups['today'])
    
    return render_template(
        'my_queue.html',
        groups=groups,
        tickets=tickets_list,
        urgent_count=urgent_count,
        days_horizon=days_horizon,
        today=now
    )


def _api_get_notifications():
    """Fetch recent notifications for the dropdown."""
    from models import Notification
    
    worker_id = session.get('worker_id')
    notifs = Notification.query.filter_by(user_id=worker_id).order_by(Notification.created_at.desc()).limit(15).all()
    
    return jsonify({
        'notifications': [
            {
                'id': n.id,
                'message': n.message,
                'link': n.link or '#',
                'is_read': n.is_read
            } for n in notifs
        ],
        'unread_count': sum(1 for n in notifs if not n.is_read)
    })

def _api_read_notification(notif_id):
    from models import Notification
    from flask import jsonify, session
    from extensions import db
    
    worker_id = session.get('worker_id')
    n = db.session.get(Notification, notif_id)
    if n and n.user_id == worker_id:
        n.is_read = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

def _api_read_all_notifications():
    from models import Notification
    from flask import jsonify, session
    from extensions import db
    
    worker_id = session.get('worker_id')
    Notification.query.filter_by(user_id=worker_id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@admin_or_management_required
def _workload_view():
    """Admin/Management: Auslastungsübersicht pro Mitarbeiter."""
    absent_entries, present_entries = TicketService.get_workload_overview()
    active_workers = Worker.query.filter_by(is_active=True).order_by(Worker.name).all()
    return render_template(
        'workload.html',
        absent_entries=absent_entries,
        present_entries=present_entries,
        active_workers=active_workers,
        today=get_utc_now(),
    )


@admin_or_management_required
@limiter.limit("30 per minute")
def _reassign_ticket_api(ticket_id):
    """API: Einzelnes Ticket einem anderen Mitarbeiter zuweisen."""
    data = request.get_json(silent=True) or {}
    to_worker_id = data.get('to_worker_id')

    if not to_worker_id:
        return jsonify({'success': False, 'error': 'Ziel-Mitarbeiter fehlt.'}), 400

    try:
        to_worker_id = int(to_worker_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Ungültige Worker-ID.'}), 400

    author_name = session.get('worker_name', 'System')
    author_id = session.get('worker_id')

    try:
        TicketService.reassign_ticket(ticket_id, to_worker_id, author_name, author_id)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        current_app.logger.exception("API Error in _reassign_ticket_api")
        return jsonify({'success': False, 'error': 'Interner Fehler.'}), 500


def register_routes(bp):
    """Register ticket routes with explicit endpoints."""
    # Dashboards
    bp.add_url_rule('/', 'index', view_func=worker_required(_dashboard_view))
    bp.add_url_rule('/archive', 'archive', view_func=worker_required(_archive_view))
    bp.add_url_rule('/my-queue', 'my_queue', view_func=worker_required(_my_queue_view))
    bp.add_url_rule('/approvals', 'approvals', view_func=_approvals_view)
    bp.add_url_rule('/projects', 'projects', view_func=worker_required(_projects_view))
    bp.add_url_rule('/workload', 'workload', view_func=_workload_view)

    # Ticket creation & view
    bp.add_url_rule('/ticket/new', 'ticket_new', 
                  view_func=limiter.limit("5 per minute")(_new_ticket_view), 
                  methods=['GET', 'POST'])
    bp.add_url_rule('/ticket/<int:ticket_id>', 'ticket_detail', 
                  view_func=worker_required(_ticket_detail_view))
    bp.add_url_rule('/ticket/<int:ticket_id>/public', 'ticket_public', 
                  view_func=_public_ticket_view)

    # Actions & API
    bp.add_url_rule('/ticket/<int:ticket_id>/comment', 'add_comment', 
                  view_func=worker_required(_add_comment_view), methods=['POST'])
    bp.add_url_rule('/ticket/<int:ticket_id>/assign_me', 'assign_to_me', 
                  view_func=worker_required(_assign_to_me_view), methods=['POST'])
    
    bp.add_url_rule('/api/ticket/<int:ticket_id>/request_approval', 'request_approval_api', 
                  view_func=worker_required(_request_approval_api), methods=['POST'])
    bp.add_url_rule('/api/ticket/<int:ticket_id>/approve', 'approve_ticket_api', 
                  view_func=_approve_ticket_api, methods=['POST'])
    bp.add_url_rule('/api/ticket/<int:ticket_id>/reject', 'reject_ticket_api', 
                  view_func=_reject_ticket_api, methods=['POST'])
    bp.add_url_rule('/api/ticket/<int:ticket_id>/checklist', 'add_checklist', 
                  view_func=_add_checklist_api, methods=['POST'])
    bp.add_url_rule('/api/checklist/<int:item_id>/toggle', 'toggle_checklist', 
                  view_func=_toggle_checklist_api, methods=['POST'])
    bp.add_url_rule('/api/checklist/<int:item_id>', 'delete_checklist', 
                  view_func=_delete_checklist_api, methods=['DELETE'])
    
    bp.add_url_rule('/api/ticket/<int:ticket_id>/status', 'update_status', 
                  view_func=worker_required(_update_status_api), methods=['POST'])
    bp.add_url_rule('/api/ticket/<int:ticket_id>/assign', 'assign_ticket_api', 
                  view_func=worker_required(_assign_ticket_api), methods=['POST'])
    bp.add_url_rule('/api/ticket/<int:ticket_id>/update', 'update_ticket', 
                  view_func=worker_required(_update_ticket_api), methods=['POST'])
    
    bp.add_url_rule('/api/ticket/<int:ticket_id>/apply_template', 'apply_template',
                  view_func=worker_required(_apply_template_api), methods=['POST'])
    bp.add_url_rule('/api/ticket/<int:ticket_id>/reassign', 'reassign_ticket_api',
                  view_func=_reassign_ticket_api, methods=['POST'])

    # Serving
    bp.add_url_rule('/attachment/<int:attachment_id>', 'serve_attachment', 
                  view_func=worker_required(_serve_attachment))

    # Notifications
    bp.add_url_rule('/api/notifications', 'get_notifications', 
                  view_func=worker_required(_api_get_notifications), methods=['GET'])
    bp.add_url_rule('/api/notifications/<int:notif_id>/read', 'read_notification', 
                  view_func=worker_required(_api_read_notification), methods=['POST'])
    bp.add_url_rule('/api/notifications/read_all', 'read_all_notifications', 
                  view_func=worker_required(_api_read_all_notifications), methods=['POST'])


def _apply_template_api(ticket_id):
    """Apply a checklist template to an existing ticket."""
    lock_error = check_approval_lock(ticket_id=ticket_id)
    if lock_error: return lock_error

    data = request.json
    template_id = data.get('template_id')
    if not template_id:
        return jsonify({'success': False, 'error': 'Keine Vorlage ausgewählt.'}), 400
    
    try:
        TicketService.apply_checklist_template(ticket_id, template_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
