# Changelog
 
## [1.11.2] - 2026-03-23
### Fixed
- **UI-UX Verbesserung:** Die Sektion „Demnächst“ visualisiert nun explizit Tickets, die durch die Fälligkeits-Filter (14/30 Tage) zusätzlich eingeblendet werden.
- **Fehlerbehebung:** Zeitberechnung der Filter-Horizonte auf das Tagesende (23:59:59) korrigiert.

## [1.11.1] - 2026-03-23
### Fixed
- **Hotfix:** Behebung eines 500-Fehlers (ImportError) beim Aufruf von „Meine Aufgaben“.

## [1.11.0] - 2026-03-23
### Added
- **Feature: „Meine Aufgaben“**: Neues Dashboard speziell für Mitarbeiter, das Tickets nach Dringlichkeit (Überfällig, Heute, Diese Woche) gruppiert.
- **Urgency Score**: Intelligente Sortierlogik im Backend, die Priorität und Fälligkeit kombiniert.
- **Navbar-Badge**: Anzeige der Anzahl dringender Aufgaben direkt in der Navigation.
- **Login-Redirect**: Mitarbeiter werden nach dem Login nun direkt zu ihrer persönlichen Aufgaben-Queue geleitet.

## [1.10.3] - 2026-03-23
### Fixed
- **UI-Fix:** Das „Auge“ zum Anzeigen von PINs funktioniert nun auch mit der neuen restriktiven CSP (Umstellung von Inline-JS auf Event-Listener).
- **UI-Improvement:** PIN-Sichtbarkeitstoggle auch auf der `change_pin.html` Seite hinzugefügt.

## [1.10.2] - 2026-03-22
### Fixed
- **Auth-Fix:** Letztes verbliebenes `datetime.utcnow()` in der Login-Lockout-Logik ersetzt.
- **Regression-Fix:** Fehlender `SQLAlchemyError` Import in `models.py` hinzugefügt.

## [1.10.1] - 2026-03-22
### Fixed (P0-P1 Bugfixes)
- **Startup-Fix (P0):** Syntaxfehler in `app.py` behoben (Backslash in f-string auf Python 3.11).
- **Dashboard-Fix (P0):** Fehlender `timezone` Import in `tickets.py` ergänzt.
- **Datenintegrität (P0):** Einrückungsfehler bei der Attachment-Erstellung in `ticket_service.py` behoben.
- **Auth-Fix (P1):** Letztes verbliebenes `datetime.utcnow()` in `auth.py` ersetzt.
- **API-Fix (P1):** Doppelten Decorator auf `_archive_view` entfernt.
- **Maintenance:** APScheduler Shutdown-Handler registriert und Inline-Imports optimiert.

## [1.10.0] - 2026-03-22
### Security (Critical CSP & Race Conditions)
- **CSP Nonce System:** Implementierung eines dynamischen Nonce-Systems für die Content Security Policy. Alle Inline-Skripte sind nun durch Nonces geschützt, was die Anwendung in restriktiven Umgebungen (Home Assistant Ingress) wieder voll funktionsfähig macht.
- **Login-Sicherheit (High):** Race-Condition beim `failed_login_count` durch Nutzung von `with_for_update()` in der Datenbank-Abfrage behoben.
- **Robustes Image-Processing:** Fehlerbehandlung für ungültige Base64-Bilddaten in `ticket_service.py` hinzugefügt (abfangen von `binascii.Error`).

### Performance & Quality
- **Dashboard-API-Optimierung (Medium):** Die `/api/dashboard/summary` Route nutzt nun eine einzige `group_by` Abfrage anstelle von vier separaten Queries.
- **Python 3.12 Readiness (Low):** Systemweite Ablösung der veralteten Methode `datetime.utcnow()` durch `datetime.now(timezone.utc).replace(tzinfo=None)`.
- **Backend-Robustheit:** `_remove_with_retry` fängt nun gezielt `OSError` ab, anstatt eine breite `Exception`.
- **Backup-Service:** Letztes `datetime.utcnow()` in `backup_service.py` durch moderne Variante ersetzt.

