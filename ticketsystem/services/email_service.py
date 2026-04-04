"""
Email Service — SMTP-based notification delivery.

Configuration via environment variables:
  SMTP_HOST      — e.g. smtp.gmail.com          (required to enable)
  SMTP_PORT      — default 587
  SMTP_USER      — SMTP login username
  SMTP_PASSWORD  — SMTP login password
  SMTP_FROM      — Sender address (falls back to SMTP_USER)
  SMTP_TLS       — 'true' (STARTTLS, default) | 'ssl' (implicit TLS) | 'false'

When SMTP_HOST is not set, every method silently no-ops and logs a debug message.
"""
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _smtp_config():
    """Return SMTP config dict from env, or None if not configured."""
    host = os.environ.get('SMTP_HOST', '').strip()
    if not host:
        return None
    return {
        'host': host,
        'port': int(os.environ.get('SMTP_PORT', 587)),
        'user': os.environ.get('SMTP_USER', ''),
        'password': os.environ.get('SMTP_PASSWORD', ''),
        'from': os.environ.get('SMTP_FROM') or os.environ.get('SMTP_USER', 'noreply@ticketsystem'),
        'tls': os.environ.get('SMTP_TLS', 'true').strip().lower(),
    }


def _send(to_address, subject, html_body, text_body=None):
    """Low-level send. Returns True on success, False on failure."""
    cfg = _smtp_config()
    if not cfg:
        logger.debug("SMTP not configured — skipping email to %s: %s", to_address, subject)
        return False
    if not to_address:
        logger.debug("No recipient address — skipping: %s", subject)
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = cfg['from']
    msg['To'] = to_address
    if text_body:
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        if cfg['tls'] == 'ssl':
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg['host'], cfg['port'], context=ctx) as server:
                if cfg['user']:
                    server.login(cfg['user'], cfg['password'])
                server.sendmail(cfg['from'], [to_address], msg.as_bytes())
        elif cfg['tls'] == 'false':
            with smtplib.SMTP(cfg['host'], cfg['port']) as server:
                if cfg['user']:
                    server.login(cfg['user'], cfg['password'])
                server.sendmail(cfg['from'], [to_address], msg.as_bytes())
        else:  # STARTTLS (default)
            ctx = ssl.create_default_context()
            with smtplib.SMTP(cfg['host'], cfg['port']) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                if cfg['user']:
                    server.login(cfg['user'], cfg['password'])
                server.sendmail(cfg['from'], [to_address], msg.as_bytes())

        logger.info("Email sent to %s: %s", to_address, subject)
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to send email to %s (%s): %s", to_address, subject, e)
        return False


def _base_url():
    """Best-effort: read SMTP_BASE_URL env for clickable links in emails."""
    return os.environ.get('SMTP_BASE_URL', '').rstrip('/')


def _ticket_url(ticket_id):
    base = _base_url()
    return f"{base}/ticket/{ticket_id}" if base else f"#ticket-{ticket_id}"


