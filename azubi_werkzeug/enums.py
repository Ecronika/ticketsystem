"""
Enums module.

Centralizes Enumeration types to prevent circular imports between models,
DTOs, and services.
"""
from enum import Enum


class CheckType(Enum):
    """Enumeration of tool check types."""

    CHECK = 'check'
    ISSUE = 'issue'
    RETURN = 'return'
    EXCHANGE = 'exchange'
