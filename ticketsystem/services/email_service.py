"""Email Service — SMTP-based notification delivery.

Configuration via SystemSettings (DB) with environment-variable fallback::

    SMTP_HOST      — e.g. smtp.gmail.com          (required to enable)
    SMTP_PORT      — default 587
    SMTP_USER      — SMTP login username
    SMTP_PASSWORD  — SMTP login password
    SMTP_FROM      — Sender address (falls back to SMTP_USER)
    SMTP_TLS       — 'true' (STARTTLS, default) | 'ssl' (implicit) | 'false'

When ``SMTP_HOST`` is unset every method silently no-ops and logs a debug
message.
"""

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

_logger = logging.getLogger(__name__)

_PRIO_LABELS: Dict[int, str] = {1: "HOCH", 2: "MITTEL", 3: "NIEDRIG"}


# ---------------------------------------------------------------------------
# SMTP plumbing
# ---------------------------------------------------------------------------

def _db_get(key: str) -> str:
    """Read a value from SystemSettings, suppressing all DB errors."""
    try:
        from models import SystemSettings
        return SystemSettings.get_setting(key) or ""
    except Exception:  # inevitable: DB may not be ready at import time
        return ""


def _smtp_config() -> Optional[Dict[str, object]]:
    """Return SMTP config dict from DB (env fallback), or ``None``."""
    host = _db_get("smtp_host") or os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return None

    port_raw = _db_get("smtp_port") or os.environ.get("SMTP_PORT", "587")
    user = _db_get("smtp_user") or os.environ.get("SMTP_USER", "")
    password = _db_get("smtp_password") or os.environ.get("SMTP_PASSWORD", "")
    from_addr = (
        _db_get("smtp_from")
        or os.environ.get("SMTP_FROM")
        or user
        or "noreply@ticketsystem"
    )
    tls = (
        _db_get("smtp_tls") or os.environ.get("SMTP_TLS", "starttls")
    ).strip().lower()

    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        port = 587

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from": from_addr,
        "tls": tls,
    }


def _send(
    to_address: str, subject: str, html_body: str, text_body: Optional[str] = None
) -> bool:
    """Low-level send.  Returns ``True`` on success, ``False`` on failure."""
    cfg = _smtp_config()
    if not cfg:
        _logger.debug(
            "SMTP not configured — skipping email to %s: %s",
            to_address, subject,
        )
        return False
    if not to_address:
        _logger.debug("No recipient address — skipping: %s", subject)
        return False

    msg = _build_message(cfg, to_address, subject, html_body, text_body)

    try:
        _dispatch(cfg, to_address, msg)
        _logger.info("Email sent to %s: %s", to_address, subject)
        return True
    except smtplib.SMTPException as exc:
        _logger.error(
            "Failed to send email to %s (%s): %s", to_address, subject, exc
        )
        return False
    except OSError as exc:
        _logger.error(
            "Network error sending email to %s (%s): %s",
            to_address, subject, exc,
        )
        return False


