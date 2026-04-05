"""Service-layer helper utilities."""

import os
import shutil
import time


def _remove_with_retry(path: str, retries: int = 3, delay: float = 0.5) -> bool:
    """Remove a file or directory with retries for locked resources.

    Args:
        path: Filesystem path to remove.
        retries: Maximum number of attempts.
        delay: Seconds to wait between retries.

    Returns:
        ``True`` on success.

    Raises:
        OSError: If removal fails after all retries.
    """
    for attempt in range(retries):
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            return True
        except OSError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
    return False
