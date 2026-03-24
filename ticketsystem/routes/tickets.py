import os
from datetime import datetime, timezone, timedelta
from flask import flash, redirect, render_template, request, session, url_for, jsonify, send_from_directory, current_app
from markupsafe import Markup
from extensions import limiter, db
from services.ticket_service import TicketService
from enums import TicketStatus, TicketPriority
from .auth import worker_required, redirect_to, admin_required
from models import Worker, Attachment, Ticket

def _dashboard_view():
    """Handle the main dashboard view."""
    worker_id = session.get('worker_id')
    search = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    assigned_to_me = request.args.get('assigned_to_me') == '1'
    unassigned_only = request.args.get('unassigned') == '1'
    
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
                          today=datetime.now(timezone.utc).replace(tzinfo=None))


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
        
        # v1.12.0: Zuweisungs-Logik
        assigned_to_id_raw = request.form.get('assigned_to_id')
        assigned_team_id_raw = request.form.get('assigned_team_id')
        
        assigned_to_id = None
        assigned_team_id = None
        
        if assigned_to_id_raw:
            assigned_to_id = int(assigned_to_id_raw)
        elif session.get('worker_id') and not assigned_team_id_raw:
            # Fallback: Ersteller ist Worker -> Auto-Zuweisung, es sei denn es ist einem Team zugewiesen
            assigned_to_id = session.get('worker_id')
        
        if assigned_team_id_raw:
            assigned_team_id = int(assigned_team_id_raw)

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
                tags=tags
            )
            session['last_created_ticket_id'] = ticket.id
            ticket_url = f"{request.headers.get('X-Ingress-Path', '')}{url_for('main.ticket_detail', ticket_id=ticket.id)}"
            link_html = f' <a href="{ticket_url}" class="alert-link">Ticket #{ticket.id} ansehen →</a>'
            
            if not session.get('worker_id'):
                return redirect_to('main.ticket_new', created=ticket.id)
            
            flash(Markup(f'Ticket {link_html} erfolgreich erstellt!'), 'success')
            return redirect_to('main.index')
        except Exception:
            flash('Fehler beim Erstellen des Tickets.', 'error')

    from models import Worker, Team
    workers = Worker.query.filter_by(is_active=True).all()
    teams = Team.query.all()
    return render_template('ticket_new.html', workers=workers, teams=teams)

@worker_required
def _ticket_detail_view(ticket_id):
    """Handle ticket detail view."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        flash('Ticket nicht gefunden.', 'error')
        return redirect_to('main.index')
    
    workers = Worker.query.filter_by(is_active=True).all()
    from models import Team
    teams = Team.query.all()
    return render_template('ticket_detail.html', ticket=ticket, workers=workers, teams=teams)

@limiter.limit("30 per minute")
def _public_ticket_view(ticket_id):
    """Public read-only status page (P0-1)."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return render_template('404.html'), 404
        
    return render_template('ticket_public.html', ticket=ticket)

@worker_required
def _add_comment_view(ticket_id):
    """Handle adding a comment."""
    text = request.form.get('text')
    author_name = session.get('worker_name', 'System')
    
    if text:
        TicketService.add_comment(ticket_id, author_name, session.get('worker_id'), text)
        flash('Kommentar hinzugefügt.', 'success')
    
    return redirect_to('main.ticket_detail', ticket_id=ticket_id, _anchor='comment-form')

@worker_required
def _update_status_api(ticket_id):
    """Handle AJAX status update."""
    data = request.get_json()
    new_status_val = data.get('status')
    author_name = session.get('worker_name', 'System')
    
    if not new_status_val:
        return jsonify({'success': False, 'error': 'Kein Status angegeben'}), 400
    
    try:
        TicketService.update_status(ticket_id, new_status_val, author_name, session.get('worker_id'))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@worker_required
def _assign_ticket_api(ticket_id):
    """Handle AJAX ticket assignment."""
    data = request.get_json()
    worker_id = data.get('worker_id')
    author_name = session.get('worker_name', 'System')
    
    try:
        # Note: worker_id can be None/null for "Unassigned"
        TicketService.assign_ticket(ticket_id, worker_id, author_name, session.get('worker_id'))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@worker_required
