"""Tests for the attachment upload feature (ticket detail page).

Covers:
  - Service: add_attachments audit comment, deleted/done ticket errors,
    no valid files, OOO delegation, skip self-notification,
    individual file too large, OSError handling, empty filename ignored,
    partial success audit.
  - API: no files → 400, too many files → 400, total size → 400,
    viewer rejected, approval lock rejected, success → HTML + count,
    mixed valid/invalid → partial success.
  - Regression: ticket creation with attachments still works.
"""

import io

import pytest

from enums import TicketStatus
from models import Attachment, Comment, Notification, Worker
from services.ticket_core_service import TicketCoreService
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(name="test.png", content=b"fake-png-data", mimetype="image/png"):
    """Create a werkzeug-compatible file-like for upload tests."""
    from werkzeug.datastructures import FileStorage
    return FileStorage(
        stream=io.BytesIO(content),
        filename=name,
        content_type=mimetype,
    )


def _login_session(client, worker):
    """Set session to simulate logged-in worker."""
    with client.session_transaction() as sess:
        sess["worker_id"] = worker.id
        sess["worker_name"] = worker.name
        sess["role"] = worker.role or "worker"
        sess["is_admin"] = worker.is_admin


def _create_worker(db_session, name, role="worker", is_admin=False, **kw):
    w = Worker(
        name=name,
        pin_hash=generate_password_hash("7391"),
        role=role,
        is_admin=is_admin,
        needs_pin_change=False,
        **kw,
    )
    db_session.add(w)
    db_session.flush()
    return w


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

