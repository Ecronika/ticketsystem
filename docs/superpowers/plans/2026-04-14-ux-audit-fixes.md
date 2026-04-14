# UX Audit Fixes 2026-04-14 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the Severity-1/2/3 findings from [docs/ux-audit-2026-04-14.md](../../ux-audit-2026-04-14.md) and lift the score from 9.2/10 to 10/10.

**Architecture:** Four independently deployable phases. Phase 1 and 4 are pure frontend/template fixes. Phase 2 introduces a new `wait_reason` column on `ticket` (schema extension, not extraction) plus an inline popover in the sidebar. Phase 3 adds a bulk-undo pattern on top of the existing soft-delete undo toast and a client-side login-chip filter.

**Tech Stack:** Flask 3, Jinja2, Bootstrap 5.3, vanilla JS, SQLAlchemy, Alembic, pytest, flake8.

---

## Scope (from audit)

| Phase | # | Finding | Sev | Files |
|-------|---|---------|-----|-------|
| 1 | 1 | Admin-Trash uses native `confirm()` instead of global modal | 2 | `templates/admin_trash.html` |
| 1 | 2 | Inline `onclick` in created-banner close button | 1 | `templates/ticket_new.html` |
| 1 | 3 | Icon-only link without `aria-label` in approvals | 1 | `templates/approvals.html` |
| 1 | 4 | Priority shown only as border color in my_queue cards | 2 | `templates/my_queue.html` |
| 2 | 5 | Status "Wartet" has no sub-state | 3 | enum, model, service, migration, sidebar, templates |
| 3 | 6 | No bulk-undo for status/assign/priority | 2 | `routes/ticket_api.py`, `templates/index.html` |
| 3 | 7 | Login worker-chip list has no filter | 2 | `templates/login.html` |
| 3 | 8 | Login rate-limit has no client-visible "X attempts left" | 2 | `routes/auth.py`, `templates/login.html` |
| 3 | 9 | PIN strength indicator missing | 2 | `templates/change_pin.html`, new JS snippet |
| 3 | 10 | Public ticket view has no navigation / no back link | 2 | `templates/ticket_public.html` |
| 3 | 11 | Mobile bulk-action bar overloaded (< 400 px) | 2 | `templates/index.html`, `static/css/style.css` |
| 4 | 12 | Help offcanvas not searchable | 1 | `templates/components/_page_help_offcanvas.html` |
| 4 | 13 | No "back to Projekte" from filtered dashboard | 1 | `templates/index.html` |
| 4 | 14 | Redundant settings subtitle | 1 | `templates/settings.html` |
| 4 | 15 | Redundant empty-trash text | 1 | `templates/admin_trash.html` |

---

## File Map

| File | Change |
|------|--------|
| `ticketsystem/enums.py` | Add `WaitReason` Enum. |
| `ticketsystem/models.py` | Add `wait_reason` column to `Ticket`. |
| `ticketsystem/migrations/versions/a7b8c9d0e1f2_add_wait_reason.py` | New migration, adds nullable column. |
| `ticketsystem/services/ticket_core_service.py` | `update_status` accepts `wait_reason`; enforces required-on-WARTET, clears-on-leave. |
| `ticketsystem/routes/ticket_api.py` | `_update_status_api` reads `wait_reason` from payload; bulk endpoint returns before-state for undo. |
| `ticketsystem/routes/auth.py` | Flash `remaining_attempts` on login failure. |
| `ticketsystem/templates/components/_management_sidebar.html` | Inline popover for Wartet-reason choice; show badge. |
| `ticketsystem/templates/components/_ticket_item.html` | Render "Wartet: Kunde" badge in row + card. |
| `ticketsystem/templates/my_queue.html` | Priority icon + label in kanban card; Wartet-reason badge. |
| `ticketsystem/templates/admin_trash.html` | `showConfirm` for permanent delete; strip redundant empty-state text. |
| `ticketsystem/templates/ticket_new.html` | Remove inline `onclick`, replace with `data-bs-dismiss="alert"`. |
| `ticketsystem/templates/approvals.html` | Add `aria-label` to icon-only link. |
| `ticketsystem/templates/login.html` | Chip-filter input; show `remaining_attempts` from flash. |
| `ticketsystem/templates/change_pin.html` | PIN strength meter. |
| `ticketsystem/templates/ticket_public.html` | Mini-header with "Neues Ticket melden"-link. |
| `ticketsystem/templates/index.html` | "Zurück zu Projekte"-breadcrumb when filtered; bulk-undo hook. |
| `ticketsystem/templates/settings.html` | Remove redundant subtitle. |
| `ticketsystem/templates/components/_page_help_offcanvas.html` | Top search input, JS filter. |
| `ticketsystem/static/css/style.css` | `.bulk-action-bar` overflow rules < 400 px; status-badge for wait_reason. |
| `ticketsystem/static/js/base_ui.js` | Undo helper: accept `prevState` payload and POST to restore endpoint. |
| `ticketsystem/static/js/help.js` | Help-offcanvas search filter (if search input present). |
| `ticketsystem/tests/test_wait_reason.py` | New: service + API tests for wait_reason. |
| `ticketsystem/tests/test_ux_audit_2026_04_14.py` | New: render-assertions for all template fixes. |

**Dockerfile:** No changes (no new top-level `.py` files).

---

## Baseline

Before starting:

```bash
cd ticketsystem && python -m pytest tests/ -q
# Expected: 106 passed
python -m flake8 --max-line-length=120 *.py routes/ services/
# Expected: clean
```

Record the pass count. Every phase ends with a verify step that must show the same or higher count and no new flake8 findings.

---

# Phase 1 — Quick Wins (Consistency + A11y)

