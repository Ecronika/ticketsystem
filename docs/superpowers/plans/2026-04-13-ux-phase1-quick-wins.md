# UX-Audit 10/10 — Phase 1: Quick Wins

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score 7.2 → 8.0 durch niedrig-hängende UX-Fixes ohne DB-Migrationen.

**Architecture:** Reine Frontend-/Template-Änderungen plus ein neuer Restore-Endpoint. Nutzt bestehende Patterns: Jinja-Templates, vanilla JS in `static/js/`, CSS-Tokens in `style.css`, Service-Methoden mit `@db_transaction`.

**Tech Stack:** Flask, Jinja2, SQLAlchemy, vanilla JS, Bootstrap 5.

**Spec:** [docs/superpowers/specs/2026-04-13-ux-audit-10-of-10-design.md](../specs/2026-04-13-ux-audit-10-of-10-design.md)

---

## File Structure

**Neu:**
- Keine neuen Dateien.

**Geändert:**
- `ticketsystem/services/ticket_core_service.py` — neue `restore_ticket`-Methode.
- `ticketsystem/routes/ticket_views.py` — neuer Route-Handler `POST /tickets/<id>/restore`.
- `ticketsystem/routes/admin.py` — nutzt neue Service-Methode.
- `ticketsystem/routes/dashboard.py` (oder wo Soft-Delete-Flash generiert wird) — erweitert Flash-Payload um Undo-Aktion.
- `ticketsystem/static/js/base_ui.js` — Flash-Auto-Dismiss liest `data-timeout`-Attribut; Undo-Button-Handler.
- `ticketsystem/templates/base.html` — Flash-Block rendert `data-undo-url` / `data-undo-label` / `data-timeout` Attribute.
- `ticketsystem/static/css/style.css` — Chevron-Rotation-Rule + Help-Text-Classes.
- `ticketsystem/templates/ticket_new.html` — `.chevron`-Klasse auf Collapse-Icons.
- `ticketsystem/templates/index.html` — Ergebnis-Count + Refresh-Label.
- `ticketsystem/templates/approvals.html`, `projects.html`, `components/_ticket_checklists.html`, `components/_comment_history.html` — Empty-State-CTAs.
- `ticketsystem/tests/test_tickets.py` — Test für Restore.

---

## Task 1: Restore-Service-Methode

**Files:**
- Modify: `ticketsystem/services/ticket_core_service.py`
- Modify: `ticketsystem/tests/test_tickets.py`

- [ ] **Step 1: Failing-Test schreiben**

In `tests/test_tickets.py` ans Dateiende anfügen:

```python
def test_restore_ticket(test_app, db):
    """Soft-deleted ticket can be restored via service method."""
    from services.ticket_core_service import TicketCoreService
    with test_app.app_context():
        ticket = TicketCoreService.create_ticket(
            title="Wird gelöscht",
            priority=TicketPriority.MITTEL,
            author_name="Max",
        )
        tid = ticket.id
        TicketCoreService.soft_delete_ticket(tid, actor_name="Admin")
        restored = TicketCoreService.restore_ticket(tid, actor_name="Admin")
        assert restored.is_deleted is False
        assert any(
            c.is_system_event and "wiederhergestellt" in (c.content or "").lower()
            for c in restored.comments
        )
```

- [ ] **Step 2: Test läuft und schlägt fehl**

```bash
cd ticketsystem && python -m pytest tests/test_tickets.py::test_restore_ticket -v
```
Erwartet: `AttributeError: ... 'restore_ticket'` oder vergleichbarer Fehler.

Falls `soft_delete_ticket` nicht existiert, auch dessen Implementierung aus `routes/admin.py` in den Service extrahieren (siehe Schritt 3 unten — gleiche Semantik wie Restore, nur mit `is_deleted=True`).

- [ ] **Step 3: Service-Methode implementieren**

In `services/ticket_core_service.py` ergänzen:

```python
@staticmethod
@db_transaction
def restore_ticket(ticket_id: int, *, actor_name: str = "System") -> Ticket:
    """Restore a soft-deleted ticket and record an audit comment."""
    ticket = Ticket.query.get(ticket_id)
    if ticket is None:
        raise TicketNotFoundError(f"Ticket {ticket_id} nicht gefunden.")
    if not ticket.is_deleted:
        return ticket  # idempotent
    ticket.is_deleted = False
    ticket.updated_at = get_utc_now()
    db.session.add(Comment(
        ticket_id=ticket.id,
        author_name=actor_name,
        content="Ticket wiederhergestellt.",
        is_system_event=True,
    ))
    return ticket
```

