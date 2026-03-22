# Changelog

## [1.5.2] - 2026-03-22
### Fixed
- **Datenbank:** Formale Alembic-Migration für das in v1.5.1 eingeführte Feld `last_active` hinzugefügt, um Abstürze beim Start zu verhindern.

---

## [1.5.1] - 2026-03-22
### Fixed
- **P0-1:** Verschachteltes Formular in Mitarbeiterverwaltung behoben (PIN-Reset funktioniert nun browserübergreifend).
- **P0-2:** Fehlerhafter Link in der anonymen Ticket-Bestätigung entfernt.
- **P2-1:** Tote Footer-Links (Impressum/Datenschutz) korrigiert und Sidebar-Hover CSS (`bg-white-hover`) implementiert.

### Added
- **P0-3:** Landing-Banner auf der Login-Seite für bessere Orientierung neuer Nutzer.
- **P1-1:** Anzeige des Ticket-Erstellers direkt in der Dashboard-Liste.
- **P1-2:** Erklärungs-Tooltips für den "WARTET"-Status und neue Kommentar-Shortcuts.
- **P1-3:** Integration des Fälligkeitsdatums (`due_date`) in Erstellung, Detailansicht und Dashboard (mit Farb-Highlighting).
- **P1-4:** Filter für "Unzugewiesene" Tickets auf dem Dashboard hinzugefügt.
- **P1-5:** Ticket-Bestätigungsbanner ist nun idempotent (URL-basiert statt Session).
- **P2-2:** Neue Spalte "Letzte Aktivität" in der Mitarbeiterverwaltung zur besseren Übersicht.
- **P2-3:** Verbesserte 400-Fehlerseite mit "Neu laden"-Button für abgelaufene Sitzungen.

---

## [1.5.0] - 2026-03-22

### Hinzugefügt (Added)
- **Login:** PIN-Sichtbarkeit lässt sich nun per Auge-Icon umschalten.
- **Login:** Mitarbeiter-Namen als anklickbare "Chips" zur Schnellauswahl.
- **Dashboard:** Hochprio-Tickets werden optisch hervorgehoben (roter Rand + Hintergrund).
- **Details:** Datum in der Ticket-Historie (z.B. "20.03. 14:00") für bessere Orientierung.
- **Details:** Status-Dropdown ändert nun dynamisch die Hintergrundfarbe passend zum Status.
- **Ticket-Erstellung:** Infobox "Was passiert nach dem Absenden?" für mehr Vertrauen.
- **Tooltips:** Exakte Datumsangaben beim Hover über relative Zeitstempel (z.B. "vor 5 Min.").

### Geändert (Changed)
- **Navigation:** "Zurück"-Button in den Details ist nun ein beschrifteter "Dashboard"-Button.
- **Mitarbeiter:** "Aktive Mitarbeiter" wurde in "Hinterlegte Mitarbeiter" umbenannt.
- **Pflichtfelder:** Markierung durch ein rotes Sternchen `*` in allen Verwaltungsformularen.
- **Shortcuts:** Diese ersetzen nun den Text im Kommentarfeld (statt anzuhängen) und zeigen bei Aktivierung einen dunklen Hintergrund.
- **Alerts:** System-Hinweise bleiben nun 8 Sekunden (bzw. 12 Sek. bei Links) sichtbar.

### Beholfen (Fixed)
- **Banner:** Doppelte Flash-Meldungen bei anonymer Ticket-Erstellung entfernt (nur noch Ticket-Bestätigung).
- **Sprache:** Konsistente Anzeige von Status-Labels in Großbuchstaben (Jinja & JS).

