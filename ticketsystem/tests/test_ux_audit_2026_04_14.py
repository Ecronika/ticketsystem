"""UX-Audit 2026-04-14: Regression tests for UX consistency fixes."""


def _login_as_admin(client, admin_worker):
    with client.session_transaction() as s:
        s["worker_id"] = admin_worker.id
        s["is_admin"] = True
        s["role"] = "admin"
        s["worker_name"] = admin_worker.name


def _login_as_worker(client, worker):
    with client.session_transaction() as s:
        s["worker_id"] = worker.id
        s["is_admin"] = False
        s["role"] = "worker"
        s["worker_name"] = worker.name


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


# ---------------------------------------------------------------------------
# Task 2.7 – Dashboard: wait_reason badge in row & mobile card
# ---------------------------------------------------------------------------

def test_dashboard_row_shows_wait_reason_badge(client, admin_worker, app):
    """Dashboard table row must show wait_reason badge after status badge when status=WARTET."""
    from models import Ticket, db
    from enums import TicketStatus, WaitReason
    _login_as_admin(client, admin_worker)
    with app.app_context():
        t = Ticket(title="WR-Row", status=TicketStatus.WARTET.value,
                   wait_reason=WaitReason.KUNDE.value)
        db.session.add(t)
        db.session.commit()
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    # The reason appears capitalized (Kunde) with the Wartet-specific title attr.
    assert "Wartet auf kunde" in html or 'title="Wartet auf kunde"' in html
    assert "Kunde" in html


def test_dashboard_hides_reason_badge_when_not_wartet(client, admin_worker, app):
    """Dashboard must not show wait_reason badge when status != WARTET."""
    from models import Ticket, db
    from enums import TicketStatus
    _login_as_admin(client, admin_worker)
    with app.app_context():
        # Status=offen → no wait_reason badge even if column has stale data.
        t = Ticket(title="Non-Wartet", status=TicketStatus.OFFEN.value,
                   wait_reason=None)
        db.session.add(t)
        db.session.commit()
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert 'title="Wartet auf' not in html


# ---------------------------------------------------------------------------
# Task 3.1 – Login: client-side filter for worker-chip quick-select
# ---------------------------------------------------------------------------

def test_login_has_worker_chip_filter(client):
    """Login page must render workerChipFilter search input."""
    resp = client.get("/login")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="workerChipFilter"' in html
    assert 'placeholder="Mitarbeiter suchen..."' in html


# ---------------------------------------------------------------------------
# Task 3.2 – Login: surface remaining PIN attempts in flash message
# ---------------------------------------------------------------------------

def test_login_failed_pin_shows_remaining_attempts(client, app):
    """After a failed login, the user should see how many attempts remain."""
    from models import Worker, db
    from services.worker_service import WorkerService

    with app.app_context():
        # Use a strong, non-blocklisted PIN (see CLAUDE.md note)
        WorkerService.create_worker("LoginTest", "7391", role="worker")

    # Attempt login with wrong PIN to trigger the remaining-attempts flash.
    resp = client.post("/login", data={
        "worker_name": "LoginTest",
        "pin": "0000",  # wrong
        "csrf_token": "test",
    }, follow_redirects=True)
    html = resp.get_data(as_text=True)
    # Check for either "Noch X Versuche" (still has attempts) or "Account gesperrt"
    assert ("Noch" in html and "Versuche" in html) or "gesperrt" in html.lower(), \
        f"expected 'Noch X Versuche übrig' or 'Account gesperrt' in flash"


# ---------------------------------------------------------------------------
# Task 3.3 – Change PIN: client-side strength meter
# ---------------------------------------------------------------------------

def test_change_pin_has_strength_meter(client, admin_worker):
    """PIN change page must render strength meter elements."""
    _login_as_admin(client, admin_worker)
    resp = client.get("/change-pin")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="pinStrengthBar"' in html
    assert 'id="pinStrengthText"' in html


# ---------------------------------------------------------------------------
# Task 3.4 – Public Ticket View: mini-header with return-path
# ---------------------------------------------------------------------------

def test_public_ticket_has_return_link(client, app):
    """Public ticket view must show mini-header with 'Neues Ticket melden' return-path."""
    from models import Ticket, db
    with app.app_context():
        t = Ticket(title="PublicViewTest")
        db.session.add(t)
        db.session.commit()
        tid = t.id
    # Public view does NOT require login
    resp = client.get(f"/ticket/{tid}/public")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Neues Ticket melden" in html
    assert f"#{tid}" in html


# ---------------------------------------------------------------------------
# Task 4.1 – Help Offcanvas: client-side search
# ---------------------------------------------------------------------------

def test_help_offcanvas_has_search_input(client, admin_worker):
    """Help offcanvas must have a searchable input and sections marked with help-section class."""
    _login_as_admin(client, admin_worker)
    # Dashboard (index) includes page_help with sections
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    if "pageHelpOffcanvas" in html:
        assert 'id="helpOffcanvasSearch"' in html, "search input missing"
        assert "help-section" in html, "help sections must carry help-section class for filter"
