# Refactoring-UI-Audit — Ticketsystem

**Datum:** 2026-04-14
**Branch:** `main`
**Methode:** *Refactoring UI* (Wathan/Schoger) — 7 Prinzipien + Grayscale-First
**Umfang:** `static/css/style.css`, `templates/base.html`, `templates/index.html`,
`templates/components/*`, Design-Token-System (`:root`)
**Komplementär zu:** [UX_AUDIT_2026-04-14_v3.md](UX_AUDIT_2026-04-14_v3.md) — dieser
Audit bewertet **visuelle Systematik**, nicht Usability-Heuristiken.

---

## 1. Executive Summary

**Gesamtscore: 7.5 / 10**

Das System hat ein **solides Design-Token-Fundament** (Spacing-Skala 4/8/12/16/24/32/48/64,
Shadow-Stufen xs/sm/md/lg, Radius-Skala, Motion-Token, Focus-Ring) — das ist weiter,
als die meisten Bootstrap-Projekte jemals kommen. Der **Abstand zum 10/10** kommt nicht
aus fehlender Sorgfalt, sondern aus **drei strukturellen Lücken**:

1. **Typografie-Skala fehlt für Überschriften.** Nur Klein-Sizes sind tokenisiert
   (`--fs-xxs` 0.65 rem bis `--fs-meta` 0.8 rem). Keine modulare Skala
   (12/14/16/20/24/30/36 px) für Headings, keine `--lh-tight`/`--lh-relaxed`.
