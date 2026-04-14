# Refactoring-UI Token-Härtung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Design-Token-System auf Refactoring-UI-Niveau härten (Score 7.5 → 9.5+/10) — ohne Template-Änderungen am Funktionsumfang, rein CSS-seitig.

**Architecture:** CSS-only Refactor. Token-Skala in `:root` erweitern (Typo, Gray-Shades, Navbar-Farben, Icon-Sizes), verstreute Hardcoded-Werte und `!important`-Kaskaden auf Tokens umbiegen. Keine Markup-Änderungen außer kleinen Klassen-Tausche (`container-fluid` → `container` auf Text-Seiten, Admin-Badge-Klasse).

**Tech Stack:** CSS Custom Properties, Bootstrap 5.3, Pytest (Regression-Guard), Flake8.

**Audit-Grundlage:** [UI_AUDIT_RefactoringUI_2026-04-14.md](UI_AUDIT_RefactoringUI_2026-04-14.md)

**Verifikations-Strategie:** Da es kein Visual-Regression-Testing gibt, dient folgendes als Sicherheitsnetz:
1. **Pytest-Baseline** vor Phase 1 erfassen, vor jedem Commit erneut prüfen (CLAUDE.md §Baseline-Regel)
2. **Grep-Assertions** auf eliminierte Hardcoded-Werte (nachweisbar 0 Treffer)
3. **Import-Check** (`python -c "from app import app"`)
4. **Manueller Smoke-Test** am Ende jeder Phase: Dashboard, Ticket-Detail, Login, Settings, Dark-Mode, HC-Mode

---

## Baseline (einmalig vor Task 1)

- [ ] **Pytest-Baseline erfassen**

```bash
cd ticketsystem && python -m pytest tests/ -v 2>&1 | tail -5
```

Ausgabe-Zeile mit `X passed, Y failed` **notieren**. Diese Zahlen sind die Ziel-Baseline für alle folgenden Tasks — keine neuen Failures einführen.

- [ ] **Branch anlegen**

```bash
git checkout -b refactor/ui-tokens-2026-04-14
```

---

## Phase 1 — Foundation Tokens

### Task 1: Typografie-Skala vervollständigen (R1)

**Files:**
- Modify: `ticketsystem/static/css/style.css:121-126` (Token-Block `Typography Scale`)

**Hintergrund:** Der bestehende Block definiert nur `--fs-xxs` bis `--fs-meta`. Es fehlen Base/Heading-Sizes und Line-Height-Tokens. Ohne modulare Skala entstehen immer wieder Ad-hoc-Werte (siehe Task 7).

- [ ] **Step 1: Typo-Token-Block ersetzen**

In [style.css](static/css/style.css) zwischen Zeile 121 und 126 den Block

```css
    /* Typography Scale */
    --fs-xxs: 0.65rem;
    --fs-xs: 0.7rem;
    --fs-sm: 0.75rem;
    --fs-meta: 0.8rem;
```

ersetzen durch:

```css
    /* Typography Scale (modular, 1.125 ratio ab base) */
    --fs-xxs: 0.65rem;   /* 10.4px */
    --fs-xs: 0.7rem;     /* 11.2px */
    --fs-sm: 0.75rem;    /* 12px */
    --fs-meta: 0.8rem;   /* 12.8px */
    --fs-base: 1rem;     /* 16px */
    --fs-lg: 1.125rem;   /* 18px */
    --fs-xl: 1.25rem;    /* 20px */
    --fs-2xl: 1.5rem;    /* 24px */
    --fs-3xl: 1.875rem;  /* 30px */
    --fs-4xl: 2.25rem;   /* 36px */

    /* Line-Height Scale (RUI: tight für Headings, relaxed für Body) */
    --lh-tight: 1.15;
    --lh-snug: 1.3;
    --lh-normal: 1.5;
    --lh-relaxed: 1.625;
```

- [ ] **Step 2: Import-Check**

```bash
cd ticketsystem && python -c "from app import app; print('ok')"
```

Erwartet: `ok`

- [ ] **Step 3: Pytest-Baseline verifizieren**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
```

Erwartet: Gleiche `X passed, Y failed` wie Baseline.

- [ ] **Step 4: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): extend typography token scale with base/heading sizes and line-heights"
```

---

### Task 2: Gray-Shade-Skala 50–900 einführen + Muted resaturieren (R3, R10)

