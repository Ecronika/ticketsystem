# Workflow-UX-Verbesserungen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die 10 kritischsten Workflow-Reibungspunkte aus dem UX-Audit beheben — Fokus auf Flow-Übergänge, Benachrichtigungen und Mobile-Tauglichkeit.

**Architecture:** Inkrementelle Verbesserungen am bestehenden Flask/Jinja-Stack. Keine neuen Abhängigkeiten. Notification-Erweiterung nutzt das vorhandene `Notification`-Model + `create_notification()`. Alle Änderungen sind rückwärtskompatibel.

**Tech Stack:** Flask 2.x, Jinja2, Bootstrap 5.3.3, SQLAlchemy, SQLite, Vanilla JS

---

## Scope

Dieser Plan deckt 7 unabhängige Verbesserungsbereiche ab:

| # | Bereich | Tasks | Geschätzter Aufwand |
|---|---------|-------|---------------------|
| A | Ticket-Erstellung Redirect | 1-2 | 30 min |
| B | Callback-Management | 3-5 | 1.5h |
| C | Notification-Erweiterung | 6-8 | 2h |
| D | Approval-Dashboard-Visibility | 9-10 | 1h |
| E | Serienticket-Management | 11-13 | 2h |
| F | Onboarding-Verbesserung | 14-15 | 45 min |
| G | Mobile-Dashboard | 16-17 | 45 min |

Jeder Bereich (A-G) ist unabhängig implementierbar und testbar.

---

## Baseline

```bash
cd ticketsystem
python -m pytest tests/ -v   # Erwarte: 138 passed
python -m flake8 --max-line-length=120 *.py routes/ services/
```

---

## A. Ticket-Erstellung: Redirect zu Bestätigungsseite

### Task 1: Redirect nach Ticket-Erstellung zu ticket_public

**Files:**
- Modify: `ticketsystem/routes/ticket_views.py:286-300` (Funktion `_after_ticket_created`)
- Modify: `ticketsystem/templates/ticket_public.html:82-93` (Footer-Info-Block)

- [ ] **Step 1: Finde die aktuelle Redirect-Logik**

In `routes/ticket_views.py` Funktion `_after_ticket_created` (~Zeile 286-300):
Der aktuelle Code macht `redirect(url_for('main.ticket_new', created=ticket.id))`,
was das Formular erneut lädt mit einem Success-Banner.

- [ ] **Step 2: Ändere Redirect für anonyme Nutzer**

```python
# In routes/ticket_views.py, Funktion _after_ticket_created:
# Ersetze den Redirect-Block für nicht-eingeloggte Nutzer:

def _after_ticket_created(ticket: Ticket) -> Response:
    """Redirect after successful ticket creation."""
    if session.get("worker_id"):
        # Eingeloggte Mitarbeiter: zurück zum Formular mit Success-Banner
        flash_with_undo(
            f"Ticket #{ticket.id} erstellt.",
            url_for("main.ticket_detail", ticket_id=ticket.id),
            "Öffnen",
        )
        return redirect(url_for("main.ticket_new"))
    # Anonyme Melder: direkt zur öffentlichen Status-Seite
    return redirect(
        url_for("main.ticket_public", ticket_id=ticket.id, new=1)
    )
```

- [ ] **Step 3: Zeige Bestätigungs-Banner auf ticket_public wenn ?new=1**

In `templates/ticket_public.html`, nach Zeile 13 (nach `</nav>`):

```html
{% set is_new = request.args.get('new') %}
{% if is_new %}
<div class="alert alert-success border-0 shadow-sm rounded-3 py-3 mb-4" role="alert">
    <div class="d-flex align-items-center">
        <i class="bi bi-check-circle-fill fs-4 me-3 text-success"></i>
        <div>
            <h5 class="h6 fw-bold mb-1">Ticket erfolgreich erstellt!</h5>
            <p class="small mb-0">Ihr Anliegen wurde unter der Nummer <strong>#{{ ticket.id }}</strong> erfasst.
               Sie können den Status jederzeit auf dieser Seite verfolgen.</p>
        </div>
    </div>
</div>
{% endif %}
```