### Documentation
- Version auf v2.0.0 angehoben (Enterprise Readiness Update).

---


## [1.9.2] - 2026-03-22
### Fixed (Critical Regressions)
- **Ticket-Erstellung (NEU-1.9.1-01):** Kritischer `NameError` (`due_date_str`) in `_new_ticket_view` behoben. Ticket-Erstellung über das Web-Formular funktioniert nun wieder wie gewohnt.
- **Import-Fix (QUAL-05):** Inline-Import von `traceback` in `database_init.py` an den Dateianfang verschoben.

### Changed (Cleanup & Quality)
- **Logger-Standardisierung (NEU-1.9.1-02/03):** f-strings in Logger-Calls in `tickets.py` und `utils.py` durch `%s` Formatierung ersetzt.
- **Import-Cleanup:** Redundanter lokaler Import von `current_app` in `_new_ticket_view` entfernt.
- **Dokumentation:** Versionsnummern in `README.md`, `config.yaml`, `VERSION` und `sw.js` konsistent auf v1.9.2 aktualisiert.

---

## [1.9.1] - 2026-03-22
### Fixed (Critical Regressions)
- **Security-Header Kollision (NEU-01):** Namenskollision von `add_security_headers` in `app.py` behoben. Hooks zusammengeführt; CSP-Header werden nun auch im Home Assistant Modus korrekt gesendet.
- **UI-Fix (NEU-02):** Ticket-Header in `ticket_detail.html` wiederhergestellt (Titel, Bearbeiten-Button und ID-Anzeige waren in v1.9.0 verloren gegangen).
- **SQL-Fix (NEU-03):** `Comment.created_at` nutzt nun ebenfalls den Lambda-Wrapper für `datetime.utcnow()`, um SQLAlchemy-Warnungen zu vermeiden.
- **Logic-Fix:** Undefinierte Variable `due_date` in `_new_ticket_view` behoben; Deadlines werden nun auch bei anonymer Erstellung korrekt verarbeitet.

### Changed (Cleanup & Quality)
- **Logging (NEU-04):** Veraltetes `import sys` und Debug-Print in `auth.py` entfernt; Nutzung des Standard-Loggers.
- **Logger-Standardisierung:** Alle f-strings in `dashboard.py` Logger-Calls durch `%s` Formatierung ersetzt (QUAL-02).
- **Security-Pfad:** Zusätzliche Validierung (`os.path.basename`) und Schutz gegen leere Pfade in `_serve_attachment` implementiert (SEC-03).
- **CSS-Cleanup (QUAL-07):** Unbenutzte Inline-Styles aus `workers.html` entfernt.
- **Import-Cleanup:** Doppelte `datetime`-Imports und lokale Logging-Imports in `app.py` bereinigt.

---

## [1.9.0] - 2026-03-22
### Security (Hardening)
- **PIN-Hashing (SEC-01):** Umstellung auf `pbkdf2:sha256` mit 600.000 Iterationen (standardmäßig via Werkzeug 3.x) für erhöhten Schutz gegen Offline-Cracking.
- **Session Fixation (SEC-02):** Explizites `session.clear()` bei PIN-Recovery implementiert, um die Übernahme alter Sitzungs-IDs zu verhindern.
- **HSTS-Header (SEC-05):** `Strict-Transport-Security` Header hinzugefügt, falls `REQUIRE_HTTPS=1` gesetzt ist.
- **Global Security Headers:** Standard-Header (`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`) für alle Responses aktiviert.
- **Rate Limiting:** Public Ticket View auf 30 Requests pro Minute erhöht, aber robuster gegen Missbrauch abgesichert.

