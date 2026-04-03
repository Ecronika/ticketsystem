"""
System Service module.

Handles system-wide administrative tasks like token generation.
"""
import json
import secrets
import string
from werkzeug.security import generate_password_hash
from extensions import db
from models import SystemSettings

class SystemService:
    """Service layer for system-wide operations."""

    @staticmethod
    def generate_recovery_tokens():
        """
        Generate 10 fresh recovery tokens.
        Hashes are stored for verification, raw tokens for one-time display.
        """
        tokens = []
        hashes = []
        
        # Alphanumeric characters (excluding confusing ones like O, 0, I, 1)
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        
        for _ in range(10):
            token = ''.join(secrets.choice(alphabet) for _ in range(12))
            tokens.append(token)
            hashes.append(generate_password_hash(token))
            
        # Store for display (expires after 5 minutes)
        SystemSettings.set_setting('recovery_tokens_raw', json.dumps(tokens))
        from datetime import datetime, timezone
        SystemSettings.set_setting('recovery_tokens_generated_at', datetime.now(timezone.utc).isoformat())
        # Store for verification
        SystemSettings.set_setting('recovery_tokens_hash', ','.join(hashes))
        
        return tokens
