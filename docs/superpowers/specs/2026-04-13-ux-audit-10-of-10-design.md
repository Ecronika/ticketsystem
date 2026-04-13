# Design-Spec — UX-Audit 10/10 Roadmap

**Datum:** 2026-04-13
**Basis:** [docs/ux-audit-2026-04-13.md](../../ux-audit-2026-04-13.md) (Score 7.2/10)
**Ziel:** UX-Audit-Score **10/10** auf allen Krug-Gesetzen und Nielsen-Heuristiken.
**Scope:** 4 Phasen, jede einzeln mergbar und deploybar. Keine DB-Migrationen.

---

## 1. Hintergrund

Das UX-Audit vom 2026-04-13 identifiziert 10 priorisierte Findings (Severity 1–4), von denen der fehlende Undo-Mechanismus (Severity 4) und fehlende Inline-Field-Validation (Severity 3) die kritischsten sind. Dieser Spec decomposed die Arbeit in vier thematisch gebündelte Phasen. Jede Phase hebt den Score messbar, ist separat review- und deploybar, und hat keine langlebigen Feature-Branch-Abhängigkeiten.

Ein ursprünglich geplanter Scope-Punkt — die Präzisierung des Status „Wartet" über Substates oder Freitextfeld — wurde auf Wunsch des Product Owners ausgeklammert und kann später als eigener Spec nachgezogen werden.

## 2. Erfolgskriterien (projektübergreifend)

- Baseline-Tests bleiben grün: `cd ticketsystem && python -m pytest tests/ -v` → 7 passed, 8 pre-existing failures. Keine neuen Failures.
- Flake8-clean: `python -m flake8 --max-line-length=120 *.py routes/ services/`.
- Keine Dockerfile-Änderung nötig (keine neuen Top-Level-`.py`-Dateien geplant).
- Re-Audit nach Phase 4 erreicht 10/10.

## 3. Architektur-Entscheidungen

### 3.1 Undo für Soft-Delete
**Entscheidung:** Direkt-Endpoint (Option A). Flash-Toast zeigt „Ticket gelöscht · Rückgängig" für 8 s. Re-use des existierenden Restore-Pfads aus dem Admin-Trash. Falls kein dedizierter Endpoint existiert, wird `POST /tickets/<id>/restore` in `routes/ticket_views.py` neu angelegt und delegiert an `TicketCoreService.restore_ticket` (mit `@db_transaction`).

**Verworfen:** Zeit-Token-Lösung (Komplexität ohne Mehrwert), Client-seitige Verzögerung (nicht netzwerk-robust).

### 3.2 Inline-Field-Validation
**Entscheidung:** Minimal-Custom-JS (Option A), ~150 LOC, vanilla. Kein Framework, kein Build-Step.

**Protokoll Server→Client für Field-Errors:**
- `DomainError` in `exceptions.py` bekommt optionales Attribut `field: Optional[str] = None`.
- `@api_endpoint` Decorator rendert bei `DomainError` mit `field`: `{"error": msg, "errors": [{"field": "...", "message": "..."}]}` mit passendem HTTP-Status.
- Service-Validation, die feldgebunden ist, wirft `DomainError(msg, field="email")` statt feldlos.

**Opt-in per Form:** `<form data-validate>` aktiviert den Renderer. Phase-2-Scope: 5 Forms (Ticket-neu, Kommentar, Worker-anlegen, Assign, Approval-Reject). Weitere Migration als Tech-Debt.

**Verworfen:** Just-validate / Parsley (neue Dependency), HTMX (Umbau zu groß, nicht im Projekt-Stil).

### 3.3 Mobile-Layout
**Entscheidung:** Hard-Breakpoint bei 900 px (Option A), Shared-Macro-Ansatz.

- **< 900 px**: Card-Layout via `render_ticket_card(ticket)` Macro.
- **900–1200 px**: Tabelle mit reduzierten Spalten (`hide-on-tablet`-CSS-Klasse auf Kontakt + Team).
- **≥ 1200 px**: Aktueller Zustand unverändert.

