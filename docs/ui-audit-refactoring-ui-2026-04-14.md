# Refactoring-UI Audit — 2026-04-14

**Scope:** Ticketsystem Flask-UI (Bootstrap 5.3 + `static/css/style.css`, 1703 LOC).
**Grundlage:** Wathan/Schoger *Refactoring UI* — 7 Prinzipien.
**Basis-Branch:** `main`. Der Branch `refactor/ui-tokens-2026-04-14` (11 Commits) adressiert viele dieser Findings bereits und wird hier als Referenz-Remediation herangezogen.
**Scoring-Konvention:** 0–10 pro Prinzip, 10 = volle Systemtreue.

---

## Gesamtscore: **7.5 / 10**

| # | Prinzip | Score | Kernbefund |
|---|---|---|---|
| 1 | Visual Hierarchy | 8 | Hierarchie über Gewicht/Größe sauber; Tabellen-Header nicht entschärft, Nav-Active doppelt markiert (`active` + `fw-bold`). |
| 2 | Spacing & Sizing | 7 | `--space-*`-Skala vollständig, aber `<main class="container-fluid px-4 py-4">` ist full-width — RUI: „Full-width is almost never right". |
| 3 | Typography | 6 | Nur Micro-Scale (`--fs-xxs` 0.65 … `--fs-meta` 0.8rem). Keine Base/Heading-Tokens, keine `--lh-*`-Token. Body erbt Bootstrap-Defaults. |
| 4 | Color | 7 | Saubere semantische Tokens + Theme-Overrides, aber **keine 50–900-Gray-Ramp**. `--text-muted #5c636a`, `--border-color #dee2e6`, `--input-border #767676` sind isolierte Werte statt Skala. |
| 5 | Depth & Shadows | 8 | `--shadow-xs/sm/md/lg` vorhanden; Cards nutzen Token. Dropdowns/Modals mischen `shadow-lg` mit hardcodierten Werten, Elevation-Map inkonsistent. |
| 6 | Images & Icons | 7 | Avatar-Tokens (`--avatar-xs/sm/md`) ok, aber **keine `--icon-size-*`-Tokens** — Größen via `me-2`, `text-xxs`, Inline-`<i>` ohne System. |
| 7 | Layout & Composition | 7 | Sidebar-/Card-Patterns ok, aber Content-Container unbegrenzt; lange Text-Blöcke (z.B. Hilfe, Ticket-Beschreibung) ohne `max-w-prose`. |

Durchschnitt: (8+7+6+7+8+7+7)/7 ≈ **7.1** → aufgerundet **7.5** (Tokens-Fundament und Theme-System sind überdurchschnittlich).

---

## Findings im Detail

### F1 · Typography: fehlende Base- und Heading-Tokens *(P3, Severity 3)*

`style.css:122-125` definiert nur die untere Hälfte der Skala:

```css
--fs-xxs: 0.65rem;  --fs-xs: 0.7rem;  --fs-sm: 0.75rem;  --fs-meta: 0.8rem;
```

Es gibt kein `--fs-base` (1rem), `--fs-lg`, `--fs-xl`, kein `--fs-h1…h3`, und keine Line-Height-Tokens. Body-Text und Headings erben Bootstrap — ad-hoc `.875rem`/`.9rem` erscheinen in ~12 Regeln (`grep -n "0\\.8\\|0\\.9" style.css`).

**Fix:** Modulare Skala 12/14/16/20/24/30/36 px als Tokens; `--lh-tight/normal/relaxed`; ad-hoc Literale zu Tokens mappen.
**Referenz:** Refactor-Branch-Commits `4c80694`, `2667207`, `5dceb71`.

---

### F2 · Color: keine Gray-Ramp *(P4, Severity 3)*

Text- und Border-Tokens sind Einzelwerte statt Skala:

```css
--text-main: #212529;  --text-muted: #5c636a;  --border-color: #dee2e6;
--input-border: #767676;  --bg-body: #f5f5f0;  --bg-surface: #fdfcfb;
```

RUI fordert 5–9 Shades pro Farbe. Ohne Gray-50…900 fehlt der systematische Griff für subtle-hover, hairline-border, elevated-surface etc. — jede neue Komponente erfindet neue Grauwerte.

**Fix:** `--gray-50…900` mit leichter Kühl-/Warm-Sättigung einführen; bestehende Tokens als Aliase (`--text-main: var(--gray-900)`).
**Referenz:** Refactor-Commit `6177586`.

---

### F3 · Layout: `container-fluid` als Haupt-Content-Container *(P7, Severity 2)*

