"""UX-Audit 2026-04-14: Regression tests for UX consistency fixes."""


def _login_as_admin(client, admin_worker):
    with client.session_transaction() as s:
        s["worker_id"] = admin_worker.id
        s["is_admin"] = True
        s["role"] = "admin"
        s["worker_name"] = admin_worker.name


# ---------------------------------------------------------------------------
# Task 1.1 – Admin-Trash: native confirm() → showConfirm modal
# ---------------------------------------------------------------------------

def test_trash_no_native_confirm(client, admin_worker):
    """GET /admin/trash must not use native onclick confirm() dialog."""
    _login_as_admin(client, admin_worker)
    r = client.get("/admin/trash")
    assert r.status_code == 200
    assert b'onclick="return confirm(' not in r.data


def test_trash_has_data_confirm_permanent_delete(client, admin_worker):
    """GET /admin/trash must use data-confirm-permanent-delete attribute."""
    _login_as_admin(client, admin_worker)
    r = client.get("/admin/trash")
    assert r.status_code == 200
    assert b'data-confirm-permanent-delete' in r.data


def test_trash_empty_state_no_redundant_paragraph(client, admin_worker):
    """Empty-state block must not contain the redundant 'Gelöschte Tickets erscheinen hier' line."""
    _login_as_admin(client, admin_worker)
    r = client.get("/admin/trash")
    assert r.status_code == 200
    assert 'Gelöschte Tickets erscheinen hier' not in r.data.decode('utf-8')


# ---------------------------------------------------------------------------
# Task 1.2 – Ticket-New: inline onclick → data-bs-dismiss
# ---------------------------------------------------------------------------

def test_ticket_new_banner_has_no_inline_onclick(client, admin_worker):
    """Created-ticket success banner must not use inline onclick="this.closest".

    Bootstrap's data-bs-dismiss="alert" is the idiomatic approach.
    """
    _login_as_admin(client, admin_worker)
    r = client.get("/ticket/new?created=1")
    assert r.status_code == 200
    assert 'onclick="this.closest' not in r.data.decode('utf-8')


# ---------------------------------------------------------------------------
# Task 1.3 – Approvals: aria-label for icon-only detail link
# ---------------------------------------------------------------------------

def test_approvals_icon_link_has_aria_label(client, admin_worker, app):
    """Icon-only detail link on approval cards must have aria-label for screen readers."""
    import re
    from models import Ticket, db
    from services.ticket_approval_service import TicketApprovalService

    _login_as_admin(client, admin_worker)

    # Seed one pending-approval ticket
    with app.app_context():
        t = Ticket(title="Approval-UX-Test", status="offen")
        db.session.add(t)
        db.session.commit()
        ticket_id = t.id

    # Request approval so ticket shows on /approvals
    TicketApprovalService.request_approval(
        ticket_id=ticket_id,
        worker_id=admin_worker.id,
        worker_name=admin_worker.name
    )

    resp = client.get("/approvals")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Every anchor containing bi-arrow-up-right must carry aria-label
    for m in re.finditer(r'<a [^>]*bi-arrow-up-right[^>]*>', html):
        assert 'aria-label' in m.group(0), f"missing aria-label: {m.group(0)}"