2. **"Nuclear Contrast Fixes" Block** ([style.css:427-475](static/css/style.css#L427))
   mit `!important`-Kaskaden auf hardcodierten Hex-Werten (`#1a1a1a`, `#fff`,
   `#0d6efd`) umgeht das Token-System, statt es zu erweitern.
3. **Farb-Shade-Skala fehlt.** Primary/Gray haben keine 50–900-Stufen; stattdessen
   Ad-hoc-Werte (`#374151`, `#1d4ed8`, `#b91c1c`) in Badge- und State-Regeln.

Score-verbesserungspotenzial ohne Feature-Arbeit: **+2.0** (auf 9.5/10) durch
ausschließlich Token-Refactoring — kein Markup muss angefasst werden.

---

## 2. Grayscale-Test (Blur/Squint-Test)

Beim Ausblenden aller Farben bleibt die Hierarchie **mehrheitlich lesbar**:

- Primary-CTA (Neues Ticket) hebt sich durch Größe + Rounded-Pill-Shape + Shadow
  auch in Grayscale ab. ✅
- Status-Badges verlieren ohne Farbe ihre Bedeutung fast vollständig — Icon-Paarung
  fehlt auf Dashboard-Rows, nur Text. ⚠️ Verstößt gegen RUI-Prinzip „Color is not
  information".
- Table-Headers und Zellen-Daten sind typografisch **zu ähnlich** gewichtet
  (beide `font-size: 0.85rem`). Label-Value-Hierarchie schwach. ⚠️

**Grayscale-Score: 6.5/10.**

---

## 3. Findings (nach RUI-Prinzip sortiert)

Schweregrad: **0** kosmetisch • **1** kleine Reibung • **2** spürbar • **3** systemisch

| # | Sev | Prinzip | Ort | Problem | Fix |
|---|-----|---------|-----|---------|-----|
| **R1** | **3** | 3 — Typography | [style.css:122-125](static/css/style.css#L122) | Typo-Skala **nur für Kleinst-Größen**. Kein `--fs-base/lg/xl/2xl/3xl`. Überschriften nutzen Bootstrap-Defaults + Einzelwerte (1.1 rem, 1.2 rem, 1.25 rem, 3 rem, 3.5 rem verstreut). | Modulare Skala ergänzen: `--fs-base: 1rem; --fs-lg: 1.125rem; --fs-xl: 1.25rem; --fs-2xl: 1.5rem; --fs-3xl: 1.875rem; --fs-4xl: 2.25rem;` + `--lh-tight: 1.15; --lh-snug: 1.3; --lh-relaxed: 1.6;` |
| **R2** | **3** | 4 — Color / Systematik | [style.css:427-475](static/css/style.css#L427) "NUCLEAR CONTRAST FIXES" | `!important` auf hardcodiertem `#1a1a1a`, `#fff`, `#0d6efd` — Token-System wird umgangen. Kommentar-Wortwahl („Nuclear") signalisiert: Entwickler hat gegen das System gekämpft. | Token-System erweitern: `--navbar-bg: #1a1a1a; --navbar-fg: #fff;`. Dann `navbar-dark` darauf mappen, `!important` entfernen. |
| **R3** | 2 | 4 — Color Scale | durchgängig in [style.css](static/css/style.css) | Keine 50–900-Shade-Skala. Farben werden punktuell neu definiert: Badges (`#1d4ed8`, `#b91c1c`), Buttons (`#0d6efd`, `#2563eb`), Text (`#374151` nicht vorhanden, stattdessen `var(--text-main) #212529`). | Primary + Gray + Semantic als 9-stufige Skala definieren (`--gray-50` bis `--gray-900`, `--primary-50` bis `--primary-900`). Bestehende Ad-hoc-Werte darauf mappen. |
| **R4** | 2 | 1 — Hierarchy | [index.html:230+](templates/index.html#L230) Dash-Table | Table-Header und Zeilendaten haben **gleiche Gewichtung** (beide `text-sm`, beide normal-weight). Label-Value-Pattern fehlt. | Header: `font-size: var(--fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted);` — Daten bleiben base. Erzeugt Label-als-sekundär-Hierarchie. |
| **R5** | 2 | 5 — Depth/Shadows | base.html + index.html | Shadow-Nutzung **flach**: navbar `shadow-sm`, primary-btn `shadow-sm`, cards `shadow-sm`. Kein `shadow-md`/`shadow-lg` auf elevated Elementen (Dropdowns, Modals teilweise `shadow-lg`, aber inkonsistent). Alles schwebt „gleich hoch" → Depth-Hierarchie verflacht. | Elevation-Map festlegen: `btn=xs, card=sm, dropdown=md, notification-dropdown=lg, modal=xl`. Bestehende Tokens sind da — nur konsistent anwenden. |
| **R6** | 2 | 3 — Typography | [style.css:1360](static/css/style.css#L1360) `.dash-table { font-size: 0.85rem; }` | `0.85rem` ist **nicht** in der Skala (`--fs-meta` ist 0.8, base 1.0). Arbiträrer Wert. | `font-size: var(--fs-meta)` oder `var(--fs-base)`. |
| **R7** | 2 | 1 — Hierarchy / Color | [base.html:105](templates/base.html#L105) Admin-Badge in Navbar | Admin-Pill hat `badge-subtle-success` — grün für Rollen-Label ist **semantische Kollision** mit Erfolgs-Feedback. Verletzt "Color = meaning". | Neutrales `badge-subtle-secondary` oder eigenes Rollen-Token `--badge-role-admin`. Grün reserviert für success/completed. |
| **R8** | 1 | 7 — Layout | [base.html:234](templates/base.html#L234) `container-fluid px-4 py-4` | `container-fluid` = volle Bildschirmbreite auf allen Breakpoints. Text-Tabellen werden auf 4K-Monitoren unleserlich breit. RUI: „Full-width is almost never right for content." | `container` oder `max-w-7xl mx-auto` + `container-fluid` nur auf genuin breiten Seiten (Dashboard-Grid, Workload-Heatmap). |
| **R9** | 1 | 2 — Spacing | [style.css:785](static/css/style.css#L785), [:805](static/css/style.css#L805), [:813](static/css/style.css#L813), [:1052](static/css/style.css#L1052), [:1275](static/css/style.css#L1275), [:1284](static/css/style.css#L1284) | Einzelwerte **außerhalb** der Spacing-Skala: `font-size: 1.1rem`, `1.2rem`, `3rem`, `3.5rem`, `0.6rem`. Spacing-Tokens sind da, werden aber nicht benutzt. | Alle Einzelwerte auf `var(--fs-*)` mappen. Bei fehlendem Token: Skala erweitern (R1), nicht neue Einzelwerte hinzufügen. |
| **R10** | 1 | 4 — Color (Gray Saturation) | [style.css:80](static/css/style.css#L80) `--text-muted: #5c636a` | Pure neutrale Grays (HSL ≈ 210°, 5% Sättigung) — RUI empfiehlt **subtile Sättigung** passend zum UI-Ton. Für ein Business/Tech-Tool: kühle Grays (blaue Untertöne). | `--text-muted: #64748b` (slate-500, HSL 215°, 16% sat) oder vergleichbar. Minimaler Change, deutlich „premium-iger" Eindruck. |
| **R11** | 1 | 5 — Depth (Flat Alternative) | card-Borders überall `1px solid var(--border-color)` | Jede Card hat **vollen Rahmen + Shadow** — doppelte Elevation-Signale. RUI: entweder Border ODER Shadow, nicht beides. | Auf weißen Surfaces: nur `shadow-sm`, keinen Border. Auf `bg-surface-subtle`: nur Border, keinen Shadow. Erzeugt klarere Depth-Stufen. |
| **R12** | 1 | 6 — Icons | durchgängig Bootstrap Icons | Icon-Größe nicht tokenisiert. In Nav 1em, in Dropdown-Items `me-2` ohne Size-Class, in Badges teils winzig. | Icon-Token: `--icon-sm: 1em, --icon-md: 1.25em, --icon-lg: 1.5em`. In Templates: `<i class="bi bi-x icon-md">`. |
| **R13** | 0 | 3 — Typography | [style.css:12](static/css/style.css#L12) `font-family: "Segoe UI", Tahoma, Geneva, Verdana` | Font-Stack ist ok, aber System-Font-Stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ...`) rendert plattform-nativ und professioneller. | Modernen System-Stack verwenden. 0-Byte-Payload-Change. |

---

## 4. Stärken (nicht ändern)

- **Spacing-Skala konsequent (4/8/12/16/24/32/48/64 px)** — keine arbiträren Paddings
  wie `13px` gefunden. RUI-konform. ✅
- **Shadow-Skala vollständig** (xs/sm/md/lg) mit physikalisch korrekten
  Transparenz-Werten statt opaken Grays. ✅
- **Focus-Ring als Token** (`--focus-ring-width`, `--focus-ring-color`) — einheitlich
  3 px, `outline-offset: 2px`. Vorbildlich. ✅
- **Radius-Skala** (sm/md/lg/pill) definiert und benutzt. ✅
- **Motion-Token** (`--duration-fast/base/slow`) + `--transition-colors` als
  wiederverwendbare Komposition. ✅
- **WCAG-Kontrast explizit dokumentiert** in Token-Kommentaren (`--color-warning:
  #856404; /* 5.5:1 auf f8d7da - WCAG AA */`). Das ist Gold. ✅
- **Touch-Target-Token** `--touch-target-min: 44px` — WCAG 2.5.8 systemisch
  umgesetzt, nicht punktuell. ✅

---

## 5. Priorisierung für 10/10

**Phase 1 — Foundation Fix (schätze 2-3 h, rein CSS):**
1. **R1** Typografie-Skala vervollständigen (`--fs-base` bis `--fs-4xl` +
   `--lh-tight/snug/relaxed`).
2. **R3** Gray-Shade-Skala (50-900) definieren; `--text-muted`, `--border-color`,
   `--bg-surface-subtle` darauf re-mappen.
3. **R10** `--text-muted` leicht kühl sättigen.
4. **R2** „Nuclear Contrast Fixes" auflösen — Werte in Tokens ziehen, `!important`
   entfernen.

**Phase 2 — Hierarchy & Depth (schätze 2 h):**
5. **R4** Table-Header als echtes Label (uppercase-small-muted).
6. **R5** Elevation-Map festlegen und auf Dropdowns/Modals anwenden.
7. **R11** Card: Border ODER Shadow, nicht beides.

**Phase 3 — Polish (schätze 1 h):**
8. **R6, R9** Arbiträre `font-size`-Werte auf Skala mappen.
9. **R7** Admin-Badge entgrünen.
10. **R8** `container-fluid` → `container` auf Text-lastigen Seiten.
11. **R12** Icon-Size-Token.

**Gesamt-Aufwand:** ~½ Tag, null Feature-Risiko, keine Migrations, keine Pytest-
Baseline-Änderung zu erwarten (pures CSS).

---

## 6. Methodik-Scoring

| RUI-Prinzip | Score | Notiz |
|---|---|---|
| 1. Visual Hierarchy | 7 | R4 Table-Labels, R7 Badge-Semantik |
| 2. Spacing & Sizing | 9 | Skala konsequent, nur R8 Container-Breite |
| 3. Typography | 6 | R1 fehlende Heading-Skala, R6/R9 Ad-hoc-Werte |
| 4. Color System | 6.5 | R2 Nuclear-Block, R3 fehlende Shade-Skala, R10 Gray-Sättigung |
| 5. Depth & Shadows | 8 | Tokens perfekt, R5/R11 Anwendung inkonsistent |
| 6. Images & Icons | 8 | R12 Icon-Size-Token fehlt |
| 7. Layout & Composition | 8 | R8 Container-Breite; sonst solide |
| **Mittelwert** | **7.5** | |

**Hauptdiagnose:** Das System ist **nicht unfertig**, sondern **unvollständig
tokenisiert**. Wer die Skala auf Typografie und Farb-Shades ausdehnt und den
„Nuclear Block" auflöst, hebt den Score ohne einen einzigen Template-Change auf
9.5+/10.
