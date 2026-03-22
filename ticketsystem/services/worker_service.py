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
    def create_worker(name, pin, is_admin=False, role=None):
        """Create a new worker with hashed PIN and RBAC role."""
        if not name or not pin:
            raise ValueError("Name und PIN sind erforderlich.")
        
        if Worker.query.filter_by(name=name).first():
            raise ValueError(f"Mitarbeiter '{name}' existiert bereits.")

        # Sync role with is_admin if not provided
        if not role:
            role = 'admin' if is_admin else 'worker'

        new_worker = Worker(
            name=name,
            pin_hash=generate_password_hash(pin),
            is_admin=is_admin,
            role=role,
            is_active=True,
            needs_pin_change=True
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
        if (worker.is_admin or worker.role == 'admin') and worker.is_active:
            admin_count = Worker.query.filter_by(role='admin', is_active=True).count()
            if admin_count <= 1:
                raise ValueError("Der letzte aktive Administrator kann nicht deaktiviert werden.")

        worker.is_active = not worker.is_active
        db.session.commit()
        return worker

    @staticmethod
    def update_worker(worker_id, name, is_admin, role=None):
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
            role = 'admin' if is_admin else 'worker'

        # Prevent removing admin from the last admin
        if (worker.is_admin or worker.role == 'admin') and role != 'admin':
            active_admins = Worker.query.filter_by(role='admin', is_active=True).count()
            if active_admins <= 1:
                raise ValueError("Der letzte aktive Administrator kann nicht zum normalen Mitarbeiter degradiert werden. Aktivieren Sie erst einen anderen Administrator.")

        worker.name = name
        worker.is_admin = is_admin
        worker.role = role
        db.session.commit()
        return worker

    @staticmethod
    def update_pin(worker_id, new_pin):
        """Update a worker's PIN."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
        
        worker.pin_hash = generate_password_hash(new_pin)
        worker.needs_pin_change = False
        db.session.commit()
        return worker

    @staticmethod
    def admin_reset_pin(worker_id):
        """Reset a worker's PIN to '0000' as an administrator."""
        worker = db.session.get(Worker, worker_id)
        if not worker:
            raise ValueError("Mitarbeiter nicht gefunden.")
            
        worker.pin_hash = generate_password_hash("0000")
        worker.needs_pin_change = True
        db.session.commit()
        return worker
