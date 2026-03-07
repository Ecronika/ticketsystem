# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.11.1] - 2026-03-07

### 🚨 Hotfixes & Accessibility (WCAG 2.2 AA)
- **Barrierefreiheit (A-01):** Skip-Navigation Link für Tastaturnavigation hinzugefügt (`#main-content`).
- **Barrierefreiheit (A-02):** Fehlende `<main>` Landmarks im Dokument integriert.
- **Barrierefreiheit (A-03):** Animationen und Transitions werden bei aktiven `prefers-reduced-motion` System-Einstellungen deaktiviert.
- **Barrierefreiheit (A-04):** Lade-Meldungen im Werkzeugaustausch-Modal sind nun per `aria-live='polite'` für Screenreader wahrnehmbar.
- **Barrierefreiheit (A-05):** Hierarchie der Überschriften korrigiert (versteckte `h1` im Dashboard).
- **Kontrast (WCAG AA):** Kontrastfehler für `--color-danger` auf Light Mode `badge-subtle` behoben.
- **Bugfix (E-01/E-02):** Die `ACTIVE_SESSIONS` Metric (Prometheus) ist nun sauber in der Request/Teardown-Logik eingebunden und ein `429 Too Many Requests` Error-Handler wurde integriert.

## [2.11.0] - 2026-03-07

### ✨ B2B UI/UX & Barrierefreiheit (WCAG 2.2)
- **Barrierefreiheit (WCAG 2.1.1):** Tastaturzugänglichkeit für Canvas-basierte Signature-Pads integriert (Eingabe über Enter/Leertaste möglich).
- **Barrierefreiheit (WCAG 2.2 AA):** Kontrast für Warnmeldungen (z.B. `--color-warning`) im Light-Mode manuell für alle Themes auf über 4,5:1 rekalibriert.
- **Agentic UX / Kognitive Last:** Breadcrumbs zur besseren prozessualen Navigation auf Detailansichten (Prüfung, Historien-Details) hinzugefügt.
- **Agentic UX / Kognitive Last:** Flash-Messages auf Basis von Timeout-Skripten nach 5 Sekunden mit automatischem Dismissal (Auto-Dismiss) versehen.
- **Agentic UX:** Semantische Statusanzeigen auf dem Dashboard ergänzt (klare Ikonografie für FÄLLIG und INFO Zustände statt reiner Farbkodierung nach WCAG 1.4.1).
- **UX:** Globalen Footer (Version, Impressum, Datenschutz) in `base.html` integriert.

### 🛠 Repository & Build Pipeline
- **Pipeline:** Zentrale `VERSION`-Datei im Repository-Root etabliert; Flask `app.py` liest die Version nun dynamisch aus.
- **Pipeline:** Git Pre-Commit Hook über `.gitattributes` implementiert, um serverseitiges LF Line-Ending für alle Checkout-Plattformen zu erzwingen.
- **Monitoring:** Neue `ACTIVE_SESSIONS` Prometheus Metrik für die Überwachung von concurrent Request-Transaktionen implementiert.

## [2.10.2] - 2026-03-07

### 🚨 Hotfix Release
- **Backend Stability:** Entfernung des In-Memory Caches (`_assigned_tools_cache`) in `services.py` zur Behebung von "Ghost Inventory"-Zuständen in Multi-Worker Gunicorn Deployments. Assigned Tools werden nun direkt via O(N) Subquery evaluiert.
- **Backend Stability:** `Model.query.get()` (SQLAlchemy 1.x Legacy) durch sauberes SQLAlchemy 2.x `db.session.get()` abgelöst.
- **Backend Stability:** Harte Prozessabbrüche in Gunicorn (`os._exit(1)`) durch saubere Signale (`os.kill(os.getpid(), signal.SIGTERM)`) während Restore-Vorgängen abgelöst, um Zombie-Prozesse in Container-Umgebungen zu verhindern.
- **Datenintegrität:** SQLite WAL-Checkpoints (`PRAGMA wal_checkpoint(FULL)`) vor Backup-Erstellung erzwungen, um ungeschriebene Memory-Transaktionen sicher in die Backups zu flushen.
- **Migration & Restore:** Aufruf von `db.create_all()` während des System-Restores entfernt, da dies Konflikte mit Alembic Migrations generierte, und reines `flask_migrate upgrade()` verwendet.
- **Python 3.12 Support:** Veraltete Datetime-Abfragen ohne Timezone-Zuweisung durch `datetime.now(timezone.utc)` ersetzt.
- **Bugfix (UI):** Autofill-Bug auf der Check-Seite (`check.html`) für überfällige Azubis behoben.
- **Quality Gates:** Die Applikation (Backend) erreicht nun standardmäßig 10.00/10 Punkten im Pylint Score über alle Instanzen. Unnötige Metriken und Dead Code (`invalidate_cache`) wurden restlos entfernt.

## [2.10.0] - 2026-03-06

### ✨ Smart Defaults & Autofill (Zero Redundant Inputs)
- **Status-Gedächtnis (`check.html`):** Radio-Button und Incident-Dropdown sind vorausgefüllt, wenn das Werkzeug beim letzten Check als DEFEKT oder FEHLT markiert war. Der spezifische Grund (z.B. "Verschleiß") ist ebenfalls vorausgewählt. Nur relevante Optgruppen werden angezeigt (Defekt-Gründe bei Status DEFEKT, Fehlt-Gründe bei Status FEHLT). Backend: `_parse_last_entry_status` in `checks.py` gibt nun `incident_reason` als 4. Rückgabewert zurück.
- **Prüfer-Memory (`check.html`):** Der zuletzt ausgewählte Prüfer / Ausbilder wird über `localStorage.setItem('lastExaminer', ...)` beim Absenden gespeichert und beim nächsten Aufruf von `check.html` automatisch wieder vorausgewählt.
- **Smart Auto-Select bei Rückgabe (`check.html`):** Wechselt der Benutzer den Vorgang auf "Werkzeug-Rückgabe", werden alle sichtbaren (im Besitz befindlichen) Werkzeuge sofort angehakt.
- **Context-Aware Exchange Modal (`index.html`):** Das "Werkzeug tauschen"-Modal erkennt beim Öffnen, welche Werkzeuge des Azubis zuletzt als defekt oder fehlend markiert waren, und hakt diese vorab an. Der spezifische Grund pro Werkzeug wird passend vorausgewählt ("Defekt" oder "Verloren"). Backend: `missing_tool_ids` / `broken_tool_ids` werden nun von `get_tool_anomalies_batch()` in `services.py` und dem Dashboard-Controller in `dashboard.py` übergeben.
- **Lehrjahr Default = 1 (`personnel.html`):** Das Lehrjahr-Eingabefeld beim Anlegen neuer Azubis hat nun den Standardwert `1`.

## [2.9.9] - 2026-03-05

### ✨ UX & Ergonomie Refactoring (Shopfloor / WCAG 2.2)
- **Bento-Card Layout (`check.html`):** Klassische HTML-Tabelle in der "Neue Prüfung" Maske wurde durch ein semantisches Bento-Card-Layout (`.bento-list-item`) ersetzt. Das verbessert die Lesbarkeit und Bedienbarkeit drastisch auf Tablets.
- **Touch Targets WCAG 2.5.5:** Die Checkboxen in der Prüfungsmaske und im "Werkzeug tauschen" Modal wurden von der Standard-Checkboxgröße auf `.form-check-input-lg` (1.5em) angehoben. Die Statusbuttons OK/DEFEKT/FEHLT wurden von `.btn-group-sm` auf Standardgröße umgestellt für garantierte 44px Touch-Target-Größe.
- **Semantische Icons:** Die Statusauswahl-Buttons (OK, DEFEKT, FEHLT) in der Prüfungsmaske erhalten jetzt Icons (✓, ⚠, ✗), um nicht nur durch Farbe zu unterscheiden (WCAG 1.4.1 No Color as Sole Means).
- **Exchange Modal (`index.html`):** Inline-Styles (`transform: scale(1.2)` und `style="cursor: pointer;"`) aus dem JavaScript-Template für das "Werkzeug tauschen" Modal wurden durch `.form-check-input-lg` und `.cursor-pointer` ersetzt. Das Dropdown wurde von `.form-select-sm` auf Standardgröße umgestellt.
- **JS Badge Konsistenz (`tools.html`):** Die AJAX-generierten Kategorie-Badges wurden mit `text-uppercase fw-bold tracking-wide` erwänzt und sind jetzt pixelgenau identisch mit dem server-seitig gerendertem Jinja-Output.

## [2.9.8] - 2026-03-05

### 🧹 UI / CSS Refactoring & Tech Debt (Phase 4)
- **Dead Code bereinigt:** Doppelt generierter CSS-Block für Typografie am Ende der `style.css` wurde restlos entfernt, um die CSS-Architektur fehlerfrei und wartbar zu halten.
- **Konsistenz the Templates:** Inkonsequente Umsetzung der Utility-Klassen in Template-If/Elif-Bäumen (z.B. in `tools.html`) wurde behoben. Hartkodierte Styles in elif-Zweigen nutzen nun konsistent die `.tracking-wide` Utility-Kombination.
- **Isolierte Styles begradigt:** Letzte verbliebene Inline-Formatierungen auf dem Dashboard (`index.html`) für Font-Abstände und Tooltip-Cursor wurden auf die neu geschaffenen abstrakten Komponentenkernklassen (`.tracking-tighter`, `.w-100`, `.cursor-help`) umgelegtet.

