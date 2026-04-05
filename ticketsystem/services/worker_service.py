"""Worker Service module.

Handles business logic for Worker management (CRUD, status, auth).
"""

from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from enums import WorkerRole
from extensions import db
from models import Worker


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

        if Worker.query.filter_by(name=name).first():
            raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")

        if not role:
            role = (
                WorkerRole.ADMIN.value if is_admin else WorkerRole.WORKER.value
            )

        try:
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
            db.session.commit()
            return new_worker
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise ValueError(
                f"Datenbankfehler beim Erstellen des Mitarbeiters: {exc}"
            ) from exc

    @staticmethod
    def toggle_status(worker_id: int) -> Worker:
        """Toggle the active status of a worker (soft-delete)."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")

        if _is_last_active_admin(worker) and worker.is_active:
            raise ValueError(
                "Der letzte aktive Administrator kann nicht deaktiviert werden."
            )

        try:
            worker.is_active = not worker.is_active
            db.session.commit()
            return worker
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise ValueError(
                f"Datenbankfehler beim Ändern des Status: {exc}"
            ) from exc

    @staticmethod
    def update_worker(
        worker_id: int,
        name: str,
        is_admin: bool,
        role: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Worker:
        """Update worker's name, admin status, and role."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        if not name:
            raise ValueError("Name ist erforderlich.")

        if worker.name != name and Worker.query.filter_by(name=name).first():
            raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")

        if not role:
            role = (
                WorkerRole.ADMIN.value if is_admin else WorkerRole.WORKER.value
            )

        if _is_last_active_admin(worker) and role != WorkerRole.ADMIN.value:
            raise ValueError(
                "Der letzte aktive Administrator kann nicht zum normalen "
                "Mitarbeiter degradiert werden. Aktivieren Sie erst einen "
                "anderen Administrator."
            )

        try:
            worker.name = name
            worker.is_admin = is_admin
            worker.role = role
            if email is not None:
                worker.email = (
                    email.strip().lower() if email.strip() else None
                )
            db.session.commit()
            return worker
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise ValueError(
                f"Datenbankfehler beim Aktualisieren des Mitarbeiters: {exc}"
            ) from exc

    @staticmethod
    def update_pin(worker_id: int, new_pin: str) -> Worker:
        """Update a worker's PIN."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")

        try:
            worker.pin_hash = generate_password_hash(new_pin)
            worker.needs_pin_change = False
            db.session.commit()
            return worker
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise ValueError(
                f"Datenbankfehler beim Ändern der PIN: {exc}"
            ) from exc

    @staticmethod
    def admin_reset_pin(worker_id: int) -> Worker:
        """Reset a worker's PIN to ``'0000'`` as an administrator."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")

        try:
            worker.pin_hash = generate_password_hash("0000")
            worker.needs_pin_change = True
            worker.failed_login_count = 0
            worker.locked_until = None
            db.session.commit()
            return worker
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise ValueError(
                f"Datenbankfehler beim PIN-Reset: {exc}"
            ) from exc


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