### Performance & SQL
- **Eager Loading (BUG-06):** N+1 Query-Problem im Dashboard behoben – Kommentare und Bearbeiter werden nun via `joinedload` in einem SQL-Statement geladen.
- **Atomic DDL (BUG-09):** `database_init.py` nutzt nun `engine.begin()` für atomare Datenbank-Reparaturen beim Start.
- **Standardisierte Datetime (BUG-12):** Konsistente Nutzung von naivem UTC (`datetime.utcnow`) in allen Service-Aktionen zur Vermeidung von SQLite-Inkompatibilitäten.
- **SQLAlchemy-Fix (BUG-07):** Deprecation-Warnungen für `datetime.utcnow` als Spalten-Default durch Lambda-Wrapper behoben.

### Fixed & Refined
- **HTML-Struktur (BUG-01):** Kritischer Verschachtelungsfehler in `ticket_detail.html` behoben; Sidebar und Verlauf werden nun wieder korrekt gerendert.
- **Layout (BUG-05):** Header-Layout in der Detailansicht für mobile Geräte optimiert (Prioritäts-Badge bricht nicht mehr unschön um).
- **ServiceWorker (PERF-04):** Root-Pfad aus der statischen Asset-Liste entfernt, um redundante Caching-Versuche des dynamischen Dashboards zu vermeiden.
- **Refactoring (QUAL-01):** View-Registrierung in `tickets.py` auf explizite Endpunkte umgestellt und redundante Imports bereinigt.

---

## [1.8.2] - 2026-03-22
### Fixed (Critical Hotfixes)
- **Startup-Fix (OFFEN-01):** Definitiver Fix für den SyntaxError in `database_init.py`. Docstring korrekt geschlossen und Funktionskörper repariert.
- **Context-Fix (OFFEN-03):** `RuntimeError` im DB-Event-Listener behoben, indem auf das Standard-Python-`logging` gewechselt wurde (verfügbar auch ohne App-Kontext).
- **ServiceWorker (OFFEN-02):** Cache-Name auf `v1.8.2` aktualisiert, um Cache-Invalidierung sicherzustellen.

### Changed
- **Logging (OFFEN-04):** Alle verbleibenden Logging-Calls in `ticket_service.py` auf Standard-Formatierung (`%s`) konsolidiert (QUAL-02).
- **Dokumentation (OFFEN-05):** Versionsnummer in `README.md` auf v1.8.2 aktualisiert.

---

## [1.8.1] - 2026-03-22
### Fixed (Critical Regressions)
- **Startup-Fix (NEU-01):** SyntaxError in `database_init.py` behoben. Die Anwendung startet nun wieder korrekt.
- **Logout-Fix (NEU-02):** NameError (`current_app`) im Logout-View behoben. Abmelden ist nun wieder möglich.
- **Public-Detail (NEU-05):** Anhänge und Kommentare werden auf der öffentlichen Ticket-Seite nun nur noch für angemeldete Mitarbeiter angezeigt, um Broken-Images und unbefugten Datenzugriff zu vermeiden.

### Changed
- **Asset-Versioning (NEU-04/07):** Versionierung via `?v={{ config.VERSION }}` in alle Templates (`ticket_detail.html`, `workers.html`) übernommen, um Cache-Probleme nach Updates zu vermeiden.
- **ServiceWorker (NEU-06):** Die Cache-Matching-Logik in `sw.js` wurde vereinfacht und erkennt nun alle statischen Assets unter `/static/` zuverlässig.
- **Logging (NEU-03):** Redundante Pragma-Logmeldungen in `app.py` entfernt und Logging-Calls in `ticket_service.py` auf Standard-Formatierung (`%s`) umgestellt (QUAL-02).

---

## [1.8.0] - 2026-03-22
### Security (Hardening)
- **Attachment-Sicherheit:** `serve_attachment` ist nun durch `@worker_required` geschützt und nutzt robuste Pfad-Validierung (`os.path.basename`), um Path-Traversal-Angriffe zu verhindern (SEC-03, SEC-04).
- **Notfall-Codes (SEC-02):** Rohe Recovery-Tokens werden nun sofort nach der Anzeige in der Datenbank gelöscht.
- **Sicherer Logout (SEC-09):** Der Logout-Prozess löscht nun explizit alle Sitzungsdaten, setzt das Cookie-Ablaufdatum auf Null und nutzt den `Clear-Site-Data`-Header für maximale Sicherheit auf geteilten Terminals.
- **Open-Redirect Schutz (SEC-06):** Die `is_safe_url`-Validierung wurde grundlegend überarbeitet und schützt nun zuverlässig vor bösartigen Weiterleitungen beim Login.
- **RBAC-Härtung (SEC-07):** Die `is_admin`-Flag in der Session wird nun strikt aus der zugewiesenen Rolle abgeleitet, um Inkonsistenzen zu vermeiden.
- **CSRF-Synchronisation:** Das CSRF-Token-Timeout wurde auf 8 Stunden reduziert, passend zur maximalen Sitzungsdauer.

