"""
Exceptions module.

Custom exception classes for tiered error handling.
"""


class AzubiWerkzeugError(Exception):
    """Base exception for the application."""


class ValidationError(AzubiWerkzeugError):
    """Exception raised for business logic validation errors."""


class DatabaseError(AzubiWerkzeugError):
    """Exception raised for database-related failures."""


class SignatureError(ValidationError):
    """Exception raised when signature processing fails."""


class BackupError(AzubiWerkzeugError):
    """Exception raised when backup or restore operations fail."""
