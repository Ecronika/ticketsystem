# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.28.1] - 2026-03-29

### Fixed
- **Security (IDOR)**: Fixed vulnerability where confidential tickets were accessible via public view or direct URL manipulation for assignment.
- **Database Integrity**:
  - Fixed broken migration `079270ff0a87` (duplicate column/foreign key errors).
  - Implemented automated repair migration for orphaned comments, attachments, and notifications.
  - Enabled strict Foreign Key enforcement (`PRAGMA foreign_keys = ON`).
- **Stability**:
  - Implemented `RUN_SCHEDULER=0` environment flag to prevent database locks during startup/migration.
  - Fixed runtime crashes in Dashboard due to missing imports.
  - Corrected UTF-8 encoding garbling in system flash messages.
- **Reliability**:
  - Hardened API endpoints with robust JSON parsing (`silent=True`) and strict Enum validation.
  - Fixed double-commit race condition in Checklist transitions.

### Changed
- Refactored Ticket detail view to use centralized, model-level access logic.
- Improved Pylint code quality score across all core modules (Enums: 10/10, Models: 9.18/10, App: 8.45/10).

## [1.28.0] - 2026-03-25
- Initial version with Advanced Agentic Coding support.
