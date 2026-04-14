"""Tests for Ticket.wait_reason behavior on status changes."""
import pytest
from enums import TicketStatus, WaitReason
from services.ticket_core_service import TicketCoreService
from exceptions import DomainError
from models import Ticket, db


@pytest.fixture
def wartet_ticket(app):
    with app.app_context():
        t = Ticket(title="WR-Test", status=TicketStatus.OFFEN.value)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    yield tid


def test_wartet_without_reason_raises(app, wartet_ticket):
    with app.app_context():
        with pytest.raises(DomainError) as exc:
            TicketCoreService.update_status(
                wartet_ticket, TicketStatus.WARTET, author_name="t"
            )
        assert getattr(exc.value, "field", None) == "wait_reason"


def test_wartet_with_reason_persists(app, wartet_ticket):
    with app.app_context():
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KUNDE.value,
        )
        t = db.session.get(Ticket, wartet_ticket)
        assert t.wait_reason == "kunde"


def test_leaving_wartet_clears_reason(app, wartet_ticket):
    with app.app_context():
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KOLLEGE.value,
        )
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.IN_BEARBEITUNG, author_name="t",
        )
        t = db.session.get(Ticket, wartet_ticket)
        assert t.wait_reason is None


def test_invalid_wait_reason_raises(app, wartet_ticket):
    with app.app_context():
        with pytest.raises(DomainError):
            TicketCoreService.update_status(
                wartet_ticket, TicketStatus.WARTET, author_name="t",
                wait_reason="mondphase",
            )


def test_changing_wait_reason_while_wartet_updates(app, wartet_ticket):
    with app.app_context():
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KUNDE.value,
        )
        TicketCoreService.update_status(
            wartet_ticket, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.LIEFERANT.value,
        )
        t = db.session.get(Ticket, wartet_ticket)
        assert t.wait_reason == "lieferant"


def _login_as_admin(client, admin_worker):
    """Set session to simulate logged-in admin worker."""
    with client.session_transaction() as s:
        s["worker_id"] = admin_worker.id
        s["is_admin"] = True
        s["role"] = "admin"
        s["worker_name"] = admin_worker.name


def test_api_wartet_without_reason_returns_400(client, admin_worker, wartet_ticket):
    """API status endpoint returns 400 when wartet without reason."""
    _login_as_admin(client, admin_worker)
    resp = client.post(
        f"/api/ticket/{wartet_ticket}/status",
        json={"status": "wartet"},
        headers={"X-CSRFToken": "test"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    # @api_endpoint serializes DomainError.field as part of the errors array.
    assert any(e.get("field") == "wait_reason" for e in (body.get("errors") or []))


def test_api_wartet_with_reason_ok(client, admin_worker, wartet_ticket):
    """API status endpoint accepts wartet with reason."""
    _login_as_admin(client, admin_worker)
    resp = client.post(
        f"/api/ticket/{wartet_ticket}/status",
        json={"status": "wartet", "wait_reason": "kunde"},
        headers={"X-CSRFToken": "test"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Task 3.6 – Bulk-undo: prev_state snapshot and restore endpoint
# ---------------------------------------------------------------------------

def test_bulk_status_change_returns_prev_state(client, admin_worker, app):
    """Bulk status_change response must include prev_state snapshot."""
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="BulkUndoTest", status="offen")
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.post(
        "/api/tickets/bulk",
        json={"ticket_ids": [tid], "action": "status_change", "new_status": "in_bearbeitung"},
        headers={"X-CSRFToken": "test"},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body.get("updated") == 1
    assert str(tid) in body.get("prev_state", {})
    assert body["prev_state"][str(tid)]["status"] == "offen"


def test_bulk_set_priority_returns_prev_state(client, admin_worker, app):
    """Bulk set_priority response must include prev_state snapshot."""
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="BulkPrioUndoTest", status="offen", priority=3)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.post(
        "/api/tickets/bulk",
        json={"ticket_ids": [tid], "action": "set_priority", "priority": 1},
        headers={"X-CSRFToken": "test"},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body.get("updated") == 1
    assert str(tid) in body.get("prev_state", {})
    assert body["prev_state"][str(tid)]["priority"] == 3


def test_bulk_set_due_date_has_no_prev_state(client, admin_worker, app):
    """Bulk set_due_date (non-reversible action) must NOT include prev_state."""
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="BulkDueDateTest", status="offen")
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.post(
        "/api/tickets/bulk",
        json={"ticket_ids": [tid], "action": "set_due_date", "due_date": "2026-12-31"},
        headers={"X-CSRFToken": "test"},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert "prev_state" not in body


def test_bulk_restore_rejects_invalid_status(client, admin_worker, app):
    """Restore with an invalid status value must be silently skipped (ticket unchanged)."""
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="RestoreInvalid", status="offen", priority=2)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    # Invalid status in prev_state — should be silently skipped (not applied).
    client.post("/api/tickets/bulk/restore", json={
        "prev_state": {str(tid): {
            "status": "mondphase",  # invalid
            "assigned_to_id": None, "assigned_team_id": None,
            "priority": 2, "wait_reason": None,
        }},
    }, headers={"X-CSRFToken": "test"})
    with app.app_context():
        t = db.session.get(Ticket, tid)
        assert t.status == "offen"  # unchanged


def test_bulk_restore_emits_audit_comment_on_status_change(client, admin_worker, app):
    """Restore must emit a STATUS_CHANGE audit comment when status is reverted."""
    from models import Comment
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="RestoreAudit", status="in_bearbeitung", priority=2)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    client.post("/api/tickets/bulk/restore", json={
        "prev_state": {str(tid): {
            "status": "offen", "assigned_to_id": None, "assigned_team_id": None,
            "priority": 2, "wait_reason": None,
        }},
    }, headers={"X-CSRFToken": "test"})
    with app.app_context():
        comments = Comment.query.filter_by(ticket_id=tid, is_system_event=True).all()
        assert any("Status geändert" in c.text for c in comments), \
            "restore must emit a STATUS_CHANGE comment for audit trail"


def test_bulk_restore_reverts_state(client, admin_worker, app):
    """POST /api/tickets/bulk/restore reverts ticket fields to prev_state."""
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="BulkRestoreTest", status="offen", priority=3)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    # Apply bulk action (priority 3 → 1).
    client.post(
        "/api/tickets/bulk",
        json={"ticket_ids": [tid], "action": "set_priority", "priority": 1},
        headers={"X-CSRFToken": "test"},
    )
    with app.app_context():
        assert db.session.get(Ticket, tid).priority == 1
    # Restore to original state.
    resp = client.post(
        "/api/tickets/bulk/restore",
        json={
            "prev_state": {
                str(tid): {
                    "status": "offen",
                    "assigned_to_id": None,
                    "assigned_team_id": None,
                    "priority": 3,
                    "wait_reason": None,
                }
            }
        },
        headers={"X-CSRFToken": "test"},
    )
    assert resp.status_code == 200
    assert resp.get_json().get("restored") == 1
    with app.app_context():
        assert db.session.get(Ticket, tid).priority == 3