def _build_message(
    cfg: Dict[str, object],
    to_address: str,
    subject: str,
    html_body: str,
    text_body: Optional[str],
) -> MIMEMultipart:
    """Assemble a MIME multipart/alternative message."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = str(cfg["from"])
    msg["To"] = to_address
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _dispatch(
    cfg: Dict[str, object], to_address: str, msg: MIMEMultipart
) -> None:
    """Send the assembled message via the configured transport."""
    host = str(cfg["host"])
    port = int(cfg["port"])  # type: ignore[arg-type]
    user = str(cfg["user"])
    password = str(cfg["password"])
    from_addr = str(cfg["from"])
    tls_mode = str(cfg["tls"])

    if tls_mode == "ssl":
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx) as server:
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to_address], msg.as_bytes())
    elif tls_mode == "false":
        with smtplib.SMTP(host, port) as server:
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to_address], msg.as_bytes())
    else:  # STARTTLS (default)
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to_address], msg.as_bytes())


def _base_url() -> str:
    """Best-effort base URL for clickable links in emails."""
    return (
        _db_get("smtp_base_url")
        or os.environ.get("SMTP_BASE_URL", "")
    ).rstrip("/")


def _ticket_url(ticket_id: int) -> str:
    """Build a ticket deep-link for email bodies."""
    base = _base_url()
    return f"{base}/ticket/{ticket_id}" if base else f"#ticket-{ticket_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class EmailService:
    """Public API for all notification emails."""

    @staticmethod
    def send_notification(
        recipient_name: str,
        ticket_id: int,
        priority: int,
        recipient_email: Optional[str] = None,
    ) -> bool:
        """Notify a worker about a high-priority ticket assignment."""
        if not recipient_email:
            _logger.debug(
                "send_notification: no email for %s — skipping",
                recipient_name,
            )
            return False

        prio_label = _PRIO_LABELS.get(priority, str(priority))
        subject = (
            f"[TicketSystem] DRINGEND: Ticket #{ticket_id} "
            f"Ihnen zugewiesen (Prio {prio_label})"
        )
        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p>Ihnen wurde Ticket <strong>#{ticket_id}</strong> "
            f"mit Priorität <strong>{prio_label}</strong> zugewiesen.</p>"
            f"<p><a href='{url}'>Ticket öffnen →</a></p>"
            "<hr><p style='color:#888;font-size:0.85em;'>"
            "TicketSystem — automatische Benachrichtigung</p>"
        )
        text = (
            f"Hallo {recipient_name},\n"
            f"Ticket #{ticket_id} (Prio {prio_label}) "
            f"wurde Ihnen zugewiesen.\n{url}"
        )
        return _send(recipient_email, subject, html, text)

    @staticmethod
    def send_mention(
        recipient_name: str,
        ticket_id: int,
        mentioned_by: str,
        recipient_email: Optional[str] = None,
    ) -> bool:
        """Notify a worker who was ``@mentioned`` in a comment."""
        if not recipient_email:
            return False
        subject = (
            f"[TicketSystem] {mentioned_by} hat Sie "
            f"in Ticket #{ticket_id} erwähnt"
        )
        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p><strong>{mentioned_by}</strong> hat Sie in einem "
            f"Kommentar zu Ticket <strong>#{ticket_id}</strong> erwähnt.</p>"
            f"<p><a href='{url}'>Zum Kommentar →</a></p>"
            "<hr><p style='color:#888;font-size:0.85em;'>"
            "TicketSystem — automatische Benachrichtigung</p>"
        )
        text = (
            f"Hallo {recipient_name},\n"
            f"{mentioned_by} hat Sie in Ticket #{ticket_id} erwähnt.\n{url}"
        )
        return _send(recipient_email, subject, html, text)

    @staticmethod
    def send_approval_request(
        admin_emails: List[str],
        ticket_id: int,
        requester_name: str,
    ) -> bool:
        """Notify admins/management that approval is requested."""
        if not admin_emails:
            return False
        subject = f"[TicketSystem] Freigabe angefragt: Ticket #{ticket_id}"
        url = _ticket_url(ticket_id)
        html = (
            f"<p><strong>{requester_name}</strong> bittet um Freigabe "
            f"für Ticket <strong>#{ticket_id}</strong>.</p>"
            f"<p><a href='{url}'>Freigabe erteilen oder ablehnen →</a></p>"
            "<hr><p style='color:#888;font-size:0.85em;'>"
            "TicketSystem — automatische Benachrichtigung</p>"
        )
        text = (
            f"{requester_name} bittet um Freigabe "
            f"für Ticket #{ticket_id}.\n{url}"
        )
        sent = sum(1 for addr in admin_emails if _send(addr, subject, html, text))
        return sent > 0

    @staticmethod
    def send_approval_result(
        recipient_name: str,
        ticket_id: int,
        approved: bool,
        reason: Optional[str] = None,
        recipient_email: Optional[str] = None,
    ) -> bool:
        """Notify assignee that a ticket was approved or rejected."""
        if not recipient_email:
            return False

        if approved:
            subject = f"[TicketSystem] Ticket #{ticket_id} wurde freigegeben"
            body = (
                f"Ticket <strong>#{ticket_id}</strong> "
                "wurde <strong>freigegeben</strong>."
            )
        else:
            subject = f"[TicketSystem] Ticket #{ticket_id} wurde abgelehnt"
            reason_text = (
                f"<br><strong>Grund:</strong> {reason}" if reason else ""
            )
            body = (
                f"Ticket <strong>#{ticket_id}</strong> "
                f"wurde <strong>abgelehnt</strong>.{reason_text}"
            )

        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p>{body}</p>"
            f"<p><a href='{url}'>Ticket öffnen →</a></p>"
            "<hr><p style='color:#888;font-size:0.85em;'>"
            "TicketSystem — automatische Benachrichtigung</p>"
        )
        return _send(recipient_email, subject, html)

    @staticmethod
    def send_sla_escalation(
        recipient_name: str,
        ticket_id: int,
        ticket_title: str,
        days_overdue: int,
        priority: int,
        recipient_email: Optional[str] = None,
    ) -> bool:
        """Notify assignee that their ticket is overdue (SLA breach)."""
        if not recipient_email:
            return False
        prio_label = _PRIO_LABELS.get(priority, str(priority))
        subject = (
            f"[TicketSystem] SLA-Eskalation: Ticket #{ticket_id} "
            f"seit {days_overdue} Tag(en) überfällig"
        )
        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p>Das Ticket <strong>#{ticket_id} – {ticket_title}</strong> "
            f"(Prio <strong>{prio_label}</strong>) ist seit "
            f"<strong>{days_overdue} Tag(en)</strong> überfällig und "
            "wurde bisher nicht abgeschlossen.</p>"
            f"<p><a href='{url}'>Ticket jetzt bearbeiten →</a></p>"
            "<hr><p style='color:#888;font-size:0.85em;'>"
            "TicketSystem — automatische SLA-Benachrichtigung</p>"
        )
        text = (
            f"Hallo {recipient_name},\n"
            f"Ticket #{ticket_id} ({prio_label}) ist seit "
            f"{days_overdue} Tag(en) überfällig.\n{url}"
        )
        return _send(recipient_email, subject, html, text)

    @staticmethod
    def send_meta_change(
        recipient_name: str,
        ticket_id: int,
        changed_by: str,
        changes: List[str],
        recipient_email: Optional[str] = None,
    ) -> bool:
        """Notify worker about ticket metadata changes."""
        if not recipient_email:
            return False
        subject = f"[TicketSystem] Ticket #{ticket_id} wurde bearbeitet"
        url = _ticket_url(ticket_id)
        changes_html = "".join(f"<li>{c}</li>" for c in changes)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p><strong>{changed_by}</strong> hat Ticket "
            f"<strong>#{ticket_id}</strong> bearbeitet:</p>"
            f"<ul>{changes_html}</ul>"
            f"<p><a href='{url}'>Ticket öffnen →</a></p>"
            "<hr><p style='color:#888;font-size:0.85em;'>"
            "TicketSystem — automatische Benachrichtigung</p>"
        )
        changes_text = "\n".join(f"  - {c}" for c in changes)
        text = (
            f"Hallo {recipient_name},\n"
            f"{changed_by} hat Ticket #{ticket_id} bearbeitet:\n"
            f"{changes_text}\n{url}"
        )
        return _send(recipient_email, subject, html, text)

    @staticmethod
    def send_pin_reset(
        worker_name: str,
        reset_url: str,
        recipient_email: str,
    ) -> bool:
        """Send a PIN reset link to a worker."""
        if not recipient_email:
            return False
        subject = "[TicketSystem] PIN zurücksetzen"
        html = (
            f"<p>Hallo <strong>{worker_name}</strong>,</p>"
            "<p>Sie haben eine PIN-Zurücksetzung angefordert.</p>"
            f"<p><a href='{reset_url}'>PIN jetzt zurücksetzen →</a></p>"
            "<p>Dieser Link ist <strong>15 Minuten</strong> gültig.</p>"
            "<p>Falls Sie diese Anfrage nicht gestellt haben, "
            "können Sie diese E-Mail ignorieren.</p>"
            "<hr><p style='color:#888;font-size:0.85em;'>"
            "TicketSystem — automatische Benachrichtigung</p>"
        )
        text = (
            f"Hallo {worker_name},\n"
            f"PIN zurücksetzen: {reset_url}\n"
            "Der Link ist 15 Minuten gültig."
        )
        return _send(recipient_email, subject, html, text)