Das Row-/Card-Macro wird in eine gemeinsame Template-Datei extrahiert und von Dashboard + My-Queue konsumiert.

**Verworfen:** Reine Column-Priorisierung (Tabelle bleibt gequetscht < 600 px), Hybrid mit zusätzlicher Card-Stufe < 600 px (Overhead für seltenen Use-Case).

### 3.4 Focus-Management
**Entscheidung:** Eigene `focus_trap.js`-Utility (~80 LOC), exportiert `trapFocus(dialogEl)` / `releaseFocus()`. Anwendungsart **explizit per Dialog-Open-Handler** statt Monkey-Patch auf `HTMLDialogElement.prototype.showModal` — macht Refactor-sicher und debugbar.

Angewendet auf:
- Confirm-Modal (`base_ui.js` → `showConfirm`)
- Reject-Approval-Modal ([ticket_detail.html:38-58](../../../ticketsystem/templates/ticket_detail.html#L38-L58))
- Lightbox ([_ticket_header.html:167-200](../../../ticketsystem/templates/_ticket_header.html#L167-L200))
- Shortcut-Hilfe-Overlay (Phase 4)

### 3.5 Keyboard-Shortcuts
**Entscheidung:** Minimal-Set (Option A): `n`, `/`, `?`. Zentraler Listener am `document`, inaktiv bei fokussiertem Input/Textarea/Select/contenteditable.

`n` ist konditioniert an Write-Berechtigung — Server rendert `data-shortcuts-writable="true"` am `<body>`-Element, Shortcut-Handler liest das vor Ausführung.

Das `?`-Overlay ist ein `<dialog>` mit Shortcut-Tabelle und nutzt die Focus-Trap-Utility aus Phase 2. **Hart-Abhängigkeit: Phase 2 muss vor Phase 4 gemergt sein.**

**Verworfen für jetzt:** Erweiterte Navigation (`j`/`k`/`g d`) und Command-Palette (`Cmd+K`) — zu groß für initialen Wurf, Zielgruppe benötigt eher Entdeckbarkeit als Power-Features.

### 3.6 „Freigabe anfordern" Trennung
**Entscheidung:** Aus Status-Button-Gruppe heraus, eigener Abschnitt „Workflow" in der Sidebar. Andere Button-Variante (`btn-outline-primary`) signalisiert anderen Kontext. Bei existierendem Freigabe-Status (`PENDING`/`APPROVED`/`REJECTED`) wird der Button zur Badge mit Rück-Link.

## 4. Phasen-Breakdown

### Phase 1 — Quick Wins

**Score-Ziel:** 7.2 → 8.0
**Dauer:** 1–2 Tage
**DB:** keine

**Deliverables:**
1. Undo-Toast für Soft-Delete
   - Flash-Payload um `undo_action: {url, method, label}` erweitern (Helper in `services/_helpers.py` oder gleichwertige bestehende Stelle).
   - `base_ui.js` rendert Undo-Button im Toast, macht `fetch(url, {method, headers: {CSRF}})` und zeigt Follow-Up-Toast.
   - Vor Implementation: Verifizieren, ob `POST /tickets/<id>/restore` existiert. Falls nein, anlegen (~30 LOC Route + Service-Methode mit `@db_transaction`).
2. Chevron-Rotation CSS
   - Globale Rule in `static/css/style.css`: `[aria-expanded="true"] > .chevron { transform: rotate(180deg); transition: transform .15s ease; }`.
   - Alle Collapse-Trigger bekommen `.chevron`-Klasse auf ihrem Icon.
3. Flash-Dauer-Tuning
   - `base.html` Alert-Init: 12 s → 6 s Default, 8 s bei Link (statt 12 s).
4. Ergebnis-Count Dashboard-Suche
   - Jinja rendert `<span role="status" aria-live="polite" data-test="search-count">{{ count }} Tickets</span>` neben Suchfeld in [index.html:406-416](../../../ticketsystem/templates/index.html#L406-L416).
5. „Aktualisiert vor X s"-Label
   - Kleines `<span data-last-refresh>` im Dashboard-Header. Polling-Funktion setzt `dataset.refreshedAt = Date.now()`, ein zweiter 1-s-Interval rendert relative Zeit.
6. Action-orientierte Empty States
   - [approvals.html:18-20](../../../ticketsystem/templates/approvals.html#L18-L20): „+ Neue Freigabe-Anfrage starten"-Hint? Nein — Approvals werden von Tickets aus erstellt. Stattdessen: Link zu Dashboard „Zum Dashboard".
   - [projects.html:22-26](../../../ticketsystem/templates/projects.html#L22-L26): „+ Neues Ticket anlegen"-Button.
   - [_ticket_checklists.html:132](../../../ticketsystem/templates/_ticket_checklists.html#L132): „+ Unteraufgabe hinzufügen"-Fokus auf bereits existierendes Add-Formular via Scroll-Ankerlink.
   - `_comment_history.html:25`: „Ersten Kommentar verfassen" fokussiert die Kommentar-Textarea.

**Definition of Done:**
- Alle 6 Items umgesetzt.
- Manueller Smoke-Test: Ticket löschen → Toast erscheint mit Undo → Klick stellt wieder her.
- Baseline-Tests grün.

---

### Phase 2 — Accessibility & Feedback

**Score-Ziel:** 8.0 → 8.8
**Dauer:** 2–3 Tage
**DB:** keine

**Deliverables:**
1. `static/js/focus_trap.js` (~80 LOC)
   - API: `trapFocus(dialogEl)`, `releaseFocus()`.
   - Selektor für fokussierbare Elemente: `'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'`.
   - Speichert vorherigen Focus, restored on release.
   - Tab/Shift+Tab cycled, Escape triggert `dialog.close()` + `releaseFocus()`.
2. Anwendung in allen bestehenden Dialogen
   - `base_ui.js` `showConfirm`: Aufruf bei Open, Release bei Close.
   - [ticket_detail.html:38-58](../../../ticketsystem/templates/ticket_detail.html#L38-L58) Reject-Modal.
   - [_ticket_header.html:167-200](../../../ticketsystem/templates/_ticket_header.html#L167-L200) Lightbox.
3. `exceptions.py` Erweiterung
   - `DomainError.__init__(self, message, field: Optional[str] = None)`.
4. `@api_endpoint` Decorator-Erweiterung
   - Bei `DomainError` mit `field`: JSON-Response `{"error": msg, "errors": [{"field": field, "message": msg}]}`.
5. `static/js/form_validate.js` (~150 LOC)
   - Opt-in: `<form data-validate>`.
   - `onblur`-Handler liest `input.validity`, rendert Fehler in `<div class="field-error" id="<inputId>-error" role="alert">` direkt nach dem Input-Element, setzt `aria-describedby`/`aria-invalid`.
   - `oninput`-Handler entfernt Fehler, sobald `input.validity.valid`.
   - Submit-Handler: Verhindert Submit bei ungültigem Form, fokussiert ersten Fehler.
   - Fetch-Wrapper: Bei JSON-Response mit `errors[]` → rendert Server-Errors ins selbe Container-Pattern.
6. Migration der 5 priorisierten Forms auf `data-validate`
   - Ticket-neu ([ticket_new.html](../../../ticketsystem/templates/ticket_new.html))
   - Kommentar-Form (`_comment_form.html`)
   - Worker-anlegen (`workers.html`)
   - Assign-Modal
   - Approval-Reject-Modal
7. Priority-Icons
   - CSS-only: `.priority-{low,mid,high,urgent}::before` mit Inline-SVG-Icons (data-URI).
   - Icons: `minus` (low), `equals` (mid), `arrow-up` (high), `double-arrow-up` (urgent).
   - Anwendung in Dashboard-Priority-Cell und My-Queue-Border.

**Definition of Done:**
- Screenreader-Test (NVDA oder macOS VoiceOver) auf 3 Modals: Fokus bleibt im Dialog, Escape released korrekt.
- Alle 5 priorisierten Forms zeigen Feld-Fehler ohne Reload beim Submit ungültiger Werte.
- Axe-DevTools-Scan auf Dashboard + Ticket-Detail: 0 Violations Severity „serious" oder „critical".
- Priority-Farbe funktioniert auch in Grayscale-Print-Vorschau (Icons erkennbar).
- Baseline-Tests grün.

---

### Phase 3 — Mobile & Dashboard

**Score-Ziel:** 8.8 → 9.4
**Dauer:** 1–2 Tage
**DB:** keine

**Deliverables:**
1. Shared-Macro-Extraktion
   - Neue Datei `templates/_ticket_item.html` mit Macros `render_ticket_row(ticket, selected)` und `render_ticket_card(ticket, selected)`.
   - Scope: Dashboard ([index.html](../../../ticketsystem/templates/index.html)). My-Queue bleibt unverändert (nutzt bereits Card-Layout mit Priority-Border).
2. Card-Layout CSS
   - `.ticket-card`: Titel (H3 fett) · Badge-Reihe (Status, Priority, Due) · Meta (Assignee-Avatar + Kontakt) · Action-Row (Checkbox, Overflow-Menü `⋯`).
   - Overflow-Menü: Bootstrap-Dropdown mit Status-Change, Assign, Delete.
3. Media-Query-Logic
   - `@media (max-width: 899px) { .ticket-table { display: none } .ticket-cards { display: flex; flex-direction: column; gap: .5rem } }`
   - `@media (min-width: 900px) { .ticket-cards { display: none } .ticket-table { display: table } }`
4. Tablet-Column-Priorisierung
   - `.hide-on-tablet { @media (max-width: 1199px) { display: none } }`.
   - Anwendung auf Kontakt-Spalte und Team-Spalte in Dashboard-Tabelle.
5. Sucherfolg ARIA-Live
   - Das Count-Element aus Phase 1 bekommt `aria-live="polite"`, Polling/Filter-Update setzt Text neu.

**Definition of Done:**
- Manueller Test auf Chromium DevTools-Device-Emulation:
  - iPhone SE (375×667): Card-Layout, keine Horizontal-Scrolls.
  - iPad (768×1024): Tabelle mit reduzierten Spalten, keine Horizontal-Scrolls.
  - Desktop (1440×900): Unverändert.
- Lighthouse-Mobile-Score ≥ 90 auf Dashboard.
- Baseline-Tests grün.

---

### Phase 4 — Workflow-Klarheit

**Score-Ziel:** 9.4 → 10.0
**Dauer:** 1–2 Tage
**DB:** keine
**Abhängigkeit:** Phase 2 (nutzt `focus_trap.js`)

**Deliverables:**
1. „Freigabe anfordern" aus Status-Gruppe trennen
   - In [_management_sidebar.html](../../../ticketsystem/templates/_management_sidebar.html): Status-Button-Gruppe endet nach „Erledigt". Darunter neuer Abschnitt:
     ```html
     <section class="sidebar-section">
       <h6>Workflow</h6>
       {% if ticket.approval and ticket.approval.status %}
         <a href="#approval-section" class="badge …">{{ approval_status_label }}</a>
       {% else %}
         <button class="btn btn-outline-primary" data-action="request-approval">
           <svg class="icon-signature">…</svg> Freigabe anfordern
         </button>
       {% endif %}
     </section>
     ```
2. `static/js/shortcuts.js` (~60 LOC)
   - Single listener auf `document`, `keydown`.
   - Guard: `if (document.activeElement.matches('input, textarea, select, [contenteditable="true"]')) return`.
   - `n`: prüft `document.body.dataset.shortcutsWritable === 'true'`, navigiert zu `/tickets/new`.
   - `/`: fokussiert `#global-search` falls vorhanden, preventDefault.
   - `?`: öffnet `<dialog id="shortcuts-help">` mit Shortcut-Tabelle, trapFocus, Escape schließt.
3. `<body>` Daten-Attribut
   - `base.html` rendert `data-shortcuts-writable="{{ 'true' if current_user.can_write else 'false' }}"` (oder was auch immer die bestehende Permission-API ist — im Plan konkret zu ermitteln).
4. Shortcut-Hilfe im Header-Help-Offcanvas
   - Bestehendes Help-Icon bekommt Tooltip „Shortcuts: `?`" als Hint.
   - Help-Offcanvas bekommt neuen Abschnitt „Tastatur-Shortcuts" mit der Tabelle.

**Definition of Done:**
- Manueller Test: Shortcuts funktionieren, keine Trigger in Input-Feldern.
- Self-Audit erreicht 10/10 auf allen Krug-Gesetzen und Nielsen-Heuristiken.
- Baseline-Tests grün.

## 5. Nicht-Scope

Explizit ausgeklammert:
- **Wartet-Substates** — auf Product-Owner-Wunsch ausgeklammert, eigener Spec falls später gewünscht.
- **Command-Palette / `Cmd+K`** — potenziell Phase 5, nicht jetzt.
- **Erweiterte Listen-Navigation** (`j`/`k`/`g d`) — zu Power-User-lastig für die Zielgruppe.
- **Formular-Migration außerhalb der Top-5** — als Tech-Debt-Items nachgezogen.
- **Dark-Mode-Überarbeitung** — bereits durch `data-theme="hc"` abgedeckt.
- **PWA / ServiceWorker-Änderungen** — aktueller Zustand ausreichend.

## 6. Offene Implementation-Details (im Plan zu klären)

- Existiert bereits ein Restore-Endpoint für Tickets? Falls ja → URL? Falls nein → Design in Phase-1-Plan.
- Konkrete Permission-API für `current_user.can_write` (oder äquivalent) — Template-seitige Variable in `base.html`.
- Konkrete Icons für Priority-Styles — SVG-Assets in `static/icons/` oder Inline-Data-URIs?

## 7. Risiken

| Risiko | Mitigation |
|---|---|
| Focus-Trap bricht bestehende Modal-Interaktionen | Explizite Aktivierung pro Dialog, nicht global. Manueller Smoke-Test jedes Dialogs. |
| Inline-Validation-Renderer kollidiert mit Server-Flash | `data-validate`-Opt-in, Flash bleibt als Fallback. Beide zeigen dieselben Fehler nur an unterschiedlichen Orten (Feld vs. Toast). |
| Card-Layout verdeckt Aktionen hinter Overflow-Menü | Wichtigste Aktionen (Select, Status) direkt auf Card, nur sekundäre im `⋯`. |
| Shortcut `/` kollidiert mit Browser-Quick-Find | `preventDefault` nur wenn Suchfeld vorhanden; sonst Browser-Default weiterleiten. |

## 8. Roadmap-Zusammenfassung

| Phase | Score | Dauer | DB | Haupt-Artefakte |
|---|---|---|---|---|
| 1 Quick Wins | 8.0 | 1–2 T | ❌ | Undo-Toast, Chevron-CSS, Flash-Tuning, Count, Refresh-Label, Empty-State-CTAs |
| 2 A11y & Feedback | 8.8 | 2–3 T | ❌ | `focus_trap.js`, `form_validate.js`, `DomainError.field`, Priority-Icons |
| 3 Mobile & Dashboard | 9.4 | 1–2 T | ❌ | `_ticket_item.html` Macro, Card-Layout, Tablet-Column-Hide |
| 4 Workflow | **10.0** | 1–2 T | ❌ | Workflow-Trennung, `shortcuts.js`, Help-Offcanvas-Erweiterung |

**Gesamt:** 5–9 Entwicklungstage, 4 einzeln mergbare Phasen, keine DB-Migrationen.
