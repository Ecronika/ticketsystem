# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