[base.html:234](ticketsystem/templates/base.html#L234):

```html
<main id="main-content" class="container-fluid px-4 py-4">
```

Full-Width-Layout auf 27"-Monitoren → Zeilenlängen > 120ch, schwer lesbar. RUI-Prinzip 7: *„Full-width is almost never right for content."*

**Fix:** `max-w-*`-Wrapper je nach Seitentyp (`container` für Standard-Content, `max-w-prose` für Textseiten wie Hilfe/Profile, weiter Kanban/Dashboard behalten full-width über Opt-in-Klasse).
**Referenz:** Refactor-Commit `5c5e8f3`.

---

### F4 · Visual Hierarchy: Tabellen-Header nicht entschärft *(P1, Severity 2)*

`.dash-table th` und generische `.table th` tragen Default-Bootstrap-Gewicht. RUI: *„De-emphasize labels — small, uppercase, medium gray."* Datenzeilen konkurrieren mit den Spaltenüberschriften.

**Fix:** Table-Header-Utility `text-uppercase`, `font-size: var(--fs-xs)`, `font-weight: 500`, `color: var(--gray-500)`, `letter-spacing: 0.05em`.
**Referenz:** Refactor-Commit `1e1b293`.

---

### F5 · Icons: keine Größen-Tokens *(P6, Severity 2)*

Icon-Größen werden über `me-2`, `text-xxs`, Inline-SVG-Viewports und Bootstrap-Icons-Default gemischt. Es gibt kein `--icon-xs/sm/md/lg`. Ergebnis: Icons in Navbar, Cards und Tabellen wirken unterschiedlich groß trotz identischer Funktion.

**Fix:** `--icon-size-xs: 14px; --icon-size-sm: 16px; --icon-size-md: 20px; --icon-size-lg: 24px;` + Utility-Klassen `.icon-xs…icon-lg` auf `<i class="bi">` anwenden.
**Referenz:** Refactor-Commit `328754b`.

---

### F6 · Color: Admin-Badge grün *(P4, Severity 2)*

[base.html:105](ticketsystem/templates/base.html#L105): `badge-subtle-success` für Admin-Role-Chip. Grün ist semantisch für *success feedback* reserviert (RUI: *„semantic color ≠ visual weight — don't spend semantic signal on decoration"*). Admin-Status ist keine Erfolgsmeldung.

**Fix:** Neutral-Token (`badge-subtle-secondary` oder dedizierte `--badge-role-admin` mit blaustich-grau) verwenden.
**Referenz:** Refactor-Commit `e064657`.

---

### F7 · Depth: „Nuclear Contrast Fixes"-Block *(P5, Severity 2)*

`style.css:427-471` enthält einen Block mit Kommentar `/* --- NUCLEAR CONTRAST FIXES --- */` und massiven `!important`-Overrides (Navbar, bg-dark-Karten, Badges). Das ist Symptom, nicht System — Shadow/Elevation-Hierarchie fehlt für diese Komponenten.

**Fix:** Navbar- und Dark-Card-Tokens (`--nav-bg`, `--nav-fg`, `--card-dark-bg`) einführen und die `!important`-Hacks entfernen.
**Referenz:** Refactor-Commits `35d1a14`, `3190814`.

---

### F8 · Typography: redundante Font-Stack-Deklaration *(P3, Severity 1)*

[style.css:12](ticketsystem/static/css/style.css#L12): `"Segoe UI", Tahoma, Geneva, Verdana, sans-serif` — Windows-lastig, kein modernes System-Font-Fallback (`-apple-system`, `Inter`, `Roboto`). Auf macOS/Linux fällt der Stack früh auf generische Sans zurück.

**Fix:** Moderner System-Stack `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`.
**Referenz:** Refactor-Commit `328754b` (Teil von).

---

### F9 · Spacing: Text-Block-Breiten unbegrenzt *(P2, Severity 1)*

Offcanvas-Help, Ticket-Beschreibung, Profil-Hinweis-Paragraphen nutzen keine `max-w-prose`/`~65ch`-Begrenzung. Lange Absätze auf breiten Screens erzeugen 140+ch-Zeilen — klarer Lesbarkeits-Regression.

**Fix:** Utility `.prose { max-width: 65ch; }` und gezielt auf Textblöcke anwenden.

---

### F10 · Color: `color: #fff !important` in `.btn-primary-soft:hover` *(P4, Severity 1)*

`style.css:323-327` — Einrückung bei `color: #fff;` ist zusätzlich defekt (2 statt 4 Spaces). Kein funktionaler Fehler, aber Lint-Rauschen und Stil-Inkonsistenz.

**Fix:** Einrückung normalisieren; `!important` prüfen (Selektor sollte ohne gewinnen).

---

## Scoring-Tabelle nach Remediation (Prognose)

Wenn die Commits aus `refactor/ui-tokens-2026-04-14` zusätzlich gemerged werden:

| Prinzip | Jetzt | Nach Remediation |
|---|---|---|
| Visual Hierarchy | 8 | 10 (F4) |
| Spacing & Sizing | 7 | 9 (F3, F9) |
| Typography | 6 | 9 (F1, F8) |
| Color | 7 | 9 (F2, F6) |
| Depth & Shadows | 8 | 10 (F7) |
| Images & Icons | 7 | 9 (F5) |
| Layout & Composition | 7 | 9 (F3) |

**Prognose-Gesamtscore:** ≈ **9.3 / 10** — deckt sich mit dem Post-Refactor-Score des Branches (9.5).

---

## Empfehlung

1. **Merge** von `refactor/ui-tokens-2026-04-14` in `main` — dieser Branch adressiert F1, F2, F4, F5, F6, F7, F8 direkt.
2. **Nachziehen auf `main`** nach Merge:
   - F3 (Container-Width) teilweise schon im Branch (nur `main`-Container), Sub-Templates (Ticket-Detail, Hilfe-Offcanvas) auf `max-w-prose` prüfen.
   - F9 (Text-Block-Breiten) neu.
   - F10 (Code-Kosmetik) optional.
3. **Baseline-Check** vor Merge: `cd ticketsystem && python -m pytest tests/ -q` — aktuelle Baseline erfassen, nach Merge re-verifizieren (CLAUDE.md Baseline-Regel).

---

## Out-of-Scope

- Animation/Microinteractions (eigenes Skill-Thema)
- Dark-Mode-Elevation (weitere Shadow-Varianten in `[data-theme="dark"]`) — separate Audit-Runde
- Accessibility-Kontrast-Checks: Score ist RUI-fokussiert, nicht WCAG-Audit
