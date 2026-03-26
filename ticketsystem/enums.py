from enum import Enum

class TicketStatus(Enum):
    """Status options for a ticket."""
    OFFEN = "offen"
    IN_BEARBEITUNG = "in_bearbeitung"
    WARTET = "wartet"
    ERLEDIGT = "erledigt"

    def __str__(self):
        return self.value

class TicketPriority(Enum):
    """Priority options for a ticket (1=High, 3=Low)."""
    HOCH = 1
    MITTEL = 2
    NIEDRIG = 3

    def __str__(self):
        return str(self.value)

class WorkerRole(str, Enum):
    """Role values for Worker.role — use instead of magic strings."""
    ADMIN = 'admin'
    WORKER = 'worker'
    VIEWER = 'viewer'
    HR = 'hr'

    def __str__(self):
        return self.value

class EventType(str, Enum):
    """Audit event types stored in Comment.event_type."""
    TICKET_CREATED = 'TICKET_CREATED'
    STATUS_CHANGED = 'STATUS_CHANGED'
    ASSIGNED = 'ASSIGNED'
    COMMENT_ADDED = 'COMMENT_ADDED'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    APPROVAL_REQUESTED = 'APPROVAL_REQUESTED'

    def __str__(self):
        return self.value