### Performance & Stabilität
- **Dashboard-Optimierung (PERF-01, PERF-02):** N+1 Query-Probleme in der Ticket-Historie behoben und die Zusammenfassungs-Kacheln auf performante Datenbank-Aggregationen umgestellt.
- **Datenbank-Initialisierung (BUG-11):** Zusammenführung mehrerer Datenbank-Verbindungen beim Start, um "Database Locked"-Fehler in Multi-Worker-Umgebungen zu verhindern.
- **Scheduler-Fix (BUG-03):** Renne-Bedingungen beim Start des Hintergrund-Schedulers durch neue Protective-Guards behoben.
- **Timestamp-Standardisierung (BUG-12):** Alle Zeitstempel wurden auf naive UTC-Werte vereinheitlicht, um Inkompatibilitäten und Abstürze in SQLite zu vermeiden.

### Fixed
- **Login-Fix (BUG-01):** Template-Vererbung der `login.html` korrigiert; die Seite nutzt nun korrekt die Basis-Styles, JS-Bibliotheken und CSRF-Meta-Tags.
- **Prioritäts-Validierung (BUG-05, BUG-06):** Serverseitige Validierung für Ticket-Prioritäten implementiert, um 500er-Fehler bei fehlenden Werten zu verhindern.
- **ServiceWorker:** Cache-Versioning (v1.8.0) und Asset-Busting via `{{ config.VERSION }}` synchronisiert (BUG-13, BUG-14).
- **Unit Tests:** Regex für Mitarbeiter-Degradierung in `test_workers.py` an die präzisen Fehlermeldungen angepasst (BUG-04).

---

## [1.7.1] - 2026-03-22
### Fixed
- **Ticket-Detail Layout:** HTML-Struktur korrigiert (Spaltenzuordnung), um Layout-Kollaps und falsches "Sticky"-Verhalten des Kommentar-Formulars zu verhindern.
- **Verlauf-Visibilität:** System-Events (Timeline-Stil) und menschliche Kommentare (Chat-Bubbles) sind nun visuell klar voneinander getrennt.
- **Sidebar-UX:** Status-Anzeige in der Management-Sidebar dezentralisiert und neutraler gestaltet.
- **Archiv-Accessibility:** Beschriftung der Datumsfilter für Screenreader und Nutzerführung verbessert.


## [1.7.0] - 2026-03-22
### Added
- **Interaktives Dashboard:** Status-Tiles ("Offen", "In Arbeit", "Wartet") sind nun klickbar und filtern die Ticketliste sofort nach dem entsprechenden Status.
- **Erweitertes Archiv:** Neue Filter für Zeitraum (Start/Ende) und Autor hinzugefügt sowie die Spalte "Erstellt von" in der Tabelle ergänzt.
- **Benutzerverwaltung:** Die Mitarbeiterliste wurde für Tablets optimiert (Action-Dropdowns statt Buttons), und die Sidebar wurde visuell modernisiert.

### Fixed
- **Layout:** Kritischer Fehler in der `ticket_detail.html` behoben, bei dem der Bearbeitungsmodus das restliche Layout verschob.
- **Navigation:** Konsolidierung der Navbar ("Mitarbeiter"-Link in Admin-Dropdown verschoben, "Neues Ticket" reduziert).
- **Accessibility:** Kontraste der Status-Badges für WCAG AA optimiert und Syntax-Fehler im CSS behoben.


