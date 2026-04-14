# UX-Audit v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die 16 offenen Findings aus [UX_AUDIT_2026-04-14_v2.md](UX_AUDIT_2026-04-14_v2.md) (10 neue + 6 Carry-Overs) umsetzen und damit den Score von 8.4 → ≥9.5/10 heben.

**Architecture:** Jinja/Bootstrap-Templates direkt editieren; keine neuen Services/Models. Für wiederkehrende Prio-Farben ein neuer Template-Filter `priority_color` in [app.py](app.py); für das duplizierte Reject-Modal ein neues Partial `templates/components/_reject_approval_modal.html`. Große Carry-Overs (Bulk-Bar, Row-Flash, DOM-Patch) betreffen `static/js/` und `templates/index.html`.

**Tech Stack:** Flask 3, Jinja2, Bootstrap 5.3, vanilla JS (kein Build-Step), pytest, flake8.

**Baseline-Regel:** Vor jedem Commit: `cd ticketsystem && python -m pytest tests/ -v` und `python -m flake8 --max-line-length=120 *.py routes/ services/` — es dürfen **keine neuen Failures** auftreten. Vor dem ersten Task die aktuelle Baseline (X passed, Y failed) als Referenz erfassen.

**Branch-Strategie:** `ux/audit-v2-fixes-2026-04-14` für Phasen 1–3 (kleine + mittlere Fixes), separater Branch `ux/audit-v2-bulk-bar-and-polling` für Phase 4 (größere JS-Änderungen).

---

## Phase 0: Baseline

### Task 0: Baseline erfassen und Branch erstellen

**Files:** keine

- [ ] **Step 1: Baseline-Tests laufen lassen**

```bash
cd ticketsystem
python -m pytest tests/ -v 2>&1 | tail -5
python -m flake8 --max-line-length=120 *.py routes/ services/
python -c "from app import app; print('import ok')"
```

Expected: X passed, Y failed — notieren. Flake8 clean. Import ok. Diese Zahlen sind die Messlatte für alle folgenden Commits.

- [ ] **Step 2: Feature-Branch anlegen**

```bash
git checkout -b ux/audit-v2-fixes-2026-04-14
```

---

## Phase 1: Quick Wins (N1, N2, N7, N9, N10)

Kleine, unabhängige Template-Edits. Jede in einem eigenen Commit, damit Reverts punktgenau möglich sind.

### Task 1: N1 — Approval-Prio-Farbe je Level (Filter `priority_color`)

**Files:**
- Modify: `ticketsystem/app.py` (nach `priority_label_filter`, ab Zeile 819)
- Modify: `ticketsystem/templates/approvals.html:30-32`
- Optional-Refactor (später): `components/_ticket_header.html`, `archive.html`, `ticket_public.html` — nicht Teil dieser Task, damit der Commit klein bleibt.

- [ ] **Step 1: Filter in `app.py` hinzufügen**

Nach Zeile 819 (Ende von `priority_label_filter`) einfügen:

```python
_PRIO_COLORS = {
    TicketPriority.HOCH.value: "danger",
    TicketPriority.MITTEL.value: "primary",
    TicketPriority.NIEDRIG.value: "success",
}


@app.template_filter("priority_color")
def priority_color_filter(priority: int) -> str:
    """Return Bootstrap color key (danger/primary/success) for a priority."""
    return _PRIO_COLORS.get(priority, "secondary")
```

- [ ] **Step 2: `approvals.html` Badge-Farbe dynamisch**

