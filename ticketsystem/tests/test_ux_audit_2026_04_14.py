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


# ---------------------------------------------------------------------------
# Task 1.4 – My Queue: Priority as text+icon chip, not only color border
# ---------------------------------------------------------------------------

def test_my_queue_shows_priority_as_text(client, admin_worker, app):
    """Priority must be shown as text label, not only via border color (WCAG: color-only info)."""
    _login_as_admin(client, admin_worker)

    # Seed a high-priority ticket assigned to the logged-in admin
    with app.app_context():
        from models import Ticket, db
        t = Ticket(
            title="Prio-Test-1.4",
            priority=1,  # HIGH
            assigned_to_id=admin_worker.id,
            status="offen",
            due_date=None,
        )
        db.session.add(t)
        db.session.commit()

    resp = client.get("/my-queue")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # HIGH priority ticket must show 'Hoch' text label
    assert "Hoch" in html, "HIGH priority ticket must show 'Hoch' text label"


# ---------------------------------------------------------------------------
# Task 2.6 – Sidebar: wait-reason popover markup
# ---------------------------------------------------------------------------

def test_sidebar_has_wait_reason_picker(client, admin_worker, app):
    from models import Ticket, db
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="WR-UI-Test")
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.get(f"/ticket/{tid}")
    html = resp.get_data(as_text=True)
    assert 'id="waitReasonPopover"' in html
    for r in ("kunde", "lieferant", "kollege", "sonstiges"):
        assert f'data-wait-reason="{r}"' in html, f"missing reason button: {r}"


def test_sidebar_shows_wait_reason_badge_when_set(client, admin_worker, app):
    from models import Ticket, db
    from enums import TicketStatus, WaitReason
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="WR-badge", status=TicketStatus.WARTET.value, wait_reason=WaitReason.LIEFERANT.value)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.get(f"/ticket/{tid}")
    html = resp.get_data(as_text=True)
    assert "Wartet auf:" in html
    assert "Lieferant" in html
