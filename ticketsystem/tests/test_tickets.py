import pytest
from models import Worker, Ticket, Comment
from services.ticket_service import TicketService
from enums import TicketStatus, TicketPriority
from werkzeug.security import generate_password_hash

def test_create_ticket(test_app, db):
    """Test creating a ticket via TicketService."""
    with test_app.app_context():
        ticket = TicketService.create_ticket(
            title="Defektes Rohr",
            description="Leckt im Keller",
            priority=TicketPriority.HOCH,
            author_name="Azubi Max"
        )
        assert ticket.id is not None
        assert ticket.title == "Defektes Rohr"
        assert ticket.status == "offen"
        assert ticket.priority == 1
        
        # Check initial comment
        comment = Comment.query.filter_by(ticket_id=ticket.id).first()
        assert comment is not None
        assert "Leckt im Keller" in comment.text
        assert comment.author == "Azubi Max"

def test_update_status(test_app, db):
    """Test updating ticket status."""
    with test_app.app_context():
        ticket = TicketService.create_ticket(title="Test Ticket")
        updated_ticket = TicketService.update_status(
            ticket.id, 
            TicketStatus.IN_BEARBEITUNG, 
            author_name="Meister"
        )
        assert updated_ticket.status == "in_bearbeitung"
        
        # Check status change comment
        comments = Comment.query.filter_by(ticket_id=ticket.id).all()
        assert any("Status geändert" in c.text for c in comments)

def test_unauthenticated_ticket_creation_route(client):
    """Test that anyone can create a ticket via the UI."""
    response = client.post('/ticket/new', data={
        'title': 'Public Issue',
        'description': 'Something is broken',
        'author_name': 'Guest',
        'priority': '2'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Ticket erfolgreich erstellt' in response.data
    
    # Verify in DB
    from models import Ticket
    ticket = Ticket.query.filter_by(title='Public Issue').first()
    assert ticket is not None
    assert ticket.description == 'Something is broken'

def test_worker_login_and_session(client, db):
    """Test worker login and session persistence."""
    # Create worker
    worker = Worker(name="Hans", pin_hash=generate_password_hash("1234"))
    db.session.add(worker)
    db.session.commit()
    
    # Login - first check for redirect
    resp = client.post('/login', data={'worker_id': worker.id, 'pin': '1234'})
    assert resp.status_code == 302
    assert "/" in resp.location # Should redirect to dashboard

    # Now follow the redirect to check the final page content
    response = client.post('/login', data={'worker_id': worker.id, 'pin': '1234'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Willkommen zur\xc3\xbcck, Hans' in response.data
    
    # Check session via dashboard (must be protected by worker_required)
    response = client.get('/')
    assert response.status_code == 200
    assert b'Willkommen, Hans' in response.data

def test_worker_required_guard(client):
    """Test that unauthorized access to dashboard is redirected to login."""
    client.get('/logout', follow_redirects=True) # Ensure logged out
    response = client.get('/', follow_redirects=True)
    assert b'Mitarbeiter Login' in response.data

def test_assign_ticket(test_app, db):
    """Test assigning a ticket to a worker."""
    with test_app.app_context():
        # Setup
        worker = Worker(name="Tester", pin_hash="hash")
        db.session.add(worker)
        db.session.commit()
        
        ticket = TicketService.create_ticket("Assign Test", "Test")
        
        # Assign
        TicketService.assign_ticket(ticket.id, worker.id, "System")
        assert ticket.assigned_to_id == worker.id
        
        # Verify comment
        comment = Comment.query.filter_by(ticket_id=ticket.id).order_by(Comment.id.desc()).first()
        assert "Zuständigkeit geändert" in comment.text
        
        # Self assign (unassign first to trigger a change)
        TicketService.assign_ticket(ticket.id, None, "System")
        TicketService.assign_ticket(ticket.id, worker.id, worker.name)
        comment = Comment.query.filter_by(ticket_id=ticket.id).order_by(Comment.id.desc()).first()
        assert "hat sich das Ticket selbst zugewiesen" in comment.text