**Files:**
- Modify: `ticketsystem/static/css/style.css:74-82` (Light-Mode `:root` Tokens)
- Modify: `ticketsystem/static/css/style.css:223-230` (Dark-Mode `[data-theme="dark"]`)

**Hintergrund:** Ad-hoc-Hex-Werte (`#212529`, `#5c636a`, `#dee2e6`, …) sollen durch eine kontrollierte 9-stufige Gray-Skala ersetzt werden. Die Text-Muted-Farbe bekommt einen kühlen Unterton (Slate-500 `#64748b`), was Business-UIs „premium" wirken lässt (RUI: Color #3).

- [ ] **Step 1: Gray-Skala in Tier-1-Primitives ergänzen**

In [style.css](static/css/style.css), **direkt nach Zeile 158** (nach `--space-16: 4rem;`), neuen Unterblock einfügen:

```css

    /* Gray scale (cool, slate-tinted — HSL 215° ~10% sat) */
    --gray-50:  #f8fafc;
    --gray-100: #f1f5f9;
    --gray-200: #e2e8f0;
    --gray-300: #cbd5e1;
    --gray-400: #94a3b8;
    --gray-500: #64748b;
    --gray-600: #475569;
    --gray-700: #334155;
    --gray-800: #1e293b;
    --gray-900: #0f172a;
```

- [ ] **Step 2: Light-Mode-Tokens auf Gray-Skala mappen**