In [approvals.html:30-32](templates/approvals.html#L30) die Zeile

```jinja
<span class="badge bg-danger-subtle text-danger rounded-pill px-2 py-1 mb-2 fw-bold text-xs">
    {{ ticket.priority|priority_label }}
</span>
```

ersetzen durch:

```jinja
{% set prio_color = ticket.priority|priority_color %}
<span class="badge bg-{{ prio_color }}-subtle text-{{ prio_color }} rounded-pill px-2 py-1 mb-2 fw-bold text-xs">
    {{ ticket.priority|priority_label }}
</span>
```

- [ ] **Step 3: App-Import + pytest + flake8**

```bash
cd ticketsystem
python -c "from app import app; print('import ok')"
python -m pytest tests/ -v 2>&1 | tail -5
python -m flake8 --max-line-length=120 app.py
```

Expected: Import ok. Pytest-Zahlen ≥ Baseline. Flake8 clean.

- [ ] **Step 4: Manuell verifizieren**

App starten (wie gewohnt lokal), auf `/approvals` gehen mit je einem Ticket Prio 1/2/3. Visuell prüfen: Hoch=rot, Mittel=blau, Niedrig=grün.

- [ ] **Step 5: Commit**

```bash
git add app.py templates/approvals.html
git commit -m "fix(ux): approval-card priority color maps to actual priority level

Hardcoded bg-danger-subtle made every priority appear red on /approvals.
New jinja filter priority_color centralises the danger/primary/success
mapping; ready to replace inline conditionals in _ticket_header.html,
archive.html and ticket_public.html in a follow-up.

Ref: UX-Audit v2 N1."
```

---

### Task 2: N2 — `|upper` aus Assign-Dropdown entfernen

**Files:**
- Modify: `ticketsystem/templates/components/_management_sidebar.html:39-50`

- [ ] **Step 1: UPPERCASE durch Titlecase ersetzen**

In [_management_sidebar.html:39-50](templates/components/_management_sidebar.html#L39):

```jinja
<option value="" {% if not ticket.assigned_to_id and not ticket.assigned_team_id %}selected{% endif %}>NICHT ZUGEWIESEN</option>
{% for worker in workers %}
<option value="{{ worker.id }}" {% if ticket.assigned_to_id == worker.id %}selected{% endif %}>
    {{ worker.name|upper }}
</option>
{% endfor %}
{% if teams %}
<optgroup label="Teams">
    {% for team in teams %}
    <option value="team_{{ team.id }}" {% if ticket.assigned_team_id == team.id %}selected{% endif %}>
        TEAM: {{ team.name|upper }}
    </option>
    {% endfor %}
</optgroup>
{% endif %}
```

ersetzen durch:

```jinja
<option value="" {% if not ticket.assigned_to_id and not ticket.assigned_team_id %}selected{% endif %}>Nicht zugewiesen</option>
{% for worker in workers %}
<option value="{{ worker.id }}" {% if ticket.assigned_to_id == worker.id %}selected{% endif %}>
    {{ worker.name }}
</option>
{% endfor %}
{% if teams %}
<optgroup label="Teams">
    {% for team in teams %}
    <option value="team_{{ team.id }}" {% if ticket.assigned_team_id == team.id %}selected{% endif %}>
        Team: {{ team.name }}
    </option>
    {% endfor %}
</optgroup>
{% endif %}
```

- [ ] **Step 2: Verifizieren**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: Pytest-Zahlen ≥ Baseline.

- [ ] **Step 3: Manuell prüfen**

Beliebiges Ticket-Detail öffnen, Assign-Dropdown aufklappen → Namen jetzt im normalen Case, „Nicht zugewiesen" normal geschrieben.

- [ ] **Step 4: Commit**

```bash
git add templates/components/_management_sidebar.html
git commit -m "fix(ux): remove |upper from assign dropdown in ticket sidebar

The v1-fix removed |upper from status badges but the assign dropdown in
_management_sidebar.html was overlooked. Titlecase is the agreed style.

Ref: UX-Audit v2 N2."
```

---

### Task 3: N7 — `h1` auf `ticket_new.html`

**Files:**
- Modify: `ticketsystem/templates/ticket_new.html:16`

- [ ] **Step 1: `<h2 class="h4">` → `<h1 class="h4">`**

In [ticket_new.html:16](templates/ticket_new.html#L16):

```jinja
<h2 class="h4 fw-bold mb-0">Neues Ticket melden</h2>
```

ersetzen durch:

```jinja
<h1 class="h4 fw-bold mb-0">Neues Ticket melden</h1>
```

- [ ] **Step 2: Pytest + visuelle Kontrolle**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

Optik bleibt identisch (Utility-Klasse `h4` trägt die Größe), nur Heading-Outline ist korrekt.

- [ ] **Step 3: Commit**

```bash
git add templates/ticket_new.html
git commit -m "fix(a11y): use h1 on ticket_new for correct heading outline

Top-level page heading should be h1 for screenreader outline. Visual
size unchanged via the h4 utility class.

Ref: UX-Audit v2 N7."
```

---

### Task 4: N9 — Footer-Jahreszahl dynamisch

**Files:**
- Modify: `ticketsystem/app.py` (context_processor-Abschnitt suchen)
- Modify: `ticketsystem/templates/base.html:269`

- [ ] **Step 1: Context-Processor-Stelle finden**

```bash
grep -n 'context_processor\|@app.context_processor' app.py
```

Notiere die Zeilenummer des ersten bestehenden `@app.context_processor`.

- [ ] **Step 2: `current_year` im Context-Processor ergänzen**

Den bestehenden Context-Processor erweitern (falls vorhanden Dictionary, Schlüssel `current_year` hinzufügen). Falls es keinen gibt, einen neuen direkt unter den bestehenden Template-Filtern (nach `priority_color_filter`) einfügen:

```python
from datetime import datetime


@app.context_processor
def inject_current_year() -> dict[str, int]:
    """Make current_year available in all templates (footer copyright)."""
    return {"current_year": datetime.utcnow().year}
```

Wenn bereits ein Context-Processor existiert, den neuen Schlüssel dort eintragen statt einen zweiten Processor anzulegen. Import-Zeile oben in `app.py` nur hinzufügen, wenn `datetime` dort noch nicht importiert ist.

- [ ] **Step 3: `base.html:269` dynamisch machen**

```jinja
TicketSystem &copy; 2026 | v{{ config.VERSION }}
```

ersetzen durch:

```jinja
TicketSystem &copy; {{ current_year }} | v{{ config.VERSION }}
```

- [ ] **Step 4: Pytest + App-Import + Footer-Check**

```bash
python -c "from app import app; print('import ok')"
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add app.py templates/base.html
git commit -m "fix(ux): dynamic footer copyright year

Replaces hardcoded 2026 with a context-processor-injected current_year so
the footer rolls over automatically.

Ref: UX-Audit v2 N9."
```

---

### Task 5: N10 — Approvals-Empty-State-CTA Primary-Stil

**Files:**
- Modify: `ticketsystem/templates/approvals.html:21`

- [ ] **Step 1: Button-Klasse angleichen**

In [approvals.html:21](templates/approvals.html#L21):

```jinja
<a href="{{ ingress_path }}{{ url_for('main.index') }}" class="btn btn-outline-primary btn-sm">Zum Dashboard</a>
```

ersetzen durch:

```jinja
<a href="{{ ingress_path }}{{ url_for('main.index') }}" class="btn btn-primary btn-sm rounded-pill px-3">Zum Dashboard</a>
```

- [ ] **Step 2: Pytest**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add templates/approvals.html
git commit -m "fix(ux): align approvals empty-state CTA with primary button style

Other empty-states use btn-primary rounded-pill; approvals.html used
btn-outline-primary btn-sm. Consistency win.

Ref: UX-Audit v2 N10."
```

---

## Phase 2: Mittelgroße Fixes (N4, N5+N6, N3)

### Task 6: N4 — SRI-Integrity für `sortablejs`

**Files:**
- Modify: `ticketsystem/templates/ticket_detail.html:63`

- [ ] **Step 1: SRI-Hash berechnen**

```bash
curl -s https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js \
  | openssl dgst -sha384 -binary | openssl base64 -A
```

Expected: Eine Base64-String-Ausgabe, z. B. `Kx…=`. Den Hash merken (Variable `<SRI_HASH>` unten).

- [ ] **Step 2: `<script>` um `integrity` + `crossorigin` erweitern**

In [ticket_detail.html:63](templates/ticket_detail.html#L63):

```jinja
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"></script>
```

ersetzen durch:

```jinja
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"
        integrity="sha384-<SRI_HASH>"
        crossorigin="anonymous"></script>
```

(`<SRI_HASH>` durch den Wert aus Step 1 ersetzen.)

- [ ] **Step 3: Laufzeit-Test**

App starten, Ticket-Detail mit Checklist öffnen, Checklist-Item per Drag&Drop neu sortieren → Sortable.js funktioniert (keine Konsolenfehler). Bei SRI-Mismatch blockt der Browser das Script; genau das wollen wir verhindert sehen.

- [ ] **Step 4: Pytest**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add templates/ticket_detail.html
git commit -m "security: add SRI integrity to sortablejs CDN include

All other CDN includes (Bootstrap, Icons) use SRI; Sortable.js was the
only unhardened script. Pins to 1.15.6 hash.

Ref: UX-Audit v2 N4."
```

---

### Task 7: N5 + N6 — Reject-Modal in Partial + Autofokus

**Files:**
- Create: `ticketsystem/templates/components/_reject_approval_modal.html`
- Modify: `ticketsystem/templates/ticket_detail.html:37-58` (Modal-Block entfernen, Include setzen)
- Modify: `ticketsystem/templates/approvals.html:93-114` (Modal-Block entfernen, Include setzen)
- Check: `ticketsystem/static/js/ticket_detail.js` (nutzt `#rejectReasonInput`, `#submitRejectBtn`, `#rejectTicketId` — IDs bleiben bestehen)

- [ ] **Step 1: Partial anlegen**

Inhalt der neuen Datei `ticketsystem/templates/components/_reject_approval_modal.html`:

```jinja
{# Reject-Approval-Modal — verwendet von ticket_detail.html und approvals.html.
   Die IDs (#rejectReasonInput, #submitRejectBtn, #rejectTicketId) werden von
   static/js/ticket_detail.js angesprochen. #}
<div class="modal fade" id="rejectApprovalModal" tabindex="-1"
     aria-labelledby="rejectApprovalModalLabel" aria-hidden="true"
     data-autofocus-target="rejectReasonInput">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content modal-content-std">
            <div class="modal-header modal-header-std">
                <h5 class="modal-title fw-bold text-danger" id="rejectApprovalModalLabel">
                    <i class="bi bi-x-circle-fill me-2"></i>Freigabe ablehnen
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Schließen"></button>
            </div>
            <div class="modal-body p-4">
                <input type="hidden" id="rejectTicketId">
                <div class="mb-3">
                    <label for="rejectReasonInput" class="form-label form-label-bold">Ablehnungsgrund (Pflichtfeld)</label>
                    <textarea id="rejectReasonInput"
                              class="form-control focus-ring focus-ring-danger border-danger-subtle"
                              rows="3"
                              placeholder="Bitte geben Sie an, warum das Ticket nicht freigegeben wurde..."
                              required></textarea>
                </div>
            </div>
            <div class="modal-footer modal-footer-std">
                <button type="button" class="btn btn-light rounded-pill px-4" data-bs-dismiss="modal">Abbrechen</button>
                <button type="button" class="btn btn-danger rounded-pill px-4" id="submitRejectBtn">Ablehnen</button>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Autofocus-Verhalten in `base_ui.js` ergänzen**

Vorher prüfen, ob bereits ein generisches `data-autofocus-target`-Handler-Pattern existiert:

```bash
grep -n 'data-autofocus\|shown.bs.modal' ticketsystem/static/js/base_ui.js ticketsystem/static/js/ticket_detail.js
```

Wenn **kein** Handler existiert, in `ticketsystem/static/js/base_ui.js` ans Ende der Datei ergänzen:

```javascript
// Auto-focus first field when a modal with [data-autofocus-target] opens.
document.addEventListener('shown.bs.modal', function(evt) {
    var modal = evt.target;
    if (!modal || !modal.dataset) return;
    var targetId = modal.dataset.autofocusTarget;
    if (!targetId) return;
    var el = modal.querySelector('#' + targetId);
    if (el && typeof el.focus === 'function') el.focus();
});
```

Wenn bereits ein vergleichbarer Handler existiert, nur ein Kommentar-Hinweis dass `data-autofocus-target` jetzt genutzt wird. Keine Duplikate.

- [ ] **Step 3: Modal-Block aus `ticket_detail.html` entfernen und Include setzen**

In [ticket_detail.html:37-58](templates/ticket_detail.html#L37) den gesamten `<!-- Reject Modal -->`-Block (Zeile 37–58) ersetzen durch:

```jinja
{% include 'components/_reject_approval_modal.html' %}
```

- [ ] **Step 4: Modal-Block aus `approvals.html` entfernen und Include setzen**

In [approvals.html:93-114](templates/approvals.html#L93) den gesamten `<!-- Reject Modal -->`-Block (Zeile 93–114) ersetzen durch:

```jinja
{% include 'components/_reject_approval_modal.html' %}
```

- [ ] **Step 5: Pytest + App-Import**

```bash
python -c "from app import app; print('import ok')"
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 6: Manuell prüfen**

Auf `/approvals`: „Ablehnen" klicken → Modal öffnet, Cursor steht **direkt** im Textarea. Gleiches auf einem Ticket-Detail mit Pending-Approval in der Sidebar.

- [ ] **Step 7: Commit**

```bash
git add templates/components/_reject_approval_modal.html \
        templates/ticket_detail.html \
        templates/approvals.html \
        static/js/base_ui.js
git commit -m "refactor(templates): extract rejectApprovalModal partial + autofocus

Removes duplication between ticket_detail.html and approvals.html. A new
data-autofocus-target handler in base_ui.js focuses the reason textarea
on modal open, saving a click.

Ref: UX-Audit v2 N5, N6."
```

---

### Task 8: N3 — Urgent-Badge auf `my_queue` entfernen (Doppelinfo)

**Files:**
- Modify: `ticketsystem/templates/my_queue.html:5-15`

- [ ] **Step 1: Header-Block vereinfachen**

In [my_queue.html:5-15](templates/my_queue.html#L5):

```jinja
<div>
    <h1 class="h3 fw-bold mb-0">Meine Aufgaben</h1>
    {% if urgent_count > 0 %}
    <span class="badge bg-danger-subtle text-danger border border-danger-subtle fw-semibold mt-1 d-inline-flex align-items-center gap-1">
        <i class="bi bi-exclamation-circle-fill"></i> {{ urgent_count }} Ticket{{ 's' if urgent_count != 1 }} benötigen Aufmerksamkeit
    </span>
    {% else %}
    <span class="text-muted small"><i class="bi bi-check-circle-fill text-success me-1"></i>Keine dringenden Aufgaben.</span>
    {% endif %}
</div>
```

ersetzen durch:

```jinja
<div>
    <h1 class="h3 fw-bold mb-0">Meine Aufgaben</h1>
    {% if urgent_count == 0 %}
    <span class="text-muted small">
        <i class="bi bi-check-circle-fill text-success me-1"></i>Keine dringenden Aufgaben.
    </span>
    {% endif %}
</div>
```

(Die „Sofort"-Spalte des Kanbans zeigt die dringenden Tickets visuell — das Badge ist redundant.)

- [ ] **Step 2: Pytest**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add templates/my_queue.html
git commit -m "ux: remove redundant urgent-count badge on my_queue header

Kanban's 'Sofort' column already visualises urgent tickets; the header
badge duplicated the information. Keeps the positive empty-state for
zero urgent tickets.

Ref: UX-Audit v2 N3."
```

---

## Phase 3: Carry-Overs aus v1 (C4, C5, C6)

### Task 9: C4 — Dirty-Warn öffnet Collapse-Bereiche

**Files:**
- Modify: `ticketsystem/static/js/form_validation.js` (Stelle mit `data-dirty-warn` / `beforeunload`-Handler)

- [ ] **Step 1: Dirty-Warn-Stelle finden**

```bash
grep -n 'data-dirty-warn\|beforeunload\|dirty' ticketsystem/static/js/form_validation.js
```

- [ ] **Step 2: Beim Submit-Attempt Collapse-Bereiche öffnen**

Der vorhandene Dirty-Warn-Flow lebt in `form_validation.js`. Ergänze eine Funktion, die beim `invalid`-Event oder bei einem fehlgeschlagenen Submit alle `.collapse`-Bereiche innerhalb des Formulars öffnet, die ein Feld mit Wert enthalten:

```javascript
// Opens every .collapse inside the form that contains a field the user has
// already filled in — prevents hidden "unsaved" fields from surprising users.
function openCollapsesWithDirtyFields(form) {
    form.querySelectorAll('.collapse').forEach(function(collapse) {
        var hasValue = Array.from(collapse.querySelectorAll('input, select, textarea'))
            .some(function(el) {
                if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
                return el.value && el.value.trim().length > 0;
            });
        if (hasValue && typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
            bootstrap.Collapse.getOrCreateInstance(collapse).show();
        }
    });
}
```

Diese Funktion an der passenden Stelle aufrufen: in dem `submit`-Handler, der die Dirty-Validation auslöst, **bevor** das Form validiert wird. Konkret direkt nach der Fehlererkennung `if (!form.checkValidity()) { … openCollapsesWithDirtyFields(form); … }`.

- [ ] **Step 3: Manuelle Verifikation**

Auf `/new-ticket`: Datum in „Erweiterte Optionen" setzen (sofern noch collapsable — nach v1-Fix ist `due_date` out), Collapse einklappen, Submit leer absenden → Collapse öffnet sich automatisch und zeigt die dirty Felder.

- [ ] **Step 4: Pytest**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add static/js/form_validation.js
git commit -m "ux: open collapse sections on dirty-form submit failure

Hidden fields in .collapse blocks were easy to forget. When validation
fails we now expand any collapse that contains a filled-in field so the
user sees exactly what they still need to address.

Ref: UX-Audit v2 C4."
```

---

### Task 10: C5 — Breadcrumb-Konsistenz dokumentieren + Profil-Breadcrumb

**Files:**
- Modify: `ticketsystem/templates/profile.html` (Breadcrumb-Block ergänzen)
- Modify: `ticketsystem/CLAUDE.md` (Konvention dokumentieren)

- [ ] **Step 1: Konvention entscheiden und in CLAUDE.md festhalten**

In `ticketsystem/CLAUDE.md` unter „Architektur-Übersicht" einen neuen Unterabschnitt hinzufügen:

```markdown
### Breadcrumbs-Konvention

- **Top-Level-Einstiegsseiten** (Dashboard `index`, `my_queue`, `login`,
  `approvals`): **kein** Breadcrumb. Diese Seiten sind in der Hauptnavigation
  sichtbar; ein Breadcrumb mit nur „Dashboard › X" wäre redundant.
- **Drill-Down- und Admin-Seiten** (`ticket_detail`, `workload`, `settings`,
  `projects`, `profile`): **Breadcrumb verpflichtend**. Muster:
  `Dashboard › [Sektion] › [Page-Name]`.
- Implementierung über den Jinja-Block `{% block breadcrumbs %}` in `base.html`.
```

- [ ] **Step 2: Breadcrumb auf `profile.html` ergänzen**

Am Anfang von `profile.html` (nach `{% extends "base.html" %}` / `{% block title %}`, vor `{% block content %}`):

```jinja
{% block breadcrumbs %}
<nav aria-label="Breadcrumb" class="mb-3">
    <ol class="breadcrumb mb-0 small">
        <li class="breadcrumb-item"><a href="{{ ingress_path }}{{ url_for('main.index') }}" class="text-decoration-none">Dashboard</a></li>
        <li class="breadcrumb-item active" aria-current="page">Mein Profil</li>
    </ol>
</nav>
{% endblock %}
```

`approvals` bleibt nach der dokumentierten Konvention **ohne** Breadcrumb (Top-Level über Nav).

- [ ] **Step 3: Pytest**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md templates/profile.html
git commit -m "docs+ux: breadcrumb convention + add profile breadcrumb

Documents 'top-level nav pages have no breadcrumb; drill-down and admin
pages must' so the split is intentional. Profile was the drill-down
outlier without one.

Ref: UX-Audit v2 C5."
```

---

### Task 11: C6 — Hinweis für Ticket-Ersteller auf `ticket_public`

**Files:**
- Modify: `ticketsystem/templates/ticket_public.html:74-77`

- [ ] **Step 1: Hinweis einfügen**

In [ticket_public.html:74-77](templates/ticket_public.html#L74) nach dem bestehenden Info-Absatz:

```jinja
<p class="text-muted small mb-0">
    <i class="bi bi-info-circle me-1"></i>
    Haben Sie Ergänzungen zu diesem Ticket? Antworten Sie auf die
    Bestätigungs-E-Mail oder kontaktieren Sie uns telefonisch — eine
    direkte Antwort auf dieser Seite ist nicht möglich.
</p>
```

(Direkt nach dem vorhandenen „Dies ist eine öffentlich einsehbare Status-Seite …"-Absatz, vor dem Mitarbeiter-Login-Button.)

- [ ] **Step 2: Pytest + Visual**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

Anonym `/public/ticket/<id>` aufrufen, Hinweis erscheint unter dem Status-Info-Text.

- [ ] **Step 3: Commit**

```bash
git add templates/ticket_public.html
git commit -m "ux: add contact hint for ticket authors on public status page

ticket_public.html explained what the page is but not how the author can
add information after submission. Points to email reply or phone.

Ref: UX-Audit v2 C6."
```

---

### Task 12: Phase 1–3 Merge

- [ ] **Step 1: Baseline final prüfen**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
python -m flake8 --max-line-length=120 *.py routes/ services/
python -c "from app import app; print('import ok')"
```

Expected: Pytest-Zahlen ≥ Baseline, Flake8 clean, Import ok.

- [ ] **Step 2: Push + PR**

```bash
git push -u origin ux/audit-v2-fixes-2026-04-14
```

PR gegen `main` eröffnen. Titel: `ux: UX-Audit v2 Fixes (Phase 1–3, 11 von 16 Findings)`.

---

## Phase 4: Große Carry-Overs (C1, C2, C3) — separater Branch

Diese betreffen JS-Logik und sind risikoreicher. Neuen Branch dafür verwenden, damit Phase 1–3 unabhängig mergen können.

### Task 13: Branch wechseln

- [ ] **Step 1:**

```bash
git checkout main
git pull
git checkout -b ux/audit-v2-bulk-bar-and-polling
```

---

### Task 14: C2 — Row-Flash bei Dashboard-Polling-Änderungen

**Files:**
- Modify: `ticketsystem/static/js/dashboard_poll.js` (oder die Datei, die das 10s-Polling macht)
- Modify: `ticketsystem/static/css/style.css` (neue `.flash-updated`-Klasse)

- [ ] **Step 1: Polling-Datei finden**

```bash
grep -rn 'dashRefreshLabel\|setInterval.*dash\|poll' ticketsystem/static/js/ | head
```

- [ ] **Step 2: CSS-Flash-Klasse hinzufügen**

In `static/css/style.css` am Ende:

```css
/* Briefly highlight ticket rows whose content changed during live polling. */
.dash-table tr.flash-updated {
    animation: rowFlash 1.5s ease-out;
}
@keyframes rowFlash {
    0%   { background-color: var(--bs-warning-bg-subtle, #fff3cd); }
    100% { background-color: transparent; }
}
```

- [ ] **Step 3: Diff-Logik im Polling-Handler**

Im Polling-JS: nach dem Empfang der neuen `<tbody>`-Markup die existierenden Rows nach `data-ticket-id` diffen. Für jede Row, deren serialisierter Inhalt (`tr.outerHTML`) sich geändert hat, nach dem DOM-Swap die Klasse `flash-updated` setzen, nach 1500 ms entfernen:

```javascript
function flashChangedRows(oldTbody, newTbody) {
    var oldMap = {};
    oldTbody.querySelectorAll('tr[data-ticket-id]').forEach(function(tr) {
        oldMap[tr.dataset.ticketId] = tr.outerHTML;
    });
    newTbody.querySelectorAll('tr[data-ticket-id]').forEach(function(tr) {
        var prev = oldMap[tr.dataset.ticketId];
        if (prev && prev !== tr.outerHTML) {
            tr.classList.add('flash-updated');
            setTimeout(function() { tr.classList.remove('flash-updated'); }, 1500);
        }
    });
}
```

Die Funktion an der Stelle aufrufen, an der `tbody.innerHTML = …` passiert — nach dem Swap, mit einem Verweis auf den alten tbody (vorher klonen: `var oldClone = tbody.cloneNode(true);`).

- [ ] **Step 4: Test — Polling auslösen**

App starten, Dashboard offen. In einer zweiten Session ein Ticket-Feld ändern (z. B. Status). Nach ≤10 s blitzt die entsprechende Zeile im Dashboard gelb auf.

- [ ] **Step 5: Pytest**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add static/js/*.js static/css/style.css
git commit -m "ux: flash changed dashboard rows on live-poll updates

The dashboard polled every 10 s but updated rows silently. A short
animation now highlights rows whose content changed so triage operators
notice updates without having to compare manually.

Ref: UX-Audit v2 C2."
```

---

### Task 15: C3 — Bulk-Aktionen: DOM-Patch statt `location.reload()`

**Files:**
- Modify: `ticketsystem/static/js/bulk_actions.js` (oder Datei, die `bulkApplyBtn` etc. verdrahtet)
- Modify: `ticketsystem/templates/index.html:270-271` (sessionStorage-Flash ggf. entfernen, wenn nicht mehr nötig)

- [ ] **Step 1: Bulk-Handler finden**

```bash
grep -rn 'bulkApplyBtn\|location\.reload\|bulkAssignBtn' ticketsystem/static/js/ ticketsystem/templates/index.html
```

- [ ] **Step 2: Reload durch DOM-Patch ersetzen**

Im Bulk-Handler: Statt `location.reload()` die betroffenen `<tr data-ticket-id="…">` und ggf. die Kartendarstellung aktualisieren. Der Server gibt bereits JSON zurück — falls nicht, Response-Shape auf `{ success, updated: [{ id, status, priority, ... }] }` erweitern. Für jedes Ticket in `updated`: Row suchen, die geänderten Zellen (Status-Badge, Prio, Due-Date) neu rendern via kleiner Template-String-Helper. Danach `flashChangedRows`-Logik aus Task 14 wiederverwenden.

Falls der Umfang zu groß wird: Minimal-Variante — nach Bulk-Erfolg `fetch('?tab=…&q=…')` den neuen `<tbody>`-Markup holen (bestehender Polling-Endpunkt) und einsetzen, dann Flash. So bleibt die Logik zentral.

- [ ] **Step 3: Flash-Message**

Statt sessionStorage + Reload: direkt `window.showUiAlert('10 Tickets aktualisiert', 'success')` (bestehender Helper aus `base_ui.js`).

- [ ] **Step 4: Test**

Bulk-Status-Änderung auf 3 Tickets anwenden → Seite blitzt nicht weiß, Toast erscheint, die 3 Zeilen sind gelb hervorgehoben für 1.5 s.

- [ ] **Step 5: Pytest**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add static/js/ templates/index.html
git commit -m "ux: replace bulk-action location.reload with DOM patch + flash

Full page reload after bulk edits produced a ~500 ms white flash. We now
patch the rows in place and reuse the flash-updated animation from the
polling path. sessionStorage relay is removed.

Ref: UX-Audit v2 C3."
```

---

### Task 16: C1 — Bulk-Action-Bar Split-Button-Pattern

**Files:**
- Modify: `ticketsystem/templates/index.html:587-640` (Bulk-Bar-Block)
- Modify: `ticketsystem/static/js/bulk_actions.js` (Button-Handler → `<select>`-change-Handler)

- [ ] **Step 1: HTML auf Split-Button-Pattern umstellen**

In [index.html:587-640](templates/index.html#L587) die Struktur so ändern, dass jede Aktionsgruppe nur noch aus **einem** Element besteht (Select mit integriertem Action-Trigger). Konkretes Ziel: `<select>` feuert `change` → Aktion wird sofort angewandt (mit Confirm-Modal bei destruktiven Änderungen). Buttons `bulkApplyBtn`, `bulkAssignBtn`, `bulkSetPriorityBtn` entfallen.

```jinja
<div id="bulkActionBar" class="d-none position-fixed bottom-0 start-50 translate-middle-x mb-4 bg-dark text-white rounded-4 shadow-lg px-4 py-3 align-items-center gap-2 flex-wrap bulk-action-bar">
    <span id="bulkCount" class="fw-bold small me-1">0 ausgewählt</span>
    <div class="vr bg-secondary opacity-50 mx-1"></div>

    <select id="bulkStatusSelect" data-bulk-action="status"
            class="form-select form-select-sm bg-dark text-white border-secondary rounded-pill toast-btn">
        <option value="" disabled selected>Status ändern…</option>
        <option value="offen">Offen</option>
        <option value="in_bearbeitung">In Bearbeitung</option>
        <option value="wartet">Wartet</option>
        <option value="erledigt">Erledigt</option>
    </select>

    <select id="bulkAssignSelect" data-bulk-action="assign"
            class="form-select form-select-sm bg-dark text-white border-secondary rounded-pill toast-btn">
        <option value="" disabled selected>Zuweisen…</option>
        <option value="none">— Keine —</option>
        {% for w in workers %}
        <option value="{{ w.id }}">{{ w.name }}</option>
        {% endfor %}
        {% if teams %}
        <optgroup label="Teams">
            {% for t in teams %}
            <option value="team_{{ t.id }}">{{ t.name }}</option>
            {% endfor %}
        </optgroup>
        {% endif %}
    </select>

    <select id="bulkPrioritySelect" data-bulk-action="priority"
            class="form-select form-select-sm bg-dark text-white border-secondary rounded-pill toast-btn">
        <option value="" disabled selected>Priorität…</option>
        <option value="1">Hoch</option>
        <option value="2">Mittel</option>
        <option value="3">Niedrig</option>
    </select>

    <input type="date" id="bulkDueDateInput" data-bulk-action="due_date"
           class="form-control form-control-sm bg-dark text-white border-secondary rounded-pill toast-btn color-scheme-dark"
           title="Fälligkeitsdatum setzen">
    {# Restliche Bar (Löschen-Button, Cancel) bleibt bestehen #}
```

Destruktive Aktionen (Delete) bleiben als Button — nicht automatisch auf Change auslösen.

- [ ] **Step 2: JS-Handler umstellen**

Im Bulk-JS:

```javascript
document.querySelectorAll('#bulkActionBar [data-bulk-action]').forEach(function(el) {
    var evt = el.tagName === 'SELECT' ? 'change' : 'input';
    el.addEventListener(evt, function() {
        if (!el.value) return;
        applyBulkAction(el.dataset.bulkAction, el.value);
        el.value = '';  // reset so gleiches Ziel erneut triggern kann
    });
});
```

`applyBulkAction(action, value)` kapselt die bisherige Einzel-Button-Logik und nutzt die DOM-Patch-Funktion aus Task 15.

- [ ] **Step 3: Pytest + Manual**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
```

Manuell: Bulk-Modus aktivieren, 3 Tickets wählen, Status-Dropdown auf „Erledigt" → sofortige Aktion + Toast + Row-Flash.

- [ ] **Step 4: Commit**

```bash
git add templates/index.html static/js/
git commit -m "ux: bulk-action bar uses split-button pattern (change triggers action)

Reduces the bulk toolbar from ~10 controls in one line (3× select+button
pairs + date + delete + cancel) to 4 inputs. Select/change fires the
action directly; only destructive delete keeps a separate button.

Ref: UX-Audit v2 C1."
```

---

### Task 17: Phase 4 Merge

- [ ] **Step 1: Baseline final prüfen**

```bash
python -m pytest tests/ -v 2>&1 | tail -5
python -m flake8 --max-line-length=120 *.py routes/ services/
python -c "from app import app; print('import ok')"
```

- [ ] **Step 2: Push + PR**

```bash
git push -u origin ux/audit-v2-bulk-bar-and-polling
```

PR-Titel: `ux: UX-Audit v2 Fixes (Phase 4 — Bulk-Bar + Row-Flash + DOM-Patch)`.

---

## Abschluss: Re-Score

### Task 18: Audit-Re-Score

**Files:**
- Modify: `ticketsystem/UX_AUDIT_2026-04-14_v2.md` (Abschluss-Abschnitt)

- [ ] **Step 1: Findings-Tabellen in v2 abhaken**

Jedes umgesetzte Finding in [UX_AUDIT_2026-04-14_v2.md](UX_AUDIT_2026-04-14_v2.md) mit einem `✅` in der ersten Spalte markieren und in Abschnitt 1 (Executive Summary) den neuen Score eintragen.

- [ ] **Step 2: Commit**

```bash
git add UX_AUDIT_2026-04-14_v2.md
git commit -m "docs: mark UX-Audit v2 findings as resolved; re-score"
```

---

## Self-Review

**Spec coverage:**
- N1 → Task 1 ✅
- N2 → Task 2 ✅
- N3 → Task 8 ✅
- N4 → Task 6 ✅
- N5 → Task 7 ✅
- N6 → Task 7 ✅
- N7 → Task 3 ✅
- N8 (Login-Chip-Filter) → **nicht adressiert** (Sev 1, bewusst out-of-scope — benötigt Interaktionsdesign)
- N9 → Task 4 ✅
- N10 → Task 5 ✅
- C1 → Task 16 ✅
- C2 → Task 14 ✅
- C3 → Task 15 ✅
- C4 → Task 9 ✅
- C5 → Task 10 ✅
- C6 → Task 11 ✅

**N8 offen dokumentieren:** Als „Future Work" im Re-Score-Kommentar festhalten.

**Type consistency:** `priority_color` (Task 1) wird nur in `approvals.html` benutzt — Folge-Refactor für andere Templates ist explizit als Nicht-Teil markiert, damit der initiale Commit klein bleibt.

**Placeholder scan:** Keine TBDs. JS-Stellen in Task 14–16 verweisen auf konkrete Funktionsnamen (`flashChangedRows`, `openCollapsesWithDirtyFields`, `applyBulkAction`).

---

## Execution Handoff

Plan gespeichert unter `ticketsystem/UX_AUDIT_2026-04-14_v2_PLAN.md`. Zwei Ausführungsoptionen:

1. **Subagent-Driven (empfohlen)** — Fresh Subagent pro Task, Review dazwischen, schnelle Iteration.
2. **Inline Execution** — Tasks in dieser Session mit executing-plans durchgehen, Batch mit Checkpoints.

Welcher Ansatz?
