# Changelog

All notable changes to the Azubi Werkzeug Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
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