Imports prüfen: `Comment`, `Ticket`, `get_utc_now`, `db_transaction`, `TicketNotFoundError` müssen vorhanden sein (ggf. ergänzen).

- [ ] **Step 4: Test passiert**

```bash
cd ticketsystem && python -m pytest tests/test_tickets.py::test_restore_ticket -v
```
Erwartet: PASS.

- [ ] **Step 5: Lint & Commit**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 services/ticket_core_service.py tests/test_tickets.py
git add services/ticket_core_service.py tests/test_tickets.py
git commit -m "feat(tickets): add restore_ticket service method with audit trail"
```

---

## Task 2: Restore-Route + Admin-Refactor

**Files:**
- Modify: `ticketsystem/routes/ticket_views.py`
- Modify: `ticketsystem/routes/admin.py:265-280`

- [ ] **Step 1: Neue Route anlegen**

In `routes/ticket_views.py` neue Route ergänzen (Blueprint ist `main_bp`):

```python
@main_bp.route("/tickets/<int:ticket_id>/restore", methods=["POST"])
@worker_required
@write_required
@api_endpoint
def _restore_ticket_api(ticket_id: int):
    actor = session.get("worker_name", "Unbekannt")
    TicketCoreService.restore_ticket(ticket_id, actor_name=actor)
    return {"success": True}
```

Imports ergänzen falls nötig.

- [ ] **Step 2: Admin-Route auf Service umstellen**

In `routes/admin.py` den Inline-Restore-Block (~Zeile 270) ersetzen:

```python
if action == "restore":
    from services.ticket_core_service import TicketCoreService
    TicketCoreService.restore_ticket(ticket_id, actor_name=session.get("worker_name", "Admin"))
    flash("Ticket wiederhergestellt.", "success")
    return redirect(url_for("main.admin_trash"))
```

- [ ] **Step 3: Smoke-Test — Import prüfen**

```bash
cd ticketsystem && python -c "from app import app; print('OK')"
```
Erwartet: `OK`.

- [ ] **Step 4: Baseline-Tests grün**

```bash
cd ticketsystem && python -m pytest tests/ -v
```
Erwartet: 8 passed, 8 failed (Baseline + neuer Test aus Task 1).

- [ ] **Step 5: Commit**

```bash
git add routes/ticket_views.py routes/admin.py
git commit -m "feat(tickets): add POST /tickets/<id>/restore endpoint; admin uses service"
```

---

## Task 3: Flash-Payload um Undo-Action erweitern

**Files:**
- Modify: `ticketsystem/services/_helpers.py` (oder wo `flash_with_action` gehostet werden soll — neu)
- Modify: `ticketsystem/routes/dashboard.py` oder `routes/ticket_views.py` (wo Soft-Delete-Flash gesetzt wird)
- Modify: `ticketsystem/templates/base.html:224-237`

- [ ] **Step 1: Helper-Funktion anlegen**

In `services/_helpers.py` ans Dateiende:

```python
from flask import flash as _flash

def flash_with_undo(message: str, undo_url: str, undo_label: str = "Rückgängig",
                   category: str = "success") -> None:
    """Flash a message that renders with an inline undo button.

    The payload is stored as a dict; base.html reads the dict keys to render
    data-attributes that base_ui.js picks up.
    """
    _flash({"message": message, "undo_url": undo_url, "undo_label": undo_label}, category)
