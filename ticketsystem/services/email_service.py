import logging

logger = logging.getLogger(__name__)

class EmailService:
    """
    Lightweight Service for handling email notifications.
    In this version, it simulates sending emails by logging them.
    """

    @staticmethod
    def send_notification(worker_name, ticket_id, priority):
        """
        Simulate sending an email notification to a worker.
        Email address is simulated as [worker_name]@firma.local.
        """
        email_address = f"{worker_name.lower().replace(' ', '.')}@firma.local"
        subject = f"DRINGEND: Ticket #{ticket_id} Ihnen zugewiesen"
        body = f"Hallo {worker_name},\n\ndas Ticket #{ticket_id} mit hoher Priorität wurde Ihnen zugewiesen.\nBitte bearbeiten Sie dies zeitnah.\n\nDies ist eine automatisch generierte E-Mail."
        
        # Simulation: Log the email
        logger.info("SIMULATED EMAIL SENT:")
        logger.info("To: %s", email_address)
        logger.info("Subject: %s", subject)
        logger.info("Body: %s", body)
        
        return True