## [2.9.7] - 2026-03-05

### 🧹 UI / CSS Refactoring & Tech Debt (Phase 3)
- **Komponenten-Lücken geschlossen:** Fehlende Basisklasse `.badge-subtle-secondary` für neutrale (graue) Statusmeldungen eingeführt und in Tabellen (`check.html`) ausgetauscht.
- **JavaScript DOM-Strings bereinigt:** Harte, veraltete Utility-Klassen-Ketten in der dynamischen Tabellengenerierung (`tools.html`) wurden vollständig auf die neuen `.badge-subtle-*` Basisklassen migriert.
- **Missed Views aktualisiert:** In `history_details.html` wurden die Status-Icons für abgeschlossene Prüfungen ebenfalls auf das neue abstrakte Badge-System umgestellt.
- **Inline-Styles restlos entfernt:** Verbleibende Typografie-Workarounds (`style="letter-spacing: 0.5px;"` und `style="cursor: help;"`) in den Templates wurden durch dedizierte Component-Utilities (`.tracking-wide`, `.cursor-help`) abgelöst.

## [2.9.6] - 2026-03-05

### 🧹 UI / CSS Refactoring & Tech Debt (Phase 2)
- **CSS Variablen Bereinigung:** Hardcodierte Theme-Farben (`#ef4444`, `#ffffff`) für den Dark-Mode wurden aus spezifischen Klassen-Overrides gelöst und sauber als Variablen (`--bg-danger-subtle`, `--text-danger-override`) im `.data-theme="dark"` Root-Element deklariert. Das löst Redundanzen und verhindert Kaskaden-Bruch durch exzessives `!important`.
- **Badge Komponenten Extraktion:** Stark redundante 6-Klassen-Kombinationen für Status-Badges (z.B. `class="badge bg-theme-warning-subtle text-theme-warning border border-theme-warning-subtle"`) wurden zu sauberen abstrakten Komponenten zusammengefasst (z.B. `.badge-subtle-warning`). HTML-DOM Struktur in 5 Templates wurde massiv gestrafft.
- **Typografie und Layout System:** Duplizierte Inline-Styles für "Magic Number"-Abstände und Schriftgrößen (z.B. `style="font-size: 3.5rem; letter-spacing: -2px;"`) wurden in wiederverwendbare Klassen (`.display-counter`, `.status-label`, `.tracking-tight`, `.icon-box-lg`) abstrahiert und bereinigt.

## [2.9.5] - 2026-03-05

### 🧹 UI / CSS Refactoring & Tech Debt
- **Token Konsolidierung:** Messbare Redundanzen in `style.css` behoben (`body` Deklarationen zusammengelegt, re-deklarationen von `.text-muted` entfernt).
- **Template Cleanup:** Über 40 harte in-line `<styles>` mit Magic-Number Schriftgrößen (z.B. `0.875rem`) aus `index.html` und Folgeseiten in das externe Stylesheet `style.css` migriert.
- **Typografie (Presbyopie):** Einführung der zentralen Utility-Klassen `.text-meta` und `.font-mono`. Diese erzwingen eine Mindest-Schriftgröße von 14px (0.875rem) für sekundäre Metadaten (`Letzte Prüfung`, `WOCHEN`, etc.), was konsistent Altersweitsichtigkeit entgegenwirkt.
- **Theme Awareness:** Raw Bootstrap-Klassen wie `bg-danger-subtle` in den Badges (`FEHLT`, `DEFEKT`) wurden systemweit durch Theme-aware Klassen (`bg-theme-danger-subtle`) ersetzt. Dadurch können Kontraste im Dark Mode und High-Contrast Mode unabhängig vom Light Mode korrigiert werden. Die Override-Klasse `bg-white` wurde aus Card-Headern entfernt, was nativen Dark Mode in `check.html` ermöglicht.

## [2.9.4] - 2026-03-05

### ✨ UX Accessibility & Formatting (v3 "Blur/Presbyopia" Fixes)
- **Luminanz-Kontrast (Light Mode):** Der "Neue Prüfung" Button und der "Werkzeug austauschen" Button wurden von Ghost-Buttons in Solid-Buttons mit deutlich stärkerer Flächenfüllung (`#eef4ff`), dickerem Rand und fetterer Schriftklasse umgewandelt. Das verhindert, dass diese Buttons bei unkorrigierter Sehschwäche (Unschärfe-Test) visuell mit dem Seitenhintergrund verschmelzen.
- **Luminanz-Kontrast (Dark Mode):** Rote Gefahr-Badges ("Überfällig", "Fehlt") erhielten eine spezielle Luminanz-Korrektur für den Dark Mode. Um ein "Verbluten" (Verlust der Formenkontur) auf dem dunklen Hintergrund zu verhindern, wurde das Rot signifikant aufgehellt (`#ef4444`), mit einem hellroten Rand eingefasst und der Innen-Text zwingend auf reines Weiß (`#ffffff`) gesetzt (Schilder-Prinzip).
- Sämtliche subtilen Status-Borders (Grün, Gelb, Rot) wurden im Dark Mode in ihrer Deckkraft (`Opacity`) von 0.4 auf 0.8 angehoben, um als klarer abgegrenzte Form bei unscharfer Sicht zu fungieren.

## [2.9.3] - 2026-03-05

### ✨ UX Accessibility & Formatting (v2 Iteration)
- **Typografie (Presbyopie):** Die Schriftgröße und Strichstärke von Sekundärtexten und Metadaten (`Letzte Prüfung`, `Lehrjahr`) wurde systemweit auf ein gut lesbares Minimum von 14px normiert, um Altersweitsichtigkeit entgegenzuwirken.
- **Dark Mode Card Borders:** Zur besseren haptisch-visuellen Abgrenzung für Low-Vision-Nutzer wurden die primären Status-Indikatoren am linken Kartenrand von schwachen 2px auf solide 4px verdickt.
- **HC Mode Halation-Fix:** Der reine schwarze Hintergrund (`#000000`) im High Contrast Theme wurde durch einen ergonomischen Soft-Black-Ton (`#111111`) ersetzt, wodurch gelbe Neon-Schriften bei Makuladegeneration nicht mehr verschmelzen oder flimmern (Irradiation/Halation).
- **Dashboard Praxisnutzen:**
  - **Sortierung:** Das Dashboard sortiert Azubis nun intelligent (Überfällig > Mängel vorhanden > Alles OK).
  - **Hover-Tooltips:** Status-Badges erklären ihre Bedeutung nun auf nativem Wege bei Mouseover.
  - **"Overdue"-Fokus:** Karten von überfälligen Prüfungen erhalten subtil einen extrem sanften rötlichen Warnton im Hintergrund.

## [2.9.2] - 2026-03-05

### ✨ UX & Accessibility
- **Signaling First:** Status badges (GEPRÜFT, ÜBERFÄLLIG, FEHLT) now explicitly feature semantic icons (`✔`, `⚠`, `❌`). This critical fix resolves a WCAG accessibility violation where status was conveyed exclusively via color (Rot-Grün-Schwäche).
- **Legibility & Glare Reduction:**
  - Darkened secondary text (`--text-muted`) in Light and Dark mode to guarantee WCAG AA contrast ratios and fix Presbyopia legibility.
  - Reduced the blinding "Taschenlampen-Effekt" in the Light Theme by subtly tinting the backgrounds (`#f5f5f0` and `#fdfcfb`), aiding users with Cataracts (Grauer Star) on the shopfloor.

## [2.9.1] - 2026-03-02

### 🚨 Hotfix Release
- **Metrics Security:** Protected `/metrics` with `@admin_required` to prevent unauthorized access to monitoring data.
- **Secure Sessions:** Dynamically toggle `SESSION_COOKIE_SECURE` based on `REQUIRE_HTTPS` to unbreak local non-HTTPS development.
- **Bugfix (Prometheus):** Fixed the `ACTIVE_SESSIONS` gauge logic which incorrectly caused unbounded metrics inflation over time.
- **Bugfix (UI):** Fixed `history.html` broken layout by closing a missing `</div>` tag.
- **Bugfix (Export):** Resolved an issue where PDF exports failed in CI due to missing application contexts or invalid signature payloads.
- **Bugfix (UI):** Corrected a string comparison error in `history_details.html` related to `CheckType` enums.
- **Bugfix (Backup):** Updated `backup.py` to correctly respect `DATA_DIR` so standalone and Add-on backups both target the correct configuration and database paths.
- **UX (Exchange Modal):** Implemented a submit guard, loading spinner, and JS `confirm()` prompt for bulk tool returns to prevent accidental duplicate issues.
- **UX (Login):** Appended an explicit hint on the login screen regarding the default '0000' PIN.
- **Quality Gates:** Formatted the backend codebase (`autopep8`) and resolved all `flake8` warnings to enforce style consistency.