- [ ] **Step 4: Test — anonymes Ticket erstellen**

```bash
cd ticketsystem && python -m pytest tests/ -v
```

Manuell: `ticket_new` als anonymer User → Submit → Redirect zu `/ticket/<id>/public?new=1` → grünes Banner sichtbar.

- [ ] **Step 5: Commit**

```bash
git add routes/ticket_views.py templates/ticket_public.html
git commit -m "feat(ux): redirect anonymous ticket creators to public status page"
```

---

## B. Callback-Management

### Task 2: "Rückruf erledigt"-Checkbox in Sidebar

**Files:**
- Modify: `ticketsystem/templates/components/_management_sidebar.html:175-190` (Callback-Display)
- Modify: `ticketsystem/routes/ticket_api.py` (neuer API-Endpoint)
- Modify: `ticketsystem/static/js/ticket_detail.js` (JS-Handler)
- Test: `ticketsystem/tests/test_callback_done.py` (neuer Test)

- [ ] **Step 1: Schreibe Test für Callback-Done-Endpoint**

```python
# tests/test_callback_done.py
import pytest
from tests.conftest import login_worker

def test_callback_done_clears_flag(client, sample_ticket_with_callback):
    """POST /api/ticket/<id>/callback-done setzt callback_requested=False."""
    login_worker(client, "Admin")
    ticket = sample_ticket_with_callback
    resp = client.post(
        f"/api/ticket/{ticket.id}/callback-done",
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    # Prüfe DB-Zustand
    from models import TicketContact
    contact = TicketContact.query.filter_by(ticket_id=ticket.id).first()
    assert contact.callback_requested is False
```

- [ ] **Step 2: Verifiziere Test schlägt fehl**

```bash
python -m pytest tests/test_callback_done.py -v
```

Erwartet: FAIL (Endpoint existiert noch nicht)

- [ ] **Step 3: Implementiere API-Endpoint**

In `routes/ticket_api.py`, nach dem `_update_contact_api` Endpoint:

```python
@main_bp.route("/api/ticket/<int:ticket_id>/callback-done", methods=["POST"])
@worker_required
@write_required
@api_endpoint
def _callback_done_api(ticket_id: int):
    """Mark callback as completed for this ticket."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        raise DomainError("Ticket nicht gefunden.", 404)
    contact = ticket.contact
    if not contact or not contact.callback_requested:
        raise DomainError("Kein offener Rückruf für dieses Ticket.", 409)
    contact.callback_requested = False
    contact.callback_due = None
    author = session.get("worker_name", "System")
    TicketCoreService.add_comment(
        ticket_id, f"Rückruf durchgeführt.", author, is_system_event=True
    )
    db.session.commit()
    return api_ok()
```

- [ ] **Step 4: Registriere Route und teste**

```bash
python -m pytest tests/test_callback_done.py -v
```

Erwartet: PASS

- [ ] **Step 5: Füge Button zur Sidebar hinzu**

In `_management_sidebar.html`, nach der Callback-Due-Anzeige (ca. Zeile 185):

```html
{% if c and c.callback_requested and session.get('role') != 'viewer' %}
<button type="button"
        class="btn btn-sm btn-outline-success w-100 mt-2 rounded-pill"
        id="callbackDoneBtn"
        data-ticket-id="{{ ticket.id }}">
    <i class="bi bi-telephone-check me-1" aria-hidden="true"></i>Rückruf erledigt
</button>
{% endif %}
```

- [ ] **Step 6: JS-Handler in ticket_detail.js**

Am Ende von `ticket_detail.js` (vor dem schließenden `});`):

