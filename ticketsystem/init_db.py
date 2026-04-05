"""Dedicated Database Initialization Script.

Runs BEFORE the web server starts to ensure migrations and seeding
are complete.
"""

import logging
import os
import sys
import traceback

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Suppress scheduler during DB initialization to prevent locks
os.environ["RUN_SCHEDULER"] = "0"

from app import app  # noqa: E402 — must come after sys.path / env setup
from database_init import init_database  # noqa: E402
from extensions import db  # noqa: E402
from models import Worker  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
_logger = logging.getLogger("db_init")


def run() -> None:
    """Execute the pre-boot database initialisation."""
    print("--- PRE-BOOT DATABASE INIT START ---", file=sys.stderr, flush=True)
    try:
        with app.app_context():
            init_database(app, logger=_logger)
            _print_worker_diagnostics()
        print(
            "--- PRE-BOOT DATABASE INIT SUCCESSFUL ---",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(0)
    except Exception as exc:
        _logger.critical("DATABASE INITIALIZATION FAILED!")
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.stdout.flush()
        sys.exit(1)


def _print_worker_diagnostics() -> None:
    """Log existing workers for startup diagnostics."""
    workers = Worker.query.all()
    if workers:
        names = [
            f"'{w.name}' ({'Admin' if w.is_admin else 'Worker'})"
            for w in workers
        ]
        print(
            f"Found existing workers: {', '.join(names)}",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            "WARNING: No workers found in database!",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    run()
