# UX-Audit 10/10 — Phase 4: Workflow-Klarheit

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score 9.4 → **10.0** durch saubere Trennung des Freigabe-Workflows vom Status-Toggle und Entdeckbarkeit via Keyboard-Shortcuts.

**Architecture:** Template-Restrukturierung der Sidebar (neuer „Workflow"-Abschnitt); neues Utility `shortcuts.js` mit document-weitem Keydown-Listener; Help-Dialog als `<dialog>` mit Phase-2-Focus-Trap.

**Tech Stack:** Jinja2, vanilla JS.

**Spec:** [docs/superpowers/specs/2026-04-13-ux-audit-10-of-10-design.md](../specs/2026-04-13-ux-audit-10-of-10-design.md)
**Voraussetzung:** Phase 2 gemergt (nutzt `focus_trap.js`). Phase 1 + 3 empfohlen.

---

## File Structure

**Neu:**
- `ticketsystem/static/js/shortcuts.js` — Keyboard-Shortcut-Layer.
- `ticketsystem/templates/components/_shortcut_help.html` — Shortcut-Hilfe-Dialog + Tabelle.

**Geändert:**
- `ticketsystem/templates/components/_management_sidebar.html` — „Freigabe anfordern" aus Status-Gruppe heraus in eigenen Workflow-Abschnitt.
- `ticketsystem/templates/base.html` — `data-shortcuts-writable` am `<body>`; `shortcuts.js` einbinden; Shortcut-Hilfe-Dialog inkludieren.

---

## Task 1: „Freigabe anfordern" aus Status-Gruppe trennen

**Files:**
- Modify: `ticketsystem/templates/components/_management_sidebar.html:5-105`

- [ ] **Step 1: Aktuellen Status-Block identifizieren**

`_management_sidebar.html` Zeilen 5–31 enthalten die Status-Buttons (OFFEN/IN_BEARBEITUNG/WARTET/ERLEDIGT). Zeilen ~92–100 enthalten den Freigabe-Button. Verifizieren mit:

```bash
grep -n 'request-approval\|Freigabe\|status-btn' ticketsystem/templates/components/_management_sidebar.html
```

- [ ] **Step 2: Freigabe-Block aus Status-Gruppe entfernen**

Den bestehenden Freigabe-Button-Block (inklusive seiner Wrapper) aus seiner bisherigen Position löschen.

- [ ] **Step 3: Neuen Workflow-Abschnitt einfügen**

Nach der Status-Button-Gruppe (nach Zeile ~31), neuer Abschnitt:

```jinja
<section class="sidebar-section workflow-section" aria-labelledby="workflow-heading">
  <h6 id="workflow-heading" class="sidebar-section-title">Workflow</h6>
  {% if ticket.approval and ticket.approval.status %}
    {% set astatus = ticket.approval.status %}
    <a href="#approval-section" class="badge
        {% if astatus == 'approved' %}bg-success
        {% elif astatus == 'rejected' %}bg-danger
        {% else %}bg-warning text-dark{% endif %}"
       aria-label="Freigabe-Status: {{ astatus|title }} (zum Abschnitt springen)">
      Freigabe: {{ astatus|title }}
    </a>
    {% if astatus == 'rejected' and session.get('role') != 'viewer' %}
      <button type="button" class="btn btn-sm btn-outline-primary mt-2 request-approval-btn"
              data-ticket-id="{{ ticket.id }}">
        Erneut anfordern
      </button>
    {% endif %}
  {% elif session.get('role') != 'viewer' %}
    <button type="button" class="btn btn-outline-primary w-100 request-approval-btn"
            data-ticket-id="{{ ticket.id }}"
            aria-label="Freigabe für dieses Ticket anfordern">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align:-.15em; margin-right:.25em">
        <path d="M12.854 2.146a.5.5 0 0 0-.707 0L3 11.293V13h1.707l9.147-9.146a.5.5 0 0 0 0-.708l-1-1z"/>
      </svg>
      Freigabe anfordern
    </button>
  {% endif %}
</section>
```

Optional CSS für `.workflow-section` in `style.css`:

```css
.workflow-section {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--bs-border-color, #dee2e6);
}
.workflow-section .sidebar-section-title {
    font-size: .75rem;
    text-transform: uppercase;
    letter-spacing: .05em;
    color: var(--bs-secondary-color, #6c757d);
    margin-bottom: .5rem;
}
```

- [ ] **Step 4: Visuell & funktional testen**

1. Ticket ohne Freigabe-Status: Status-Buttons oben, darunter getrennter „Workflow"-Abschnitt mit „Freigabe anfordern" als outline-primary Button.
2. Ticket mit PENDING-Approval: Badge „Freigabe: Pending" als Link zum Approval-Abschnitt.
3. Ticket mit APPROVED: Grünes Badge.
4. Ticket mit REJECTED: Rotes Badge + darunter „Erneut anfordern"-Button (nur für Editor+).
5. Viewer-Rolle sieht nur Badges, keine Buttons.

- [ ] **Step 5: Commit**

```bash
git add templates/components/_management_sidebar.html static/css/style.css
git commit -m "feat(ui): separate approval workflow from status button group"
```

---

## Task 2: `<body>` bekommt `data-shortcuts-writable`

**Files:**
- Modify: `ticketsystem/templates/base.html`

- [ ] **Step 1: `<body>`-Tag erweitern**

Das bestehende `<body ...>`-Tag in `base.html` erweitern:

```html
<body data-shortcuts-writable="{{ 'true' if session.get('role') and session.get('role') != 'viewer' else 'false' }}">
```

Falls bereits andere `data-*` Attribute am Body hängen, diese beibehalten.

- [ ] **Step 2: Smoke-Test**

Dev-Server, eingeloggt als Editor → DevTools → `<body data-shortcuts-writable="true">`. Als Viewer → `"false"`. Nicht eingeloggt → `"false"`.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat(ui): body carries data-shortcuts-writable for keyboard layer"
```

---

## Task 3: Shortcut-Hilfe-Dialog-Template

**Files:**
- Create: `ticketsystem/templates/components/_shortcut_help.html`
- Modify: `ticketsystem/templates/base.html`

- [ ] **Step 1: Dialog-Template anlegen**

`templates/components/_shortcut_help.html`:

```html
<dialog id="shortcutHelpDialog" aria-labelledby="shortcutHelpTitle">
  <form method="dialog">
    <header class="d-flex justify-content-between align-items-center mb-3">
      <h2 id="shortcutHelpTitle" class="h5 mb-0">Tastatur-Shortcuts</h2>
      <button type="submit" class="btn-close" aria-label="Schließen"></button>
    </header>
    <table class="table table-sm">
      <thead>
        <tr><th scope="col">Taste</th><th scope="col">Aktion</th></tr>
      </thead>
      <tbody>
        <tr><td><kbd>n</kbd></td><td>Neues Ticket erstellen</td></tr>
        <tr><td><kbd>/</kbd></td><td>Dashboard-Suche fokussieren</td></tr>
        <tr><td><kbd>?</kbd></td><td>Diese Hilfe öffnen</td></tr>
        <tr><td><kbd>Esc</kbd></td><td>Dialog schließen</td></tr>
      </tbody>
    </table>
    <p class="text-muted small mb-0">
      Shortcuts sind in Eingabefeldern deaktiviert. <kbd>n</kbd> nur mit Schreibberechtigung.
    </p>
  </form>
</dialog>
```

- [ ] **Step 2: Dialog in base.html inkludieren**

Kurz vor `</body>` in `base.html`:

```jinja
{% include "components/_shortcut_help.html" %}
```

- [ ] **Step 3: Commit**

```bash
git add templates/components/_shortcut_help.html templates/base.html
git commit -m "feat(ui): shortcut help dialog template"
```

---

## Task 4: `shortcuts.js` — Keyboard-Layer

**Files:**
- Create: `ticketsystem/static/js/shortcuts.js`
- Modify: `ticketsystem/templates/base.html` (Script-Tag)

- [ ] **Step 1: Shortcut-Handler implementieren**

Neue Datei `static/js/shortcuts.js`:

```javascript
// Minimal keyboard shortcut layer.
// Keys: n (new ticket), / (focus search), ? (help dialog).
// Disabled when a text input has focus.

(function () {
    'use strict';

    function isTypingTarget(el) {
        if (!el) return false;
        const tag = el.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
        if (el.isContentEditable) return true;
        return false;
    }

    function openHelp() {
        const dlg = document.getElementById('shortcutHelpDialog');
        if (!dlg) return;
        if (typeof dlg.showModal === 'function') {
            dlg.showModal();
            if (typeof window.trapFocus === 'function') window.trapFocus(dlg);
            dlg.addEventListener('close', () => {
                if (typeof window.releaseFocus === 'function') window.releaseFocus();
            }, { once: true });
        }
    }

    document.addEventListener('keydown', (ev) => {
        if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
        if (isTypingTarget(document.activeElement)) return;

        if (ev.key === 'n') {
            if (document.body.dataset.shortcutsWritable !== 'true') return;
            ev.preventDefault();
            // Use a data-attribute on <body> for the new-ticket URL to avoid hardcoding ingress paths.
            const url = document.body.dataset.newTicketUrl || '/tickets/new';
            window.location.href = url;
        } else if (ev.key === '/') {
            const search = document.getElementById('dashSearch') || document.getElementById('global-search');
            if (search) {
                ev.preventDefault();
                search.focus();
                search.select?.();
            }
        } else if (ev.key === '?') {
            ev.preventDefault();
            openHelp();
        }
    });
})();
```

- [ ] **Step 2: `data-new-ticket-url` am Body setzen**

In `base.html` den `<body>`-Tag weiter ergänzen:

```html
<body data-shortcuts-writable="{{ 'true' if session.get('role') and session.get('role') != 'viewer' else 'false' }}"
      data-new-ticket-url="{{ url_for('main.new_ticket_view') }}">
```

Den Endpoint-Namen via `grep -rn 'def.*new_ticket\|@.*route.*tickets/new' ticketsystem/routes/` bestätigen und ggf. anpassen.

- [ ] **Step 3: Script einbinden**

In `base.html` vor `</body>`:

```html
<script src="{{ url_for('static', filename='js/shortcuts.js') }}"></script>
```

- [ ] **Step 4: Manuell testen**

1. Dashboard öffnen, `n` drücken → Redirect zu Neues-Ticket-Form. Als Viewer: kein Redirect.
2. Dashboard offenes Search-Feld → `/` drücken → Focus springt ins Such-Feld. Innerhalb des Feldes `/` nochmal tippen → `/` erscheint im Feld (keine Shortcut-Wiederholung).
3. Beliebige Seite, `?` drücken → Hilfe-Dialog öffnet sich, Focus-Trap aktiv. `Esc` schließt.
4. Kommentar-Textarea fokussieren, `n`/`/`/`?` tippen → erscheint als Text, kein Shortcut.

- [ ] **Step 5: Commit**

```bash
git add static/js/shortcuts.js templates/base.html
git commit -m "feat(ui): minimal keyboard shortcuts n / ?"
```

---

## Task 5: Help-Icon-Hint auf Shortcuts

**Files:**
- Modify: `ticketsystem/templates/base.html` (Help-Icon-Tooltip)

- [ ] **Step 1: Tooltip erweitern**

Das bestehende Help-Icon im Header (mit Offcanvas-Toggle) bekommt Hinweis im Tooltip oder Aria-Label:

```html
<button class="btn btn-link" type="button" aria-label="Hilfe (Shortcuts: ?)"
        data-bs-toggle="offcanvas" data-bs-target="#helpOffcanvas">
  <i class="bi bi-question-circle"></i>
</button>
```

- [ ] **Step 2: Shortcuts-Abschnitt im Help-Offcanvas**

Im Help-Offcanvas-Template (suchen mit `grep -rn 'helpOffcanvas' templates/`) neuen Abschnitt ergänzen:

```html
<section class="mb-3">
  <h6>Tastatur-Shortcuts</h6>
  <dl class="small mb-0">
    <div><dt class="d-inline"><kbd>n</kbd></dt> <dd class="d-inline">Neues Ticket</dd></div>
    <div><dt class="d-inline"><kbd>/</kbd></dt> <dd class="d-inline">Suche fokussieren</dd></div>
    <div><dt class="d-inline"><kbd>?</kbd></dt> <dd class="d-inline">Shortcut-Hilfe</dd></div>
  </dl>
</section>
```

- [ ] **Step 3: Commit**

```bash
git add templates/base.html templates/components/_help_offcanvas.html
git commit -m "feat(ui): surface shortcuts in help icon tooltip and offcanvas"
```

Falls das Help-Offcanvas in einem anderen Pfad liegt, den Pfad anpassen.

---

## Task 6: Final Verification + UX-Audit-Re-Score

- [ ] **Step 1: Baseline-Tests**

```bash
cd ticketsystem && python -m pytest tests/ -v
```
Erwartet: Tests aus Phase 1 + 2 + Baseline, keine neuen Failures.

- [ ] **Step 2: Lint**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```

- [ ] **Step 3: Vollständiger UX-Test-Pfad (alle Phasen)**

1. **Phase 1:** Ticket-Delete → Undo-Toast → Restore funktioniert. Chevron rotiert. Flash-Dauern korrekt. Dashboard-Count sichtbar. Refresh-Label zählt hoch. Empty-States haben CTAs.
2. **Phase 2:** Focus-Trap in 3 Modals funktioniert. 5 Forms zeigen Inline-Field-Fehler. Priority-Badges haben Icon + Farbe.
3. **Phase 3:** iPhone SE zeigt Cards. iPad zeigt Tabelle mit reduzierten Spalten. Desktop unverändert.
4. **Phase 4:** Sidebar hat separaten Workflow-Abschnitt. `n`, `/`, `?` funktionieren. `?`-Hilfe zeigt Shortcut-Tabelle.

- [ ] **Step 4: UX-Audit-Re-Score**

Neuer Audit-Run gegen `docs/ux-audit-2026-04-13.md`. Für jeden Finding prüfen, ob behoben:

| # Finding | Behoben? |
|---|---|
| 1 Kein Undo | ✅ Phase 1 Task 3+4 |
| 2 Keine Inline-Validation | ✅ Phase 2 Task 5+6 |
| 3 Dashboard-Tabelle auf Tablet | ✅ Phase 3 Task 3 |
| 4 Modal-Focus nicht getrappt | ✅ Phase 2 Task 3+4 |
| 5 „Wartet" ambig | ❌ bewusst ausgeklammert — **Abweichung 10/10** |
| 6 Keine Sucherfolg-Rückmeldung | ✅ Phase 1 Task 6 |
| 7 Collapse-Chevron ohne Rotation | ✅ Phase 1 Task 5 |
| 8 Keine „Aktualisiert vor X s" | ✅ Phase 1 Task 7 |
| 9 Keine Keyboard-Shortcuts | ✅ Phase 4 Task 4 |
| 10 Passive Empty States | ✅ Phase 1 Task 8 |

**Hinweis:** Finding #5 „Wartet"-Substates wurde bewusst ausgeklammert (siehe Spec §2 + §5). Ohne diesen Punkt wird der max. Score realistisch **9.5–9.8/10**, nicht exakt 10/10. Falls 10/10 strikt gefordert ist, Finding #5 als eigenes Spec nachziehen (eigene Brainstorming-/Planungs-Runde).

- [ ] **Step 5: Neues Audit-Dokument**

Neuen Audit-Score in `docs/ux-audit-2026-04-13-rescore.md` dokumentieren mit Ist-Score, Vergleich zu vorherigem und verbleibenden Punkten.

- [ ] **Step 6: Phase-4-Tag**

```bash
git tag ux-phase-4-complete
git tag ux-audit-10-of-10-roadmap-complete
```
