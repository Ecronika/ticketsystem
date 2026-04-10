import pytest
from services.worker_service import WorkerService
from exceptions import InvalidPinError, LastAdminError
from models import Worker

def test_create_worker(test_app):
    worker = WorkerService.create_worker("Test Worker", "7391", is_admin=False)
    assert worker.id is not None
    assert worker.name == "Test Worker"
    assert worker.is_admin is False
    assert worker.is_active is True

def test_duplicate_worker_error(test_app):
    WorkerService.create_worker("Dup", "7391")
    with pytest.raises(ValueError, match="existiert bereits"):
        WorkerService.create_worker("Dup", "8264")

def test_toggle_worker_status(test_app):
    worker = WorkerService.create_worker("ToggleMe", "7391")
    assert worker.is_active is True

    WorkerService.toggle_status(worker.id)
    assert worker.is_active is False

    WorkerService.toggle_status(worker.id)
    assert worker.is_active is True

def test_prevent_last_admin_deactivation(test_app):
    # Setup: one active admin
    admin = Worker.query.filter_by(is_admin=True, is_active=True).first()
    if not admin:
        admin = WorkerService.create_worker("Admin1", "7391", is_admin=True)

    # Try to deactivate the only active admin
    with pytest.raises(LastAdminError):
        WorkerService.toggle_status(admin.id)

def test_update_worker(test_app):
    worker = WorkerService.create_worker("UpdateName", "7391", is_admin=False)

    # Update name
    WorkerService.update_worker(worker.id, "NewName", is_admin=False)
    assert worker.name == "NewName"

    # Update admin status
    WorkerService.update_worker(worker.id, "NewName", is_admin=True)
    assert worker.is_admin is True

    # Prevent degrading last admin
    with pytest.raises(LastAdminError):
        WorkerService.update_worker(worker.id, "NewName", is_admin=False)
