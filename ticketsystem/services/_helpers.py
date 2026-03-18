import os
import shutil
import time

def _remove_with_retry(path, retries=3, delay=0.5):
    """Attempt to remove a file or directory with retries (for Windows/SQLite locks)."""
    for i in range(retries):
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            return True
        except Exception:
            if i < retries - 1:
                time.sleep(delay)
            else:
                raise
    return False
