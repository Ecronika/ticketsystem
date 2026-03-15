"""Internal helpers for services."""
import os
import time

from flask import current_app


def _remove_with_retry(filepath, retries=5, delay=0.5):
    """Remove files with retry logic for Windows file locks."""
    for i in range(retries):
        if not os.path.exists(filepath):
            return True
        try:
            os.remove(filepath)
            return True
        except OSError as e:
            if i == retries - 1:
                current_app.logger.warning(
                    "Failed to remove %s after %s retries: %s",
                    filepath, retries, e
                )
            time.sleep(delay)
    return False
