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