class EmailService:
    """Public API for all notification emails."""

    # ------------------------------------------------------------------ #
    #  High-priority assignment (previously stubbed)                       #
    # ------------------------------------------------------------------ #
    @staticmethod
    def send_notification(recipient_name, ticket_id, priority, recipient_email=None):
        """Prio-1 ticket assigned to worker."""
        if not recipient_email:
            logger.debug("send_notification: no email for %s — skipping", recipient_name)
            return False

        prio_label = {1: 'HOCH', 2: 'MITTEL', 3: 'NIEDRIG'}.get(priority, str(priority))
        subject = f"[TicketSystem] DRINGEND: Ticket #{ticket_id} Ihnen zugewiesen (Prio {prio_label})"
        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p>Ihnen wurde Ticket <strong>#{ticket_id}</strong> mit Priorität <strong>{prio_label}</strong> zugewiesen.</p>"
            f"<p><a href='{url}'>Ticket öffnen →</a></p>"
            f"<hr><p style='color:#888;font-size:0.85em;'>TicketSystem — automatische Benachrichtigung</p>"
        )
        return _send(recipient_email, subject, html,
                     f"Hallo {recipient_name},\nTicket #{ticket_id} (Prio {prio_label}) wurde Ihnen zugewiesen.\n{url}")

    # ------------------------------------------------------------------ #
    #  @mention in comment                                                 #
    # ------------------------------------------------------------------ #
    @staticmethod
    def send_mention(recipient_name, ticket_id, mentioned_by, recipient_email=None):
        """Worker was @mentioned in a comment."""
        if not recipient_email:
            return False
        subject = f"[TicketSystem] {mentioned_by} hat Sie in Ticket #{ticket_id} erwähnt"
        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p><strong>{mentioned_by}</strong> hat Sie in einem Kommentar zu Ticket <strong>#{ticket_id}</strong> erwähnt.</p>"
            f"<p><a href='{url}'>Zum Kommentar →</a></p>"
            f"<hr><p style='color:#888;font-size:0.85em;'>TicketSystem — automatische Benachrichtigung</p>"
        )
        return _send(recipient_email, subject, html,
                     f"Hallo {recipient_name},\n{mentioned_by} hat Sie in Ticket #{ticket_id} erwähnt.\n{url}")

    # ------------------------------------------------------------------ #
    #  Approval request → notify all admins/management                    #
    # ------------------------------------------------------------------ #
    @staticmethod
    def send_approval_request(admin_emails, ticket_id, requester_name):
        """Notify admins/management that approval is requested."""
        if not admin_emails:
            return False
        subject = f"[TicketSystem] Freigabe angefragt: Ticket #{ticket_id}"
        url = _ticket_url(ticket_id)
        html = (
            f"<p><strong>{requester_name}</strong> bittet um Freigabe für Ticket <strong>#{ticket_id}</strong>.</p>"
            f"<p><a href='{url}'>Freigabe erteilen oder ablehnen →</a></p>"
            f"<hr><p style='color:#888;font-size:0.85em;'>TicketSystem — automatische Benachrichtigung</p>"
        )
        text = f"{requester_name} bittet um Freigabe für Ticket #{ticket_id}.\n{url}"
        sent = 0
        for addr in admin_emails:
            if _send(addr, subject, html, text):
                sent += 1
        return sent > 0

    # ------------------------------------------------------------------ #
    #  Approval result → notify assignee / ticket creator                 #
    # ------------------------------------------------------------------ #
    @staticmethod
    def send_approval_result(recipient_name, ticket_id, approved, reason=None, recipient_email=None):
        """Ticket was approved or rejected."""
        if not recipient_email:
            return False
        if approved:
            subject = f"[TicketSystem] Ticket #{ticket_id} wurde freigegeben"
            body = f"Ticket <strong>#{ticket_id}</strong> wurde <strong>freigegeben</strong>."
        else:
            subject = f"[TicketSystem] Ticket #{ticket_id} wurde abgelehnt"
            reason_text = f"<br><strong>Grund:</strong> {reason}" if reason else ""
            body = f"Ticket <strong>#{ticket_id}</strong> wurde <strong>abgelehnt</strong>.{reason_text}"

        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p>{body}</p>"
            f"<p><a href='{url}'>Ticket öffnen →</a></p>"
            f"<hr><p style='color:#888;font-size:0.85em;'>TicketSystem — automatische Benachrichtigung</p>"
        )
        return _send(recipient_email, subject, html)

    # ------------------------------------------------------------------ #
    #  SLA Escalation                                                      #
    # ------------------------------------------------------------------ #
    @staticmethod
    def send_sla_escalation(recipient_name, ticket_id, ticket_title, days_overdue,
                            priority, recipient_email=None):
        """Notify assignee that their ticket is overdue (SLA breach)."""
        if not recipient_email:
            return False
        prio_label = {1: 'HOCH', 2: 'MITTEL', 3: 'NIEDRIG'}.get(priority, str(priority))
        subject = f"[TicketSystem] SLA-Eskalation: Ticket #{ticket_id} seit {days_overdue} Tag(en) überfällig"
        url = _ticket_url(ticket_id)
        html = (
            f"<p>Hallo <strong>{recipient_name}</strong>,</p>"
            f"<p>Das Ticket <strong>#{ticket_id} – {ticket_title}</strong> (Prio <strong>{prio_label}</strong>) "
            f"ist seit <strong>{days_overdue} Tag(en)</strong> überfällig und wurde bisher nicht abgeschlossen.</p>"
            f"<p><a href='{url}'>Ticket jetzt bearbeiten →</a></p>"
            f"<hr><p style='color:#888;font-size:0.85em;'>TicketSystem — automatische SLA-Benachrichtigung</p>"
        )
        return _send(recipient_email, subject, html,
                     f"Hallo {recipient_name},\nTicket #{ticket_id} ({prio_label}) ist seit {days_overdue} Tag(en) überfällig.\n{url}")