def _assign_to_me_view(ticket_id):
    """Assign the ticket to the current logged-in worker."""
    worker_id = session.get('worker_id')
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
        
    from extensions import Config
    data_dir = current_app.config.get('DATA_DIR', Config.get_data_dir())
    attachments_dir = os.path.join(data_dir, 'attachments')
    
    # Path-Traversal protection: only use basename and ensure it's not empty
    safe_filename = os.path.basename(attachment.path)
    if not safe_filename or safe_filename in ['.', '..']:
        return "Invalid Path", 400
        
    return send_from_directory(attachments_dir, safe_filename)

@worker_required
def _update_ticket_api(ticket_id):
    """Handle ticket meta updates (title/priority/due_date)."""
    data = request.get_json()
    new_title = data.get('title')
    new_prio = data.get('priority')
    new_due_str = data.get('due_date')
    order_reference = data.get('order_reference')
    reminder_date_str = data.get('reminder_date')
    tags = data.get('tags') # List of strings expected
    author_name = session.get('worker_name', 'System')
    
    if not new_title:
        return jsonify({'success': False, 'error': 'Titel fehlt'}), 400
        
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

    if new_prio is None:
        return jsonify({'success': False, 'error': 'Priorität fehlt'}), 400

    try:
        TicketService.update_ticket_meta(
            ticket_id, new_title, new_prio, author_name, session.get('worker_id'), 
            due_date=due_date, order_reference=order_reference, reminder_date=reminder_date,
            tags=tags
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_required
def _approve_ticket_api(ticket_id):
    author_name = session.get('worker_name', 'System')
    try:
        TicketService.approve_ticket(ticket_id, session.get('worker_id'), author_name)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@worker_required
def _add_checklist_api(ticket_id):
    data = request.get_json()
    title = data.get('title')
    assigned_to_id_raw = data.get('assigned_to_id')
    assigned_to_id = int(assigned_to_id_raw) if assigned_to_id_raw else None
    
    if not title:
        return jsonify({'success': False, 'error': 'Titel fehlt'}), 400
        
    try:
        item = TicketService.add_checklist_item(ticket_id, title, assigned_to_id)
        return jsonify({'success': True, 'item_id': item.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@worker_required
def _toggle_checklist_api(item_id):
    try:
        worker_name = session.get('worker_name', 'System')
        worker_id = session.get('worker_id')
        item = TicketService.toggle_checklist_item(item_id, worker_name=worker_name, worker_id=worker_id)
        return jsonify({'success': True, 'is_completed': item.is_completed if item else False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@worker_required
def _delete_checklist_api(item_id):
    try:
        TicketService.delete_checklist_item(item_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@worker_required
def _my_queue_view():
    """Persönliche Aufgaben-Queue, gruppiert nach Dringlichkeit (v1.11.3)."""
    worker_id = session.get('worker_id')
    days_horizon = request.args.get('days', 7, type=int)
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # PWA-Filter: Horizon immer bis zum Ende des Ziel-Tages (23:59:59)
    horizon = (now + timedelta(days=days_horizon)).replace(hour=23, minute=59, second=59) if days_horizon > 0 else None
    
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
    
    if horizon:
        # Überfällige IMMER + fällige inerhalb des Horizonts + ohne Datum
        query = query.filter(
            db.or_(
                Ticket.due_date <= horizon,
                Ticket.due_date == None
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


def register_routes(bp):
    """Register ticket routes with explicit endpoints."""
    # Dashboards
    bp.add_url_rule('/', 'index', view_func=worker_required(_dashboard_view))
    bp.add_url_rule('/archive', 'archive', view_func=worker_required(_archive_view))
    bp.add_url_rule('/my-queue', 'my_queue', view_func=worker_required(_my_queue_view))

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
    
    bp.add_url_rule('/api/ticket/<int:ticket_id>/approve', 'approve_ticket_api', 
                  view_func=_approve_ticket_api, methods=['POST'])
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

    # Serving
    bp.add_url_rule('/attachment/<int:attachment_id>', 'serve_attachment', 
                  view_func=worker_required(_serve_attachment))