## [2.9.0] - 2026-03-01

### ✨ Features & UX Enhancements
- **Bulk Tool Exchange (Massenverarbeitung):** Overhauled the exchange modal to support selecting multiple tools concurrently. This eliminates the need for repetitive signatures and clicks for power users.
- **Dynamic Pricing:** The exchange modal now aggregates the estimated total replacement value in real-time as tools are selected via check boxes.
- **Progressive Disclosure UI:** Redesigned the "Tool Reason" selection to support a "Global Reason" up top with the option to override on an individual tool level natively within the Bento-style list.
- **Prometheus Metrics:** Integrated a `/metrics` endpoint to monitor application health, check submissions, durations, and scans natively.
- **Persistent Pagination Search:** Upgraded the UI search functionality. Database queries now process search terms server-side with a debounce, applying queries across all result pages instead of limiting filters to the visible HTML DOM.

### 🎨 Theming & Accessibility
- **High Contrast (HC) Mode Signature Polish:** Fixed signature rendering artifacts in High-Contrast Mode. The signature pad now enforces a pure black background with glowing Cyan ink and borders to prevent halation and maximize visibility.
- **Semantic Button Styling:** Refined button state logic to ensure the "Defekt" danger states correctly apply soft pastel-red backgrounds natively via RGB coordinates, circumventing Bootstrap 5 "Dark Mode Variable" invisibility issues.

### 🐛 Bug Fixes
- **Tools Table Search:** Corrected the client-side limitation where the UI search bar would only filter results located within the active 20-row pagination chunk.

## [2.8.0] - 2026-02-21

### Added
- **Authentication System:** New PIN-based login system for administrators (`routes/auth.py`) including session management and the `@admin_required` decorator.
- **Data Models:** Added `price` property to the `Werkzeug` model.
- **Data Models:** Added `manufacturer` property to the `Check` model.
- **PDF Reports:** Display the estimated replacement value on exchange protocols if the tool replacement is payable.
- **Performance:** New batch query (`get_assigned_tools_batch`) to fetch assigned tools for multiple apprentices more efficiently (prevents N+1 query performance issues).
- **System Initialization:** Automatic seeding of default system settings on first startup (e.g., default manufacturers and initial PIN hash).
- **Migration Mode:** Introduced the ability to temporarily bypass the signature requirement during data imports (`migration_mode`).

### Changed
- **Migrations:** Refactored database migration logic to use optimized helper functions (`_add_column_if_missing`) for cleaner schema updates.
- **Dev Server:** The local development server now starts in Adhoc SSL mode (`https://`) by default.

### Fixed
- **Database Locks:** Resolved errors caused by file locks (SQLite WAL Locks) during startup migrations by explicitly disposing of SQLAlchemy connections beforehand (`db.engine.dispose()`).
- **Backup Service:** Fixed `OSError` crashes when listing backups if files are moved or deleted while being read.
- **Cleanup:** Temporary PDF and signature files are now more reliably deleted when database transactions fail during the tool exchange process.

### Security
- **Reverse Proxy Support:** Integrated `werkzeug.middleware.proxy_fix.ProxyFix` to correctly process IP addresses and protocols behind Nginx or HAProxy.
- **Open Redirect Protection:** Added a validation function (`_is_safe_redirect`) to the login process to prevent malicious redirects to external domains.
- **Content-Security-Policy (CSP):** Added `unpkg.com` as a safe source for scripts and external connections in the CSP headers (for both Talisman and manual headers).

## [2.8.2-beta34] - 2026-02-28
### 🐛 Hotfix
- **Data Loss on Backup Restore (WAL/SHM ignored):** Fixed a critical bug in `BackupService.create_backup()` where only `werkzeug.db` was added to the ZIP archive, ignoring the `werkzeug.db-wal` (Write-Ahead Log) and `werkzeug.db-shm` files. Because SQLite operates in WAL mode, all recent data (up to the last checkpoint) lives in the WAL file. Creating or restoring a backup without it caused recent checks (up to two weeks old) to vanish. The archiver now includes `.db`, `-wal`, and `-shm` files. The restore process copies them back, or actively deletes existing local WAL files if the backup does not contain them (e.g. older v2.7.0 backups) to prevent DB corruption.

## [2.8.2-beta33] - 2026-02-28
### 🐛 Hotfix
- **504 Gateway Time-out on backup restore:** Replaced the immediate `sys.exit(1)` upon successful backup restore with a 2.0-second delayed `os._exit(1)`. The immediate exit caused Gunicorn to die before the HTTP 302 response could properly flush through NGINX to the browser, resulting in a 504 error instead of the success message and redirect. `os._exit(1)` also prevents the `CRITICAL:concurrent.futures:Exception in worker` log entry that `sys.exit(1)` caused in Gunicorn's thread pool.

## [2.8.2-beta32] - 2026-02-28
### 🐛 Hotfix
- **nginx 413 Request Entity Too Large on backup upload:** `client_max_body_size` was missing from the nginx config in `rootfs/etc/services.d/azubi-werkzeug/run` — nginx defaulted to 1 MB. Added `client_max_body_size 50m` to both the SSL and HTTP server blocks. 50 MB gives ample headroom for backup ZIPs (DB + signatures + reports). **Requires Add-on restart to take effect.**

## [2.8.2-beta31] - 2026-02-28 — RC1 Preparation
### 🐛 Bug Fixes
- **B-02: Root `tests/` deleted:** The root `tests/conftest.py` imported the old monolithic `app.py` (routes.py no longer exists since v2.7 blueprint split). Running `pytest` at repo root caused import errors. Directory removed, all tests are in `azubi_werkzeug_beta/tests/`.
- **B-03: History total count hint:** `history()` now also queries `total_count` before applying `.limit(2000)`. Template shows `"Neueste 2.000 von X Einträgen"` banner when the display limit is reached.
- **`/health` returns JSON:** Changed from plain text `"OK"` to `{"status": "ok", "version": "...", "uptime": ..., "db_ok": true}`. Returns 503 with `"degraded"` status on DB failure.

### 🧪 Tests
- **Rate limit regression:** `test_auth.py` — 6th wrong PIN within one burst must return 429.
- **Open redirect blocked:** `test_auth.py` — Login with `next=https://evil.com` must not redirect externally.
- **B-01 regression (4 cases):** `test_critical_fixes.py` — `is_migration_active()` correctly handles expired, valid, malformed and missing timestamps.
- **Zip Slip rejected:** `test_backup.py` — `BackupService.restore_backup()` rejects ZIP archives with path-traversal entries.

### 📦 Build
- **`pytest.ini` added:** `testpaths = azubi_werkzeug_beta/tests` — running `pytest` at repo root now always targets the correct test directory.

## [2.8.2-beta30] - 2026-02-28
### 🐛 Hotfix
- **B-01: `TypeError` in `services._handle_signatures` (migration mode broken via Service layer):** The inline migration check introduced in beta28 compared `time.time()` (Unix float) against `migration_mode_expires` which `admin.py` stores as `expires.isoformat()` (ISO datetime string). Python 3 raises `TypeError` for this comparison, silently breaking migration-mode bypass of the signature requirement in `CheckService`. Fixed by using `datetime.utcnow() < datetime.fromisoformat(...)` matching the identical logic already present in `routes/utils.py → is_migration_active()`.

## [2.8.2-beta29] - 2026-02-28
### 🛠 Code Quality
- **Quality gate compliance pass:** All 7 quality gates now pass.
  - **autopep8** applied recursively (PEP 8 formatting).
  - **Flake8** (`--max-line-length=120`): clean — removed unused `session` import from `routes/checks.py`.
  - **Pylint** 10.00/10 — same fix resolved the W0611 warning.
  - **pydocstyle** (PEP 257 convention): clean.
  - **Safety**: 0 known CVEs in `requirements.txt`.
  - **Xenon** CC ≤ B: extracted 5 helper functions from `checks.py` (`_parse_last_entry_status`, `_validate_signatures`, `_parse_session_checks`, `_collect_session_files`, `_log_session_deleted`) to reduce cyclomatic complexity from B(10) → B(8) on the most complex functions; module average now A (4.2).
  - **Radon MI**: all modules grade A.

## [2.8.2-beta28] - 2026-02-28
### 🐛 Hotfix
- **Startup crash — circular import in `services.py`:** beta27 introduced `from routes.utils import is_migration_active` into `services.py`. Because `routes/` imports from `services`, this created a circular import (`services` → `routes.utils` → `routes/__init__` → `routes/dashboard` → `services`) and crashed Gunicorn on startup with `ImportError: cannot import name 'CheckService'`. Fixed by inlining the migration-expiry check directly in `services._handle_signatures`, removing the cross-layer import.

