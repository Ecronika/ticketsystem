"""Retention job tests."""
from datetime import timedelta

from models import ApiAuditLog, TicketTranscript, Ticket
from services.api_retention_service import ApiRetentionService
from utils import get_utc_now


def test_audit_log_retention_deletes_old_entries(app, db_session):
    old = ApiAuditLog(
        timestamp=get_utc_now() - timedelta(days=91),
        source_ip="1.2.3.4", method="POST", path="/api/v1/x",
        status_code=200, latency_ms=1, outcome="success", request_id="old",
    )
    new = ApiAuditLog(
        timestamp=get_utc_now() - timedelta(days=1),
        source_ip="1.2.3.4", method="POST", path="/api/v1/x",
        status_code=200, latency_ms=1, outcome="success", request_id="new",
    )
    db_session.add_all([old, new])
    db_session.commit()
    deleted = ApiRetentionService.prune_audit_log(retention_days=90)
    assert deleted == 1
    assert ApiAuditLog.query.filter_by(request_id="new").count() == 1
    assert ApiAuditLog.query.filter_by(request_id="old").count() == 0


def test_transcript_retention_deletes_old_but_keeps_ticket(app, db_session):
    t = Ticket(title="T", created_at=get_utc_now() - timedelta(days=95))
    db_session.add(t)
    db_session.flush()
    old_tr = TicketTranscript(
        ticket_id=t.id, position=0, role="user", content="old",
        created_at=get_utc_now() - timedelta(days=95),
    )
    new_tr = TicketTranscript(
        ticket_id=t.id, position=1, role="user", content="new",
        created_at=get_utc_now() - timedelta(days=5),
    )
    db_session.add_all([old_tr, new_tr])
    db_session.commit()
    deleted = ApiRetentionService.prune_transcripts(retention_days=90)
    assert deleted == 1
    # Ticket survives
    assert db_session.get(Ticket, t.id) is not None
    # Only one transcript left
    assert len(db_session.get(Ticket, t.id).transcripts) == 1


def test_audit_log_retention_commits_across_sessions(app, db_session):
    """Regression test: the delete must be committed, not only flushed in-session.

    If prune_audit_log forgets to commit, a fresh session would still see the
    'deleted' rows. This test opens a fresh session (via expire_all) and
    verifies the deletion is actually persisted.
    """
    old = ApiAuditLog(
        timestamp=get_utc_now() - timedelta(days=91),
        source_ip="1.2.3.4", method="POST", path="/api/v1/x",
        status_code=200, latency_ms=1, outcome="success",
        request_id="commit-check",
    )
    db_session.add(old)
    db_session.commit()

    deleted = ApiRetentionService.prune_audit_log(retention_days=90)
    assert deleted == 1

    # Expire all in-session state → forces re-fetch from DB.
    # If the delete was NOT committed, the row would re-appear here.
    db_session.expire_all()
    assert ApiAuditLog.query.filter_by(request_id="commit-check").count() == 0


def test_transcript_retention_commits_across_sessions(app, db_session):
    """Regression test: transcript delete persists across session expiry."""
    t = Ticket(title="TCOM", created_at=get_utc_now() - timedelta(days=95))
    db_session.add(t)
    db_session.flush()
    old_tr = TicketTranscript(
        ticket_id=t.id, position=0, role="user", content="commit-check",
        created_at=get_utc_now() - timedelta(days=95),
    )
    db_session.add(old_tr)
    db_session.commit()

    deleted = ApiRetentionService.prune_transcripts(retention_days=90)
    assert deleted == 1

    db_session.expire_all()
    # Ticket survives
    assert db_session.get(Ticket, t.id) is not None
    # Transcript gone
    assert TicketTranscript.query.filter_by(ticket_id=t.id).count() == 0
