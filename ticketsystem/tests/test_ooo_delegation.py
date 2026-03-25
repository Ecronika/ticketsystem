import pytest
from services.ticket_service import TicketService
from services.worker_service import WorkerService
from models import Worker
from extensions import db

def test_circular_delegation(test_app):
    w1 = WorkerService.create_worker("W1", "1234")
    w2 = WorkerService.create_worker("W2", "1234")
    w3 = WorkerService.create_worker("W3", "1234")
    
    # Create loop W1 -> W2 -> W3 -> W1
    w1.is_out_of_office = True
    w1.delegate_to_id = w2.id
    
    w2.is_out_of_office = True
    w2.delegate_to_id = w3.id
    
    w3.is_out_of_office = True
    w3.delegate_to_id = w1.id
    
    db.session.commit()
    
    # Try delegation resolution
    final_id, logs = TicketService._resolve_delegation(w1.id)
    assert final_id is None
    assert any("Zirkuläre Vertretung erkannt" in log for log in logs)

def test_linear_delegation(test_app):
    w4 = WorkerService.create_worker("L1", "1234")
    w5 = WorkerService.create_worker("L2", "1234")
    
    w4.is_out_of_office = True
    w4.delegate_to_id = w5.id
    
    db.session.commit()
    
    final_id, logs = TicketService._resolve_delegation(w4.id)
    assert final_id == w5.id
    assert any("L1 abwesend -> delegiert an L2" in log for log in logs)