## [2.8.2-beta27] - 2026-02-28
### 🐛 Bug Fixes
- **Double-click protection on Check/Issue/Return form:** After a valid submission the submit button is immediately disabled and replaced with a loading spinner, preventing duplicate check records from PDF generation latency.
- **`detect_exchange_type` returns `CheckType` enum:** Previously returned the raw string `'exchange'` instead of `CheckType.EXCHANGE`. Fixed for type safety and to prevent silent breakage on refactoring.
- **`settings.html` extra closing `</div>`:** Removed one superfluous `</div>` at the end of the file that caused an unbalanced DOM tree (masked by browser tolerance).
- **Debug `console.log` statements removed from `tools.html`:** Five leftover development `console.log('DEBUG: ...')` statements are no longer printed to the browser console in production.

### 🔒 Security / Ops
- **Multi-worker startup guard:** `app.py` now logs a `CRITICAL` message at startup if `GUNICORN_WORKERS > 1` is detected, warning that the in-memory tool-assignment cache is process-local and will cause inventory inconsistencies.

### 📦 Build
- **`.dockerignore` added:** `final_polish.py`, `score_check.py`, `verify_setup.py` are now excluded from the Docker image via `.dockerignore`, reducing image size and attack surface.

## [2.8.2-beta26] - 2026-02-28
### 🔒 Security
- **Rate limit on `/login`:** Added `@limiter.limit("5 per minute")` to the login route. Previously there was no brute-force protection — all 10,000 four-digit PIN combinations could be tried in ~100 seconds.
- **`SESSION_COOKIE_SECURE` enabled:** Session cookies are now sent with the `Secure` flag in production. Set `FLASK_ENV=development` to disable for local HTTP debugging.

### 🐛 Bug Fixes
- **`session` variable shadowing in `history.html`:** The loop variable `{% for session in sessions %}` was overwriting the Flask/Jinja context variable `session`, causing the migration mode badge to read from the loop dict instead of the Flask session. Renamed to `check_session`.
- **`data-price` HTML attribute escaping in `tools.html`:** Inner double quotes in the Jinja expression `data-price="{{ "%.2f"|format(...) }}"` split the attribute across two tokens. The browser parsed an incorrect price value. Fixed by using single quotes inside the Jinja expression.
- **`repository.yaml` placeholder values:** Replaced `USERNAME/REPOSITORY` and `Your Name <your@email.com>` with real values. HA Add-on Store validation would have failed with the placeholders.

## [2.8.2-beta25] - 2026-02-28
### ✨ Features
- **Auto-logout after 8 hours:** Admin sessions now automatically expire 8 hours after login. Flask's `PERMANENT_SESSION_LIFETIME` is set to 8 hours and `session.permanent = True` is set on successful login.
- **Migration mode auto-expiry:** When migration mode is activated, an expiry timestamp (8 hours from now) is stored in the session. A new `is_migration_active()` helper in `routes/utils.py` checks this timestamp on every access and silently clears migration mode when it has elapsed. This replaces all direct `session.get('migration_mode')` calls in `routes/checks.py` and `services.py`.

### 🐛 Hotfix
- **Reverted port 5001:** Removed the HTTP→HTTPS redirect NGINX block and `5001/tcp` from `config.yaml` introduced in beta24. Direct HTTPS access via `https://<host>:5000/` is the intended path when SSL is enabled.

## [2.8.2-beta24] - 2026-02-28
### 🐛 Hotfix
- **SSL mode: HTTP 400 on port 5000:** When `ssl: true` is configured, NGINX was listening on port 5000 with SSL only. Accessing the add-on via plain `http://` resulted in a cryptic `400 Bad Request - The plain HTTP request was sent to HTTPS port`. Added a second NGINX server block on port 5001 that issues a `301` redirect to `https://$host:5000`. Port 5001 is now declared in `config.yaml`.

## [2.8.2-beta23] - 2026-02-28
### 🐛 Hotfix
- **Ingress: Post-login 404 error:** Fixed a `404 Not Found` error after entering the PIN when accessing the app via Home Assistant Ingress. Two root causes were addressed:
  1. `_is_safe_redirect` was comparing the internal `host_url` netloc against the external Ingress URL, causing the check to always fail. The redirect target was discarded and the fallback redirected to `/` (no Ingress prefix), resulting in a 404. The check now additionally trusts URLs whose path starts with the current `X-Ingress-Path` prefix.
  2. The fallback redirect after login and the logout redirect both now prepend the `X-Ingress-Path` header value before calling `url_for`.

## [2.8.2-beta22] - 2026-02-28
### 🐛 Hotfix
- **Ingress: Settings 404 error:** Fixed a `404 Not Found` error when clicking "Einstellungen" (Settings) via Home Assistant Ingress. The `@admin_required` decorator was redirecting unauthenticated users to `/login` without prepending the Ingress path prefix. The redirect now correctly reads the `X-Ingress-Path` header and constructs the login URL accordingly.

## [2.8.2-beta21] - 2026-02-21
### ✨ Quality Gates & Cleanup
- **Code Quality:** Systematically cleared all Pylint, Xenon, Radon, and Flake8 warnings to achieve a perfect 10.00/10 Score and a Grade A/B Maintainability Index.
- **Refactoring:** Removed redundant `pylint: disable` comments, fixed remaining broad-exception blocks structurally where applicable, and extracted API formatters to reduce Cyclomatic Complexity.
- **Cleanup:** Added `lint_report*.txt` to `.gitignore` and removed leftover lint/QA files to keep the repository clean.

## [2.8.2-beta20] - 2026-02-21
### ✨ Security & Performance Polish
- **Dependency / Stability:** Fixed a runtime crash when generating QR codes in Alpine Docker by adding the `[pil]` extra to `qrcode` inside `requirements.txt`.
- **Database Stability:** Prevented double SQLite migration initializations by removing the redundant manual `setup_database()` invocation in the `run` script.
- **Performance Optimization:** Eliminated a severe N+1 database query bottleneck in the frontend Check page (`routes/checks.py`). The tool status list now uses a highly efficient grouped SQLAlchemy Subquery.
- **Logic:** Fixed a bug in `detect_exchange_type` where string comparisons to Enum keys always failed.
- **Stability:** Fixed a Time-of-Check to Time-of-Use (TOCTOU) file deletion race condition in `BackupService.list_backups()` that could crash the settings page.
- **Documentation:** Removed the outdated `safety_report.json` file.

## [2.8.2-beta19] - 2026-02-21
### ✨ Final Audit Fixes & Performance
- **Security:** Patched an Open Redirect vulnerability in `routes/auth.py` by strictly validating the `next` URL parameter to ensure it remains on the same host before redirecting after login.
- **Security:** Prevented a potential information leak in production by stripping the raw exception traceback (`{{ error }}`) from `500.html` unless `config.DEBUG` is active.
- **Security:** Pinned all third-party dependencies in `requirements.txt` to exact known-safe versions to prevent supply-chain attacks and ReDoS vulnerabilities in unpinned packages like `fpdf2`.
- **Database Stability:** Patched a critical `NameError` crash in `app.py`'s `setup_database()` routine that could crash Gunicorn workers if `sqlite3.connect` threw an exception.
- **Database Stability:** Resolved a race condition where the raw sqlite3 migration connection conflicted with the active SQLAlchemy WAL transaction by explicitly disposing the SQLAlchemy engine pool before migrations.
- **Performance Optimization:** Eliminated a severe N+1 database query bottleneck in the frontend dashboard. The system now fetches all "assigned tool counts" for every Azubi in a single batched query instead of firing individual queries per apprentice on cold cache.
- **Performance Optimization:** Eliminated a duplicate N+1 database query inside the API loop returning assigned tools (`routes/api.py`), replacing it with a single, highly efficient SQLAlchemy Subquery.
- **UI & Accessibility:** Fixed unclosed grid rows in `history.html` that broke responsive layouts. Fixed missing title tags in `base.html` and corrected ARIA roles on the main navigation. Fixed a bug in `check.html` where tech parameters were erroneously forced as `required` even for completely verified tool rows.

## [2.8.2-beta18] - 2026-02-21
### ✨ Consistency Polish
- **Input Consistency:** Aligned the "Edit Tool" modal's Price field with the creation form. It now uses `inputmode="decimal"` and processes comma separators in the backend to ensure a frictionless mobile UX and zero HTML5 validation errors when entering values like `15,99`.

## [2.8.2-beta17] - 2026-02-21
### ✨ Release Candidate Polish
- **Mobile UX:** Fixed a severe scroll lockout on smartphones inside the "Exchange Tool" modal by adding `touch-action: none;` to the signature canvas (`index.html`).
- **Signature Distortion:** Switched the auto-resize listener mechanism in `check.html` from preserving pixel bitmaps via `toDataURL()` to preserving the original vector coordinates via `toData()`. This guarantees razor-sharp signature repainting without any aspect ratio distortion when rotating a tablet between portrait and landscape.
- **Accessibility:** Added dynamically populated `aria-label` tags to the individual tool selection checkboxes and the "Select All" checkbox. Screenreaders will now precisely announce the tool's designation when navigating the list.
- **Input Flexibility:** Changed the "Price" input type to `text` with `inputmode="decimal"` and added backend sanitization (`api.py`) to flawlessly support comma-separated European decimal inputs (`15,99`) on HTML5 without triggering silent validation bypasses or input truncation.

