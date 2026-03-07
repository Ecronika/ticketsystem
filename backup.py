"""
Script for creating system backups.
"""
import os
import zipfile
import datetime
from datetime import timezone
import sys

# Configuration
DATA_DIR = os.environ.get('DATA_DIR', 'azubi_werkzeug')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
ITEMS_TO_BACKUP = [
    os.path.join(DATA_DIR, 'werkzeug.db'),
    os.path.join(DATA_DIR, 'werkzeug.db-wal'),
    os.path.join(DATA_DIR, 'werkzeug.db-shm'),
    os.path.join(DATA_DIR, 'config.yaml'),
    os.path.join(DATA_DIR, 'options.json'),
    os.path.join(DATA_DIR, 'signatures'),  # Directory
    os.path.join(DATA_DIR, 'reports')  # Directory
]
MAX_BACKUPS = 10


def create_backup():
    """Creates a timestamped zip backup of critical files."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    timestamp = datetime.datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_filename = f"backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    print(f"Creating backup: {backup_path}...")

    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for item in ITEMS_TO_BACKUP:
                if os.path.exists(item):
                    if os.path.isdir(item):
                        for root, _, files in os.walk(item):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, DATA_DIR)
                                zipf.write(file_path, arcname)
                                print(f"  Added: {file_path}")
                    else:
                        arcname = os.path.basename(item)
                        zipf.write(item, arcname)
                        print(f"  Added: {item}")
                else:
                    print(f"  Warning: {item} not found, skipping.")

        print(f"SUCCESS: Backup created successfully: {backup_filename}")
        rotate_backups()
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"FAILED: Backup failed: {e}")
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return False


def rotate_backups():
    """Keeps only the last MAX_BACKUPS files."""
    backups = sorted([
        os.path.join(BACKUP_DIR, f)
        for f in os.listdir(BACKUP_DIR)
        if f.startswith('backup_')
    ])

    if len(backups) > MAX_BACKUPS:
        to_delete = backups[:-MAX_BACKUPS]
        for f in to_delete:
            try:
                os.remove(f)
                print(f"  Rotated (deleted): {f}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"  Error deleting {f}: {e}")


if __name__ == "__main__":
    SUCCESS = create_backup()
    sys.exit(0 if SUCCESS else 1)
