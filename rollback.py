"""
Rollback script.

Restores the application state from a zip backup.
"""
# pylint: disable=duplicate-code
import os
import zipfile
import sys

BACKUP_DIR = 'backups'


def rollback(backup_filename):
    """Restores files from a backup zip."""
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    if not os.path.exists(backup_path):
        print(f"FAILED: Backup file not found: {backup_path}")
        return False

    print(f"WARNING: This will OVERWRITE current data with content from {backup_filename}!")
    confirm = input("Are you sure? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Rollback cancelled.")
        return False

    print(f"Restoring from {backup_path}...")

    try:
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            # Basic validation
            file_list = zipf.namelist()
            # FIX: Abwärtskompatibel - Datei muss nur auf '.db' oder 'yaml' enden, egal in welchem Unterordner
            if not any(f.endswith('werkzeug.db') for f in file_list) and \
               not any(f.endswith('config.yaml') for f in file_list):
                print("FAILED: Invalid backup: Missing core files (db or config).")
                return False

            # Secure Extraction (Zip Slip Protection)
            target_dir = os.path.abspath('.')
            for member in zipf.namelist():
                dest_path = os.path.join(target_dir, member)
                # Ensure the path is within the target directory by checking
                # normalized abspath prefix
                if not os.path.abspath(dest_path).startswith(
                        os.path.join(target_dir, '')):
                    print(f"SECURITY ALERT: Skipping suspicious file path: {member}")
                    continue
                zipf.extract(member, target_dir)
            print("SUCCESS: Restore completed successfully.")
            return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"FAILED: Restore failed: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rollback.py <backup_filename>")
        print("Available backups:")
        if os.path.exists(BACKUP_DIR):
            for f in sorted(os.listdir(BACKUP_DIR)):
                if f.endswith('.zip'):
                    print(f" - {f}")
        sys.exit(1)

    FILENAME = sys.argv[1]
    SUCCESS = rollback(FILENAME)
    sys.exit(0 if SUCCESS else 1)