## [2.8.2-beta16] - 2026-02-21
### 🐛 Hotfixes
- **CSRF Token Validation:** Fixed a severe `400 Bad Request: The referrer does not match the host.` CSRF error that surfaced when accessing the system directly via local IP and port 5000. The internal NGINX proxy was aggressively stripping the port from the `Host` header (`$host`), breaking the Flask-WTF Referrer boundary check. The NGINX config now passes the exact `Host` header via `$http_host`.

## [2.8.2-beta15] - 2026-02-21
### 🚀 UX & Stability
- **AJAX DOM Generation:** Fixed invalid HTML DOM generation (`<td><td class='text-end'>`) when adding Azubis/Examiners via AJAX, preventing page layout destruction (`personnel.html`).
- **Safari/iOS Compatibility:** Replaced `style.display='none'` on `<optgroup>` elements with robust `disabled` and `hidden` properties to prevent iOS Safari users from selecting invalid defect reasons in the check workflow (`check.html`).
- **Form Validation Lockout:** Disabled input fields and select tags dynamically inside hidden table rows to prevent silent HTML5 "invalid form control is not focusable" locking submissions (`check.html`).
- **Modal Stability:** Handled empty or invalid `azubiId` parameters with an early return in asynchronous tool fetching (`index.html`).

### 🔒 Security
- **Pinned Dependencies:** Pinned `html5-qrcode` scanning library to version `@2.3.8` on unpkg CDN to enforce dependency security and eliminate HTTP 302 redirects for performance (`scanner.html`).

## [2.8.2-beta14] - 2026-02-21
### 🔒 Security
- **QR Scanner:** Fixed a DOM-based XSS vulnerability by avoiding `innerHTML` when displaying unrecognized QR codes. URLs are now also securely URL-encoded on redirect.
  
### 🚀 UX & Performance
- **Search Filters:** Fixed layout thrashing and massive memory leaks in table searches (`tools.html`, `personnel.html`) by implementing proper debounce timers (200ms).
- **Scanner Modal:** Fixed a resize glitch where the signature canvas in the exchange modal calculated its size as 0 width. Transitioned the listener from `show` to `shown` for exact DOM sizing.
- **Dependencies:** Deduplicated script loads. The index page now uniformly uses `signature_pad@4.1.7` instead of loading redundant older versions.

### 🐛 Bugfixes
- **Pricing:** Fixed a critical bug where the "Preis" field was entirely missing from the frontend AJAX injection and backend model logic upon new tool creation. The DB and UI now correctly propagate the price.
- **Form Validation:** Improved the fallback placeholder value for assigned tools to `value=""`, which securely hooks into HTML5 `required` validation.
- **Accessibility:** Added compliant ARIA attributes (`aria-label`, `role="img"`) to all signature canvas elements for screenreader compatibility.

## [2.8.2-beta13] - 2026-02-21
### 🐛 Hotfixes
- **Add-on Missing Dependency:** Fixed a container startup crash where `nginx` was not installed in the Docker image, leading to a `No such file or directory` error when trying to write the NGINX configuration. Added `nginx` to the Dockerfile and ensured config directories are created.

## [2.8.2-beta12] - 2026-02-21
### 🐛 Hotfixes
- **Add-on Startup Script:** Fixed a bash syntax error (`unexpected token else`) in the Add-on startup script (`run`) introduced in beta11 when configuring the SSL certification block.

## [2.8.2-beta11] - 2026-02-21
### 🐛 Hotfixes
- **Add-on Ingress + SSL Compatibility:** Fixed a severe issue where enabling SSL in the Home Assistant Add-on caused the addon to abruptly crash Home Assistant Ingress traffic, flooding the logs with `[SSL: HTTP_REQUEST]`. 
  - The application is now served securely behind an internal NGINX reverse-proxy, ensuring external local access responds over HTTPS while keeping Ingress HTTP traffic flowing smoothly. 
  - Integrated `ProxyFix` to parse accurate user IPs from Home Assistant through the Nginx proxy, fixing potential rate-limit bugs.

## [2.8.2-beta10] - 2026-02-21
### 🚀 Enhancements
- **Add-on Local SSL Support:** Fixed an issue where enabling `ssl: true` in the Home Assistant Add-on configuration without providing valid Let's Encrypt certificates would cause Gunicorn to crash or fail to provide HTTPS. The Add-on's startup container now includes `openssl` and will automatically generate a temporary self-signed certificate (`adhoc`) if the configured certificates are missing. This allows local direct IP access over HTTPS (e.g. `https://<ip>:5000`) for camera testing out-of-the-box.

## [2.8.2-beta9] - 2026-02-20
### 🚀 Enhancements
- **Standalone Mode Settings:** In development/standalone mode (`app.py` execution), the server now spins up with a temporary ad-hoc SSL certificate (`ssl_context='adhoc'`). This solves the problem of testing camera functionality on other devices within the local network, as mobile browsers strictly require a secure `https://` context to access `navigator.mediaDevices`. Added `pyOpenSSL` to dependencies.

## [2.8.2-beta8] - 2026-02-20
### 🚀 Enhancements
- **Scanner Mobile Optimization:** Implemented several HTML5-QRCode best practices for mobile usage:
  - **Battery Saving:** The camera stream is now explicitly stopped immediately upon a successful scan, saving battery life.
  - **Haptic Feedback:** Added device vibration on successful scan if supported by the browser.
  - **Aspect Ratio:** Enforced a predictable 1.0 aspect ratio for the camera feed.

## [2.8.2-beta7] - 2026-02-20
### 🐛 Hotfixes
- **Ingress Support:** Fixed an issue where saving settings (e.g. Backups, Manufacturers, Pins) in Home Assistant Ingress would result in a `404 Not Found` error due to missing `ingress_path` prefixes on the redirect URLs.

## [2.8.2-beta6] - 2026-02-20
### 🐛 Hotfixes
- **Scanner UI:** Fixed an issue where the QR scanner on PC/Desktop would focus but fail to scan. This was caused by the experimental BarcodeDetector API failing silently on some Chromium browsers and a rigid scan box size. The scanning area (`qrbox`) now scales dynamically (70% of screen size) to make scanning much easier, and experimental features were disabled. Added visual feedback for unrecognized QR formats.

## [2.8.2-beta5] - 2026-02-20
### 🚀 Enhancements
- **Scanner UI:** Replaced the default camera dropdown selection menu. The scanner now automatically selects the back camera (`environment`) on mobile devices, providing a faster and more user-friendly scanning experience.

## [2.8.2-beta4] - 2026-02-20
### 🐛 Hotfixes
- **Scanner UI:** Fixed a critical issue where the QR code scanner failed to load completely. The `html5-qrcode` script was being blocked from loading by the Content-Security-Policy (CSP) because `unpkg.com` was missing from the allowed `script-src` and `connect-src` headers.

## [2.8.2-beta3] - 2026-02-20
### 🐛 Hotfixes
- **Scanner UI:** Fixed an issue where the camera permission requests or scanner errors were invisible due to a black background.
- **Iframe Camera Lock:** Added explicit detection for Home Assistant Ingress aggressively blocking the camera via iFrame permissions. The UI now shows a helpful error asking the user to open the Addon in a new tab if blocked.

## [2.8.2-beta2] - 2026-02-20
### 🐛 Hotfixes
- **Ingress Support:** Fixed `404 Not Found` error in the QR Code Scanner by prepending `ingress_path` to all related URLs.
- **Scanner Access:** Added a clear warning message when the camera is blocked due to missing HTTPS (secure context).

## [2.8.2-beta1] - 2026-02-20
### ✨ Features & Enhancements
- **QR Code Generation:** Added a UI to select specific Azubis for QR code generation in settings.
- **Tool Exchange:** Added price display in the exchange modal showing the estimated tool value.
### 🐛 Bug Fixes
- **PDF Generation:** Fixed a PDF encoding error by replacing the '€' symbol with 'EUR'.
- **UI:** Added "Select All" toggle for faster bulk QR generation.

## [2.8.1] - 2026-02-20
### Security
- **Critical:** Fixed Broken Access Control by enforcing `@admin_required` on all modification routes and API endpoints.
- **Medium:** Fixed DOM-based XSS vulnerability in `tools.html` by safely handling tool names with quotes.
- Enforced PNG format for logo uploads to prevent file type inconsistencies.

### Fixed
- Fixed "Tool Exchange" on Dashboard by making `get_assigned_tools` public (removing `@admin_required`).
- Fixed "Signature Skip" in Migration Mode (server now accepts empty signatures when migration is active).
- Fixed HTML structure error (nested `<td>`) in tools table.
- Implemented system restart after backup restoration to ensure configuration reload.

## [2.8.0-beta5] - 2026-02-19
### Fixed
- Fixed missing "Preis" table header in `tools.html`.

## [2.8.0-beta4] - 2026-02-19
### Fixed
- Fixed critical 500 error on Login page due to missing CSRF token.