```javascript
// Callback-Done Button
const callbackDoneBtn = document.getElementById('callbackDoneBtn');
if (callbackDoneBtn) {
    callbackDoneBtn.addEventListener('click', async function() {
        const btn = this;
        const ticketId = btn.dataset.ticketId;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>...';
        try {
            const resp = await fetch(ingress + '/api/ticket/' + ticketId + '/callback-done', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
            });
            const errMsg = await window.extractApiError(resp);
            if (errMsg) {
                if (window.showUiAlert) window.showUiAlert(errMsg, 'danger');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-telephone-check me-1"></i>Rückruf erledigt';
                return;
            }
            if (window.showUiAlert) window.showUiAlert('Rückruf als erledigt markiert.', 'success');
            // Callback-Sektion aus der Sidebar entfernen
            const callbackDisplay = document.querySelector('.callback-overdue, [data-callback-display]');
            if (callbackDisplay) callbackDisplay.remove();
            btn.remove();
        } catch(e) {
            if (window.showUiAlert) window.showUiAlert('Netzwerkfehler.', 'danger');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-telephone-check me-1"></i>Rückruf erledigt';
        }
    });
}
```

- [ ] **Step 7: Baseline-Test**

```bash
python -m pytest tests/ -v  # Alle 138+ Tests müssen passen
```

- [ ] **Step 8: Commit**

```bash
git add routes/ticket_api.py templates/components/_management_sidebar.html static/js/ticket_detail.js tests/test_callback_done.py
git commit -m "feat(callback): add 'Rückruf erledigt' button with API endpoint"
```

### Task 3: Callback-Tab Alarm-Badge im Dashboard

**Files:**
- Modify: `ticketsystem/templates/index.html:580-583` (Tab "Rückruf")

- [ ] **Step 1: Ändere Badge-Styling wenn callback_pending > 0**

In `templates/index.html`, finde den Rückruf-Tab (~Zeile 580-583). Ersetze:

```html
<a href="{{ ingress_path }}{{ url_for('main.index', tab='callback', q=query) }}" class="dash-tab text-decoration-none {{ 'active' if active_tab == 'callback' }}">
    <i class="bi bi-telephone-forward me-1 text-warning" aria-hidden="true"></i>Rückruf
    <span class="tab-count {{ 'bg-danger text-white animate-pulse' if summary_counts.callback_pending > 0 else 'bg-surface-subtle text-muted' }}">{{ summary_counts.callback_pending }}</span>
    {% if summary_counts.callback_pending > 0 %}<span class="visually-hidden"> – Aufmerksamkeit erforderlich</span>{% endif %}
</a>
```

Hinweis: Die `animate-pulse` Klasse + `bg-danger` statt `bg-warning` macht den Tab bei offenen Callbacks deutlich sichtbarer.

- [ ] **Step 2: Test**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "fix(ux): callback tab uses danger-badge with pulse when pending > 0"
```

### Task 4: Überfällige Callbacks: Alarm-Badge in Sidebar

**Files:**
- Modify: `ticketsystem/templates/components/_management_sidebar.html:178-186`
- Modify: `ticketsystem/static/css/style.css` (neue Klasse)

- [ ] **Step 1: CSS für Callback-Overdue-Badge**

In `style.css`, nach den Sidebar-Collapse-Styles:

```css
/* Überfälliger Rückruf: pulsierendes Badge in Sidebar */
.callback-overdue-badge {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-1) var(--space-2);
    background-color: var(--color-danger);
    color: #fff;
    border-radius: var(--radius-pill);
    font-size: var(--fs-xs);
    font-weight: 700;
    animation: pulse-scale 1.8s ease infinite;
}
```

- [ ] **Step 2: Template-Update**

In `_management_sidebar.html`, ersetze die Callback-Anzeige (~Zeile 178-186):

```html
{% if c and c.callback_requested %}
<div class="mt-2 d-flex align-items-center gap-1" data-callback-display>
    {% if c.callback_due and c.callback_due < now %}
    <span class="callback-overdue-badge">
        <i class="bi bi-telephone-forward"></i>
        Rückruf ÜBERFÄLLIG
        <span class="ms-1">{{ c.callback_due|local_time|datetime('%d.%m. %H:%M') }}</span>
    </span>
    {% else %}
    <i class="bi bi-telephone-forward small text-warning-emphasis"></i>
    <span class="x-small fw-bold text-warning-emphasis">Rückruf erforderlich</span>
    {% if c.callback_due %}
    <span class="x-small ms-1 text-warning-emphasis">bis {{ c.callback_due|local_time|datetime('%d.%m. %H:%M') }}</span>
    {% endif %}
    {% endif %}