**Score goal:** 9.2 → 9.4. **Duration:** 0.5 day. **DB:** none.

## Task 1.1: Admin-Trash — replace native `confirm()` with `showConfirm`

**Files:**
- Modify: `ticketsystem/templates/admin_trash.html:68-82`
- Modify: `ticketsystem/templates/admin_trash.html:92` (redundant text)
- Test: `ticketsystem/tests/test_ux_audit_2026_04_14.py` (new)

- [ ] **Step 1: Write failing render test**

Create `ticketsystem/tests/test_ux_audit_2026_04_14.py`:

```python
"""Render-level assertions for the 2026-04-14 UX audit fixes."""
from tests.conftest import login_as_admin


def test_trash_uses_global_confirm_not_native(client, app):
    login_as_admin(client, app)
    resp = client.get("/admin/trash")
    html = resp.get_data(as_text=True)
    assert 'onclick="return confirm(' not in html, "native confirm() still present"
    assert 'data-confirm-permanent-delete' in html, "new confirm-hook missing"


def test_trash_empty_state_has_no_redundant_text(client, app):
    login_as_admin(client, app)
    resp = client.get("/admin/trash")
    html = resp.get_data(as_text=True)
    if "Der Papierkorb ist leer" in html:
        assert "Gelöschte Tickets erscheinen hier" not in html
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ticketsystem && python -m pytest tests/test_ux_audit_2026_04_14.py -v
# Expected: FAIL — 'onclick="return confirm(' still present
```

- [ ] **Step 3: Replace inline `onclick` in admin_trash.html**

Edit `admin_trash.html` around line 76-81:

```html
<button type="submit" name="action" value="delete_permanent"
        class="btn btn-sm btn-outline-danger rounded-pill"
        data-confirm-permanent-delete
        data-ticket-id="{{ ticket.id }}">
    <i class="bi bi-trash me-1"></i>Endgültig
</button>
```

Add a small inline `<script nonce="{{ g.csp_nonce }}">` at the bottom of the `{% block content %}`:

```html
<script nonce="{{ g.csp_nonce }}">
document.querySelectorAll('[data-confirm-permanent-delete]').forEach(function(btn) {
    btn.addEventListener('click', function(ev) {
        const id = btn.dataset.ticketId;
        ev.preventDefault();
        if (!window.showConfirm) {
            if (confirm('Ticket #' + id + ' dauerhaft löschen?')) btn.form.submit();
            return;
        }
        window.showConfirm(
            'Ticket #' + id + ' endgültig löschen?',
            'Diese Aktion kann nicht rückgängig gemacht werden.',
            { confirmLabel: 'Endgültig löschen', variant: 'danger' }
        ).then(function(ok) { if (ok) btn.form.submit(); });
    });
});
</script>
```

- [ ] **Step 4: Remove redundant empty-state paragraph**

In `admin_trash.html` around line 89-93, delete this line:

```html
<p class="small opacity-75">Gelöschte Tickets erscheinen hier und können wiederhergestellt werden.</p>
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd ticketsystem && python -m pytest tests/test_ux_audit_2026_04_14.py -v
# Expected: PASS (both)
```

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/templates/admin_trash.html ticketsystem/tests/test_ux_audit_2026_04_14.py
git commit -m "fix(ui): replace native confirm() in admin trash with global showConfirm modal"
```

## Task 1.2: Remove inline `onclick` in ticket_new banner

**Files:**
- Modify: `ticketsystem/templates/ticket_new.html:33`

- [ ] **Step 1: Add failing render test**

Append to `tests/test_ux_audit_2026_04_14.py`:

```python
def test_ticket_new_banner_has_no_inline_onclick(client, app):
    login_as_admin(client, app)
    resp = client.get("/ticket/new?created=1")
    html = resp.get_data(as_text=True)
    assert "onclick=\"this.closest" not in html, "inline onclick still present"
```

- [ ] **Step 2: Run and confirm fail**

```bash
cd ticketsystem && python -m pytest tests/test_ux_audit_2026_04_14.py::test_ticket_new_banner_has_no_inline_onclick -v
```

- [ ] **Step 3: Replace inline onclick**

In `ticket_new.html:33`:

```html
<button type="button" class="btn btn-sm btn-link text-muted text-decoration-none ms-auto"
        data-bs-dismiss="alert" aria-label="Meldung schließen">Schließen</button>
```

- [ ] **Step 4: Verify pass and commit**

```bash
cd ticketsystem && python -m pytest tests/test_ux_audit_2026_04_14.py -v
git add ticketsystem/templates/ticket_new.html ticketsystem/tests/test_ux_audit_2026_04_14.py
git commit -m "style(ticket_new): replace inline onclick with data-bs-dismiss"
```

## Task 1.3: Add `aria-label` to approvals icon-only link

**Files:**
- Modify: `ticketsystem/templates/approvals.html:43`

- [ ] **Step 1: Failing test**

```python
def test_approvals_icon_link_has_aria_label(client, app):
    login_as_admin(client, app)
    resp = client.get("/approvals")
    html = resp.get_data(as_text=True)
    import re
    # Every <a> containing arrow-up-right without text must carry aria-label
    for match in re.finditer(r'<a [^>]*bi-arrow-up-right[^>]*>', html):
        assert 'aria-label' in match.group(0), f"missing aria-label: {match.group(0)}"
```

- [ ] **Step 2: Run and confirm fail**

- [ ] **Step 3: Fix approvals.html line 43**

```html
<a href="{{ ingress_path }}{{ url_for('main.ticket_detail', ticket_id=ticket.id) }}"
   class="btn btn-sm btn-light rounded-circle flex-shrink-0"
   title="Ticket Details ansehen"
   aria-label="Ticket #{{ ticket.id }} öffnen">
    <i class="bi bi-arrow-up-right"></i>
