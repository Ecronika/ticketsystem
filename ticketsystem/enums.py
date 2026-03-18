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
