import os
import zipfile
import datetime
import shutil
import sys

# Configuration
BACKUP_DIR = 'backups'
ITEMS_TO_BACKUP = [
    'azubi_werkzeug/werkzeug.db',
    'azubi_werkzeug/config.yaml',
    'azubi_werkzeug/signatures' # Directory
]
MAX_BACKUPS = 10

def create_backup():
    """Creates a timestamped zip backup of critical files."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    print(f"Creating backup: {backup_path}...")
    
    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for item in ITEMS_TO_BACKUP:
                if os.path.exists(item):
                    if os.path.isdir(item):
                        for root, dirs, files in os.walk(item):
                            for file in files:
                                file_path = os.path.join(root, file)
                                zipf.write(file_path, file_path)
                                print(f"  Added: {file_path}")
                    else:
                        zipf.write(item, item)
                        print(f"  Added: {item}")
                else:
                    print(f"  Warning: {item} not found, skipping.")
                    
        print(f"SUCCESS: Backup created successfully: {backup_filename}")
        rotate_backups()
        return True
    except Exception as e:
        print(f"FAILED: Backup failed: {e}")
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return False

def rotate_backups():
    """Keeps only the last MAX_BACKUPS files."""
    backups = sorted([os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')])
    
    if len(backups) > MAX_BACKUPS:
        to_delete = backups[:-MAX_BACKUPS]
        for f in to_delete:
            try:
                os.remove(f)
                print(f"  Rotated (deleted): {f}")
            except Exception as e:
                print(f"  Error deleting {f}: {e}")

if __name__ == "__main__":
    success = create_backup()
    sys.exit(0 if success else 1)