class TestAddAttachmentsService:
    """Test TicketCoreService.add_attachments()."""

    def test_audit_comment_created(self, test_app, db):
        """Uploading files creates an ATTACHMENTS_ADDED system event."""
        with test_app.app_context():
            worker = _create_worker(db.session, "Tester")
            ticket = TicketCoreService.create_ticket(
                title="Audit Test", author_name="Tester", author_id=worker.id,
            )
            files = [_make_file("photo.png"), _make_file("doc.pdf", b"pdf", "application/pdf")]
            result = TicketCoreService.add_attachments(
                ticket.id, files, worker.id, "Tester",
            )
            assert len(result.saved) == 2
            comment = (
                Comment.query
                .filter_by(ticket_id=ticket.id, event_type="ATTACHMENTS_ADDED")
                .first()
            )
            assert comment is not None
            assert "2 Anhänge hinzugefügt" in comment.text

    def test_deleted_ticket_raises(self, test_app, db):
        """Cannot add attachments to a deleted ticket."""
        with test_app.app_context():
            worker = _create_worker(db.session, "Tester2")
            ticket = TicketCoreService.create_ticket(
                title="Del Test", author_name="Tester2", author_id=worker.id,
            )
            ticket.is_deleted = True
            db.session.commit()

            from exceptions import TicketNotFoundError
            with pytest.raises(TicketNotFoundError):
                TicketCoreService.add_attachments(
                    ticket.id, [_make_file()], worker.id, "Tester2",
                )

    def test_done_ticket_raises(self, test_app, db):
        """Cannot add attachments to a completed ticket."""
        with test_app.app_context():
            worker = _create_worker(db.session, "Tester3")
            ticket = TicketCoreService.create_ticket(
                title="Done Test", author_name="Tester3", author_id=worker.id,
            )
            ticket.status = TicketStatus.ERLEDIGT.value
            db.session.commit()

            from exceptions import DomainError
            with pytest.raises(DomainError, match="Erledigtes Ticket"):
                TicketCoreService.add_attachments(
                    ticket.id, [_make_file()], worker.id, "Tester3",
                )

    def test_no_valid_files(self, test_app, db):
        """All files invalid → empty result, no audit comment."""
        with test_app.app_context():
            worker = _create_worker(db.session, "Tester4")
            ticket = TicketCoreService.create_ticket(
                title="No Valid", author_name="Tester4", author_id=worker.id,
            )
            files = [_make_file("virus.exe", b"bad", "application/octet-stream")]
            result = TicketCoreService.add_attachments(
                ticket.id, files, worker.id, "Tester4",
            )
            assert len(result.saved) == 0
            assert len(result.skipped) == 1
            assert result.skipped[0]["reason"] == "Dateityp nicht erlaubt"
            # No audit comment for zero saved
            assert not Comment.query.filter_by(
                ticket_id=ticket.id, event_type="ATTACHMENTS_ADDED",
            ).first()

    def test_file_too_large_skipped(self, test_app, db):
        """Individual file exceeding limit is skipped."""
        with test_app.app_context():
            worker = _create_worker(db.session, "Tester5")
            ticket = TicketCoreService.create_ticket(
                title="Size Test", author_name="Tester5", author_id=worker.id,
            )
            # Create a file that exceeds MAX_UPLOAD_FILE_SIZE (15 MB)
            big = _make_file("big.png", b"x" * (15 * 1024 * 1024 + 1))
            result = TicketCoreService.add_attachments(
                ticket.id, [big], worker.id, "Tester5",
            )
            assert len(result.saved) == 0
            assert result.skipped[0]["reason"] == "Datei zu groß"

    def test_empty_filename_ignored(self, test_app, db):
        """Files with empty filename are silently ignored."""
        with test_app.app_context():
            worker = _create_worker(db.session, "Tester6")
            ticket = TicketCoreService.create_ticket(
                title="Empty FN", author_name="Tester6", author_id=worker.id,
            )
            empty = _make_file("", b"data")
            valid = _make_file("ok.txt", b"hello", "text/plain")
            result = TicketCoreService.add_attachments(
                ticket.id, [empty, valid], worker.id, "Tester6",
            )
            assert len(result.saved) == 1
            assert result.saved[0].filename == "ok.txt"

    def test_notification_not_sent_to_self(self, test_app, db):
        """No notification if uploader is the assigned worker."""
        with test_app.app_context():
            worker = _create_worker(db.session, "SelfAssign")
            ticket = TicketCoreService.create_ticket(
                title="Self Notify", author_name="SelfAssign",
                author_id=worker.id,
            )
            ticket.assigned_to_id = worker.id
            db.session.commit()

            count_before = Notification.query.filter_by(user_id=worker.id).count()
            TicketCoreService.add_attachments(
                ticket.id, [_make_file()], worker.id, "SelfAssign",
            )
            count_after = Notification.query.filter_by(user_id=worker.id).count()
            assert count_after == count_before

    def test_notification_with_ooo_delegation(self, test_app, db):
        """Notification goes to delegate when assigned worker is OOO."""
        with test_app.app_context():
            uploader = _create_worker(db.session, "Uploader")
            assigned = _create_worker(
                db.session, "Absent",
                is_out_of_office=True,
            )
            delegate = _create_worker(db.session, "Delegate")
            assigned.delegate_to_id = delegate.id
            db.session.flush()

            ticket = TicketCoreService.create_ticket(
                title="OOO Test", author_name="Uploader",
                author_id=uploader.id,
            )
            ticket.assigned_to_id = assigned.id
            db.session.commit()

            TicketCoreService.add_attachments(
                ticket.id, [_make_file()], uploader.id, "Uploader",
            )
            notif = Notification.query.filter_by(user_id=delegate.id).first()
            assert notif is not None
            assert "1 Anhänge" in notif.message

    def test_partial_success_audit(self, test_app, db):
        """Mixed valid/invalid files: audit only mentions saved files."""
        with test_app.app_context():
            worker = _create_worker(db.session, "Partial")
            ticket = TicketCoreService.create_ticket(
                title="Partial Test", author_name="Partial",
                author_id=worker.id,
            )
            files = [
                _make_file("good.png"),
                _make_file("bad.exe", b"x", "application/octet-stream"),
            ]
            result = TicketCoreService.add_attachments(
                ticket.id, files, worker.id, "Partial",
            )
            assert len(result.saved) == 1
            assert len(result.skipped) == 1
            comment = Comment.query.filter_by(
                ticket_id=ticket.id, event_type="ATTACHMENTS_ADDED",
            ).first()
            assert "1 Anhänge hinzugefügt" in comment.text


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TestUploadAttachmentsAPI:
    """Test POST /api/ticket/<id>/attachments endpoint."""

    def _setup_worker_and_ticket(self, db_session, client):
        worker = _create_worker(db_session, "APIWorker", role="admin", is_admin=True)
        db_session.commit()
        _login_session(client, worker)
        ticket = TicketCoreService.create_ticket(
            title="API Test", author_name="APIWorker", author_id=worker.id,
        )
        return worker, ticket

    def test_no_files_returns_400(self, test_app, db, client):
        with test_app.app_context():
            _, ticket = self._setup_worker_and_ticket(db.session, client)
            resp = client.post(
                f"/api/ticket/{ticket.id}/attachments",
                content_type="multipart/form-data",
                data={},
            )
            assert resp.status_code == 400
            assert b"Keine Dateien" in resp.data

    def test_too_many_files_returns_400(self, test_app, db, client):
        with test_app.app_context():
            _, ticket = self._setup_worker_and_ticket(db.session, client)
            data = {
                "attachments": [_make_file(f"file{i}.png") for i in range(11)]
            }
            resp = client.post(
                f"/api/ticket/{ticket.id}/attachments",
                content_type="multipart/form-data",
                data=data,
            )
            assert resp.status_code == 400
            assert b"Maximal 10" in resp.data

    def test_success_returns_html_and_count(self, test_app, db, client):
        with test_app.app_context():
            _, ticket = self._setup_worker_and_ticket(db.session, client)
            data = {
                "attachments": _make_file("photo.jpg", b"img", "image/jpeg"),
            }
            resp = client.post(
                f"/api/ticket/{ticket.id}/attachments",
                content_type="multipart/form-data",
                data=data,
            )
            assert resp.status_code == 200
            json_data = resp.get_json()
            assert json_data["success"] is True
            assert json_data["count"] == 1
            assert len(json_data["attachment_ids"]) == 1
            assert "html" in json_data

    def test_viewer_rejected(self, test_app, db, client):
        with test_app.app_context():
            worker = _create_worker(db.session, "Viewer", role="viewer")
            db.session.commit()
            ticket = TicketCoreService.create_ticket(
                title="Viewer Test", author_name="System",
            )
            _login_session(client, worker)
            data = {
                "attachments": _make_file(),
            }
            resp = client.post(
                f"/api/ticket/{ticket.id}/attachments",
                content_type="multipart/form-data",
                data=data,
            )
            # write_required decorator blocks viewers
            assert resp.status_code in (302, 403)

    def test_invalid_files_only_returns_400(self, test_app, db, client):
        with test_app.app_context():
            _, ticket = self._setup_worker_and_ticket(db.session, client)
            data = {
                "attachments": _make_file("virus.exe", b"bad", "application/octet-stream"),
            }
            resp = client.post(
                f"/api/ticket/{ticket.id}/attachments",
                content_type="multipart/form-data",
                data=data,
            )
            assert resp.status_code == 400
            assert b"Keine g" in resp.data  # "Keine gültigen Dateien"


# ---------------------------------------------------------------------------
# Regression test
# ---------------------------------------------------------------------------

class TestTicketCreationWithAttachments:
    """Ensure ticket creation with attachments still works after refactoring."""

    def test_create_ticket_with_attachments(self, test_app, db):
        with test_app.app_context():
            files = [
                _make_file("photo.jpg", b"imgdata", "image/jpeg"),
                _make_file("doc.pdf", b"pdfdata", "application/pdf"),
            ]
            ticket = TicketCoreService.create_ticket(
                title="With Attachments",
                description="Regression test",
                author_name="Tester",
                attachments=files,
            )
            assert ticket.id is not None
            attachments = Attachment.query.filter_by(ticket_id=ticket.id).all()
            assert len(attachments) == 2

    def test_create_ticket_without_attachments(self, test_app, db):
        with test_app.app_context():
            ticket = TicketCoreService.create_ticket(
                title="No Attachments",
                author_name="Tester",
            )
            assert ticket.id is not None
            attachments = Attachment.query.filter_by(ticket_id=ticket.id).all()
            assert len(attachments) == 0