## [2.8.0-beta3] - 2026-02-19
### Fixed
- Fixed `404` page crashing with `BuildError` (referenced wrong endpoint).
- Fixed "Archiv" filter in Admin/Personnel view to correctly show *only* archived users.
- Fixed "Neuer Azubi" button on Dashboard (added missing `addAzubiModal`).

## [2.8.0-beta2] - 2026-02-19
### 🐛 Hotfixes
- **Crash Fix:** Added missing `404.html` template to prevent 500 Internal Server Error on invalid routes.
- **Session Stability:** Implemented persistent `secret.key` generation in `DATA_DIR` to ensure sessions survive restarts without breaking Docker builds.

## [2.8.0-beta1] - 2026-02-19

### 🛡️ Quality & Security (Phase 5)
- **Code Quality:** Achieved **10/10 Pylint score** across all core modules. passed Flake8, pydocstyle, Xenon (Complexity), and Radon (Maintainability) gates.
- **Dependency Hardening:** Pinned all dependencies in `requirements.txt` and hardened `Dockerfile` with explicit pip upgrades.
- **Security:** Fixed `gunicorn` vulnerability (PVE-2024-72809) by upgrading to v23.0.0.
- **Refactoring:** significantly reduced complexity in `app.py` and `services.py`.
- **Price Monitoring:** Added `price` field to tools. Exchange transactions now calculate and display estimated replacement costs for "Payable" exchanges.
- **Manufacturer Tracking:** Added `manufacturer` field to checks. Includes smart presets (Wera, Wiha, etc.) and custom input, configurable via settings.
- **Admin Authentication:** Secure PIN-based login (default: `0000`) for all admin routes. PIN can be changed in settings.
- **QR Code System:**
  - **Generator:** Creates PDF with Azubi QR codes (`AZUBI:<id>`) in Avery B5274-50 layout.
  - **Scanner:** Integrated camera scanner (`/scanner`) using `html5-qrcode` to quickly find Azubi check pages.
- **Dashboard Enhancements:** Added "QR Scan" and "New Azubi" buttons to the main header for quicker access.

### 🛡️ Security
- **Admin Protection:** All management routes now require session-based authentication via `@admin_required` decorator.
- **Secure PIN:** PINs are stored as SHA-256 hashes (pbkdf2) in the database.

### 🐛 Fixes
- **Exchange Modal:** Fixed sorting of assigned tools (Missing > Broken > Ok) to prioritize critical items.
- **Code Quality:** Comprehensive refactoring of `routes.py`, `pdf_utils.py`, and `services.py` to meet strict Pylint (10/10) standards.

---

## [2.7.0] - 2026-02-18

> Stable release consolidating all changes from v2.7.0-beta1 through v2.7.0-rc10.

### ✨ New Features
- **Auto-Backup Scheduler:** Backups can be scheduled directly from the UI (Daily/Weekly at configurable times).
- **Disaster Recovery (Restore):** Admins can upload a backup ZIP to restore the entire system (Database, Config, Signatures, Reports). Triggers an automatic application restart.
- **Retention Policy:** Automatic deletion of old backups (configurable, default: 30 days).
- **Reports in Backups:** Backups now include the `reports/` directory (PDFs), preserving full compliance history.

### 🔒 Security
- **Zip Slip Protection:** Hardened `rollback.py` and `services.py` against path traversal attacks during zip extraction.
- **DoS Protection:** Limited `session_id` length to 64 characters; implemented `WTF_CSRF_TIME_LIMIT` (7 days); added `MAX_CONTENT_LENGTH` (16 MB).
- **Image Validation:** Strict Magic Bytes AND EOF checks in logo upload (`routes/admin.py`) to prevent Polyglot file attacks.
- **Input Validation:** Enforced explicit arguments in `process_check_submission` to prevent unexpected kwargs injection.
- **Dependency Vulnerability:** Upgraded `gunicorn` from `==21.2.0` to `>=22.0.0` to fix CVE-2024-1135 and CVE-2024-6827 (HTTP Request Smuggling).
- **Signature Validation:** Enforced server-side validation for signature presence in `submit_check`.
- **Generic API Errors:** API endpoints now return generic error messages to prevent information leakage.
- **Atomic File Cleanup:** `delete_session` performs database deletion before file cleanup, preventing data inconsistency.
- **Row Locking:** Implemented `with_for_update()` in `SystemSettings.set_setting` to prevent concurrent write conflicts.

### 🛡️ Stability & Robustness
- **Startup Crash:** Automatic `DATA_DIR` creation in `app.py` to prevent `FileNotFoundError` on fresh installs.
- **Gunicorn Compatibility:** `setup_database()` runs on application import (guarded), ensuring migrations complete on all Gunicorn workers.
- **Concurrency:** Double-check locking in `services.py` to prevent race conditions during cache population.
- **Race Condition:** Moved `invalidate_cache()` after DB commit in `routes/admin.py` to ensure fresh data.
- **Context Safety:** `get_backup_dir` uses `Config` instead of `current_app`, fixing `RuntimeError` in APScheduler context.
- **Scheduler Persistence:** Backup schedules now survive application restarts.
- **Transactional Migrations:** Database migrations are wrapped in a transaction with automatic rollback on failure.
- **Secret Key Logging:** Added critical logging for `OSError` when writing `secret.key` to prevent silent session invalidation.

### 📊 Data Integrity
- **File Leaks:** Reliable cleanup of signature files and PDFs if database commit fails in `services.py`.
- **CheckType Normalization:** Implemented `parse_check_type` to robustly handle Enum vs. String mismatches in database records, fixing report generation errors.
- **Logic Fixes:** Replaced fragile string comparisons with robust `CheckType` enum handling across the entire application.
- **Transaction Safety:** PDF is now generated *before* DB lock in tool exchange to prevent partial data states.
- **Atomicity:** `submit_check` is fully atomic — all-or-nothing to prevent Ghost Checks.

### 🐛 Bug Fixes
- **Import Fixes:** Corrected missing exports in `app.py` causing `ImportError` in `verify_setup.py`.
- **Dead Code:** Removed obsolete `check_date` guards and redundant debug endpoints.
- **Pagination:** Fixed edge case where accessing a page beyond total pages caused errors.
- **CheckType Default:** Fixed Enum vs. String mismatch in `models.py` default values.
- **Extension Init Order:** Fixed initialization order of Flask extensions preventing `SQLAlchemy` context errors.

### 🏗️ Architecture
- **Blueprint Split:** Monolithic `routes.py` (1200+ lines) split into modular sub-modules: `routes/dashboard.py`, `routes/checks.py`, `routes/admin.py`, `routes/api.py`, `routes/utils.py`.
- **Service Layer:** Complex exchange logic fully extracted from routes into `CheckService`.
- **Centralized Config:** `DATA_DIR` and `DB_PATH` logic unified in `Config` class. Configurable `HA_OPTIONS_PATH` via environment variable.

### ✅ Code Quality
- **Pylint:** 10.00/10 across all core modules.
- **Flake8:** Fully clean at `--max-line-length=120`.
- **Docstrings (PEP 257):** Imperative mood, proper blank lines, and consistent formatting in all Python files.
- **Pylint Disable Audit:** Reviewed all 44 `pylint: disable` comments — removed 4 unnecessary suppressions, 37 remain as justified.
- **Formatting:** `autopep8` applied across the entire codebase.

### 🧪 Tests
- Added `tests/test_critical_fixes.py` to verify cache invalidation, type normalization, and CheckType parsing.
- Fixed broken Enum assertions in `test_check_service.py`.
- Improved `conftest.py` and test configurations.

## [2.7.0-rc10] - 2026-02-18
### Security
- **Dependency Vulnerability:** Upgraded `gunicorn` from `==21.2.0` to `>=22.0.0` to fix CVE-2024-1135 and CVE-2024-6827 (HTTP Request Smuggling).

### Improved
- **Docstring Compliance (PEP 257):** All Python files now use imperative mood, proper blank lines, and consistent formatting.
- **Flake8 Compliance:** Resolved all violations (E501, F841, F401) across test files. Codebase is fully flake8-clean at `--max-line-length=120`.
- **Pylint Disable Audit:** Reviewed all 44 `pylint: disable` comments. Removed 4 unnecessary suppressions (`line-too-long`, `import-outside-toplevel`, overly broad `too-few-public-methods`, misplaced docstring suppress). 37 remain as justified.
- **Code Quality:** Pylint score maintained at 10.00/10.

## [2.7.0-rc9] - 2026-02-17
### Security
- **Zip Slip Protection:** Hardened `rollback.py` and `services.py` against path traversal attacks during zip extraction.
- **DoS Protection:** Limited `session_id` length to 64 chars in `checks.py` and implemented `WTF_CSRF_TIME_LIMIT` (7 days) to prevent session expiry DoS.
- **Image Validation:** Implemented strict Magic Bytes AND EOF checks in `routes/admin.py` to prevent Polyglot file attacks.
- **Input Validation:** Enforced explicit arguments in `process_check_submission` to prevent injection of unexpected kwargs.