## [1.6.4] - 2026-03-22
### Added
- **Benutzerverwaltung:** Administratoren können nun neue Mitarbeiter anlegen, ohne sofort einen PIN festzulegen. Das System nutzt dann automatisch den Standard-PIN '0000', der beim ersten Login geändert werden muss.


## [1.6.3] - 2026-03-22
### Fixed
- **Admin Management:** Fehlermeldungen beim Deaktivieren oder Degradieren von Administratoren präzisiert. Es wird nun explizit darauf hingewiesen, dass mindestens ein **aktiver** Administrator im System verbleiben muss, um Lockouts zu verhindern.


## [1.6.2] - 2026-03-22
### Fixed
- **Attachment Fix (Windows):** Korrektur der `DATA_DIR` Konfiguration, die das Speichern von Fotos auf Windows-Systemen verhinderte.
- **Robustheit:** Fallback-Logik für Pfade in `TicketService` und Bild-Bereitstellung ergänzt.


## [1.6.1] - 2026-03-22
### Fixed (Regressions from 1.6.0)
- **Attachments:** Behobener Endpunkt für Ticket-Anhänge; Fotos sind nun wieder in allen Ansichten sichtbar.
- **Interaktivität:** Login-Chips (Mitarbeiternamen) sind nun durch robuste JavaScript-Eventlistener browserübergreifend funktionsfähig.
- **Shortcuts:** Die Kommentar-Schnellauswahl befüllt nun zuverlässig das Textfeld.
- **Security:** "Unerwarteter Fehler" bei der Generierung von Notfall-Codes durch Implementierung des fehlenden `SystemService` behoben.

### Added (Features & UX)
- **Deadline Edit:** Das "Zu bearbeiten bis"-Datum kann nun direkt in der Ticket-Detailansicht bearbeitet werden.
- **Dashboard UI:** Dynamisches Layout und verbesserte Beschriftung bei aktivem "Mir zugewiesen" Filter. Redundante Seitenleisten werden nun ausgeblendet.


## [1.6.0] - 2026-03-22
### Added (UX & Features)
- **Public Status:** Neue Status-Seite unter `/ticket/<id>/public` ermöglicht Einsicht ohne Login (Aussprache: "Anonymer Pfad").
- **Edit Feature:** Mitarbeiter können nun Titel und Priorität von Tickets direkt in der Detailansicht bearbeiten.
- **Bento Dashboard:** Neue Zusammenfassungs-Kacheln ("Offen", "In Arbeit", "Wartet") für schnellen Überblick.
- **Quick Jump:** Suchen nach `#ID` (z.B. `#42`) führt direkt zum entsprechenden Ticket.
- **Empfty State:** Verbesserte Hilfestellung und "Erstes Ticket"-Button für leere Dashboards.

### Fixed (P0-P1 Bugs)
- **PWA:** Service Worker Asset-Liste korrigiert – "Add to Home Screen" funktioniert nun wieder.
- **Logic:** Bestätigungsbanner (`?created=1`) sind nun idempotent und URL-basiert.
- **Security:** CSRF-Schutz für Ticket-Bestätigungen durch Idempotenz verbessert.
- **Templates:** Jinja2-Template-Vererbung in `ticket_new.html` korrigiert.
- **Feedback:** Flash-Meldungen unterstützen nun korrektes HTML (z.B. für Links).

### Accessibility (WCAG 2.2 AA)
- **Kontrast:** Manuelle Rekalibrierung der Kontraste für "Subtle Badges" und Warnmeldungen (A-2).
- **Navigation:** ARIA-Labels für Breadcrumbs, Pagination und Navbars ergänzt.
- **Touch Targets:** Minimale Klickgröße von 44x44px für Alert-Schließen-Buttons implementiert (Apple/WCAG).
- **Focus:** Automatischer Fokus auf Aktions-Buttons in Bestätigungsdialogen (A-3).
- **Semantik:** Korrekte Listen-Rollen (`role="list"`) für Dashboard-Einträge.

---

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
