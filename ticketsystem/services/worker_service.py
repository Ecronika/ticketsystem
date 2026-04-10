"""Worker Service module.

Handles business logic for Worker management (CRUD, status, auth).
"""

from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from enums import WorkerRole
from exceptions import InvalidPinError, LastAdminError, WorkerNotFoundError
from extensions import db
from models import Worker


_WEAK_PINS: frozenset = frozenset({
    "0000", "1111", "2222", "3333", "4444", "5555",
    "6666", "7777", "8888", "9999", "1234", "4321",
    "1212", "2580", "0852", "2468", "1357",
})


def _validate_pin(pin: str) -> None:
    """Raise ``InvalidPinError`` if the PIN is too simple."""
    if not pin or len(pin) < 4:
        raise InvalidPinError("Die PIN muss mindestens 4 Zeichen lang sein.")
    if pin in _WEAK_PINS:
        raise InvalidPinError(
            "Diese PIN ist zu einfach (z. B. 0000, 1234). "
            "Bitte wählen Sie eine sicherere PIN."
        )


def _get_worker_or_raise(worker_id: int) -> Worker:
    """Load a worker by ID or raise ``WorkerNotFoundError``."""
    worker = db.session.get(Worker, worker_id)
    if not worker:
        raise WorkerNotFoundError()
    return worker


def _commit_or_raise(error_msg: str) -> None:
    """Commit the current session or raise ``ValueError`` on failure."""
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise ValueError(f"{error_msg}: {exc}") from exc


class WorkerService:
    """Service layer for Worker-related operations."""

    @staticmethod
    def get_all_workers() -> List[Worker]:
        """Return all workers, ordered by admin status and name."""
        return Worker.query.order_by(
            Worker.is_admin.desc(), Worker.name.asc()
        ).all()

    @staticmethod
    def create_worker(
        name: str,
        pin: Optional[str] = None,
        is_admin: bool = False,
        role: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Worker:
        """Create a new worker with hashed PIN and RBAC role."""
        if not name:
            raise ValueError("Name ist erforderlich.")

        effective_pin = pin or "0000"
        if pin:
            _validate_pin(pin)

        if Worker.query.filter_by(name=name).first():
            raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")

        if not role:
            role = (
                WorkerRole.ADMIN.value if is_admin else WorkerRole.WORKER.value
            )

        new_worker = Worker(
            name=name,
            pin_hash=generate_password_hash(effective_pin),
            is_admin=is_admin,
            role=role,
            is_active=True,
            needs_pin_change=True,
            email=(
                email.strip().lower() if email and email.strip() else None
            ),
        )
        db.session.add(new_worker)
        _commit_or_raise("Datenbankfehler beim Erstellen des Mitarbeiters")
        return new_worker

    @staticmethod
    def toggle_status(worker_id: int) -> Worker:
        """Toggle the active status of a worker (soft-delete)."""
        worker = _get_worker_or_raise(worker_id)

        if _is_last_active_admin(worker) and worker.is_active:
            raise LastAdminError()

        worker.is_active = not worker.is_active
        _commit_or_raise("Datenbankfehler beim Ändern des Status")
        return worker

    @staticmethod
    def update_worker(
        worker_id: int,
        name: str,
        is_admin: bool,
        role: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Worker:
        """Update worker's name, admin status, and role."""
        worker = _get_worker_or_raise(worker_id)
        if not name:
            raise ValueError("Name ist erforderlich.")

        if worker.name != name and Worker.query.filter_by(name=name).first():
            raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")

        if not role:
            role = (
                WorkerRole.ADMIN.value if is_admin else WorkerRole.WORKER.value
            )

        if _is_last_active_admin(worker) and role != WorkerRole.ADMIN.value:
            raise LastAdminError()

        worker.name = name
        worker.is_admin = is_admin
        worker.role = role
        if email is not None:
            worker.email = (
                email.strip().lower() if email.strip() else None
            )
        _commit_or_raise("Datenbankfehler beim Aktualisieren des Mitarbeiters")
        return worker

    @staticmethod
    def update_pin(worker_id: int, new_pin: str) -> Worker:
        """Update a worker's PIN."""
        worker = _get_worker_or_raise(worker_id)
        _validate_pin(new_pin)

        worker.pin_hash = generate_password_hash(new_pin)
        worker.needs_pin_change = False
        _commit_or_raise("Datenbankfehler beim Ändern der PIN")
        return worker

    @staticmethod
    def admin_reset_pin(worker_id: int) -> Worker:
        """Reset a worker's PIN to ``'0000'`` as an administrator."""
        worker = _get_worker_or_raise(worker_id)

        worker.pin_hash = generate_password_hash("0000")
        worker.needs_pin_change = True
        worker.failed_login_count = 0
        worker.locked_until = None
        _commit_or_raise("Datenbankfehler beim PIN-Reset")
        return worker

    @staticmethod
    def update_theme(worker_id: int, theme: str) -> None:
        """Persist the UI theme preference for *worker_id*."""
        worker = db.session.get(Worker, worker_id)
        if worker:
            worker.ui_theme = theme
            _commit_or_raise("Datenbankfehler beim Speichern des Themes")


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _is_last_active_admin(worker: Worker) -> bool:
    """Return ``True`` if *worker* is the only active admin."""
    if not (worker.is_admin or worker.role == WorkerRole.ADMIN.value):
        return False
    admin_count = Worker.query.filter_by(
        role=WorkerRole.ADMIN.value, is_active=True
    ).count()
    return admin_count <= 1
