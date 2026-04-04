"""
Worker Service module.

Handles business logic for Worker management (CRUD, Status, Auth).
"""
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models import Worker
from enums import WorkerRole

class WorkerService:
    """Service layer for Worker-related operations."""

    @staticmethod
    def get_all_workers():
        """Return all workers, ordered by admin status and name."""
        return Worker.query.order_by(Worker.is_admin.desc(), Worker.name.asc()).all()

    @staticmethod
    def create_worker(name, pin=None, is_admin=False, role=None, email=None):
        """Create a new worker with hashed PIN and RBAC role."""
        if not name:
            raise ValueError("Name ist erforderlich.")
        
        # Default PIN to '0000' if not provided
        effective_pin = pin if pin else "0000"
        
        if Worker.query.filter_by(name=name).first():
            raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")

        # Sync role with is_admin if not provided
        if not role:
            role = WorkerRole.ADMIN.value if is_admin else WorkerRole.WORKER.value

        try:
            new_worker = Worker(
                name=name,
                pin_hash=generate_password_hash(effective_pin),
                is_admin=is_admin,
                role=role,
                is_active=True,
                needs_pin_change=True,
                email=email.strip().lower() if email and email.strip() else None,
            )
            db.session.add(new_worker)
            db.session.commit()
            return new_worker
        except SQLAlchemyError as e:
            db.session.rollback()
            raise ValueError(f"Datenbankfehler beim Erstellen des Mitarbeiters: {e}")

    @staticmethod
    def toggle_status(worker_id):
        """Toggle the active status of a worker (Soft-Delete)."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        
        # Prevent deactivating the last admin (safety)
        if (worker.is_admin or worker.role == WorkerRole.ADMIN.value) and worker.is_active:
            admin_count = Worker.query.filter_by(role=WorkerRole.ADMIN.value, is_active=True).count()
            if admin_count <= 1:
                raise ValueError("Der letzte aktive Administrator kann nicht deaktiviert werden.")


        try:
            worker.is_active = not worker.is_active
            db.session.commit()
            return worker
        except SQLAlchemyError as e:
            db.session.rollback()
            raise ValueError(f"Datenbankfehler beim Ändern des Status: {e}")

    @staticmethod
    def update_worker(worker_id, name, is_admin, role=None, email=None):
        """Update worker's name and admin status/role."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        
        if not name:
            raise ValueError("Name ist erforderlich.")
        
        # Check for name collision if name changed
        if worker.name != name:
            if Worker.query.filter_by(name=name).first():
                raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")
        
        # Sync role with is_admin if only is_admin changed
        if not role:
            role = WorkerRole.ADMIN.value if is_admin else WorkerRole.WORKER.value

        # Prevent removing admin from the last admin
        if (worker.is_admin or worker.role == WorkerRole.ADMIN.value) and role != WorkerRole.ADMIN.value:
            active_admins = Worker.query.filter_by(role=WorkerRole.ADMIN.value, is_active=True).count()
            if active_admins <= 1:
                raise ValueError("Der letzte aktive Administrator kann nicht zum normalen Mitarbeiter degradiert werden. Aktivieren Sie erst einen anderen Administrator.")


        try:
            worker.name = name
            worker.is_admin = is_admin
            worker.role = role
            if email is not None:  # None = not submitted; empty string = clear
                worker.email = email.strip().lower() if email.strip() else None
            db.session.commit()
            return worker
        except SQLAlchemyError as e:
            db.session.rollback()
            raise ValueError(f"Datenbankfehler beim Aktualisieren des Mitarbeiters: {e}")

    @staticmethod
    def update_pin(worker_id, new_pin):
        """Update a worker's PIN."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        

        try:
            worker.pin_hash = generate_password_hash(new_pin)
            worker.needs_pin_change = False
            db.session.commit()
            return worker
        except SQLAlchemyError as e:
            db.session.rollback()
            raise ValueError(f"Datenbankfehler beim Ändern der PIN: {e}")

    @staticmethod
    def admin_reset_pin(worker_id):
        """Reset a worker's PIN to '0000' as an administrator."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
            
        try:
            worker.pin_hash = generate_password_hash("0000")
            worker.needs_pin_change = True
            # Reset lockout parameters so the user can log in immediately
            worker.failed_login_count = 0
            worker.locked_until = None
            db.session.commit()
            return worker
        except SQLAlchemyError as e:
            db.session.rollback()
            raise ValueError(f"Datenbankfehler beim PIN-Reset: {e}")
