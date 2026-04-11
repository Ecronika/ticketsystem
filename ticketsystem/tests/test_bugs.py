"""Regression tests for confirmed bugs."""
from extensions import db as _db
from models import SystemSettings, Ticket, TicketApproval, Worker
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Bug 1: onboarding_complete set_setting
# ---------------------------------------------------------------------------

def test_setup_creates_onboarding_setting_when_absent(test_app, client):
    """_setup_view must create onboarding_complete even when the row is absent."""
    with test_app.app_context():
        # Ensure an admin worker exists
        admin = Worker.query.filter_by(is_admin=True).first()
        if not admin:
            admin = Worker(
                name="TestAdmin",
                pin_hash=generate_password_hash("7391"),
                is_admin=True,
                is_active=True,
                role="admin",
            )
            _db.session.add(admin)
            _db.session.commit()

        admin_name = admin.name

        # Remove the onboarding_complete row entirely to simulate the edge case
        setting = SystemSettings.query.filter_by(key="onboarding_complete").first()
        if setting:
            _db.session.delete(setting)
            _db.session.commit()

        # Confirm the row is absent (the setup route must NOT redirect away)
        assert SystemSettings.query.filter_by(key="onboarding_complete").first() is None

        # Simulate setup form submission
        client.post("/setup", data={"name": admin_name, "pin": "7391", "pin_confirm": "7391"})

        # After setup: the setting must exist and be "true"
        row = SystemSettings.query.filter_by(key="onboarding_complete").first()
        assert row is not None, "onboarding_complete row must be created"
        assert row.value == "true", f"Expected 'true', got {row.value!r}"


# ---------------------------------------------------------------------------
# Bug 2: approval query uses enum value, not hardcoded string
# ---------------------------------------------------------------------------

def test_get_pending_approvals_uses_enum_value(test_app, client):
    """get_pending_approvals must find tickets whose approval.status equals
    ApprovalStatus.PENDING.value (currently "pending").
    This test documents that the query uses the enum — not a hardcoded literal.
    """
    from enums import ApprovalStatus
    from services.ticket_approval_service import TicketApprovalService

    with test_app.app_context():
        # Create a minimal ticket with a pending approval
        t = Ticket(title="Approval-Test", priority=2, status="offen")
        _db.session.add(t)
        _db.session.flush()

        approval = TicketApproval(
            ticket_id=t.id,
            status=ApprovalStatus.PENDING.value,
        )
        _db.session.add(approval)
        _db.session.commit()

        page = TicketApprovalService.get_pending_approvals(page=1, per_page=100)
        ids = [ticket.id for ticket in page.items]
        assert t.id in ids, (
            f"Ticket {t.id} with approval.status={ApprovalStatus.PENDING.value!r} "
            f"not found in pending approvals."
        )

        # Cleanup
        _db.session.delete(approval)
        _db.session.delete(t)
        _db.session.commit()


# ---------------------------------------------------------------------------
# Bug 3: checklist toggle/delete return 404 for missing items
# ---------------------------------------------------------------------------

def _get_or_create_admin_worker(db_session):
    """Return an admin Worker, creating one if the DB is empty."""
    worker = Worker.query.filter_by(is_admin=True).first()
    if worker is None:
        worker = Worker(
            name="ChecklistTestAdmin",
            pin_hash=generate_password_hash("8264"),
            is_admin=True,
            is_active=True,
            role="admin",
            needs_pin_change=False,
        )
        db_session.add(worker)
        db_session.commit()
    elif worker.needs_pin_change:
        worker.needs_pin_change = False
        db_session.commit()
    return worker


def _login_as_worker(client, worker):
    """Inject a worker session into the test client."""
    with client.session_transaction() as sess:
        sess["worker_id"] = worker.id
        sess["worker_name"] = worker.name
        sess["is_admin"] = worker.is_admin
        sess["role"] = worker.role or "admin"


def test_toggle_checklist_missing_item_returns_404(test_app, client):
    """Toggling a non-existent checklist item must return 404, not 200."""
    with test_app.app_context():
        worker = _get_or_create_admin_worker(_db.session)
        _login_as_worker(client, worker)
    rv = client.post("/api/checklist/999999/toggle")
    assert rv.status_code == 404, (
        f"Expected 404 for missing item, got {rv.status_code}"
    )


def test_delete_checklist_missing_item_returns_404(test_app, client):
    """Deleting a non-existent checklist item must return 404, not 200."""
    with test_app.app_context():
        worker = _get_or_create_admin_worker(_db.session)
        _login_as_worker(client, worker)
    rv = client.delete("/api/checklist/999999")
    assert rv.status_code == 404, (
        f"Expected 404 for missing item, got {rv.status_code}"
    )


# ---------------------------------------------------------------------------
# Bug 4: _notify_meta_change batches notifications into one commit
# ---------------------------------------------------------------------------

def test_notify_meta_change_creates_notification(test_app, client):
    """update_ticket_meta must persist a notification for the assigned worker."""
    from models import Notification
    from services.ticket_core_service import TicketCoreService

    with test_app.app_context():
        # Create a worker to be assigned
        assignee = Worker(
            name="Assignee-Notify-Test",
            pin_hash="x",
            is_active=True,
            role="worker",
        )
        _db.session.add(assignee)
        _db.session.flush()

        ticket = Ticket(
            title="Notify-Meta-Test",
            priority=2,
            status="offen",
            assigned_to_id=assignee.id,
        )
        _db.session.add(ticket)
        _db.session.commit()

        before = Notification.query.filter_by(user_id=assignee.id).count()

        # Call update_ticket_meta as a different author so notification fires
        TicketCoreService.update_ticket_meta(
            ticket.id,
            title="Notify-Meta-Test (updated)",
            priority=2,
            author_name="OtherWorker",
            author_id=None,
        )

        after = Notification.query.filter_by(user_id=assignee.id).count()
        assert after == before + 1, (
            f"Expected one new notification, got {after - before}"
        )

        # Cleanup
        Notification.query.filter_by(user_id=assignee.id).delete()
        _db.session.delete(ticket)
        _db.session.delete(assignee)
        _db.session.commit()
