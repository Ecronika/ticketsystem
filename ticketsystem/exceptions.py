"""Domain exception hierarchy for the Ticket System.

Each exception carries a ``status_code`` that the global error handler
and the ``@api_endpoint`` decorator translate into the appropriate HTTP
response.
"""


class DomainError(Exception):
    """Base class for all domain-specific errors."""

    status_code: int = 400


class NotFoundError(DomainError):
    """Requested resource does not exist."""

    status_code = 404


class TicketNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("Ticket nicht gefunden.")


class WorkerNotFoundError(NotFoundError):
    def __init__(self, msg: str = "Mitarbeiter nicht gefunden.") -> None:
        super().__init__(msg)


class AccessDeniedError(DomainError):
    """Caller lacks permission for the requested action."""

    status_code = 403

    def __init__(self, msg: str = "Keine Berechtigung.") -> None:
        super().__init__(msg)


class InvalidStatusTransitionError(DomainError):
    """Status change is not allowed."""
    pass


class DependencyNotMetError(DomainError):
    """A prerequisite (e.g. checklist dependency) is not fulfilled."""
    pass


class ApprovalAlreadyPendingError(DomainError):
    """An approval request already exists for this ticket."""

    def __init__(self) -> None:
        super().__init__("Freigabe bereits angefragt.")


class InvalidPinError(DomainError):
    """The supplied PIN does not meet the security requirements."""
    pass


class LastAdminError(DomainError):
    """Operation would remove the last active admin account."""

    def __init__(self) -> None:
        super().__init__(
            "Letzter aktiver Admin kann nicht deaktiviert oder "
            "herabgestuft werden."
        )


class ApiKeyError(DomainError):
    """Base class for API-key related errors."""
    status_code = 401


class InvalidApiKey(ApiKeyError):
    """Generic invalid or missing API key."""

    def __init__(self):
        super().__init__("unauthorized")


class IpNotAllowed(ApiKeyError):
    """Source IP is not in the key's allowlist."""

    status_code = 403

    def __init__(self):
        super().__init__("forbidden")


class ScopeDenied(ApiKeyError):
    """Key does not have the required scope."""

    status_code = 403

    def __init__(self, scope: str):
        self.scope = scope
        super().__init__("forbidden")