</a>
```

- [ ] **Step 4: Verify pass and commit**

```bash
git add ticketsystem/templates/approvals.html ticketsystem/tests/test_ux_audit_2026_04_14.py
git commit -m "a11y(approvals): add aria-label to icon-only detail link"
```

## Task 1.4: Priority icon + label in my_queue kanban cards

**Files:**
- Modify: `ticketsystem/templates/my_queue.html:37-50` (kanban_card macro header)

- [ ] **Step 1: Failing test**

```python
def test_my_queue_shows_priority_as_text_not_just_color(client, app):
    from models import Ticket, db
    login_as_admin(client, app)
    with app.app_context():
        t = Ticket(title="Prio-Test", priority=1)
        db.session.add(t); db.session.commit()
        t_id = t.id
    resp = client.get("/my_queue")
    html = resp.get_data(as_text=True)
    # HIGH-priority tickets must show either "Hoch" text or a flame/priority icon
    assert ("Hoch" in html) or ("bi-exclamation-triangle-fill" in html), \
        "priority conveyed only by border color"
```

- [ ] **Step 2: Run and confirm fail**

- [ ] **Step 3: Add priority chip to kanban_card**

In `my_queue.html` inside `{% macro kanban_card(ticket, today) %}`, just after the `<div class="card-body p-3">` opening and before the header flex, insert:

```html
<div class="d-flex align-items-center gap-1 mb-1">
    {% if ticket.priority == 1 %}
    <span class="badge bg-danger-subtle text-danger rounded-pill x-small fw-bold">
        <i class="bi bi-exclamation-triangle-fill"></i> Hoch
    </span>
    {% elif ticket.priority == 2 %}
    <span class="badge bg-primary-subtle text-primary rounded-pill x-small">Mittel</span>
    {% else %}
    <span class="badge bg-success-subtle text-success rounded-pill x-small">Niedrig</span>
    {% endif %}
</div>
```

- [ ] **Step 4: Verify pass and commit**

```bash
cd ticketsystem && python -m pytest tests/test_ux_audit_2026_04_14.py -v
git add ticketsystem/templates/my_queue.html ticketsystem/tests/test_ux_audit_2026_04_14.py
git commit -m "a11y(my_queue): show priority as text+icon, not only border color"
```

## Task 1.5: Phase-1 verification

- [ ] **Step 1: Full test run**

```bash
cd ticketsystem && python -m pytest tests/ -q
# Expected: 106 + new tests, 0 failed
```

- [ ] **Step 2: Flake8**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
# Expected: clean
```

- [ ] **Step 3: Tag phase**

```bash
git tag -a phase-1-ux-20260414 -m "UX audit 2026-04-14 — Phase 1 (Quick Wins) complete"
```

---

# Phase 2 — Status "Wartet" Sub-States

**Score goal:** 9.4 → 9.7. **Duration:** 1 day. **DB:** **yes** (one additive migration).

**Design decision:** Add a nullable `wait_reason` VARCHAR(20) column on `ticket`, constrained by a new `WaitReason` enum with four values: `kunde`, `lieferant`, `kollege`, `sonstiges`. Service layer enforces the rule: setting status to WARTET requires a non-empty `wait_reason`; switching to any other status clears it.

**Why column, not satellite table:** One small, ticket-bound scalar with a closed enum — a satellite would be over-engineering. Contrast with `TicketContact` (many fields, logically grouped).

## Task 2.1: Add `WaitReason` enum

**Files:**
- Modify: `ticketsystem/enums.py`

- [ ] **Step 1: Add enum**

In `enums.py` after `TicketStatus`:

```python
class WaitReason(str, Enum):
    """Reason a ticket is in status WARTET. Required whenever status=WARTET."""

    KUNDE = "kunde"
    LIEFERANT = "lieferant"
    KOLLEGE = "kollege"
    SONSTIGES = "sonstiges"

    def __str__(self) -> str:
        return self.value
```

Add to `__all__`:

```python
__all__ = [
    "TicketStatus",
    "TicketPriority",
    "WorkerRole",
    "ApprovalStatus",
    "WaitReason",
    "ELEVATED_ROLES",
]
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/enums.py
git commit -m "feat(enums): add WaitReason enum for WARTET sub-states"
```

## Task 2.2: Add `wait_reason` column on Ticket model

**Files:**
- Modify: `ticketsystem/models.py` (Ticket class, after `status` column)

- [ ] **Step 1: Add column**

In `models.py` right after `status = db.Column(...)` (~ line 313):

```python
    wait_reason = db.Column(db.String(20), nullable=True)
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/models.py
git commit -m "feat(model): add Ticket.wait_reason column (nullable)"
```

## Task 2.3: Alembic migration

**Files:**
- Create: `ticketsystem/migrations/versions/a7b8c9d0e1f2_add_wait_reason.py`

- [ ] **Step 1: Find current head**

```bash
cd ticketsystem && python -m alembic heads
# Note the current head revision ID; use it as down_revision below.
```

- [ ] **Step 2: Create migration file**

Create `ticketsystem/migrations/versions/a7b8c9d0e1f2_add_wait_reason.py`:

```python
"""Add ticket.wait_reason column for WARTET sub-states.

Revision ID: a7b8c9d0e1f2
Revises: <PASTE CURRENT HEAD HERE>
Create Date: 2026-04-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "<PASTE CURRENT HEAD HERE>"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    result = bind.execute(sa.text(f"PRAGMA table_info({table_name})"))
    return column_name in [row[1] for row in result]


def upgrade():
    if not _column_exists("ticket", "wait_reason"):
        op.add_column(
            "ticket",
            sa.Column("wait_reason", sa.String(length=20), nullable=True),
        )


def downgrade():
    if _column_exists("ticket", "wait_reason"):
        with op.batch_alter_table("ticket") as batch:
            batch.drop_column("wait_reason")
```

