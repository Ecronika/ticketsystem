# Changelog

All notable changes to the Azubi Werkzeug Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
