"""Enum definitions for the Ticket System domain model."""

from enum import Enum

__all__ = [
    "TicketStatus",
    "TicketPriority",
    "WorkerRole",
    "ApprovalStatus",
    "ELEVATED_ROLES",
]


class TicketStatus(Enum):
    """Status options for a ticket."""

    OFFEN = "offen"
    IN_BEARBEITUNG = "in_bearbeitung"
    WARTET = "wartet"
    ERLEDIGT = "erledigt"

    def __str__(self) -> str:
        return self.value


class TicketPriority(Enum):
    """Priority levels for a ticket (1=High, 3=Low)."""

    HOCH = 1
    MITTEL = 2
    NIEDRIG = 3

    def __str__(self) -> str:
        return str(self.value)


class WorkerRole(str, Enum):
    """Role values for ``Worker.role`` — use instead of magic strings."""

    ADMIN = "admin"
    WORKER = "worker"
    VIEWER = "viewer"
    HR = "hr"
    MANAGEMENT = "management"

    def __str__(self) -> str:
        return self.value


ELEVATED_ROLES = frozenset({
    WorkerRole.ADMIN.value,
    WorkerRole.HR.value,
    WorkerRole.MANAGEMENT.value,
})


class ApprovalStatus(str, Enum):
    """Approval states for a ticket."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NONE = "none"

    def __str__(self) -> str:
        return self.value