- [ ] **Step 3: Replace `<PASTE CURRENT HEAD HERE>` with the revision from Step 1.**

- [ ] **Step 4: Apply migration against a fresh test DB**

```bash
cd ticketsystem && python -m alembic upgrade head
# Expected: runs without error; ticket table now has wait_reason column
```

- [ ] **Step 5: Commit**

```bash
git add ticketsystem/migrations/versions/a7b8c9d0e1f2_add_wait_reason.py
git commit -m "feat(db): migration adds ticket.wait_reason column"
```

## Task 2.4: Service enforces wait_reason on WARTET

**Files:**
- Modify: `ticketsystem/services/ticket_core_service.py` (`update_status`)
- Modify: `ticketsystem/exceptions.py` (if a new domain error is needed)
- Test: `ticketsystem/tests/test_wait_reason.py` (new)

- [ ] **Step 1: Write failing service test**

Create `ticketsystem/tests/test_wait_reason.py`:

```python
"""Tests for Ticket.wait_reason behavior on status changes."""
import pytest
from enums import TicketStatus, WaitReason
from services.ticket_core_service import TicketCoreService
from exceptions import DomainError
from models import Ticket, db


@pytest.fixture
def ticket(app):
    with app.app_context():
        t = Ticket(title="WR-Test", status=TicketStatus.OFFEN.value)
        db.session.add(t); db.session.commit()
        yield t


def test_wartet_without_reason_raises(app, ticket):
    with app.app_context(), pytest.raises(DomainError) as exc:
        TicketCoreService.update_status(
            ticket.id, TicketStatus.WARTET, author_name="t"
        )
    assert exc.value.field == "wait_reason"


def test_wartet_with_reason_persists(app, ticket):
    with app.app_context():
        TicketCoreService.update_status(
            ticket.id, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KUNDE.value,
        )
        db.session.refresh(ticket)
        assert ticket.wait_reason == "kunde"


def test_leaving_wartet_clears_reason(app, ticket):
    with app.app_context():
        TicketCoreService.update_status(
            ticket.id, TicketStatus.WARTET, author_name="t",
            wait_reason=WaitReason.KOLLEGE.value,
        )
        TicketCoreService.update_status(
            ticket.id, TicketStatus.IN_BEARBEITUNG, author_name="t",
        )
        db.session.refresh(ticket)
        assert ticket.wait_reason is None
```

- [ ] **Step 2: Run — FAIL (`wait_reason` kwarg unknown)**

```bash
cd ticketsystem && python -m pytest tests/test_wait_reason.py -v
```

- [ ] **Step 3: Extend `update_status`**

In `services/ticket_core_service.py`, replace the `update_status` signature + body:

```python
    @staticmethod
    @db_transaction
    def update_status(
        ticket_id: int,
        status: Any,
        author_name: str = "System",
        author_id: Optional[int] = None,
        wait_reason: Optional[str] = None,
        commit: bool = True,
    ) -> Optional[Ticket]:
        """Update ticket status. When switching to WARTET, wait_reason is required
        and must be a valid WaitReason value. Leaving WARTET clears wait_reason."""
        from enums import TicketStatus, WaitReason  # local to avoid cycles
        ticket = _get_ticket_or_none(ticket_id)
        if not ticket:
            return None

        old_status = ticket.status
        new_status = status.value if hasattr(status, "value") else status

        if new_status == TicketStatus.WARTET.value:
            valid = {r.value for r in WaitReason}
            if wait_reason not in valid:
                raise DomainError(
                    "Bitte Grund für 'Wartet' angeben.",
                    field="wait_reason",
                    status_code=400,
                )

        if old_status != new_status:
            ticket.status = new_status
            if new_status == TicketStatus.WARTET.value:
                ticket.wait_reason = wait_reason
            else:
                ticket.wait_reason = None
            ticket.updated_at = get_utc_now()
            reason_suffix = (
                f" ({wait_reason})"
                if new_status == TicketStatus.WARTET.value else ""
            )
            comment = Comment(
                ticket_id=ticket_id,
                author=author_name,
                author_id=author_id,
                text=f"Status geändert: {old_status} -> {new_status}{reason_suffix}",
                is_system_event=True,
                event_type="STATUS_CHANGE",
            )
            db.session.add(comment)
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        elif new_status == TicketStatus.WARTET.value and ticket.wait_reason != wait_reason:
            # Same status but reason change — update silently.
            ticket.wait_reason = wait_reason
            ticket.updated_at = get_utc_now()
            if commit:
                db.session.commit()

        return ticket
```

- [ ] **Step 4: Ensure `DomainError` supports `field` and `status_code`**

```bash
cd ticketsystem && grep -n "class DomainError" exceptions.py
# Expected: existing class. Check that it accepts field=... and status_code=...
```

If it doesn't yet accept `field`, the audit's Phase 2 spec of 2026-04-13 already added it — verify and skip.

- [ ] **Step 5: Run service tests — PASS**

