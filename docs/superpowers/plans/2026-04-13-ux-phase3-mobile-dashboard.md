# UX-Audit 10/10 — Phase 3: Mobile & Dashboard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score 8.8 → 9.4 durch Card-Layout für Dashboard unter 900 px und Column-Priorisierung auf Tablets.

**Architecture:** Shared-Macro `_ticket_item.html` rendert sowohl `<tr>` als auch `<article class="ticket-card">`. CSS-Media-Queries entscheiden, welches sichtbar ist. Keine DB-Änderungen, keine Service-Änderungen.

**Tech Stack:** Jinja2, CSS3, Bootstrap 5.

**Spec:** [docs/superpowers/specs/2026-04-13-ux-audit-10-of-10-design.md](../specs/2026-04-13-ux-audit-10-of-10-design.md)
**Voraussetzung:** Phase 1 + 2 gemergt (Phase 2 nicht hart erforderlich, aber Tests laufen damit gegen aktuellen Stand).

---

## File Structure

**Neu:**
- `ticketsystem/templates/components/_ticket_item.html` — zwei Macros: `render_ticket_row(ticket, selected)` und `render_ticket_card(ticket, selected)`.

**Geändert:**
- `ticketsystem/templates/index.html` — importiert + nutzt das Macro, rendert beide Blöcke (Tabelle + Card-Liste).
- `ticketsystem/static/css/style.css` — Card-Layout, Media-Queries, `.hide-on-tablet`.

---

## Task 1: Macro-Datei anlegen

**Files:**
- Create: `ticketsystem/templates/components/_ticket_item.html`

- [ ] **Step 1: Ist-Zustand der Row in `index.html` analysieren**

`grep -n '<tr' ticketsystem/templates/index.html` und die Schleife `{% for ticket in tickets %}` finden (~Zeile 468+). Notieren: welche Zellen (Checkbox, ID, Titel, Status-Dropdown, Priority, Assignee, Due, Actions) und welche Daten-Attribute.

- [ ] **Step 2: Row-Macro extrahieren**

Neue Datei `templates/components/_ticket_item.html` mit zwei Macros. Zuerst `render_ticket_row`, exakt 1:1-Kopie der bestehenden `<tr>`-Zeile aus `index.html`, Parameter `ticket` und `selected`:

```jinja
{% macro render_ticket_row(ticket, selected=False) %}
<tr data-ticket-id="{{ ticket.id }}" class="{% if selected %}table-active{% endif %}">
  <td><input type="checkbox" class="bulk-select" value="{{ ticket.id }}" aria-label="Ticket {{ ticket.id }} auswählen"></td>
  <td>{{ ticket.id }}</td>
  <td><a href="{{ url_for('main.ticket_detail', ticket_id=ticket.id) }}">{{ ticket.title }}</a></td>
  {# ... restliche Zellen aus index.html 1:1 übernehmen #}
</tr>
{% endmacro %}
```

**Wichtig:** Exakte Zell-Struktur aus `index.html` übernehmen, nichts umbauen. Ziel in dieser Task ist rein das Extrahieren.

- [ ] **Step 3: Card-Macro ergänzen**

Im selben Macro-File:

```jinja
{% macro render_ticket_card(ticket, selected=False) %}
<article class="ticket-card {% if selected %}selected{% endif %}"
         data-ticket-id="{{ ticket.id }}"
         data-priority="{{ ticket.priority.value if ticket.priority else 'mittel' }}">
  <header class="ticket-card-header">
    <label class="ticket-card-select">
      <input type="checkbox" class="bulk-select" value="{{ ticket.id }}"
             aria-label="Ticket {{ ticket.id }} auswählen">
    </label>
    <h3 class="ticket-card-title">
      <a href="{{ url_for('main.ticket_detail', ticket_id=ticket.id) }}">
        #{{ ticket.id }} · {{ ticket.title }}
      </a>
    </h3>
  </header>

  <div class="ticket-card-badges">
    <span class="badge status-{{ ticket.status.value }}">{{ ticket.status.value|title }}</span>
    <span class="badge priority-{{ ticket.priority.value if ticket.priority else 'mid' }}">
      {{ ticket.priority.value|title if ticket.priority else 'Mittel' }}
    </span>
    {% if ticket.due_date %}
      <span class="badge bg-light text-dark">📅 {{ ticket.due_date.strftime('%d.%m.') }}</span>
    {% endif %}
  </div>

  <div class="ticket-card-meta">
    {% if ticket.assigned_worker %}
      <span title="{{ ticket.assigned_worker.name }}">👤 {{ ticket.assigned_worker.name }}</span>
    {% else %}
      <span class="text-muted">Nicht zugewiesen</span>
    {% endif %}
    {% if ticket.contact and ticket.contact.name %}
      · <span>{{ ticket.contact.name }}</span>
    {% endif %}
  </div>

  <footer class="ticket-card-actions">
    <div class="dropdown">
      <button class="btn btn-sm btn-outline-secondary" data-bs-toggle="dropdown"
              aria-label="Aktionen für Ticket {{ ticket.id }}">⋯</button>
      <ul class="dropdown-menu">
        <li><a class="dropdown-item" href="{{ url_for('main.ticket_detail', ticket_id=ticket.id) }}">Öffnen</a></li>
        <li><button class="dropdown-item" type="button" data-quick-status="in_progress" data-ticket-id="{{ ticket.id }}">In Bearbeitung</button></li>
        <li><button class="dropdown-item" type="button" data-quick-status="done" data-ticket-id="{{ ticket.id }}">Erledigt</button></li>
      </ul>
    </div>
  </footer>
</article>
{% endmacro %}
```

- [ ] **Step 4: Importfähigkeit testen**

```bash
cd ticketsystem && python -c "from app import app
with app.app_context():
    from flask import render_template_string
    out = render_template_string('{% from \"components/_ticket_item.html\" import render_ticket_card %}OK')
    print(out)
"
```
Erwartet: `OK`.

- [ ] **Step 5: Commit**

```bash
git add templates/components/_ticket_item.html
git commit -m "feat(templates): extract ticket row + card macros into shared component"
```

---

## Task 2: `index.html` auf Macros umstellen

**Files:**
- Modify: `ticketsystem/templates/index.html` (Tabelle + neu: Card-Liste)

- [ ] **Step 1: Macro importieren**

Am Anfang von `index.html` nach `{% extends "base.html" %}`:

```jinja
{% from "components/_ticket_item.html" import render_ticket_row, render_ticket_card %}
```

- [ ] **Step 2: Tabelle auf Macro umstellen**

Im `{% for ticket in tickets %}`-Loop der `<tbody>`-Section den `<tr>`-Block ersetzen durch:

```jinja
{% for ticket in tickets %}
  {{ render_ticket_row(ticket) }}
{% endfor %}
```

Die bestehende `<table class="table ...">` bekommt zusätzlich eine Klasse `ticket-table`:

```html
<div class="ticket-table-wrapper table-responsive">
  <table class="table ticket-table">
    ...
  </table>
</div>
```

- [ ] **Step 3: Card-Liste neben Tabelle einfügen**

Direkt vor dem `<div class="ticket-table-wrapper">`:

```jinja
<div class="ticket-cards" role="list" aria-label="Tickets">
  {% for ticket in tickets %}
    {{ render_ticket_card(ticket) }}
  {% endfor %}
  {% if not tickets %}
    <p class="text-center text-muted py-4">Keine Tickets gefunden.</p>
  {% endif %}
</div>
```

- [ ] **Step 4: Template-Rendering-Test**

Dev-Server starten, Dashboard öffnen. Bei aktuellem Viewport sollte genau eine Variante sichtbar sein (nach Task 3 — im Moment noch beide).

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat(dashboard): render tickets via shared macro with card alternative"
```

---

## Task 3: CSS — Card-Layout + Media-Queries

**Files:**
- Modify: `ticketsystem/static/css/style.css`

- [ ] **Step 1: Card-Layout-Regeln**

Ans Ende von `style.css`:

```css
/* ============= Ticket Card (Mobile) ============= */
.ticket-cards {
    display: none;  /* default hidden, shown <900px via media query */
    flex-direction: column;
    gap: .5rem;
    margin-top: 1rem;
}