</div>
{% endif %}
```

- [ ] **Step 3: Test + Commit**

```bash
python -m pytest tests/ -v
git add static/css/style.css templates/components/_management_sidebar.html
git commit -m "fix(ux): overdue callback shows pulsing danger badge in sidebar"
```

---

## C. Notification-Erweiterung

### Task 5: Notification bei Approval-Statuswechsel

**Files:**
- Modify: `ticketsystem/services/ticket_approval_service.py:138-180`
- Test: `ticketsystem/tests/test_approval_notifications.py`

- [ ] **Step 1: Test schreiben**

```python
# tests/test_approval_notifications.py
from models import Notification

def test_approval_creates_notification_for_requester(client, db_session, sample_ticket_with_approval):
    """Approving a ticket notifies the original requester."""
    from services.ticket_approval_service import TicketApprovalService
    ticket = sample_ticket_with_approval  # hat approval.status=PENDING, requester_id
    
    TicketApprovalService.approve_ticket(
        ticket.id, worker_id=1, author="Admin"
    )
    
    # Notification für den Ticket-Ersteller
    notif = Notification.query.filter_by(user_id=ticket.author_id).first()
    assert notif is not None
    assert "freigegeben" in notif.message.lower()
    assert f"/ticket/{ticket.id}" in notif.link
```

- [ ] **Step 2: Verifiziere Fehlschlag**

```bash
python -m pytest tests/test_approval_notifications.py -v
```

- [ ] **Step 3: Implementiere Notification in approve_ticket**

In `services/ticket_approval_service.py`, in der `approve_ticket` Methode,
nach dem E-Mail-Versand (~Zeile 147):

```python
# In-App-Notification für Ticket-Ersteller
if ticket.author_id:
    TicketCoreService.create_notification(
        user_id=ticket.author_id,
        message=f"Ticket #{ticket.id} wurde freigegeben.",
        link=f"/ticket/{ticket.id}",
    )
```

Gleiches Muster in `reject_ticket` (~Zeile 177):

```python
if ticket.author_id:
    TicketCoreService.create_notification(
        user_id=ticket.author_id,
        message=f"Freigabe für Ticket #{ticket.id} abgelehnt: {reason[:80]}",
        link=f"/ticket/{ticket.id}",
    )
```

- [ ] **Step 4: Test bestätigen + Commit**

```bash
python -m pytest tests/ -v
git add services/ticket_approval_service.py tests/test_approval_notifications.py
git commit -m "feat(notifications): notify requester on approval/rejection"
```

### Task 6: Notification bei neuer Approval-Anforderung an Admins

**Files:**
- Modify: `ticketsystem/services/ticket_approval_service.py` (request_approval Methode)
- Test: `ticketsystem/tests/test_approval_notifications.py` (erweitern)

- [ ] **Step 1: Test schreiben**

```python
# In tests/test_approval_notifications.py hinzufügen:

def test_approval_request_notifies_admins(client, db_session, sample_ticket):
    """Requesting approval sends notifications to all admin/hr/management users."""
    from services.ticket_approval_service import TicketApprovalService
    from models import Worker, Notification
    
    # Erstelle Admin-Worker
    admin = Worker.query.filter_by(role="admin").first()
    
    TicketApprovalService.request_approval(
        sample_ticket.id, requester_id=2, author="Worker"
    )
    
    notif = Notification.query.filter_by(user_id=admin.id).first()
    assert notif is not None
    assert "Freigabe" in notif.message
```

- [ ] **Step 2: Implementiere Notification in request_approval**

In `services/ticket_approval_service.py`, in `request_approval`:

```python
# Benachrichtige alle Admins/HR/Management
from models import Worker, WorkerRole
elevated = Worker.query.filter(
    Worker.role.in_([
        WorkerRole.ADMIN.value,
        WorkerRole.HR.value,
        WorkerRole.MANAGEMENT.value,
    ]),
    Worker.is_active.is_(True),
).all()
for w in elevated:
    TicketCoreService.create_notification(
        user_id=w.id,
        message=f"Ticket #{ticket.id} wartet auf Freigabe.",
        link=f"/ticket/{ticket.id}",
    )
```

- [ ] **Step 3: Test + Commit**

```bash
python -m pytest tests/ -v
git add services/ticket_approval_service.py tests/test_approval_notifications.py
git commit -m "feat(notifications): notify admins when approval requested"
```

### Task 7: Notification bei OOO-Delegation an Vertreter

**Files:**
- Modify: `ticketsystem/routes/auth.py:628-639` (Funktion `_update_ooo`)

- [ ] **Step 1: Notification an Vertreter senden**

In `routes/auth.py`, in `_update_ooo`, nach `db.session.commit()` (Zeile ~636):

```python
def _update_ooo(worker: Worker) -> None:
    """Apply out-of-office form data to *worker*."""
    worker.is_out_of_office = request.form.get("is_out_of_office") == "on"
    delegate_id_str = request.form.get("delegate_to_id", "")
    if delegate_id_str.isdigit():
        delegate_id = int(delegate_id_str)
        if delegate_id != worker.id:
            worker.delegate_to_id = delegate_id
            db.session.commit()
            # Vertreter benachrichtigen
            if worker.is_out_of_office:
                from services.ticket_core_service import TicketCoreService
                TicketCoreService.create_notification(
                    user_id=delegate_id,
                    message=f"{worker.name} hat dich als Vertreter eingetragen. Neue Tickets werden an dich weitergeleitet.",
                    link="/my-queue",
                )
                db.session.commit()
            return
    worker.delegate_to_id = None
    db.session.commit()
