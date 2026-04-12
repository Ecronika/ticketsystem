"""Retention jobs for API-related PII data."""
from __future__ import annotations

import logging
from datetime import timedelta

from flask import Flask

from models import ApiAuditLog, TicketTranscript
from services._helpers import db_transaction
from utils import get_utc_now

_logger = logging.getLogger(__name__)


class ApiRetentionService:
    """Deletes old PII data (audit log + call transcripts) per retention policy."""

    @staticmethod
    @db_transaction
    def prune_audit_log(retention_days: int = 90) -> int:
        """Delete api_audit_log rows older than *retention_days*. Returns delete count."""
        cutoff = get_utc_now() - timedelta(days=retention_days)
        count = ApiAuditLog.query.filter(ApiAuditLog.timestamp < cutoff).delete(
            synchronize_session=False
        )
        return count

    @staticmethod
    @db_transaction
    def prune_transcripts(retention_days: int = 90) -> int:
        """Delete ticket_transcript rows older than *retention_days*. Ticket survives."""
        cutoff = get_utc_now() - timedelta(days=retention_days)
        count = TicketTranscript.query.filter(
            TicketTranscript.created_at < cutoff
        ).delete(synchronize_session=False)
        return count


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

def schedule_api_retention_jobs(app: Flask) -> None:
    """Register the API retention jobs (daily at 03:15 and 03:30 UTC)."""
    try:
        from extensions import scheduler

        def _prune_audit() -> None:
            with app.app_context():
                deleted = ApiRetentionService.prune_audit_log(90)
                _logger.info("api_audit_retention: deleted %d rows", deleted)

        def _prune_transcripts() -> None:
            with app.app_context():
                deleted = ApiRetentionService.prune_transcripts(90)
                _logger.info("api_transcript_retention: deleted %d rows", deleted)

        scheduler.add_job(
            id="api_audit_retention",
            func=_prune_audit,
            trigger="cron",
            hour=3,
            minute=15,
            replace_existing=True,
        )
        _logger.info("Scheduled job: api_audit_retention at 03:15")

        scheduler.add_job(
            id="api_transcript_retention",
            func=_prune_transcripts,
            trigger="cron",
            hour=3,
            minute=30,
            replace_existing=True,
        )
        _logger.info("Scheduled job: api_transcript_retention at 03:30")
    except Exception as exc:
        _logger.error("Failed to schedule API retention jobs: %s", exc)