In [style.css:74-82](static/css/style.css#L74) den Block

```css
    --bg-body: #f5f5f0;
    --bg-surface: #fdfcfb;
    --bg-surface-subtle: #f8f9fa;
    --text-main: #212529;
    --text-muted: #5c636a;
    --border-color: #dee2e6;
    --input-border: #767676;
```

ersetzen durch:

```css
    --bg-body: #f5f5f0;          /* warmes Off-White beibehalten (Marke) */
    --bg-surface: #fdfcfb;       /* warmes Surface beibehalten */
    --bg-surface-subtle: var(--gray-50);
    --text-main: var(--gray-900);
    --text-muted: var(--gray-500);          /* resaturiert, WCAG ≥ 4.5:1 auf weiss */
    --border-color: var(--gray-200);
    --input-border: var(--gray-400);        /* 3:1 non-text contrast, WCAG 1.4.11 */
```

- [ ] **Step 3: Dark-Mode-Tokens konsistent anpassen**

In [style.css:223-230](static/css/style.css#L223) den Dark-Mode-Block prüfen und die `--text-muted` und `--border-color` auf korrespondierende Gray-Stufen mappen:

```css
[data-theme="dark"] {
    --bg-body: #121212;
    --bg-surface: #1e1e1e;
    --bg-surface-subtle: #2d2d2d;
    --text-main: var(--gray-100);       /* war #e0e0e0 */
    --text-muted: var(--gray-400);      /* war #b5bcc7 — WCAG ≥ 4.5:1 auf #1e1e1e */
    --border-color: var(--gray-700);    /* war #333 */
    --input-border: var(--gray-500);    /* war #888888 */
    /* ... rest unverändert ... */
```

Nur die vier genannten Zeilen tauschen.

- [ ] **Step 4: Kontrast manuell prüfen**

Dev-Server starten:

```bash
cd ticketsystem && python app.py
```

Im Browser öffnen: Dashboard, Ticket-Detail. In DevTools (F12 → Accessibility → Contrast) prüfen:
- Body-Text auf `--bg-surface`: ≥ 7:1 (AAA)
- Text-Muted auf `--bg-surface`: ≥ 4.5:1 (AA)
- Border sichtbar gegen Surface

Falls ein Kontrast unter AA liegt: Muted auf `--gray-600` anheben.

- [ ] **Step 5: Pytest-Baseline verifizieren**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
```

Erwartet: Baseline-Parität.

- [ ] **Step 6: Commit**

```bash
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): introduce gray 50-900 scale and map text/border tokens to it"
```

---

### Task 3: Navbar-Hardcodes → Tokens ("Nuclear" auflösen) (R2)

**Files:**
- Modify: `ticketsystem/static/css/style.css:74-82` (Token-Block erweitern)
- Modify: `ticketsystem/static/css/style.css:427-445` ("NUCLEAR CONTRAST FIXES" → Navbar)

**Hintergrund:** Der `!important`-Block mit Label „NUCLEAR CONTRAST FIXES" enthält Hardcodes (`#1a1a1a`, `#fff`, `rgba(255,255,255,0.1)`, `#0d6efd`). Wir ziehen sie in Tokens und entfernen `!important`, wo möglich.

- [ ] **Step 1: Navbar-Token ergänzen**

In [style.css:74-82](static/css/style.css#L74) **innerhalb** des `:root`-Blocks (z.B. vor `--btn-soft-bg`) einfügen:

```css
    /* Navbar (independent of body theme) */
    --navbar-bg: #1a1a1a;
    --navbar-fg: #fff;
    --navbar-fg-muted: rgb(255 255 255 / 70%);
    --navbar-border: rgb(255 255 255 / 10%);
    --navbar-hover-bg: rgb(255 255 255 / 5%);
```

- [ ] **Step 2: Navbar-Rules auf Tokens mappen**

In [style.css:427-445](static/css/style.css#L427) den Block

```css
/* --- NUCLEAR CONTRAST FIXES --- */

/* Force Navbar to be readable (Dark background for navbar-dark) */
.navbar-dark {
    background-color: #1a1a1a !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.navbar-dark .navbar-brand,
.navbar-dark .nav-link {
    color: #fff !important;
    opacity: 0.9;
}

.navbar-dark .nav-link:hover {
    opacity: 1;
    color: var(--color-primary, #0d6efd) !important;
}
```

ersetzen durch:

```css
/* --- Navbar — token-based, independent of body theme --- */
.navbar-dark {
    background-color: var(--navbar-bg);
    border-bottom: 1px solid var(--navbar-border);
}

.navbar-dark .navbar-brand,
.navbar-dark .nav-link {
    color: var(--navbar-fg);
    opacity: 0.9;
}

.navbar-dark .nav-link:hover {
    opacity: 1;
    color: var(--color-primary);
}
```

Die `!important` und hardcoded `#0d6efd`-Fallbacks entfallen.

- [ ] **Step 3: Grep verifiziert Eliminierung**

```bash
grep -n "NUCLEAR" ticketsystem/static/css/style.css
grep -cn "#1a1a1a" ticketsystem/static/css/style.css
```

Erwartet:
- `NUCLEAR` 0 Treffer (Kommentar entfernt)
- `#1a1a1a` genau **1** Treffer (nur in `--navbar-bg` Token-Definition)

- [ ] **Step 4: Dev-Server — Navbar sichtbar prüfen**

Manuell: Light-Mode, Dark-Mode, HC-Mode. Navbar muss in allen drei Modi dunkel bleiben, Text weiß, Hover blau.

- [ ] **Step 5: Pytest-Baseline + Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): replace nuclear contrast block with navbar tokens"
```

---

## Phase 2 — Hierarchy & Depth

### Task 4: Table-Header als Label-Hierarchie (R4)

**Files:**
- Modify: `ticketsystem/static/css/style.css:1360+` (oder neuer Block am Ende der Dash-Table-Sektion)

**Hintergrund:** RUI-Prinzip #1: Label ist sekundär gegenüber Daten. Aktuell sind Header und Zellen beide `~0.85rem normal` — sie konkurrieren visuell. Header soll kleiner, uppercase, muted.

- [ ] **Step 1: Bestehende `.dash-table`-Regel inspizieren**

```bash
grep -n "dash-table" ticketsystem/static/css/style.css
```

Die existierenden Regeln merken — wir fügen nur `.dash-table thead th`-Regeln hinzu, bestehende nicht ersetzen (außer der Font-Size in Task 7).

- [ ] **Step 2: Label-Styling ergänzen**

Direkt nach der letzten `.dash-table`-Regel (Zeile ~1363) hinzufügen:

```css

/* RUI #1: Table headers as de-emphasized labels, data stays primary */
.dash-table thead th,
.table thead th {
    font-size: var(--fs-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    background-color: var(--bg-surface-subtle);
}
```

- [ ] **Step 3: Responsive-Mode (`table-responsive-cards`) prüfen**

In [style.css:680-689](static/css/style.css#L680) existiert bereits `::before { content: attr(data-label); text-transform: uppercase; font-size: 0.75rem; ... }` — konsistent, keine Änderung nötig. Gut so, nur den `font-size: 0.75rem` Hardcode auf `var(--fs-sm)` ziehen:

```css
    .table-responsive-cards tbody td::before {
        content: attr(data-label);
        font-weight: bold;
        text-align: left;
        padding-right: var(--space-4);
        flex-shrink: 0;
        color: var(--text-muted);
        text-transform: uppercase;
        font-size: var(--fs-sm);
    }
```

- [ ] **Step 4: Dev-Server — Dashboard optisch prüfen**

Dashboard öffnen. Header-Zeile muss deutlich kleiner/leiser wirken als Datenzeilen. Daten bleiben primary. Squint-Test: wer dominiert? → Daten.

- [ ] **Step 5: Pytest-Baseline + Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): table headers as de-emphasized uppercase labels"
```

---

### Task 5: Elevation-Map konsolidieren + Card-Border-or-Shadow (R5, R11)

**Files:**
- Modify: `ticketsystem/static/css/style.css:473-476` (Card-Regel)
- Modify: `ticketsystem/static/css/style.css` — neuer Elevation-Block am Ende

**Hintergrund:** Karten haben momentan Border UND Shadow (doppeltes Elevation-Signal, RUI #5). Ziel: klare Hierarchie `btn → card → dropdown → modal` mit `shadow-xs/sm/md/lg`.

- [ ] **Step 1: Card-Regel entschärfen**

In [style.css:473-476](static/css/style.css#L473) den Block

```css
/* Ensure consistent card borders for separation */
.card {
    border: 1px solid var(--border-color) !important;
}
```

ersetzen durch:

```css
/* RUI #5: Cards use shadow OR border, not both. On white surfaces → shadow. */
.card {
    border: 1px solid transparent;
    box-shadow: var(--card-shadow);
}

/* On subtle backgrounds, swap to border-only for clearer depth separation */
.bg-surface-subtle .card,
.card.card-flat {
    border-color: var(--border-color);
    box-shadow: none;
}
```

- [ ] **Step 2: Elevation-Map für Dropdowns + Modals dokumentieren**

Am Ende der Datei (nach letzter Regel) neuen Block anfügen:

```css

/* =========================================
   ELEVATION MAP (RUI #5 — consistent depth scale)
   btn=xs, card=sm, dropdown=md, notification/modal=lg, global-modal=xl
   ========================================= */
.btn {
    box-shadow: var(--shadow-xs);
}
.btn:disabled,
.btn[aria-disabled="true"] {
    box-shadow: none;
}
.dropdown-menu {
    box-shadow: var(--shadow-md);
}
.notification-dropdown,
.modal-content {
    box-shadow: var(--shadow-lg);
}
```

- [ ] **Step 3: Grep — keine Shadow-Konflikte mit Bootstrap-Utilities**

```bash
grep -c "shadow-sm\|shadow-lg" ticketsystem/templates/base.html
```

Erwartet: Bootstrap-Utilities wie `shadow-sm` bleiben auf Markup-Ebene erhalten — sie sind jetzt stärker als unser `--card-shadow` und OVERRIDE bewusst. OK.

- [ ] **Step 4: Dev-Server — Hierarchie prüfen**

Dashboard öffnen. Notification-Dropdown aufklappen → muss deutlich über Karten schweben. Global-Confirm-Modal öffnen → höchste Elevation.

- [ ] **Step 5: Pytest-Baseline + Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): elevation map — cards use shadow-or-border, dropdowns/modals lifted"
```

---

### Task 6: Admin-Badge semantisch entgrünen (R7)

**Files:**
- Modify: `ticketsystem/templates/base.html:105`

**Hintergrund:** Die Admin-Rollen-Pille in der Navbar trägt `badge-subtle-success` (grün). Grün = Erfolgsfeedback; Rollen-Label ist neutrale Info. Semantische Kollision.

- [ ] **Step 1: Badge-Klasse tauschen**

In [base.html:105](templates/base.html#L105) den Span

```html
              <span class="badge-subtle-success px-2 py-1 rounded-pill small fw-bold">Admin</span>
```

ändern zu:

```html
              <span class="badge-subtle-secondary px-2 py-1 rounded-pill small fw-bold">Admin</span>
```

- [ ] **Step 2: Dev-Server — Admin-Menü prüfen**

Als Admin einloggen. Navbar-Badge „Admin" muss neutral-grau sein (nicht mehr grün). Erfolgs-Flashes (z.B. Ticket erstellt) bleiben grün → semantische Trennung wiederhergestellt.

- [ ] **Step 3: Pytest-Baseline + Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/templates/base.html
git commit -m "refactor(ui): admin role badge neutral — green reserved for success feedback"
```

---

## Phase 3 — Polish

### Task 7: Ad-hoc Font-Sizes auf Skala mappen (R6, R9)

**Files:**
- Modify: `ticketsystem/static/css/style.css` — ca. 8 Einzelstellen

**Hintergrund:** Werte `0.85rem`, `1.1rem`, `1.2rem`, `1.25rem`, `3rem`, `3.5rem`, `0.6rem` stehen außerhalb der (jetzt erweiterten) Skala. Nach Task 1 haben wir Tokens für alle.

- [ ] **Step 1: Liste der Treffer generieren**

```bash
grep -n "font-size:" ticketsystem/static/css/style.css | grep -v "var(--fs" | grep -v "max(" | grep -v "16px" | grep -v "^.*:.*\/\*"
```

Erwartete Treffer (je ~Zeilen, können variieren):
- `688: font-size: 0.75rem;` (im `::before`, schon in Task 4 gefixt — prüfen)
- `781: .x-small { font-size: 0.75rem ... }` → `var(--fs-sm)`
- `782: .text-meta { font-size: 0.8rem; }` → `var(--fs-meta)`
- `785: .fs-check-status { font-size: 1.1rem; }` → `var(--fs-lg)` (18px ≈ 1.1rem)
- `805: .status-label { font-size: 1.25rem; }` → `var(--fs-xl)`
- `813: .display-counter { font-size: 3.5rem; }` → `var(--fs-4xl)` oder behalten (Display-Hero legitim)
- `1052: font-size: 1.2rem;` → `var(--fs-lg)`
- `1275: font-size: 3rem;` → beibehalten + Kommentar (Empty-State-Icon, Hero-Kontext)
- `1284: font-size: 1.25rem;` → `var(--fs-xl)`
- `1299: font-size: 0.6rem;` → `var(--fs-xxs)` (nah genug, 0.6 vs 0.65)
- `1360: .dash-table { font-size: 0.85rem; }` → `var(--fs-meta)` (≈ 0.8rem, minimal kleiner akzeptiert) oder neues Token `--fs-compact: 0.85rem`

- [ ] **Step 2: Einzelne Ersetzungen durchführen**

Jede Stelle einzeln ersetzen. Empfehlung: pro Ersetzung Edit-Tool nutzen, nicht Find-and-Replace — Kontext prüfen.

**Sonderfall Task-7-Konflikt:** `.display-counter: 3.5rem` und `empty-state-icon: 3rem` sind bewusst groß (Hero/Display-Kontext, RUI erlaubt). Kommentar ergänzen statt tokenisieren:

```css
.display-counter {
    font-size: 3.5rem;  /* hero metric — out-of-scale intentional */
    ...
}
```

**Sonderfall `.dash-table: 0.85rem`:** Zwischen `--fs-meta` (0.8) und `--fs-base` (1.0). Zwei Optionen:
- A) Auf `var(--fs-meta)` mappen (minimal kleiner, akzeptiert)
- B) Neues Token `--fs-compact: 0.875rem` einführen

**Empfehlung Option A.** Wenn Nutzer den Shrink bemerken: später Option B.

- [ ] **Step 3: Post-Grep**

```bash
grep -n "font-size:" ticketsystem/static/css/style.css | grep -vE "(var\(--fs|max\(|16px|hero|intentional|attr\()" | wc -l
```

Erwartet: ≤ 2 (nur legitime Sonderfälle mit `intentional`-Kommentar).

- [ ] **Step 4: Dev-Server — Smoke-Test**

Dashboard, Ticket-Detail, Settings. Prüfen dass keine Überschrift/Label „abgesprungen" aussieht.

- [ ] **Step 5: Pytest-Baseline + Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): map ad-hoc font-sizes to typography scale tokens"
```

---

### Task 8: `container-fluid` → `container` auf Text-Seiten (R8)

**Files:**
- Modify: `ticketsystem/templates/base.html:234`

**Hintergrund:** `container-fluid px-4` lässt Inhalt auf 4K-Monitoren überbreit laufen. Bootstrap `container` respektiert Responsive-Max-Widths (1320px @ xxl).

**Entscheidungskriterium:** Dashboard und Workload sind echt breit (Tabellen/Heatmaps); Settings/Profile/Login sind Text-lastig. Der `main` in `base.html` ist gemeinsam → wir wählen den Kompromiss.

- [ ] **Step 1: Option wählen**

Zwei Wege:
- **A) Global `container`**: Alle Seiten auf 1320px max. Dashboard verliert etwas Breite, aber Tabellen sind horizontal scroll-/card-fallback-fähig.
- **B) Per-Page-Override**: `base.html` bleibt `container-fluid`, aber Jinja-Block `{% block main_container_class %}container{% endblock %}` einführen; Text-Seiten setzen es.

**Empfehlung A** — weniger Template-Churn, und Dashboard wirkt bei 1320px noch komfortabel.

- [ ] **Step 2: Änderung in base.html:234**

```html
  <main id="main-content" class="container-fluid px-4 py-4">
```

ändern zu:

```html
  <main id="main-content" class="container py-4">
```

(`px-4` entfällt, `container` hat eingebautes Padding.)

- [ ] **Step 3: Dev-Server — Breakpoints prüfen**

Chrome DevTools Responsive: 1920×1080, 1366×768, 768×1024. Dashboard muss auf allen lesbar bleiben, keine horizontalen Scrollbars auf Desktop.

Falls Dashboard-Tabelle bei 1366px zu gedrängt wirkt: Revert oder Option B wählen.

- [ ] **Step 4: Pytest-Baseline + Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/templates/base.html
git commit -m "refactor(ui): constrain main container width (RUI #7 — full-width rarely right)"
```

---

### Task 9: Icon-Size-Token (R12)

**Files:**
- Modify: `ticketsystem/static/css/style.css` — Token-Block + neue Utility-Klassen

**Hintergrund:** Bootstrap Icons nehmen Inline-Font-Size. Ohne Token variieren sie unkontrolliert.

- [ ] **Step 1: Icon-Token ergänzen**

In [style.css](static/css/style.css) innerhalb `:root`, nach den Avatar-Tokens (ca. Zeile 131), ergänzen:

```css

    /* Icon sizes (RUI #6) */
    --icon-sm: 1em;      /* inline in text */
    --icon-md: 1.25em;   /* navigation */
    --icon-lg: 1.5em;    /* feature/hero */
    --icon-xl: 2em;      /* empty states */
```

- [ ] **Step 2: Utility-Klassen am Ende der Typography-Sektion anfügen**

Nach `.tracking-wide` (ca. Zeile 802) ergänzen:

```css

/* Icon sizing utilities — use on <i class="bi ..."> */
.icon-sm { font-size: var(--icon-sm); }
.icon-md { font-size: var(--icon-md); }
.icon-lg { font-size: var(--icon-lg); }
.icon-xl { font-size: var(--icon-xl); }
```

- [ ] **Step 3: Opportunistischer Einsatz**

**Nicht** jetzt alle 100+ Icon-Usages umstellen. Neue Template-Arbeit nutzt die Klassen, Bestandsmigration per Bedarf (YAGNI).

- [ ] **Step 4: Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/static/css/style.css
git commit -m "feat(css): icon-size tokens and utility classes"
```

---

### Task 10: System-Font-Stack modernisieren (R13)

**Files:**
- Modify: `ticketsystem/static/css/style.css:11-16` (body)

**Hintergrund:** Aktueller Stack (`"Segoe UI", Tahoma, Geneva, Verdana`) rendert nur unter Windows nativ. Moderner System-Stack nutzt plattform-native Fonts auf macOS/iOS/Android/Linux.

- [ ] **Step 1: Font-Stack ersetzen**

In [style.css:11-16](static/css/style.css#L11) den Block

```css
body {
    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    background-color: var(--bg-body);
    ...
}
```

ändern zu:

```css
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, "Noto Sans", sans-serif,
                 "Apple Color Emoji", "Segoe UI Emoji";
    background-color: var(--bg-body);
    ...
}
```

- [ ] **Step 2: Dev-Server — kurz quer prüfen**

Ein Chrome-Reload. Text muss leicht anders wirken (etwas weniger eckig unter Windows nicht — dort bleibt Segoe UI) — auf anderen Plattformen klarer Unterschied.

- [ ] **Step 3: Pytest-Baseline + Commit**

```bash
cd ticketsystem && python -m pytest tests/ -q 2>&1 | tail -3
git add ticketsystem/static/css/style.css
git commit -m "refactor(css): modern system font stack (native on macOS/iOS/Android)"
```

---

## Phase 4 — Abschluss

### Task 11: Final-Smoke-Test + PR

- [ ] **Step 1: Vollständige Pytest-Suite**

```bash
cd ticketsystem && python -m pytest tests/ -v 2>&1 | tail -10
```

Erwartet: Baseline-Parität, keine neuen Failures.

- [ ] **Step 2: Flake8**

```bash
cd ticketsystem && python -m flake8 --max-line-length=120 *.py routes/ services/
```

Erwartet: 0 Findings (CSS ist nicht erfasst, aber Python-Sauberkeit muss stehen).

- [ ] **Step 3: Manueller Smoke-Test**

Browser, alle Haupt-Flows durchklicken:
- Login
- Dashboard (inkl. Bulk-Mode)
- Ticket erstellen, editieren, Kommentar, Status-Change
- My-Queue
- Workload (als Admin)
- Settings
- Dark-Mode-Toggle
- HC-Mode-Toggle

Pro Seite: sichtbare Brüche? Navbar stabil? Hover-States? Focus-Rings? Typo harmonisch?

- [ ] **Step 4: Re-Score gegen Audit**

[UI_AUDIT_RefactoringUI_2026-04-14.md](UI_AUDIT_RefactoringUI_2026-04-14.md) §6 durchgehen. Welche R-Findings sind fixed? Score nachrechnen (Ziel: ≥ 9.5).

Re-Score kurz als `UI_AUDIT_RefactoringUI_2026-04-14_POST.md` dokumentieren (2-3 Absätze reichen).

- [ ] **Step 5: PR erstellen**

```bash
git push -u origin refactor/ui-tokens-2026-04-14
gh pr create --title "refactor(ui): tighten design token system (7.5 → 9.5/10)" --body "$(cat <<'EOF'
## Summary
- Erweitert Typo-Skala um Base/Heading-Sizes + Line-Height-Tokens
- Führt Gray-Shade-Skala 50–900 ein, mappt Text/Border darauf
- Löst "Nuclear Contrast Fixes"-Block durch Navbar-Tokens auf
- Table-Header als de-emphasized Labels (RUI #1)
- Elevation-Map für Buttons/Cards/Dropdowns/Modals (RUI #5)
- Admin-Badge entgrünt (semantische Kollision behoben)
- Ad-hoc Font-Sizes auf Skala migriert
- `container-fluid` → `container` auf Hauptlayout
- Icon-Size-Utility + moderner System-Font-Stack

## Audit
Basiert auf [UI_AUDIT_RefactoringUI_2026-04-14.md](ticketsystem/UI_AUDIT_RefactoringUI_2026-04-14.md) — Score-Ziel 7.5 → 9.5.

## Test plan
- [x] Pytest-Baseline-Parität
- [x] Flake8 clean
- [x] Manueller Smoke-Test: Dashboard, Ticket-Detail, Settings, Login
- [x] Dark-Mode + HC-Mode visuell OK
- [x] DevTools Kontrast-Check: Body ≥ 7:1, Muted ≥ 4.5:1
EOF
)"
```

---

## Rollback-Strategie

Jeder Commit ist in sich eigenständig (CSS-only oder Template-Klassen-Tausch). Bei sichtbarer Regression:

```bash
git revert <commit-hash>
```

Keine DB-Migration, keine Service-Änderung — kein kaskadierender Rollback nötig.

---

## Nicht in diesem Plan

- **Markup-Level Icon-Migration** (Task 9 Step 3): opportunistisch, kein eigener Task.
- **Visual-Regression-Testing-Setup** (Playwright/Percy): separates Projekt, außerhalb Scope.
- **Dark-Mode-Gray-Skala-Audit**: Dark-Mode nutzt noch eigene Hex-Werte (`#121212`, `#1e1e1e`) — bewusst beibehalten (warmere Surfaces als Gray-900), nur Text/Border gemappt.
- **Bootstrap-Utility-Deprecation** (`shadow-sm` → Tokens im Markup): zu invasiv, kein Nutzen gegenüber Token-OVERRIDE in CSS.