### Stability & Robustness
- **Startup Crash:** Added automatic creation of `DATA_DIR` in `app.py` to prevent `FileNotFoundError` on fresh installs.
- **Gunicorn Compatibility:** Ensured `setup_database()` runs on application import (guarded) to support Gunicorn workers.
- **Concurrency:** Implemented double-check locking in `services.py` to prevent race conditions in cache population.
- **Race Condition:** Moved `invalidate_cache()` after DB commit in `routes/admin.py` to ensure fresh data is fetched.
- **Context Safety:** Refactored `get_backup_dir` to use `Config` instead of `current_app`, fixing `RuntimeError` in scheduler context.

### Data Integrity
- **File Leaks:** Implemented reliable cleanup of signature files and PDFs if database commit fails in `services.py`.
- **Logic Fixes:** Replaced fragile string comparisons with robust `CheckType` enum handling in `services.py` and tests.
- **Tests:** Fixed broken Enum assertions in `test_check_service.py`.

### Fixes
- **Imports:** Corrected missing exports in `app.py` causing `ImportError` in `verify_setup.py`.
- **Refactoring:** Removed dead code (`check_date` checks) and improved code clarity in `services.py`.
### Improved
- **Code Quality:** All core Python modules now exceed Pylint 9.6, with `models.py`, `forms.py`, and `extensions.py` scoring a perfect 10.00.
- **Formatting:** Applied `autopep8` across the entire codebase for consistent style.
- **Refactoring:** Improved `verify_setup.py` and test configurations.

## [2.7.0-rc3] - 2026-02-16
### Critical Fixes
- **Cache Invalidation:** Fixed "Ghost Inventory" bug by centralizing cache logic in `CheckService` and ensuring invalidation on all state changes.
- **Transactional Migrations:** Database migrations are now wrapped in a transaction with automatic rollback on failure to prevent partial schema updates.
- **Secret Key Logging:** Added critical logging for `OSError` when writing `secret.key` to prevent silent failures and session invalidation.
- **CheckType Normalization:** Implemented `parse_check_type` to robustly handle Enum vs String mismatches in database records, fixing report generation errors.

### Security & Reliability
- **Atomic File Cleanup:** Refactored `delete_session` to perform database deletion before file cleanup, preventing data inconsistency.
- **Signature Validation:** Enforced server-side validation for signature presence in `submit_check`.
- **Race Condition Fix:** Implemented row locking logic (`with_for_update`) for `SystemSettings.set_setting` to prevent concurrent write conflicts.

### Verification
- Added `tests/test_critical_fixes.py` to verify cache invalidation and type normalization logic.

## [2.7.0-rc2] - 2026-02-16
### Fixed
- **Critical**: Restored `routes.py` from truncation and verified integrity.
- **Refactor**: Completed comprehensive Pylint refactoring for `routes.py` (Score: 9.51), ensuring all core modules now meet the > 9.5 quality standard.
- **Cleanup**: Removed unused imports, fixed indentation, and resolved variable shadowing across the codebase.

## [2.7.0-rc1] - 2026-02-16
### Fixed
- **Critical**: Restored scheduler persistence (backups now survive restarts).
- **High**: Fixed database transaction risk during PDF generation (PDFs now generated before DB lock).
- **High**: Unified configuration logic for `DATA_DIR` across application.
- **Security**: Added `MAX_CONTENT_LENGTH` (16MB) to prevent DoS via large uploads.

## [2.7.0-beta7] - 2026-02-16
### Improved
- **Code Quality**: Achieved Pylint score > 9.0 across all core modules (Aggregate: 9.53/10).
- **Refactor**: Comprehensive cleanup of `routes.py`, `app.py`, and `pdf_utils.py` to meet strict quality standards.

## [2.7.0-beta6] - 2026-02-16
### Improved
- **Code Quality**: Achieved Pylint score > 8.0 (from 5.6) across all Python modules.
- **Refactor**: Fixed indentation, whitespace, line lengths, and import sorting.
- **Docs**: Added module and class docstrings to `extensions.py`, `forms.py`, `routes.py`, `models.py`, `app.py`, `services.py`.

## [2.7.0-beta5] - 2026-02-16
### Fixed
- **Lint**: Fixed IndentationError and SyntaxError issues in `app.py`, `routes.py`, and `services.py`.
- **Refactor**: Improved `pdf_utils.py` code quality (Imports, Docstrings, Exception Handling).
- **Fix**: Corrected initialization order of flask extensions in `app.py` (SQLAlchemy Context Error).

## [2.7.0-beta4] - 2026-02-16
### Fixed
- **Security**: Generic error messages for API endpoints (prevent info leakage).
- **Refactor**: Centralized `DATA_DIR` and `DB_PATH` logic in `Config` class.
- **Refactor**: Removed dead code/comments in `services.py`.
- **Improvement**: Added Google-style docstrings to `BackupService`.
- **Improvement**: Configurable Home Assistant options path via `HA_OPTIONS_PATH`.

## [2.7.0-beta3] - 2026-02-16
### Fixed
- **Bug**: Fixed `CheckType` parsing vulnerability (Unhandled Exception).
- **Refactor**: Aligned atomicity in `submit_check` (All-or-Nothing to prevent Ghost Checks).
- **Bug**: Fixed typo in `routes.py` (`import time`).
- **Dependency**: Added `Flask-APScheduler` to `requirements.txt`.

## [2.7.0-beta2] - 2026-02-16
### Fixed
- **Critical**: Fixed `IndentationError` in `app.py` preventing startup.
- **Critical**: Fixed atomicity violation in `submit_check` (Ghost Checks).
- **Critical**: Implemented missing `restore_backup` and `prune_backups` methods.
- **Security**: Added Zip Slip protection to restore function.
- **Security**: Fixed resource leak in file upload (restore).
- **Stability**: Added `threading.Lock` to tool cache to prevent race conditions.
- **Bug**: Fixed `CheckType` default value in models (Enum vs String).
- **Bug**: Fixed pagination edge case for empty databases.
- **Bug**: Fixed missing `time` import in `routes.py`.
- **Bug**: Added explicit null handling for PDF generation.
- **Improvement**: Robust handling for `CheckType` and `tool_id` parsing.
- **Improvement**: Backup now supports HA Add-on config (`options.json`).

## [2.7.0-beta1] - 2026-02-16

### ✨ New Features (Advanced Backup)
- **Auto-Backup Scheduler:** Backups can now be scheduled directly from the UI (Daily/Weekly at specific times).
- **Disaster Recovery (Restore):** Added "Restore" functionality. Admins can upload a backup ZIP to restore the entire system (Database, Config, Signatures, Reports). **Note:** Triggering a restore will restart the application.
- **Retention Policy:** Added automatic deletion of old backups (configurable, default: 30 days).
- **Reports Backup:** Backups now include the `reports/` directory (PDFs), ensuring full compliance history is preserved.

## [2.6.2] - 2026-02-16

### 🚀 New Features
- **Backup Manager:** Added a manual backup system in Settings. Users can now create, list, and download backups of the database + signatures directly from the UI.

### 🛡️ Security & Stability
- **Transaction Safety:** Rewrote the tool exchange logic (`exchange_tool`) to ensure "All-or-Nothing" transactions. Database records are now only committed *after* the PDF report is successfully generated, preventing corrupt data states.
- **Input Validation:** Added strict validation for custom dates in Migration Mode to prevent data corruption from invalid formats.
- **Cache Invalidation:** Fixed "Ghost Inventory" bug where issued tools didn't appear immediately. The inventory cache is now properly cleared after every transaction.

### 🐛 Bug Fixes
- **PDF Download:** Fixed `404 Not Found` error when downloading reports by correcting the file path resolution logic.
- **PDF Styling:** Fixed visual regression where defective tools in exchange reports were not highlighted in red.
- **Inventory List:** Fixed an issue where the tool list was empty due to case-sensitivity mismatches in `CheckType` checks.
- **Merge Cleanup:** Removed duplicate error handling code in the exchange route.

### ♻️ Refactoring
- **Service Layer:** Moved complex exchange logic from `routes.py` to `CheckService` for better maintainability and testing.

## [2.6.0] - 2026-02-15

### 🚀 Stable Release
- **Feature Complete:** Includes all improvements from the beta phase (v2.6.0-beta1 to -rc2).
- **Checks:** Implemented robust PDF generation and data validation.
- **Security:** Added CSRF protection and rate limiting.
- **Tools:** Added one-click exchange feature.

## [2.6.0-rc2] - 2026-02-15

### 🛡️ Final Polish
- **Exchange Tool:** Added missing Azubi existence check to prevent errors.
- **PDF Utils:** Added logging for missing tool data (name/category) to aid debugging.
- **UX:** Improved error message when PDF generation fails.

## [2.6.0-rc1] - 2026-02-15