### Beholfen (Fixed)
- **P0-1:** Kritischer Fehler in der Ticket-Erstellung behoben (Ticket-Bestätigung wird nun korrekt angezeigt).
- **Redirct:** Kommentare springen nach dem Absenden nun direkt zurück zum Formular (#comment-form).

### Verbessert (Changed)
- **Priorität:** Buttons in Ticket-Erstellung logischer sortiert (Hoch -> Mittel -> Niedrig).
- **Dashboard:** Spalte "Meine Tickets" zeigt nun die Gesamtzahl der zugewiesenen Tickets.
- **Benutzerverwaltung:** Warn-Icon für Mitarbeiter mit fehlgeschlagenen Logins hinzugefügt.
- **Design:** Pflichtfelder nun mit Sternchen (*) markiert.
- **Tablet:** Sidebar in Ticket-Details rückt auf kleinen Displays nach oben.
- **Terminologie:** "Recovery-Token" systemweit in "Notfall-Code" umbenannt; IT-Jargon (soft-delete) entfernt.
- **Archiv:** Status-Spalte hinzugefügt.
- **Performance:** Benachrichtigungen mit Links bleiben nun länger sichtbar.

## [1.4.0] - 2026-03-22
### Added
- **My Tickets Filter:** Added deep link and backend filter `?assigned_to_me=1` to the dashboard for quick access to personal assignments.
- **System Event Styling:** Implemented a slim, timeline-based UI for system-generated comments (status changes, assignments) to distinguish them from worker talk.
- **PIN Visibility:** Added a toggle button to PIN fields in setup and worker management.

### Fixed (P0/P1 UX Overhaul)
- **Status Colors:** Standardized status colors across all views (offen=red, in_bearbeitung=yellow, wartet=gray, erledigt=green).
- **Confirmation Loop:** Added a persistent confirmation banner after ticket creation with a direct link to the new ticket.
- **Terminology:** Standardized system-wide terminology (replaced "Klärungsfall" and "Azubi Tracker" with "Ticket" and "TicketSystem").
- **Navigation:** Enabled "New Ticket" button in navbar for logged-in workers.
- **Accessibility:** Set default ticket priority to "Mittel" and fixed broken Home icon on 404 page.
- **Consistency:** Fixed contrast of "Emergency Codes" button and improved "Add Worker" form visibility in Dark Mode.
- **Validation:** Fixed PIN confirmation pattern and length validation in setup UI.

## [1.3.9] - 2026-03-22
### Fixed
- **Image Upload:** Implemented a state-based submit button to prevent premature ticket submission before image processing is finished.
- **Image Upload:** Added error handling for client-side image loading failures.
- **Diagnostics:** Added detailed backend logging for attachment processing to identify silent failures.
- **Reliability:** Corrected potential race conditions during Base64 image encoding on mobile devices.

## [1.3.8] - 2026-03-21
### Fixed
- **Worker Management:** Restored the "Add Worker" form which was accidentally removed in v1.3.7.
- **Critical Runtime Fix:** Fixed `NameError` and missing import (`SystemSettings`) in `admin.py` that caused crashes when updating workers or generating recovery tokens.
- **UI/UX:** Fixed visibility of the "Neue Notfall-Codes" button in Dark Mode by switching to `btn-outline-warning`.
- **Dashboard:** Fixed potential JS syntax issues in `index.html` polling logic.

## [1.3.7] - 2026-03-21
### Fixed (Critical UX P0/P1)
- **Visibility:** "Ticket melden" is now visible to unauthenticated users on the login page and navigation bar.
- **Workflow:** Corrected public ticket submission redirect to ensure users stay on the success message.
- **Admin Control:** Implemented Admin-initiated PIN resets and Emergency Recovery Token generation.
- **UI Logic:** Fixed dashboard ticket count badge and added polling-refresh hints.
- **Clarity:** Renamed ambiguous internal labels (e.g., "Fokus" -> "Alle offenen Tickets", "Deaktivieren" -> "Zugang sperren").
- **Accessibility:** Integrated confirmation dialogs for all sensitive worker status actions.
- **Visualization:** System events (status changes, assignments) are now visually distinct from user comments.

### Refined (P2)
- **Data Integrity:** Ticket description field is now optional.
- **Archiving:** Renamed archive column to "ZULETZT AKTUALISIERT" for transparency on closure dates.
- **PIN Standards:** Aligned PIN length requirements (4-16 digits) across all setup and reset forms.
- **Consistency:** Fixed JSend status badge labeling in JavaScript to match server-side display.

## [1.3.6] - 2026-03-21
### Fixed
- **Filter Stability:** Resolved `TypeError` in `time_ago` filter caused by mismatched timezone-aware (from `local_time`) and naive timestamps.

## [1.3.5] - 2026-03-21
### Fixed
- **Critical Runtime Fixes:** Fixed specialized `IndentationError` and `NameError` in `auth.py` and `tickets.py` that caused application crashes.
- **Timezone Stability:** Standardized all internal timestamps to naive UTC for full SQLite compatibility, resolving `TypeError` crashes during account lockout checks.
- **HA Ingress Optimization:** Fixed dashboard polling with correct Ingress path prefix.

## [1.3.4] - 2026-03-21
### Fixed
- **Redirect Reliability:** Introduced a centralized Ingress-aware redirect helper to prevent 404 errors and double-slash pathing issues across all authenticated and unauthenticated routes.

## [1.3.3] - 2026-03-21
### Added
- **Image Support:** Fixed the missing link between frontend image uploads and backend storage. Tickets now correctly save and display uploaded images in the detail view.
- **Secure File Serving:** Dedicated route for serving attachments from the persistent data directory.

## [1.3.2] - 2026-03-21
### Fixed
- **Critical Database Fix:** Added missing `comment.author_id` column to the pre-boot repair tool and Alembic migrations. Resolves crashes when viewing or creating tickets.
- **Authentication:** Fixed logout redirection logic for Home Assistant Ingress to prevent double-slash pathing issues.
- **Network Stability:** Refined NGINX `listen` directive with `default_server` to ensure Port 5001 accessibility.
- **UI Cleanup:** Removed redundant version badge from dashboard header.

## [1.3.1] - 2026-03-21
### Fixed
- **Critical Migration Fix:** Added missing `sqlalchemy` import in Alembic's `env.py` to prevent startup crashes.
- **Initialization Order:** Fixed extension initialization order to ensure `db.init_app` runs before `Migrate`.
- **Database Safety:** Removed dangerous `db.create_all()` fallbacks that could lead to untracked schema states.
- **Deployment & Proxy:** Deduplicated `ProxyFix` middleware and ensured absolute database paths for Home Assistant Ingress.
- **Standalone Support:** Updated `Dockerfile.standalone` to correctly trigger database migrations on boot.
- **Diagnostics:** Added `init_db.py` for pre-boot initialization and better startup logging.
- **Performance:** Consolidated SQLite connection listeners for optimal concurrency.

## [1.3.0] - 2026-03-21
### Shopfloor Ergonomics & PWA
- **PWA Support:** Added `manifest.json` and Service Worker for offline-capable "Add to Home Screen" support on industrial tablets.
- **Polling System:** Real-time dashboard updates via automated 30s background polling (`/api/dashboard/summary`).
- **Client-side Image Optimization:** Automated Resizing/Compression (max 1200px) before upload to save bandwidth and storage.

### Security & RBAC
- **Role-Based Access Control (RBAC):** Transitioned from binary `is_admin` to a granular `role` system (`admin`, `worker`, `viewer`).
- **Shared Terminal Security:** Implementation of the `Clear-Site-Data` HTTP header on logout to purge cache/cookies on shared devices.
- **Admin PIN Reset:** Administrators can now reset forgotten worker PINs to "0000" with a forced change on next login.

### Architektur & Maintenance
- **Alembic Migrations:** Integrated Flask-Migrate for robust, versioned database schema management.
- **Soft-Delete System:** Tickets are no longer permanently deleted, preserving audit trails while cleaning the UI.
- **Consolidated Audit Trail:** All system events (status changes, assignments) are now stored as internal comments (`is_system_event`).

## [1.2.0] - 2026-03-18
### Sicherheit & Enterprise-Readiness (Hardening)
- **Account-Lockout Mechanism (H-1):** Sperrt Benutzer nach 5 Fehlversuchen für 15 Minuten, um Brute-Force-Angriffe zu verhindern.
- **Worker Enumeration Prevention (M-1):** Benutzerliste auf der Login-Seite entfernt, um Angriffsfläche zu minimieren.
- **Audit-Trail Integrität (H-2):** Alle Kommentare, Statusänderungen und Zuweisungen werden nun über eine nicht fälschbare `author_id` (Fremdschlüssel) verknüpft.
- **Strict Content Security Policy (C-1):** Alle Inline-Scripte wurden externalisiert; `'unsafe-inline'` wurde aus der CSP entfernt.
- **CSRF-Härtung:** Session-Bindung für AJAX-Requests via Meta-Tag und POST-only für sensible Aktionen.

### Architektur & Maintenance
- **JavaScript Externalisierung:** Refactoring von `base.html`, `ticket_detail.html` und `workers.html` – Logik in saubere, versionierte `.js` Dateien ausgelagert.
- **Service-Layer Update:** `TicketService` unterstützt nun die native Verknpfung von Aktionen mit Mitarbeiter-Datensätzen.

### UI/UX & Barrierefreiheit (WCAG 2.2 AA)
- **Kontrast-Optimierung (L-1/M-6):** Einführung von theme-sensitiven Badge-Klassen (`badge-subtle-*`) für perfekte Lesbarkeit in Light, Dark und High-Contrast.
- **Design-System Konsistenz:** Entfernung aller hardcodierten Bootstrap-Farben (`bg-white` etc.) aus den Haupttemplates zugunsten von CSS-Variablen.
- **Shopfloor-Ergonomie:** Korrektur von PIN-Eingabemustern und Modal-Fokus-Management.

---

## [1.1.1] - 2026-03-19

### Fixed
- **Security**: Hardened `showUiAlert` against XSS by switching to `textContent` DOM manipulation.
- **Security**: Restricted `/logout` route to `POST` only (CSRF protection).
- **Ingress**: Fixed broken pagination links by prepending `ingress_path` in `index.html` and `archive.html`.
- **UI/UX**: Fixed select element revert logic in `ticket_detail.html` using `data-original` state tracking.
- **UI/UX**: Added visual loading feedback (opacity) during ticket status and assignment updates.
- **UI/UX**: Fixed theme icon FOUC (Flash of Unstyled Content) during page load.
- **UI/UX**: Refined PIN pattern to allow flexible lengths (4-16 digits) and added mobile `inputmode="numeric"`.
- **A11y**: Restored focus to triggering button after closing the worker edit modal.
- **A11y**: Integrated `#ajaxStatusAnnouncer` into global alert utility for screen reader support.
- **Performance**: Added DNS `preconnect` hints for CDN-hosted assets.

## [1.1.0] - 2026-03-19

### Secured
- **Hardened Authentication**: Replaced worker selection dropdown with secure name-input (Anti-Enumeration).
- **Mandatory PIN Change**: Enforces PIN update on first login for new or reset accounts.
- **Frontend Security**: Added Subresource Integrity (SRI) hashes for Bootstrap CDN.
- **XSS Protection**: Replaced unsafe DOM operations with `textContent` in notification alerts.
- **Internal Cleanup**: Resolved critical bug with duplicate function definitions in `auth.py`.

### Added
- **Search & Filter**: Added keyword search and status-based filtering to the main Dashboard.
- **Server-side Pagination**: Improved performance for large ticket volumes (10 per page).
- **Ticket Archive**: Dedicated view for closed tickets, separate from daily work.
- **Human-Readable Labels**: Integrated Jinja filters for translated status and priority labels.

### Fixed
- **Logout Visibility**: Fixed issue where the logout button was hidden for certain worker roles.
- **AJAX Feedback**: Added loading states (spinners) and input locking during server requests.
- **Confirmation Flow**: Added mandatory "Confirm" step before closing tickets.

## [1.0.0] - 2026-03-18

### Added
- Initial release of the Ticket System Boilerplate.
- Clean Bento-Grid based UI.
- PIN-based authentication.
- Generic `Ticket` model and repository structure.
- Docker and Home Assistant Ingress support.
- Optimized SQLite/WAL database initialization.
