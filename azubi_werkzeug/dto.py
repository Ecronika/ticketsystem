"""DTO module."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from enums import CheckType


@dataclass
class CheckSubmissionContext:
    """Context for a tool check submission."""

    azubi_id: int
    azubi_name: str
    examiner_name: str
    datum: datetime
    check_type: CheckType
    session_id: str
    sig_azubi_path: Optional[str]
    sig_examiner_path: Optional[str]
    is_migration: bool = False
