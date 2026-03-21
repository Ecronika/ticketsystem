import os
from flask import flash, redirect, render_template, request, session, url_for, jsonify, send_from_directory
from extensions import limiter, db
from services.ticket_service import TicketService
from enums import TicketStatus, TicketPriority
from .auth import worker_required, redirect_to
from models import Worker, Attachment

def _dashboard_view():
    """Handle the main dashboard view."""
    worker_id = session.get('worker_id')
    search = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)

    tickets_data = TicketService.get_dashboard_tickets(
        worker_id=worker_id,
        search=search,
        status_filter=status_filter,
        page=page,
        per_page=10
    )
    
    return render_template('index.html', 
                          pagination=tickets_data['focus_pagination'], 
                          focus_tickets=tickets_data['focus_pagination'].items,
                          self_tickets=tickets_data['self'],
                          query=search,
                          current_status=status_filter)

@worker_required
def _archive_view():
    """Handle the ticket archive view (completed tickets)."""
    search = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    tickets_data = TicketService.get_dashboard_tickets(
        search=search,
        status_filter=TicketStatus.ERLEDIGT.value,
        page=page,
        per_page=15
    )
    
    return render_template('archive.html', 
                          pagination=tickets_data['focus_pagination'], 
                          tickets=tickets_data['focus_pagination'].items,
                          query=search,
                          current_status=TicketStatus.ERLEDIGT.value)

def _new_ticket_view():
    """Handle new ticket creation (unauthenticated)."""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        priority_val = request.form.get('priority', 2)
        author_name = request.form.get('author_name') or "Anonym"
        image_base64 = request.form.get('image_base64')

        if not title:
            flash('Bitte einen Titel angeben.', 'warning')
            return render_template('ticket_new.html')

        try:
            priority = TicketPriority(int(priority_val))
            TicketService.create_ticket(
                title=title,
                description=description,
                priority=priority,
                author_name=author_name,
                author_id=session.get('worker_id'),
                image_base64=image_base64
            )
            flash('Ticket erfolgreich erstellt!', 'success')
            return redirect_to('main.index')
        except Exception:
            flash('Fehler beim Erstellen des Tickets.', 'error')

    return render_template('ticket_new.html')

@worker_required
def _ticket_detail_view(ticket_id):
    """Handle ticket detail view."""
    from models import Ticket
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        flash('Ticket nicht gefunden.', 'error')
        return redirect_to('main.index')
    
    workers = Worker.query.filter_by(is_active=True).all()
    return render_template('ticket_detail.html', ticket=ticket, workers=workers)

@worker_required
def _add_comment_view(ticket_id):
    """Handle adding a comment."""
    text = request.form.get('text')
    author_name = session.get('worker_name', 'System')
    
    if text:
        TicketService.add_comment(ticket_id, author_name, session.get('worker_id'), text)
        flash('Kommentar hinzugefügt.', 'success')
    
    return redirect_to('main.ticket_detail', ticket_id=ticket_id)

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

def _serve_attachment(attachment_id):
    """Securely serve uploaded attachments."""
    attachment = db.session.get(Attachment, attachment_id)
    if not attachment:
        return "Not Found", 404
        
    data_dir = current_app.config.get('DATA_DIR', '/data')
    attachments_dir = os.path.join(data_dir, 'attachments')
    
    # Path is stored as just the filename in DB
    return send_from_directory(attachments_dir, attachment.path)

def register_routes(bp):
    """Register ticket routes."""
    # Public Dashboard (Anyone can see? Or only workers? User said "Dashboard fills Self-tickets", implying login)
    # Actually, the user's plan said "Auth refactoring... session['worker_id']".
    # I'll make the dashboard protected for now.
    dashboard_view = worker_required(_dashboard_view)
    dashboard_view.__name__ = 'index'
    bp.add_url_rule('/', view_func=dashboard_view)

    # Public Ticket Creation (limiter 10/min)
    new_ticket_view = limiter.limit("10 per minute")(_new_ticket_view)
    new_ticket_view.__name__ = 'ticket_new'
    bp.add_url_rule('/ticket/new', view_func=new_ticket_view, methods=['GET', 'POST'])

    # Protected Detail & Actions
    ticket_detail_view = _ticket_detail_view
    ticket_detail_view.__name__ = 'ticket_detail'
    bp.add_url_rule('/ticket/<int:ticket_id>', view_func=ticket_detail_view)

    add_comment_view = _add_comment_view
    add_comment_view.__name__ = 'add_comment'
    bp.add_url_rule('/ticket/<int:ticket_id>/comment', view_func=add_comment_view, methods=['POST'])

    update_status_api = _update_status_api
    update_status_api.__name__ = 'update_status'
    bp.add_url_rule('/api/ticket/<int:ticket_id>/status', view_func=update_status_api, methods=['POST'])

    assign_ticket_api = _assign_ticket_api
    assign_ticket_api.__name__ = 'assign_ticket_api'
    bp.add_url_rule('/api/ticket/<int:ticket_id>/assign', view_func=assign_ticket_api, methods=['POST'])

    assign_to_me_view = _assign_to_me_view
    assign_to_me_view.__name__ = 'assign_to_me'
    bp.add_url_rule('/ticket/<int:ticket_id>/assign_me', view_func=assign_to_me_view, methods=['POST'])

    archive_view = _archive_view
    archive_view.__name__ = 'archive'
    bp.add_url_rule('/archive', view_func=archive_view)

    # Attachment Serving
    bp.add_url_rule('/attachment/<int:attachment_id>', 'serve_attachment', view_func=_serve_attachment)