### 🛡️ Stability & Security
- **Exchange Tool Fixes:** fixed logic error (logo upload message) and added missing validation for `tool_id` in `exchange_tool` (#119, #120).
- **PDF Reliability:** Hardened `pdf_utils.py` to safely handle `None` values from the database, preventing crashes during report generation (#121).
- **Improved Feedback:** `submit_check` now correctly warns users if PDF generation fails even if the database save was successful (#122).

## [2.6.0-beta3] - 2026-02-14

### 🐛 Bug Fixes
- **Dashboard UX:** Fixed link on empty dashboard pointing to tools instead of personnel management (#118).

## [2.6.0-beta2] - 2026-02-14

### 🐛 Critical Bug Fixes
- **Fixed Crash in PDF Generation:** Added critical null-check for Azubi lookup in `CheckService`. Previously, invalid Azubi IDs could cause a 500 status masked as success (#112).

### 🔒 Security
- **API Hardening:** Added Rate Limiting (`30/min`) and CSRF exemption to `/api/stats` endpoint (#113).

### 🧪 Testing
- **Coverage Increased:** Added test cases for missing Azubi and invalid Tool IDs.

## [2.6.0-beta1] - 2026-02-14

### 🏗️ Refactoring (Stable Beta)
- **CheckType Enum:** Replaced magic strings with a robust `CheckType` Enum across the entire application for better type safety and stability.
- **Service Layer:** Extracted complex check submission logic from `routes.py` into a dedicated `CheckService`, improving maintainability and testability.
- **Testing:** Added initial unit tests for core business logic (`CheckService`).

### ✨ New Features
- **API Stats:** Added `/api/stats` endpoint to provide data for future dashboard widgets.

## [2.5.5] - 2026-02-14

### 💄 UX Improvements
- **History View:** "Tool Exchange" transactions are now correctly labeled as **"Werkzeug-Austausch"** in details (previously showed as simple Return/Issue).
- **Dashboard:** Renamed "Kostenpflichtig Austauschen" button to **"Werkzeug austauschen"** to avoid confusion (cost is optional).

## [2.5.4] - 2026-02-14

### 🐛 Critical Bug Fixes
- **Fixed Crash in Tool Exchange:** Resolved `NameError: name 'pdf_path' is not defined` when exchanging tools.

## [2.5.3] - 2026-02-14

### 🐛 Critical Bug Fixes (Hotfix)
- **Fixed Service Crash:** Resolved `IndentationError` in `routes.py` that prevented application startup.
- **Fixed Frontend Error:** Resolved global scope pollution in `check.html` where `window.clearResult` was conflicting with other scripts.
- **Improved Code Stability:** Added missing `CheckType` class to `models.py` to prevent potential runtime errors during tool exchange.

### 🔒 Security
- **Hardened Session Deletion:** Verified and enforced `migration_mode` check for the `delete_session` endpoint.

## [2.5.2] - 2026-02-14
### Changed
- **UX:** Mobile Signature Pad is now throttled for smoother drawing.
- **Accessibility:** Added ARIA labels to navigation and buttons.

### Fixed
- **Cache:** Logo update now clears Jinja2 cache immediately.
- **Stability:** Prevented race conditions in session ID generation.
- **Pagination:** Fixed edge case where accessing page > total_pages caused errors (now redirects).
- **DevOps:** Application now validates critical environment variables on startup.

### Added
- **Backup & Rollback:** CLI scripts (`backup.py`, `rollback.py`) for data safety.
- **Payable Exchange:** Option to mark tool exchanges as "Kostenpflichtig".
- **API Documentation:** New `API_DOCS.md` for developers.

### Changed
- Refactored internal logic to use `CheckType` constants instead of magic strings.

### Fixed
- Restored missing Jinja block in dashboard (Hotfix for 500 Error).

## [2.5.0] - 2026-02-13

### 🚀 New Features
- **Tool Exchange (Austausch)** - One-Click workflow for replacing defective/lost tools
  - Wraps "Return" and "Issue" into a single transaction
  - Maintains correct inventory history (Defect -> Replacement)
  - **Dashboard:** New "Austauschen" button with signature pad modal
  - **Reports:** Generates combined "Austauschprotokoll" PDF
  - **Backend:** Transactional safety with shared session ID

### 📦 Included Fixes (from v2.4.3)
- **Performance:** 10x faster Dashboard loading (N+1 Query fix)
- **Stability:** Solved Watchdog timeouts on Raspberry Pi SD cards
- **Health:** New lightweight `/health` endpoint for Docker

## [2.4.3] - 2026-02-12

### 🚀 Performance & Stability (Critical Fixes)
- **Resolved Watchdog Restarts** - Fixed "unhealthy" container kills on Raspberry Pi SD cards
  - Implemented lightweight `/health` route (avoids heavy DB queries during healthcheck)
  - Optimized Docker healthcheck: `interval=30s`, `timeout=15s`, `retries=5`
- **Dashboard Speedup (10x faster)** - Refactored Index/Dashboard route
  - Replaced N+1 query pattern with single optimized SQL query using subqueries
  - Reduced load time from >10s to <1s on low-end hardware
- **Caching Implemented** - Added 5-minute TTL cache for `get_assigned_tools` calculation
  - Significantly reduces DB load on highly accessed pages
- **SD Card Optimizations** - Tuned SQLite and Server for flash storage
  - SQLite: Enabled `WAL` mode, `mmap_size=256MB`, and `temp_store=MEMORY` (RAM-based temp files)
  - Gunicorn: Enabled multi-threading (`--threads 2`) and max-requests limit to prevent memory leaks
- **Async Logging** - Replaced synchronous file logging with non-blocking `QueueHandler`
  - Prevents request threads from blocking during I/O spikes

### 🔒 Security
- **Secure File Deletion** - Added safety checks for session deletion
  - Deletion only allowed in "Migration Mode"
  - Explicit check against accidental legacy session deletion

## [2.4.2] - 2026-02-11

### 🔒 Security
- **Enhanced Content Security Policy (CSP)** - Added comprehensive security headers (#3)
  - Conditional implementation: Flask-Talisman for standalone, manual headers for Home Assistant Ingress
  - Added `'unsafe-inline'` to script-src to allow inline JavaScript (templates requirement)
  - Added `connect-src` for CDN source maps
  - Fixed CSP blocking all inline scripts (was breaking AJAX functionality)

### 🐛 Critical Bug Fixes
- **Fixed werkzeug add/edit functionality** - AJAX endpoints not working due to CSP blocking JavaScript
  - Root cause: CSP blocked inline `<script>` tags preventing EventListener registration
  - Form submitted as GET instead of AJAX POST
  - Added defensive null-check for editWerkzeugModal event.relatedTarget
- **Fixed PDF generation failures** - 500 errors when downloading reports
  - Added missing `make_response` import for end_of_training_report
  - Added missing `send_from_directory` import for handover PDFs (Protokoll_*.pdf)
- **Fixed logo missing in PDFs** - Logo path resolution issue
  - Changed from hardcoded `os.environ` at import time to dynamic `current_app.config` resolution
  - Created `get_logo_path()` function with Flask app context support

### ✨ Features
- **Signature File Cleanup** - New Flask CLI command for automated cleanup (#8)
  - Command: `flask cleanup-signatures`
  - Configurable retention via `SIGNATURE_RETENTION_DAYS` env var (default: 3650 days = 10 years)
  - Detailed console output with counts and error reporting
  - Suitable for cron/systemd timer automation

### 🔧 Technical Improvements
- **Error Handling** - Pragmatic implementation for critical operations (#4)
  - Added `SQLAlchemyError` handling to all 3 API endpoints (werkzeug, azubi, examiner)
  - Created `handle_db_error()` helper function with logging and rollback
  - Proper German error messages for user feedback
- **Structured Logging** - Production-ready logging setup (#17)
  - Implemented `RotatingFileHandler` at `/data/app.log`
  - 10MB per file, 3 backup files retained
  - Dual output: file + console for Docker/HA compatibility

## [2.4.1] - 2026-02-10

### 🔒 Security
- **Fixed Path Traversal vulnerability** in logo upload by adding `secure_filename()` sanitization (#2)
- **Fixed XSS vulnerability** in AJAX dynamic content by replacing `innerHTML` with DOM API (`textContent`) (#13)
  - Fixed in werkzeug addition (tools.html)
  - Fixed in azubi/examiner addition (personnel.html)

### 🐛 Bug Fixes
- **Fixed logo cache issue** - Logo now updates immediately after upload without hard refresh
  - Implemented cache-busting via query parameter (`?v=timestamp`)
  - Browser automatically fetches new logo when file modification time changes
- **Fixed personnel AJAX bug** - Azubi and Examiner additions now appear immediately in list
  - Added missing `appendChild()` calls in DOM manipulation

### 🔧 Technical
- Removed LRU cache in favor of ETag-based HTTP caching with file modification time
- Context processor now injects `logo_version` for cache busting across all templates

## [2.4.0] - 2026-02-09

### ✨ Features
- Initial stable release
- Tool tracking system for apprentices
- QR code generation
- PDF reports
- Digital handover protocol
- End-of-training reports
- Home Assistant Add-on support with Ingress compatibility

---

[2.4.2]: https://github.com/Ecronika/azubi_werkzeug/compare/v2.4.1...v2.4.2
[2.4.1]: https://github.com/Ecronika/azubi_werkzeug/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/Ecronika/azubi_werkzeug/releases/tag/v2.4.0
