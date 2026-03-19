"""
Worker Service module.

Handles business logic for Worker management (CRUD, Status, Auth).
"""
from werkzeug.security import generate_password_hash
from extensions import db
from models import Worker

class WorkerService:
    """Service layer for Worker-related operations."""

    @staticmethod
    def get_all_workers():
        """Return all workers, ordered by admin status and name."""
        return Worker.query.order_by(Worker.is_admin.desc(), Worker.name.asc()).all()

    @staticmethod
    def create_worker(name, pin, is_admin=False):
        """Create a new worker with hashed PIN."""
        if not name or not pin:
            raise ValueError("Name und PIN sind erforderlich.")
        
        if Worker.query.filter_by(name=name).first():
            raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")

        new_worker = Worker(
            name=name,
            pin_hash=generate_password_hash(pin),
            is_admin=is_admin,
            is_active=True
        )
        db.session.add(new_worker)
        db.session.commit()
        return new_worker

    @staticmethod
    def toggle_status(worker_id):
        """Toggle the active status of a worker (Soft-Delete)."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        
        # Prevent deactivating the last admin (safety)
        if worker.is_admin and worker.is_active:
            admin_count = Worker.query.filter_by(is_admin=True, is_active=True).count()
            if admin_count <= 1:
                raise ValueError("Der letzte aktive Administrator kann nicht deaktiviert werden.")

        worker.is_active = not worker.is_active
        db.session.commit()
        return worker

    @staticmethod
    def update_worker(worker_id, name, is_admin):
        """Update worker's name and admin status."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        
        if not name:
            raise ValueError("Name ist erforderlich.")
        
        # Check for name collision if name changed
        if worker.name != name:
            if Worker.query.filter_by(name=name).first():
                raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")
        
        # Prevent removing admin from the last admin
        if worker.is_admin and not is_admin:
            active_admins = Worker.query.filter_by(is_admin=True, is_active=True).count()
            if active_admins <= 1:
                raise ValueError("Der letzte Administrator kann nicht zum normalen Mitarbeiter degradiert werden.")

        worker.name = name
        worker.is_admin = is_admin
        db.session.commit()
        return worker

    @staticmethod
    def update_pin(worker_id, new_pin):
        """Update a worker's PIN."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        
        worker.pin_hash = generate_password_hash(new_pin)
        db.session.commit()
        return worker