```

- [ ] **Step 2: Soft-Delete-Aufrufer anpassen**

Im Dashboard-Soft-Delete-Handler (suchen mit `grep -n 'is_deleted = True' ticketsystem/routes/` oder nach dem Flash-Text), den bisherigen `flash("Ticket gelöscht.", "success")` ersetzen durch:

```python
from services._helpers import flash_with_undo
flash_with_undo(
    "Ticket gelöscht.",
    undo_url=url_for("main._restore_ticket_api", ticket_id=ticket.id),
    undo_label="Rückgängig",
)
```

Für Bulk-Delete analog, aber mit aggregiertem Undo (siehe Task 4 für Bulk-Handling falls nötig — für MVP nur Single-Delete, Bulk bekommt nur normalen Flash).

- [ ] **Step 3: base.html Flash-Block anpassen**

In `templates/base.html` Zeilen 224–237 den Flash-Loop ersetzen:

```jinja
{% for category, payload in messages %}
  {% if payload is mapping %}
    <div class="alert alert-{{ category if category != 'error' else 'danger' }} alert-dismissible fade show shadow auto-dismiss-alert"
         role="alert"
         data-timeout="{{ 8000 if payload.get('undo_url') else 6000 }}">
      <span>{{ payload.message }}</span>
      {% if payload.get('undo_url') %}
        <button type="button" class="btn btn-sm btn-link ms-2 undo-action-btn"
                data-undo-url="{{ payload.undo_url }}">{{ payload.undo_label }}</button>
      {% endif %}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Schließen"></button>
    </div>
  {% else %}
    <div class="alert alert-{{ category if category != 'error' else 'danger' }} alert-dismissible fade show shadow auto-dismiss-alert"
         role="alert"
         data-timeout="{{ 8000 if '<a' in payload|string else 6000 }}">
      {{ payload }}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Schließen"></button>
    </div>
  {% endif %}
{% endfor %}
```

- [ ] **Step 4: Commit**

```bash
git add services/_helpers.py routes/*.py templates/base.html
git commit -m "feat(ui): flash messages support inline undo action"
```

---

## Task 4: base_ui.js — data-timeout + Undo-Button-Handler

**Files:**
- Modify: `ticketsystem/static/js/base_ui.js`

- [ ] **Step 1: Auto-Dismiss auf data-timeout umstellen**

In `base_ui.js`, die bestehende Auto-Dismiss-Logik (hardcoded 8000/12000) suchen und ersetzen durch:

```javascript
document.querySelectorAll('.auto-dismiss-alert').forEach(alertEl => {
    const timeout = parseInt(alertEl.dataset.timeout || '6000', 10);
    setTimeout(() => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
        bsAlert.close();
    }, timeout);
});
```

- [ ] **Step 2: Undo-Button-Handler ergänzen**

Ans Ende von `base_ui.js`:

```javascript
document.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('.undo-action-btn');
    if (!btn) return;
    ev.preventDefault();
    const url = btn.dataset.undoUrl;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    btn.disabled = true;
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: {'X-CSRFToken': csrfToken, 'Accept': 'application/json'},
        });
        if (!resp.ok) throw new Error(await resp.text());
        showUiAlert('Aktion rückgängig gemacht.', 'success');
        // Optional: Reload für konsistente Darstellung
        setTimeout(() => window.location.reload(), 500);
    } catch (err) {
        showUiAlert('Rückgängig fehlgeschlagen.', 'danger');
        btn.disabled = false;
    }
});
```

- [ ] **Step 3: Manuell smoke-testen**

Server lokal starten, Ticket erstellen, löschen, Toast erscheint mit „Rückgängig", Klick stellt wieder her. Zweiter Toast bestätigt.

- [ ] **Step 4: Commit**

```bash
git add static/js/base_ui.js
git commit -m "feat(ui): undo-button handler + data-timeout for flash dismissal"
```

---

## Task 5: Chevron-Rotation für Collapse-Trigger

**Files:**
- Modify: `ticketsystem/static/css/style.css`
- Modify: `ticketsystem/templates/ticket_new.html:182`
- Modify: `ticketsystem/templates/ticket_new.html:119` (Kundenkontakt)

- [ ] **Step 1: CSS-Rule ergänzen**

Ans Ende von `static/css/style.css`:

```css
[data-bs-toggle="collapse"] .chevron,
[aria-expanded] .chevron {
    display: inline-block;
    transition: transform .15s ease;
}
[aria-expanded="true"] .chevron {
    transform: rotate(180deg);
}
```

- [ ] **Step 2: Collapse-Buttons markieren**

In `templates/ticket_new.html`, die zwei Collapse-Toggles (Kundenkontakt-Section ~Zeile 119, Erweiterte-Optionen ~Zeile 182) enthalten Icons. Icon-Element bekommt zusätzlich `class="chevron"`:

Vorher (Beispiel):
```html
<button class="btn btn-link" data-bs-toggle="collapse" data-bs-target="#advancedOpts"
        aria-expanded="false" aria-controls="advancedOpts">
  Erweiterte Optionen <i class="bi bi-chevron-down"></i>
</button>
```

Nachher:
```html
<button class="btn btn-link" data-bs-toggle="collapse" data-bs-target="#advancedOpts"
        aria-expanded="false" aria-controls="advancedOpts">
  Erweiterte Optionen <i class="bi bi-chevron-down chevron"></i>
</button>
```

Bootstrap setzt `aria-expanded` automatisch, die CSS-Regel greift.

- [ ] **Step 3: Visuell testen**

Dev-Server, `/tickets/new` öffnen, Kundenkontakt + Erweiterte Optionen ein-/ausklappen. Chevron rotiert um 180°.

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css templates/ticket_new.html
git commit -m "feat(ui): rotate chevron icons when collapse sections expand"
```

---

## Task 6: Dashboard-Suche — Ergebnis-Count mit ARIA-Live

**Files:**
- Modify: `ticketsystem/templates/index.html:406-416` (Such-Form) und ~494 (Count-Stelle)

- [ ] **Step 1: Count neben Suchfeld positionieren**

In `index.html`, nahe dem Suchformular (~Zeile 416, nach dem Submit-Button):

```html
<span id="dashSearchCount" class="text-muted small ms-2"
      role="status" aria-live="polite" aria-atomic="true">
  {% if pagination.total == 1 %}1 Ticket{% else %}{{ pagination.total }} Tickets{% endif %}
  {% if request.args.get('q') %}für „{{ request.args.get('q') }}"{% endif %}
</span>
```

Den bestehenden Count in der Card-Footer (`{{ pagination.total }} Tickets gesamt` bei Zeile 494) optional entfernen, um Redundanz zu vermeiden — oder belassen als „gesamt"-Info. **Entscheidung:** Belassen, der Footer-Count zeigt den Total-Count, der Header-Count zeigt das Such-Ergebnis (bei gleicher Zahl ohne Filter).

- [ ] **Step 2: Visuell testen**

Dev-Server, Dashboard öffnen, Suchbegriff eingeben → Count aktualisiert sich nach Submit. Screenreader-Test (NVDA/VO) liest die Änderung vor.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat(dashboard): inline search result count with aria-live announcement"
```

---

## Task 7: Dashboard „Aktualisiert vor X s"-Label

**Files:**
- Modify: `ticketsystem/templates/index.html` (Polling-JS-Bereich, ~Zeile 31-54 + Header-Bereich)

- [ ] **Step 1: Label im Header einfügen**

In `index.html`, nahe dem Dashboard-Überschrift-Bereich (vor der Tabelle, am besten in der Card-Header):

```html
<span id="dashRefreshLabel" class="text-muted small"
      data-refreshed-at="{{ (now_utc or get_utc_now()).isoformat() }}"
      aria-live="off">Aktualisiert gerade eben</span>
```

Falls `now_utc` nicht im Template-Context ist, Template-Context-Processor oder Inline-JS `new Date().toISOString()` auf Page-Load.

- [ ] **Step 2: JS — Polling setzt Zeitstempel, separater Interval rendert Label**

Im bestehenden Polling-Script (`index.html` ~Zeile 31-54), nach erfolgreichem Fetch:

```javascript
const refreshLabel = document.getElementById('dashRefreshLabel');
if (refreshLabel) refreshLabel.dataset.refreshedAt = new Date().toISOString();
```

Unterhalb als eigenständiger Interval:

```javascript
setInterval(() => {
    const el = document.getElementById('dashRefreshLabel');
    if (!el) return;
    const ts = new Date(el.dataset.refreshedAt);
    const diffSec = Math.max(0, Math.round((Date.now() - ts.getTime()) / 1000));
    if (diffSec < 5) el.textContent = 'Aktualisiert gerade eben';
    else if (diffSec < 60) el.textContent = `Aktualisiert vor ${diffSec}s`;
    else el.textContent = `Aktualisiert vor ${Math.floor(diffSec / 60)}min`;
}, 1000);
```

- [ ] **Step 3: Smoke-Test**

Dashboard öffnen, 10+ Sekunden warten. Label zählt hoch („Aktualisiert vor 3s", „Aktualisiert vor 7s"). Nach Polling-Refresh springt es zurück auf „gerade eben".

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat(dashboard): relative timestamp label for live polling"
```

---

## Task 8: Empty-State CTAs

**Files:**
- Modify: `ticketsystem/templates/approvals.html:18-20`
- Modify: `ticketsystem/templates/projects.html:22-26`
- Modify: `ticketsystem/templates/components/_ticket_checklists.html:132`
- Modify: `ticketsystem/templates/components/_comment_history.html:25`

- [ ] **Step 1: Approvals Empty State**

Aktuell: „Keine ausstehenden Freigaben". Ergänzen zu:

```html
<div class="text-center py-5 text-muted">
  <p class="mb-2">Keine ausstehenden Freigaben.</p>
  <a href="{{ url_for('main.index') }}" class="btn btn-outline-primary btn-sm">
    Zum Dashboard
  </a>
</div>
```

- [ ] **Step 2: Projects Empty State**

Aktuell: „Keine Bauvorhaben/Projekte gefunden". Ergänzen zu:

```html
<div class="text-center py-5 text-muted">
  <p class="mb-2">Keine Projekte gefunden.</p>
  <a href="{{ url_for('main.new_ticket_view') }}" class="btn btn-outline-primary btn-sm">
    + Neues Ticket anlegen
  </a>
</div>
```

URL-Endpoint-Name durch passenden ersetzen (via `grep -rn 'new_ticket\|ticket_new' routes/` bestätigen).

- [ ] **Step 3: Checklists Empty State**

Aktuell: „Keine Unteraufgaben vorhanden". Falls das bestehende Add-Formular direkt darunter steht, CTA-Button, der es fokussiert:

```html
<div class="text-muted small py-3 text-center" data-test="checklist-empty">
  <p class="mb-2">Keine Unteraufgaben vorhanden.</p>
  <button type="button" class="btn btn-outline-primary btn-sm"
          onclick="document.getElementById('newChecklistItemInput')?.focus()">
    + Unteraufgabe hinzufügen
  </button>
</div>
```

Input-ID ggf. anpassen.

- [ ] **Step 4: Comments Empty State**

Aktuell: „Noch keine Kommentare". Erweitern zu:

```html
<div class="text-muted small py-3 text-center">
  <p class="mb-2">Noch keine Kommentare.</p>
  <button type="button" class="btn btn-outline-primary btn-sm"
          onclick="document.getElementById('commentTextarea')?.focus()">
    Ersten Kommentar verfassen
  </button>
</div>
```

- [ ] **Step 5: Commit**

```bash
git add templates/approvals.html templates/projects.html templates/components/_ticket_checklists.html templates/components/_comment_history.html
git commit -m "feat(ui): action-oriented empty states with CTA buttons"
```

---

## Task 9: Final Verification

- [ ] **Step 1: Baseline-Tests**

```bash
cd ticketsystem && python -m pytest tests/ -v
```
Erwartet: 8 passed (7 Baseline + 1 neu aus Task 1), 8 failed (pre-existing).

- [ ] **Step 2: Lint**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```
Erwartet: keine Warnings.

- [ ] **Step 3: Import-Check**

```bash
cd ticketsystem && python -c "from app import app; print('OK')"
```

- [ ] **Step 4: Manueller Smoke-Test-Pfad**

1. Ticket erstellen → Flash „Ticket angelegt" erscheint, verschwindet nach 6 s.
2. Ticket soft-delete → Flash „Ticket gelöscht · Rückgängig", 8 s sichtbar.
3. Klick auf „Rückgängig" → Ticket ist wieder da, zweiter Toast „Aktion rückgängig gemacht".
4. `/tickets/new` → Erweiterte Optionen ein-/ausklappen → Chevron dreht sich.
5. Dashboard → Suche „Test" → Count-Label aktualisiert sich.
6. Dashboard öffnen, 15 s warten → Refresh-Label zählt hoch.
7. Approvals-Page ohne Einträge → „Zum Dashboard"-Button erscheint.

- [ ] **Step 5: Phase-1-Abschluss-Commit (falls nötig)**

Alle Änderungen sollten bereits commited sein. Optional Tag:

```bash
git tag ux-phase-1-complete
```