```

- [ ] **Step 2: Test + Commit**

```bash
python -m pytest tests/ -v
git add routes/auth.py
git commit -m "feat(notifications): notify delegate when OOO activated"
```

---

## D. Approval-Dashboard-Visibility

### Task 8: Approval-Pending-Icon in Dashboard-Tabelle

**Files:**
- Modify: `ticketsystem/templates/components/_ticket_item.html` (render_ticket_row Macro)
- Modify: `ticketsystem/templates/components/_dashboard_cards.html` (Mobile-Card-Variante)

- [ ] **Step 1: Icon in Desktop-Row hinzufügen**

In `_ticket_item.html`, im `render_ticket_row` Macro, nach dem Status-Badge
(suche nach `status_label`):

```html
{# Approval-Pending-Indicator #}
{% if ticket.approval and ticket.approval.status == ApprovalStatus.PENDING.value %}
<span class="badge bg-warning text-dark x-small rounded-pill ms-1" title="Wartet auf Freigabe">
    <i class="bi bi-hourglass-split" aria-hidden="true"></i>
    <span class="visually-hidden">Wartet auf Freigabe</span>
</span>
{% endif %}
```

Hinweis: Prüfe ob dieser Code bereits existiert — das Kanban-Card-Macro in `my_queue.html` hat ihn schon (Zeile 91-92). Wenn er in `_ticket_item.html` fehlt, einfügen.

- [ ] **Step 2: Test + Commit**

```bash
python -m pytest tests/ -v
git add templates/components/_ticket_item.html
git commit -m "feat(ux): show approval-pending badge in dashboard table rows"
```

---

## E. Serienticket-Management

### Task 9: Hilfe-Text für Serienticket-Select

**Files:**
- Modify: `ticketsystem/templates/ticket_new.html` (Serienticket-Select-Feld)

- [ ] **Step 1: Finde das Serienticket-Select**

In `ticket_new.html`, suche nach `recurrence_rule` oder "Serienticket".

- [ ] **Step 2: Füge Helper-Text hinzu**

Direkt nach dem `</select>` des Serienticket-Dropdowns:

```html
<div class="form-text text-muted">
    <i class="bi bi-info-circle me-1" aria-hidden="true"></i>
    Ein Serienticket wird automatisch zum nächsten Termin neu erstellt.
    Die Serie kann später im Ticket-Detail gestoppt werden.
</div>
```

- [ ] **Step 3: Commit**

```bash
git add templates/ticket_new.html
git commit -m "feat(ux): add helper text explaining recurrence behavior"
```

### Task 10: is_active Flag für Recurrence + Stop-Button

**Files:**
- Create: `ticketsystem/migrations/versions/xxx_add_recurrence_is_active.py`
- Modify: `ticketsystem/models.py:284-297` (TicketRecurrence)
- Modify: `ticketsystem/services/scheduler_service.py:52-57`
- Modify: `ticketsystem/routes/ticket_api.py` (neuer Endpoint)
- Modify: `ticketsystem/templates/components/_management_sidebar.html`
- Modify: `ticketsystem/static/js/ticket_detail.js`
- Test: `ticketsystem/tests/test_recurrence_stop.py`

- [ ] **Step 1: Test schreiben**

```python
# tests/test_recurrence_stop.py
def test_stop_recurrence(client, sample_recurring_ticket):
    """POST /api/ticket/<id>/recurrence/stop deaktiviert die Serie."""
    from tests.conftest import login_worker
    login_worker(client, "Admin")
    ticket = sample_recurring_ticket
    
    resp = client.post(
        f"/api/ticket/{ticket.id}/recurrence/stop",
        content_type="application/json",
    )
    assert resp.status_code == 200
    
    from models import TicketRecurrence
    rec = TicketRecurrence.query.filter_by(ticket_id=ticket.id).first()
    assert rec.is_active is False
```

- [ ] **Step 2: Migration erstellen**

```bash
cd ticketsystem
python -c "
from app import app, db
from models import TicketRecurrence
with app.app_context():
    # Add is_active column with default True
    from sqlalchemy import text
    db.session.execute(text('ALTER TABLE ticket_recurrence ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL'))
    db.session.commit()
    print('Column added')
"
```

Oder als Alembic-Migration:

```python
# migrations/versions/xxx_add_recurrence_is_active.py
def upgrade():
    op.add_column("ticket_recurrence", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))

def downgrade():
    op.drop_column("ticket_recurrence", "is_active")