.ticket-card {
    background: var(--bs-body-bg, #fff);
    border: 1px solid var(--bs-border-color, #dee2e6);
    border-radius: .5rem;
    padding: .75rem 1rem;
    display: flex;
    flex-direction: column;
    gap: .5rem;
    border-left-width: 4px;
}
.ticket-card[data-priority="urgent"] { border-left-color: #dc3545; }
.ticket-card[data-priority="hoch"] { border-left-color: #fd7e14; }
.ticket-card[data-priority="mittel"] { border-left-color: #ffc107; }
.ticket-card[data-priority="niedrig"] { border-left-color: #198754; }

.ticket-card-header {
    display: flex;
    align-items: flex-start;
    gap: .5rem;
}
.ticket-card-select { margin-top: .25rem; }
.ticket-card-title {
    font-size: 1rem;
    font-weight: 600;
    margin: 0;
    flex: 1;
}
.ticket-card-title a { color: inherit; text-decoration: none; }

.ticket-card-badges {
    display: flex;
    flex-wrap: wrap;
    gap: .25rem;
}
.ticket-card-meta { font-size: .875rem; color: var(--bs-secondary-color, #6c757d); }
.ticket-card-actions { display: flex; justify-content: flex-end; }

.ticket-card.selected {
    outline: 2px solid var(--bs-primary, #0d6efd);
    outline-offset: -2px;
}

/* ============= Breakpoint Switching ============= */
@media (max-width: 899.98px) {
    .ticket-table-wrapper { display: none; }
    .ticket-cards { display: flex; }
}

/* Tablet column priorisation */
@media (max-width: 1199.98px) and (min-width: 900px) {
    .ticket-table .hide-on-tablet { display: none; }
}
```

- [ ] **Step 2: `hide-on-tablet` auf sekundäre Spalten setzen**

In `templates/components/_ticket_item.html` und `index.html` `<thead>`-Block die `<th>` / `<td>` für Kontakt und Team mit Klasse versehen:

```html
<th class="hide-on-tablet">Kontakt</th>
<th class="hide-on-tablet">Team</th>
```

Und in der Row:

```jinja
<td class="hide-on-tablet">{{ ticket.contact.name if ticket.contact else '' }}</td>
<td class="hide-on-tablet">{{ ticket.team.name if ticket.team else '' }}</td>
```

- [ ] **Step 3: Test im DevTools**

Chromium DevTools Device-Emulation:
1. **iPhone SE (375×667):** Nur Cards sichtbar, kein Horizontal-Scroll.
2. **iPad (768×1024):** Tabelle sichtbar, Kontakt- und Team-Spalten weg.
3. **Desktop (1440×900):** Tabelle komplett mit allen Spalten.

- [ ] **Step 4: Bulk-Select-Konsistenz prüfen**

Auf Mobile eine Card ankreuzen → Bulk-Action-Bar sollte erscheinen (Logik liest `.bulk-select`-Checkboxen). Wenn existierender JS-Code auf `tr.bulk-select` selektiert, umstellen auf `.bulk-select` (Class, unabhängig vom Parent-Tag).

- [ ] **Step 5: Commit**

```bash
git add static/css/style.css templates/index.html templates/components/_ticket_item.html
git commit -m "feat(dashboard): card layout <900px, column priorisation 900-1200px"
```

---

## Task 4: Lighthouse-Check

**Files:** keine.

- [ ] **Step 1: Lighthouse-Mobile-Run**

Dev-Server starten, Dashboard mit Test-Daten. Chromium DevTools → Lighthouse → Mobile → Performance + Accessibility + Best Practices auditieren.

**Erwartet:**
- Performance ≥ 80 (wegen Dev-Server ggf. niedriger als Prod).
- Accessibility ≥ 90.
- Best Practices ≥ 90.

Fixes bei konkreten Findings ergänzen (z. B. Tap-Target-Size, Contrast-Ratio).

- [ ] **Step 2: Manuell-End-to-End-Test**

1. iPhone SE (375px): Ticket in Card antippen → Detail-Seite öffnet. Checkbox antippen → Bulk-Bar erscheint. Overflow-Menü öffnet Status-Optionen.
2. iPad (768px): Tabelle scrollbar ohne Horizontal-Scroll-Leiste. Spalten Kontakt/Team fehlen.
3. Desktop: Unverändert.

- [ ] **Step 3: Sucherfolg ARIA-Live (Phase 1 Anknüpfung)**

Suchbegriff eingeben → `#dashSearchCount` aktualisiert sich und Screenreader liest den neuen Count vor (aria-live aus Phase 1 bleibt aktiv).

- [ ] **Step 4: Phase-3-Tag**

```bash
git tag ux-phase-3-complete
```
