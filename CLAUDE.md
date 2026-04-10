# Project Rules

## Dockerfile Sync (Home Assistant Addon)

The file `ticketsystem/Dockerfile` explicitly copies each top-level `.py` file
(it does NOT use `COPY *.py .`). Directories (`routes/`, `services/`, etc.)
are copied whole.

**When creating a new top-level `.py` file:** Add a corresponding `COPY` line
to the Dockerfile.

**When deleting a top-level `.py` file:** Remove the corresponding `COPY` line
from the Dockerfile.

**When creating/deleting files inside `routes/` or `services/`:** No Dockerfile
change needed -- those directories are copied entirely.

## Testing

- Run tests from `ticketsystem/`: `cd ticketsystem && python -m pytest tests/ -v`
- Tests use in-memory SQLite; all 15 tests must pass after any change
- Worker PINs in tests must NOT be in the weak-PIN blocklist (`_WEAK_PINS` in
  `services/worker_service.py`). Use PINs like "7391", "8264", "9173".

## Architecture

- Services use `@staticmethod` + `@db_transaction` decorators
- Domain exceptions live in `exceptions.py` (not inline `ValueError`)
- `ticket_service.py` is a thin facade delegating to focused service modules
- `routes/tickets.py` is a thin coordinator delegating to route sub-modules
- Single `main_bp` Blueprint; each route sub-module exports `register_routes(bp)`
- German-language UI text in all user-facing messages and audit comments
