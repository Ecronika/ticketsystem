"""System Service module.

Handles system-wide administrative tasks like recovery-token generation.
"""

import json
import secrets
from datetime import datetime, timezone
from typing import List

from werkzeug.security import generate_password_hash

from models import SystemSettings

# Alphanumeric alphabet excluding visually ambiguous characters (O/0, I/1)
_TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_TOKEN_LENGTH = 12
_TOKEN_COUNT = 10


class SystemService:
    """Service layer for system-wide operations."""

    @staticmethod
    def generate_recovery_tokens() -> List[str]:
        """Generate fresh recovery tokens.

        Hashes are stored for verification; raw tokens are stored
        temporarily for one-time display (expires after 5 minutes).
        """
        tokens: List[str] = []
        hashes: List[str] = []

        for _ in range(_TOKEN_COUNT):
            token = "".join(
                secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LENGTH)
            )
            tokens.append(token)
            hashes.append(generate_password_hash(token))

        SystemSettings.set_setting("recovery_tokens_raw", json.dumps(tokens))
        SystemSettings.set_setting(
            "recovery_tokens_generated_at",
            datetime.now(timezone.utc).isoformat(),
        )
        SystemSettings.set_setting(
            "recovery_tokens_hash", ",".join(hashes)
        )

        return tokens
