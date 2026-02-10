# Changelog

All notable changes to the Azubi Werkzeug Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

[2.4.1]: https://github.com/Ecronika/azubi_werkzeug/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/Ecronika/azubi_werkzeug/releases/tag/v2.4.0