```

- [ ] **Step 3: Model erweitern**

In `models.py`, `TicketRecurrence` Klasse (~Zeile 284-297):

```python
class TicketRecurrence(db.Model):
    __tablename__ = "ticket_recurrence"
    
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("ticket.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rule = db.Column(db.String(50), nullable=False)
    next_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
```

- [ ] **Step 4: Scheduler anpassen**

In `services/scheduler_service.py`, `_fetch_due_recurring_tickets` (~Zeile 52-57):

```python
return Ticket.query.filter(
    Ticket.is_deleted.is_(False),
    Ticket.recurrence.has(
        db.and_(
            TicketRecurrence.next_date <= now,
            TicketRecurrence.is_active.is_(True),  # NEU
        )
    ),
).all()
```

- [ ] **Step 5: API-Endpoint**

In `routes/ticket_api.py`:

```python
@main_bp.route("/api/ticket/<int:ticket_id>/recurrence/stop", methods=["POST"])
@worker_required
@write_required
@api_endpoint
def _stop_recurrence_api(ticket_id: int):
    """Deactivate the recurrence rule for this ticket."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        raise DomainError("Ticket nicht gefunden.", 404)
    rec = ticket.recurrence
    if not rec or not rec.rule:
        raise DomainError("Kein Serienticket.", 409)
    rec.is_active = False
    author = session.get("worker_name", "System")
    TicketCoreService.add_comment(
        ticket_id, "Serie deaktiviert.", author, is_system_event=True
    )
    db.session.commit()
    return api_ok()
```

- [ ] **Step 6: UI-Button in Sidebar**

In `_management_sidebar.html`, in der Serienticket-Anzeige (suche nach
`ticket.recurrence.rule`):

```html
{% if ticket.recurrence and ticket.recurrence.rule %}
<div class="meta-chip">
    <small class="meta-chip-label"><i class="bi bi-arrow-repeat me-1"></i>Serie</small>
    <span class="fw-semibold small">{{ ticket.recurrence.rule|capitalize }}</span>
    {% if ticket.recurrence.is_active and session.get('role') != 'viewer' %}
    <button type="button"
            class="btn btn-link btn-sm text-danger p-0 ms-2"
            id="stopRecurrenceBtn"
            data-ticket-id="{{ ticket.id }}"
            title="Serie stoppen">
        <i class="bi bi-stop-circle" aria-hidden="true"></i>
        <span class="visually-hidden">Serie stoppen</span>
    </button>
    {% elif not ticket.recurrence.is_active %}
    <span class="badge bg-secondary-subtle text-secondary x-small ms-1">gestoppt</span>
    {% endif %}
</div>
{% endif %}
```

- [ ] **Step 7: JS-Handler**

In `ticket_detail.js`:

```javascript
const stopRecBtn = document.getElementById('stopRecurrenceBtn');
if (stopRecBtn) {
    stopRecBtn.addEventListener('click', async function() {
        const ok = window.showConfirm
            ? await window.showConfirm('Serie stoppen', 'Zukünftige Serien-Tickets werden nicht mehr automatisch erstellt. Fortfahren?', true)
            : confirm('Serie stoppen?');
        if (!ok) return;
        const btn = this;
        btn.disabled = true;
        try {
            const resp = await fetch(ingress + '/api/ticket/' + btn.dataset.ticketId + '/recurrence/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
            });
            const errMsg = await window.extractApiError(resp);
            if (errMsg) {
                if (window.showUiAlert) window.showUiAlert(errMsg, 'danger');
                btn.disabled = false;
                return;
            }
            if (window.showUiAlert) window.showUiAlert('Serie gestoppt.', 'success');
            btn.outerHTML = '<span class="badge bg-secondary-subtle text-secondary x-small ms-1">gestoppt</span>';
        } catch(e) {
            if (window.showUiAlert) window.showUiAlert('Netzwerkfehler.', 'danger');
            btn.disabled = false;
        }
    });
}
```

- [ ] **Step 8: Tests + Commit**

```bash
python -m pytest tests/ -v
git add models.py services/scheduler_service.py routes/ticket_api.py templates/components/_management_sidebar.html static/js/ticket_detail.js tests/test_recurrence_stop.py
git commit -m "feat(recurrence): add is_active flag + stop button + scheduler filter"
```

---

## F. Onboarding-Verbesserung

### Task 11: Erstanmeldungs-Text auf change_pin.html verbessern

**Files:**
- Modify: `ticketsystem/templates/change_pin.html:8-12`

- [ ] **Step 1: Kontext-abhängigen Text anzeigen**

Ersetze den statischen Text (Zeile 8-12):

```html
<div class="card-header bg-warning text-dark">
    <h4 class="mb-0"><i class="bi bi-shield-lock-fill" aria-hidden="true"></i> PIN ändern erforderlich</h4>
</div>
<div class="card-body">
    {% if request.args.get('first_login') %}
    <p class="text-muted small">Willkommen! Dies ist deine erste Anmeldung. Wähle einen persönlichen PIN (nur Ziffern, mind. 4), den du dir merken kannst.</p>
    {% else %}
    <p class="text-muted small">Zu deiner Sicherheit muss der PIN nach einem Reset geändert werden.</p>
    {% endif %}
```

In `routes/auth.py`, wo der Redirect zu `change_pin` passiert, füge `?first_login=1`
hinzu wenn `worker.needs_pin_change and worker.login_count == 1`.

- [ ] **Step 2: Commit**

```bash
git add templates/change_pin.html routes/auth.py
git commit -m "feat(ux): context-aware intro text on change_pin (first login vs reset)"
```

### Task 12: Welcome-Toast nach erstem PIN-Wechsel

**Files:**
- Modify: `ticketsystem/routes/auth.py` (nach change_pin Success)

- [ ] **Step 1: Flash-Message nach PIN-Change**

In `routes/auth.py`, nach dem Redirect aus `_change_pin_view`:

```python
flash("Willkommen im Ticketsystem! Dein neuer PIN ist aktiv.", "success")
return redirect(url_for("main.my_queue"))
```

Statt des aktuellen generischen Redirects.

- [ ] **Step 2: Test + Commit**

```bash
python -m pytest tests/ -v
git add routes/auth.py
git commit -m "feat(ux): welcome toast after first PIN change"
```

---

## G. Mobile-Dashboard

### Task 13: Adaptive per_page für Mobile

**Files:**
- Modify: `ticketsystem/routes/dashboard.py:55-56`
- Modify: `ticketsystem/templates/index.html` (Pagination-Info)

- [ ] **Step 1: User-Agent-basierte Default-Pagination**

In `routes/dashboard.py`, ersetze die per_page Logik (~Zeile 55-56):

```python
# Adaptive per_page: Mobile-Geräte bekommen weniger Zeilen
default_per_page = 25
ua = request.headers.get("User-Agent", "")
if any(kw in ua.lower() for kw in ("mobile", "android", "iphone", "ipad")):
    default_per_page = 10

per_page = request.args.get("per_page", default_per_page, type=int)
per_page = min(max(per_page, 5), 100)
```

- [ ] **Step 2: Test + Commit**

```bash
python -m pytest tests/ -v
git add routes/dashboard.py
git commit -m "feat(mobile): adaptive per_page (10 on mobile, 25 on desktop)"
```

---

## Zusammenfassung

| Task | Bereich | Aufwand | Dateien |
|------|---------|---------|---------|
| 1 | Ticket-Redirect | 15 min | ticket_views.py, ticket_public.html |
| 2 | Callback-Done | 30 min | ticket_api.py, _management_sidebar.html, ticket_detail.js |
| 3 | Callback-Tab-Badge | 10 min | index.html |
| 4 | Callback-Overdue-Badge | 15 min | _management_sidebar.html, style.css |
| 5 | Approval-Notifications | 20 min | ticket_approval_service.py |
| 6 | Approval-Request-Notif | 15 min | ticket_approval_service.py |
| 7 | OOO-Delegation-Notif | 10 min | auth.py |
| 8 | Approval-Icon-Dashboard | 10 min | _ticket_item.html |
| 9 | Serienticket-Hilfe | 5 min | ticket_new.html |
| 10 | Recurrence-Stop | 45 min | models.py, scheduler, ticket_api, sidebar, JS |
| 11 | Onboarding-Text | 10 min | change_pin.html, auth.py |
| 12 | Welcome-Toast | 5 min | auth.py |
| 13 | Mobile-per_page | 10 min | dashboard.py |

**Gesamt: ~3.5h Implementation + Testing**
