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
    """Test worker login and session persistence (with needs_pin_change=False)."""
    # Create worker who already changed their PIN
    worker = Worker(name="Hans", pin_hash=generate_password_hash("1234"), needs_pin_change=False)
    db.session.add(worker)
    db.session.commit()
    
    # Login - first check for redirect to dashboard
    resp = client.post('/login', data={'worker_name': 'Hans', 'pin': '1234'})
    assert resp.status_code == 302
    assert "/" in resp.location 

    # Now follow the redirect to check the final page content
    response = client.post('/login', data={'worker_name': 'Hans', 'pin': '1234'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Hans' in response.data
    
    # Check session via dashboard
    response = client.get('/')
    assert response.status_code == 200
    assert b'Hans' in response.data

def test_mandatory_pin_change(client, db):
    """Test that a new worker is forced to change their PIN."""
    # Create worker with default needs_pin_change=True
    worker = Worker(name="Neu", pin_hash=generate_password_hash("0000"), needs_pin_change=True)
    db.session.add(worker)
    db.session.commit()
    
    # Login should redirect to /change-pin
    resp = client.post('/login', data={'worker_name': 'Neu', 'pin': '0000'})
    assert resp.status_code == 302
    assert "/change-pin" in resp.location

    # Verify /change-pin is accessible
    with client:
        # We need to be logged in to access change-pin
        client.post('/login', data={'worker_name': 'Neu', 'pin': '0000'})
        response = client.get('/change-pin')
        assert response.status_code == 200
        assert b'PIN \xc3\xa4ndern' in response.data

def test_worker_required_guard(client):
    """Test that unauthorized access to dashboard is redirected to login."""
    # FIX-14: /logout is POST-only; directly clear session instead
    with client.session_transaction() as sess:
        sess.clear()
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


def test_confidential_ticket_access(client, db, test_app):
    """Test that confidential tickets are protected against unauthorized access."""
    # Create users
    admin = Worker(name="Admin", pin_hash="hash", is_admin=True, role='admin')
    worker1 = Worker(name="Worker 1", pin_hash="hash", role='worker')
    worker2 = Worker(name="Worker 2", pin_hash="hash", role='worker')
    db.session.add_all([admin, worker1, worker2])
    db.session.commit()
    
    with test_app.app_context():
        ticket = TicketService.create_ticket(
            title="Geheim", 
            description="Lohnabrechnung", 
            author_name="Worker 1",
            author_id=worker1.id,
            is_confidential=True
        )
        ticket_id = ticket.id
        
    # Test Worker 2 (No Access)
    with client.session_transaction() as sess:
        sess['worker_id'] = worker2.id
        sess['worker_name'] = worker2.name
        sess['role'] = 'worker'
        sess['is_admin'] = False
    response = client.get(f'/ticket/{ticket_id}', follow_redirects=True)
    assert b'Keine Berechtigung' in response.data
    
    # Test Admin (Access)
    with client.session_transaction() as sess:
        sess['worker_id'] = admin.id
        sess['worker_name'] = admin.name
        sess['role'] = 'admin'
        sess['is_admin'] = True
    response = client.get(f'/ticket/{ticket_id}')
    assert response.status_code == 200
    assert b'Geheim' in response.data
    
    # Test Worker 1 (Author Access)
    with client.session_transaction() as sess:
        sess['worker_id'] = worker1.id
        sess['worker_name'] = worker1.name
        sess['role'] = 'worker'
        sess['is_admin'] = False
    response = client.get(f'/ticket/{ticket_id}')
    assert response.status_code == 200
    assert b'Geheim' in response.data
    
    # Test Worker 2 after Assignment (Access)
    with test_app.app_context():
        TicketService.assign_ticket(ticket_id, worker2.id, "Admin", admin.id)
    with client.session_transaction() as sess:
        sess['worker_id'] = worker2.id
        sess['worker_name'] = worker2.name
        sess['role'] = 'worker'
        sess['is_admin'] = False
    response = client.get(f'/ticket/{ticket_id}')
    assert response.status_code == 200
    assert b'Geheim' in response.data
