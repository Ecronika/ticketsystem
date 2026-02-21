# Changelog

All notable changes to the Azubi Werkzeug Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