```bash
cd ticketsystem && python -m pytest tests/test_wait_reason.py -v
```

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/services/ticket_core_service.py ticketsystem/tests/test_wait_reason.py
git commit -m "feat(service): enforce wait_reason on TicketStatus.WARTET"
```

## Task 2.5: API endpoint passes `wait_reason` through

**Files:**
- Modify: `ticketsystem/routes/ticket_api.py` (`_update_status_api`, ~ line 86-118)

- [ ] **Step 1: API test**

Append to `tests/test_wait_reason.py`:

```python
def test_api_wartet_requires_reason(client, app, ticket):
    from tests.conftest import login_as_admin
    login_as_admin(client, app)
    resp = client.post(
        f"/api/ticket/{ticket.id}/status",
        json={"status": "wartet"},
        headers={"X-CSRFToken": "test"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert any(e.get("field") == "wait_reason" for e in body.get("errors", []))


def test_api_wartet_with_reason_ok(client, app, ticket):
    from tests.conftest import login_as_admin
    login_as_admin(client, app)
    resp = client.post(
        f"/api/ticket/{ticket.id}/status",
        json={"status": "wartet", "wait_reason": "kunde"},
        headers={"X-CSRFToken": "test"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Update endpoint**

In `routes/ticket_api.py` around line 99-118:

```python
    data: dict[str, Any] = request.get_json(silent=True) or {}
    new_status = data.get("status")
    wait_reason = data.get("wait_reason")
    if not new_status:
        return api_error("Kein Status angegeben", 400)

    valid_statuses = {s.value for s in TicketStatus}
    if new_status not in valid_statuses:
        return api_error(f"Ungültiger Status: {new_status}", 400)

    if new_status == TicketStatus.ERLEDIGT.value and ticket.checklists:
        open_items = [c for c in ticket.checklists if not c.is_completed]
        if open_items:
            return api_error(
                f"Ticket kann nicht geschlossen werden: "
                f"{len(open_items)} offene Checklisten-Aufgabe(n).",
                400,
            )

    author = session.get("worker_name", "System")
    TicketCoreService.update_status(
        ticket_id, new_status, author, worker_id,
        wait_reason=wait_reason,
    )
    return api_ok()
```

- [ ] **Step 3: Run tests — PASS**

```bash
cd ticketsystem && python -m pytest tests/test_wait_reason.py -v
```

- [ ] **Step 4: Commit**

```bash
git add ticketsystem/routes/ticket_api.py ticketsystem/tests/test_wait_reason.py
git commit -m "feat(api): status endpoint accepts and validates wait_reason"
```

## Task 2.6: Sidebar — inline popover to choose reason

**Files:**
- Modify: `ticketsystem/templates/components/_management_sidebar.html:4-32`
- Modify: `ticketsystem/static/js/ticket_detail.js` (status button handler)

- [ ] **Step 1: Render test**

Append to `tests/test_ux_audit_2026_04_14.py`:

```python
def test_sidebar_has_wait_reason_picker(client, app):
    from models import Ticket, db
    from tests.conftest import login_as_admin
    login_as_admin(client, app)
    with app.app_context():
        t = Ticket(title="WR-UI"); db.session.add(t); db.session.commit()
        t_id = t.id
    resp = client.get(f"/ticket/{t_id}")
    html = resp.get_data(as_text=True)
    assert 'data-wait-reason="kunde"' in html
    assert 'data-wait-reason="lieferant"' in html
    assert 'data-wait-reason="kollege"' in html
    assert 'data-wait-reason="sonstiges"' in html
```

- [ ] **Step 2: Render fails**

- [ ] **Step 3: Extend sidebar**

In `_management_sidebar.html` just after the WARTET `<button>` (line 17), add a hidden popover block:

```html
            </div>
            <div id="waitReasonPopover" class="wait-reason-popover d-none border rounded-3 shadow-sm p-2 bg-surface mt-2" role="dialog" aria-label="Grund für Status 'Wartet'">
                <small class="d-block fw-semibold mb-1 text-muted">Worauf wird gewartet?</small>
                <div class="btn-group btn-group-sm w-100" role="group">
                    <button type="button" class="btn btn-outline-secondary" data-wait-reason="kunde">Kunde</button>
                    <button type="button" class="btn btn-outline-secondary" data-wait-reason="lieferant">Lieferant</button>
                    <button type="button" class="btn btn-outline-secondary" data-wait-reason="kollege">Kollege</button>
                    <button type="button" class="btn btn-outline-secondary" data-wait-reason="sonstiges">Sonstiges</button>
                </div>
            </div>
```

Also add a visible badge under the button row when `ticket.wait_reason` is set, right after the `Als erledigt markieren` block:

```html
            {% if ticket.status == TicketStatus.WARTET.value and ticket.wait_reason %}
            <div class="mt-2 small text-muted">
                <span class="badge bg-warning-subtle text-warning-emphasis rounded-pill">
                    Wartet auf: {{ ticket.wait_reason|capitalize }}
                </span>
            </div>
            {% endif %}
```

- [ ] **Step 4: Hook up JS in `ticket_detail.js`**

Find the existing status-button handler. Replace the WARTET branch so that clicking "Wartet" shows the popover and actual status POST only fires after a reason is chosen. Pattern:

```javascript
const popover = document.getElementById('waitReasonPopover');
const statusBtns = document.querySelectorAll('#statusSegmented [data-status]');
statusBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
        const newStatus = btn.dataset.status;
        if (newStatus === 'wartet') {
            popover.classList.remove('d-none');
            return; // wait for reason click
        }
        popover?.classList.add('d-none');
        postStatusChange(newStatus, null);
    });
});
popover?.querySelectorAll('[data-wait-reason]').forEach(function(rb) {
    rb.addEventListener('click', function() {
        popover.classList.add('d-none');
        postStatusChange('wartet', rb.dataset.waitReason);
    });
});

async function postStatusChange(status, waitReason) {
    const payload = { status };
    if (waitReason) payload.wait_reason = waitReason;
    const resp = await fetch(ingress + '/api/ticket/' + ticketId + '/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(payload),
    });
    if (resp.ok) {
        window.location.reload();
    } else {
        const data = await resp.json().catch(() => ({}));
        window.showUiAlert(data.error || 'Statuswechsel fehlgeschlagen.', 'danger');
    }
}
```

(If the existing handler uses a different variable layout, adapt — the skeleton above is the reference contract.)

- [ ] **Step 5: Tests pass**

```bash
cd ticketsystem && python -m pytest tests/test_ux_audit_2026_04_14.py::test_sidebar_has_wait_reason_picker -v
```

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/templates/components/_management_sidebar.html ticketsystem/static/js/ticket_detail.js ticketsystem/tests/test_ux_audit_2026_04_14.py
git commit -m "feat(ui): wait-reason popover on WARTET status change"
```

## Task 2.7: Show "Wartet: X" badge in dashboard row + card

**Files:**
- Modify: `ticketsystem/templates/components/_ticket_item.html` (row and card macros)

- [ ] **Step 1: Extend row and card status column**

In the row macro, wherever `ticket.status` is rendered as a badge (Status column), add after the status badge:

```html
{% if ticket.status == TicketStatus.WARTET.value and ticket.wait_reason %}
<span class="badge bg-warning-subtle text-warning-emphasis rounded-pill x-small ms-1"
      title="Wartet auf {{ ticket.wait_reason }}">
    {{ ticket.wait_reason|capitalize }}
</span>
{% endif %}
```

Repeat the exact same block in the card macro next to the card-status badge.

- [ ] **Step 2: Manual smoke**

Create a WARTET ticket with reason "kunde", load dashboard, confirm the chip is visible on both desktop row and mobile card views.

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/templates/components/_ticket_item.html
git commit -m "feat(ui): surface wait_reason badge in dashboard rows and mobile cards"
```

## Task 2.8: Phase-2 verification

- [ ] **Step 1: Full test run**

```bash
cd ticketsystem && python -m pytest tests/ -q
# Expected: 106 + all new tests, 0 failed
```

- [ ] **Step 2: Flake8**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```

- [ ] **Step 3: Grep for stale access patterns** (per CLAUDE.md rule 15)

```bash
grep -rn "status.*wartet" ticketsystem/routes ticketsystem/templates ticketsystem/services
# For every match, verify it either checks status or uses wait_reason correctly.
```

- [ ] **Step 4: Tag phase**

```bash
git tag -a phase-2-ux-20260414 -m "Phase 2 — WaitReason sub-states complete"
```

---

# Phase 3 — Core UX Enhancements

**Score goal:** 9.7 → 9.9. **Duration:** 1–1.5 days. **DB:** none.

## Task 3.1: Login worker-chip filter

**Files:**
- Modify: `ticketsystem/templates/login.html`

- [ ] **Step 1: Add search input above chip list** (between line 36 and 37)

```html
<input type="search" id="workerChipFilter"
       class="form-control form-control-sm mt-2"
       placeholder="Mitarbeiter suchen..."
       aria-label="Mitarbeiter-Schnellwahl filtern"
       autocomplete="off">
```

- [ ] **Step 2: Add JS in `{% block scripts %}`** (extend existing DOMContentLoaded):

```javascript
const chipFilter = document.getElementById('workerChipFilter');
if (chipFilter) {
    chipFilter.addEventListener('input', function() {
        const q = this.value.trim().toLowerCase();
        document.querySelectorAll('.worker-chip').forEach(function(chip) {
            chip.style.display = (!q || chip.dataset.name.toLowerCase().includes(q)) ? '' : 'none';
        });
    });
}
```

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/templates/login.html
git commit -m "feat(login): client-side filter for worker-chip quick-select"
```

## Task 3.2: Login rate-limit feedback

**Files:**
- Modify: `ticketsystem/routes/auth.py` (login POST handler)

- [ ] **Step 1: Find the failed-login branch**

```bash
grep -n "failed_login_count\|flash.*PIN" ticketsystem/routes/auth.py | head
```

- [ ] **Step 2: In the failed-login branch**, compute remaining attempts and flash:

```python
MAX_ATTEMPTS = 5  # match the existing limit
remaining = max(0, MAX_ATTEMPTS - worker.failed_login_count)
if remaining > 0:
    flash(f"PIN ungültig. Noch {remaining} Versuche übrig.", "error")
else:
    flash("Account gesperrt. Admin kontaktieren.", "error")
```

If `MAX_ATTEMPTS` already lives elsewhere as a constant, import and reuse — do not hardcode.

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/routes/auth.py
git commit -m "feat(auth): surface remaining PIN attempts in login flash"
```

## Task 3.3: PIN strength indicator

**Files:**
- Modify: `ticketsystem/templates/change_pin.html`

- [ ] **Step 1: Add meter after the PIN input**

```html
<div class="mt-2">
    <div class="progress progress-thin" role="progressbar" aria-label="PIN-Stärke">
        <div id="pinStrengthBar" class="progress-bar bg-danger" style="width: 0%;"></div>
    </div>
    <small id="pinStrengthText" class="text-muted">PIN eingeben…</small>
</div>
<script nonce="{{ g.csp_nonce }}">
(function() {
    const input = document.getElementById('pin');
    const bar = document.getElementById('pinStrengthBar');
    const txt = document.getElementById('pinStrengthText');
    if (!input) return;
    function score(pin) {
        if (!pin || pin.length < 4) return { pct: 10, label: 'Zu kurz', cls: 'bg-danger' };
        const weak = ['1234','0000','1111','2222','1212','4321','9999'];
        if (weak.includes(pin)) return { pct: 20, label: 'Sehr schwach', cls: 'bg-danger' };
        if (/^(\d)\1+$/.test(pin)) return { pct: 20, label: 'Wiederholung', cls: 'bg-danger' };
        if (/^(0123|1234|2345|3456|4567|5678|6789)$/.test(pin)) return { pct: 30, label: 'Sequenz', cls: 'bg-warning' };
        if (pin.length >= 6) return { pct: 90, label: 'Stark', cls: 'bg-success' };
        return { pct: 60, label: 'Akzeptabel', cls: 'bg-primary' };
    }
    input.addEventListener('input', function() {
        const s = score(input.value);
        bar.style.width = s.pct + '%';
        bar.className = 'progress-bar ' + s.cls;
        txt.textContent = s.label;
    });
})();
</script>
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/change_pin.html
git commit -m "feat(pin): client-side PIN strength indicator"
```

## Task 3.4: Public ticket view — mini-header

**Files:**
- Modify: `ticketsystem/templates/ticket_public.html`

- [ ] **Step 1: Add mini-header at the top of `{% block content %}`**

```html
<nav aria-label="Top navigation" class="mb-3 d-flex justify-content-between align-items-center">
    <span class="small text-muted">
        <i class="bi bi-ticket-perforated me-1"></i>Ticket-Status #{{ ticket.id }}
    </span>
    <a href="{{ ingress_path }}{{ url_for('main.ticket_new') }}"
       class="btn btn-sm btn-outline-primary rounded-pill">
        <i class="bi bi-plus-lg me-1"></i>Neues Ticket melden
    </a>
</nav>
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/ticket_public.html
git commit -m "feat(public): minimal header with return-path on public ticket view"
```

## Task 3.5: Mobile bulk-action bar — overflow on narrow screens

**Files:**
- Modify: `ticketsystem/static/css/style.css`

- [ ] **Step 1: Add a breakpoint rule**

Append near the existing `.bulk-action-bar` rules:

```css
@media (max-width: 480px) {
    .bulk-action-bar {
        flex-direction: column !important;
        align-items: stretch !important;
        padding: .75rem !important;
        gap: .5rem !important;
    }
    .bulk-action-bar .vr { display: none; }
    .bulk-action-bar select,
    .bulk-action-bar input[type="date"] {
        width: 100% !important;
    }
}
```

- [ ] **Step 2: Manual check**

Resize browser to 380 px; open dashboard; select ≥ 1 ticket; verify bar stacks vertically, each control full-width, no horizontal overflow.

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "ui(mobile): stack bulk-action bar vertically below 480px"
```

## Task 3.6: Bulk-undo for status / assign / priority

**Files:**
- Modify: `ticketsystem/routes/ticket_api.py` (bulk endpoint — `/api/tickets/bulk`)
- Modify: `ticketsystem/templates/index.html` (bulkPost handler)

- [ ] **Step 1: Locate bulk endpoint**

```bash
grep -n "def _bulk\|tickets/bulk\|bulk_tickets" ticketsystem/routes/ticket_api.py | head
```

- [ ] **Step 2: Modify endpoint to return before-state for each action**

Before applying the bulk action, collect `prev_state = {id: {status, assigned_to_id, assigned_team_id, priority}}` for the affected IDs. Return it in the success payload as `prev_state`. Example addition in the handler for `status_change`:

```python
prev_state = {
    str(t.id): {
        "status": t.status,
        "assigned_to_id": t.assigned_to_id,
        "assigned_team_id": t.assigned_team_id,
        "priority": t.priority,
        "wait_reason": t.wait_reason,
    }
    for t in tickets
}
# ... apply action ...
return api_ok(updated=len(tickets), prev_state=prev_state, action=action)
```

Also add a restore endpoint:

```python
@worker_required
@write_required
@limiter.limit("20 per minute")
@api_endpoint
def _bulk_restore_state_api():
    """Restore a bulk before-state produced by a previous /api/tickets/bulk call."""
    payload = request.get_json(silent=True) or {}
    prev_state = payload.get("prev_state") or {}
    if not isinstance(prev_state, dict):
        return api_error("prev_state must be a dict", 400)
    restored = 0
    for ticket_id_str, state in prev_state.items():
        try:
            tid = int(ticket_id_str)
        except ValueError:
            continue
        t = _get_ticket_or_none(tid)
        if not t:
            continue
        t.status = state.get("status", t.status)
        t.assigned_to_id = state.get("assigned_to_id")
        t.assigned_team_id = state.get("assigned_team_id")
        t.priority = state.get("priority", t.priority)
        t.wait_reason = state.get("wait_reason")
        restored += 1
    db.session.commit()
    return api_ok(restored=restored)
```

Register the route next to the existing bulk route:

```python
bp.add_url_rule(
    "/api/tickets/bulk/restore", "bulk_restore_state",
    view_func=_bulk_restore_state_api, methods=["POST"],
)
```

- [ ] **Step 3: Modify `bulkPost` in `templates/index.html` (around line 284)**

Extend the success branch to show an undo toast with a POST-body callback. Easiest: introduce a second argument to `showUiAlert` or a helper. Example inside the success branch:

```javascript
if (data.prev_state && Object.keys(data.prev_state).length > 0) {
    const prevState = data.prev_state;
    window.showUiAlert(
        data.updated + ' Ticket(s) aktualisiert.',
        'success',
        {
            undoLabel: 'Rückgängig',
            undoAction: async function() {
                await fetch(ingress + '/api/tickets/bulk/restore', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ prev_state: prevState }),
                });
                await refreshTableRows();
            }
        }
    );
}
```

- [ ] **Step 4: Extend `showUiAlert` to support `undoAction`**

In `base_ui.js`, locate the existing `showUiAlert` (or the toast-render code) and add support for `options.undoAction`. When present, render a `<button class="undo-action-btn">` whose click handler calls `undoAction()` and dismisses the toast. If the existing soft-delete undo already uses `undoUrl`, keep both paths (URL-based + function-based).

- [ ] **Step 5: Smoke test manually**

1. Select 3 tickets, bulk-set status to "Wartet" — toast appears with "Rückgängig".
2. Click "Rückgängig" within 8 s — tickets revert.
3. Check: if Wartet was applied without wait_reason (unlikely via bulk), API should still work because bulk has not yet gained wait_reason enforcement (keep scope here narrow; add bulk-wait_reason as follow-up if needed).

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/routes/ticket_api.py ticketsystem/templates/index.html ticketsystem/static/js/base_ui.js
git commit -m "feat(bulk): undo for status/assign/priority bulk actions"
```

## Task 3.7: Phase-3 verification

- [ ] **Step 1: Full test run + flake8**

```bash
cd ticketsystem && python -m pytest tests/ -q
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```

- [ ] **Step 2: Tag phase**

```bash
git tag -a phase-3-ux-20260414 -m "Phase 3 — core UX enhancements complete"
```

---

# Phase 4 — Polish (Severity 1)

**Score goal:** 9.9 → 10.0. **Duration:** 0.5 day. **DB:** none.

## Task 4.1: Searchable help offcanvas

**Files:**
- Modify: `ticketsystem/templates/components/_page_help_offcanvas.html`
- Modify: `ticketsystem/static/js/help.js`

- [ ] **Step 1: Add search input at top of offcanvas body**

```html
<input type="search" id="helpOffcanvasSearch"
       class="form-control form-control-sm mb-3"
       placeholder="Hilfe durchsuchen..."
       aria-label="Hilfe-Inhalte filtern">
```

- [ ] **Step 2: Extend `help.js`**

```javascript
document.addEventListener('DOMContentLoaded', function() {
    const search = document.getElementById('helpOffcanvasSearch');
    if (!search) return;
    search.addEventListener('input', function() {
        const q = this.value.trim().toLowerCase();
        document.querySelectorAll('#offcanvasPageHelp .help-section').forEach(function(sec) {
            const hit = !q || sec.textContent.toLowerCase().includes(q);
            sec.style.display = hit ? '' : 'none';
        });
    });
});
```

Ensure each help section in the offcanvas carries `class="help-section"`.

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/templates/components/_page_help_offcanvas.html ticketsystem/static/js/help.js
git commit -m "feat(help): client-side search for page-help offcanvas"
```

## Task 4.2: "Zurück zu Projekte" breadcrumb when dashboard is filtered by project

**Files:**
- Modify: `ticketsystem/templates/index.html` (breadcrumb block)

- [ ] **Step 1: Add a `{% block breadcrumbs %}` at the top of the content block**

```html
{% block breadcrumbs %}
{% if query and query in project_names %}
<nav aria-label="breadcrumb" class="mb-2">
    <ol class="breadcrumb mb-0 small">
        <li class="breadcrumb-item">
            <a href="{{ ingress_path }}{{ url_for('main.projects') }}" class="text-decoration-none">Projekte</a>
        </li>
        <li class="breadcrumb-item active" aria-current="page">{{ query }}</li>
    </ol>
</nav>
{% endif %}
{% endblock %}
```

- [ ] **Step 2: Pass `project_names` from dashboard route**

In `routes/dashboard.py`, where the index view collects context, add:

```python
project_names = {
    p.order_reference for p in Ticket.query
        .filter(Ticket.order_reference.isnot(None))
        .with_entities(Ticket.order_reference).distinct()
}
```

and pass `project_names=project_names` to `render_template`.

- [ ] **Step 3: Commit**

```bash
git add ticketsystem/templates/index.html ticketsystem/routes/dashboard.py
git commit -m "ux(dashboard): breadcrumb back to Projekte when filtered by order_reference"
```

## Task 4.3: Remove redundant settings subtitle

**Files:**
- Modify: `ticketsystem/templates/settings.html:18`

- [ ] **Step 1: Delete the subtitle line**

```html
<p class="text-secondary small mb-0">Konfiguration des E-Mail-Versands und weiterer Systemparameter.</p>
```

- [ ] **Step 2: Commit**

```bash
git add ticketsystem/templates/settings.html
git commit -m "ux(settings): drop redundant subtitle that duplicates card headers"
```

## Task 4.4: Phase-4 verification

- [ ] **Step 1: Full test run + flake8**

```bash
cd ticketsystem && python -m pytest tests/ -q
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```

- [ ] **Step 2: Tag final**

```bash
git tag -a phase-4-ux-20260414 -m "Phase 4 — polish complete; score target 10/10"
```

- [ ] **Step 3: Re-audit**

Write a short re-score note in `docs/ux-audit-2026-04-14-rescore.md`, confirming 10/10 (or flagging remaining items).

---

## Cross-Cutting Rules

- **Baseline rule (CLAUDE.md):** Before each phase, record the pytest baseline. At phase end, it must be ≥ baseline with **zero** new failures. Never hide a failure behind `# noqa` or `skip`.
- **German UI strings:** All user-facing text is German. Error messages too.
- **No Dockerfile change:** Every new file goes under `routes/`, `services/`, `static/`, `templates/`, `migrations/` or `tests/` — each copied as a whole directory.
- **Rule 15 (schema extraction):** After Phase 2, grep for any remaining raw `== 'wartet'` checks and verify none leak the assumption that `wait_reason` is empty.
- **Commits:** One focused commit per task step; use `feat:` / `fix:` / `a11y:` / `ui:` / `ux:` prefixes.

---

## Out of Scope (deferred, could become follow-up specs)

- Keyboard navigation `j`/`k`/`g+d` extensions and Command-Palette (Cmd+K).
- Bulk action `wait_reason` picker (bulk → WARTET would need a sub-popover; today the bulk API rejects without reason — acceptable because that flow already asks for explicit status).
- Shortcut-Help categorization / keyboard semantics `<kbd>` normalization.
- Service-Worker offline-fallback UX.
