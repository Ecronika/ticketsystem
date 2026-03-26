"""
Backup Service module.

Handles system backups, pruning, and restoration logic.
"""
from utils import get_utc_now
import logging
import os
import shutil
import time
import zipfile
from datetime import datetime, timezone

_logger = logging.getLogger(__name__)

from flask import current_app
from flask_migrate import upgrade


class BackupError(Exception):
    """Raised when a backup or restore operation fails."""
    pass

class ValidationError(Exception):
    """Raised when backup validation fails."""
    pass

from extensions import Config, db, scheduler
from models import SystemSettings
from ._helpers import _remove_with_retry


class BackupService:
    """
    Service for handling system backups and restores.

    Manages backup creation, validation, and restoration.
    """

    @staticmethod
    def get_backup_dir():
        """Return the path to the backup directory."""
        data_dir = Config.get_data_dir()
        backup_dir = os.path.join(data_dir, 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
        return backup_dir

    @staticmethod
    def restore_backup(zip_path):
        """Restore the system state from a ZIP backup."""
        data_dir = Config.get_data_dir()
        temp_dir = os.path.join(data_dir, 'temp_restore')

        try:
            BackupService._extract_and_validate_zip(zip_path, temp_dir)

            BackupService._shutdown_sessions()

            BackupService._perform_restore_overwrite(data_dir, temp_dir)

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            BackupService._post_restore_actions()
            
            # FIX-15: Trigger a background restart after a short delay to allow response
            # (In HA/Docker, the supervisor will restart the container)
            import threading
            import sys
            import time
            def delayed_restart():
                time.sleep(1)
                _logger.info("Restarting application after restore...")
                os._exit(0)
            threading.Thread(target=delayed_restart, daemon=True).start()

            return True

        except (ValidationError, BackupError):
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise
        except Exception as e:
            current_app.logger.error("Restore failed: %s", e)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise BackupError(
                f"Unerwarteter Fehler bei der Wiederherstellung: {e}") from e

    @staticmethod
    def _extract_and_validate_zip(zip_path, temp_dir):
        """Verify and extract ZIP with Zip Slip protection."""
        if not zipfile.is_zipfile(zip_path):
            raise ValidationError("Die Datei ist kein gültiges ZIP-Archiv.")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            if 'werkzeug.db' not in zip_ref.namelist():
                raise ValidationError("Backup ungültig: 'werkzeug.db' fehlt.")

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            abs_root = os.path.abspath(temp_dir)
            for member in zip_ref.namelist():
                # FIX-ZIP: Use os.path.commonpath for foolproof Zip Slip protection
                target_path = os.path.abspath(os.path.join(abs_root, member))
                if os.path.commonpath([abs_root, target_path]) != abs_root:
                    raise ValidationError(
                        f"Sicherheitswarnung: Zip Slip Versuch erkannt bei {member}")
                zip_ref.extract(member, abs_root)

    @staticmethod
    def _shutdown_sessions():
        """Shut down DB sessions and scheduler for restore."""
        if scheduler.running:
            try:
                scheduler.pause()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        db.session.remove()
        db.engine.dispose()
        time.sleep(0.5)

    @staticmethod
    def _post_restore_actions():
        """Handle migrations and scheduler resume."""
        if scheduler.running:
            try:
                scheduler.resume()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        try:
            # Upgrade schema only, NO create_all fallback
            upgrade()
        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error("Migration after restore failed: %s", e)

    @staticmethod
    def _perform_restore_overwrite(data_dir, temp_dir):
        """Overwrite current data with restored data using safe renaming."""
        # DB
        db_dst = os.path.join(data_dir, 'werkzeug.db')
        db_bak = db_dst + '.bak'
        
        # Safe Rename for the main DB file
        try:
            if os.path.exists(db_dst):
                if os.path.exists(db_bak):
                    os.remove(db_bak)
                os.rename(db_dst, db_bak)
        except Exception as e:
            _logger.warning("Could not rename live DB to .bak (likely locked): %s. Attempting direct overwrite.", e)

        shutil.copy2(os.path.join(temp_dir, 'werkzeug.db'), db_dst)

        # Handle WAL and SHM files
        for ext in ['-wal', '-shm']:
            src = os.path.join(temp_dir, f'werkzeug.db{ext}')
            dst = os.path.join(data_dir, f'werkzeug.db{ext}')
            if os.path.exists(src):
                if os.path.exists(dst):
                    _remove_with_retry(dst)
                shutil.copy2(src, dst)
            elif os.path.exists(dst):
                _remove_with_retry(dst)

        # Handle Config
        if os.path.exists(os.path.join(temp_dir, 'config.yaml')):
            shutil.copy2(
                os.path.join(temp_dir, 'config.yaml'),
                os.path.join(data_dir, 'config.yaml')
            )

        # Signatures & Reports
        for folder in ['signatures', 'reports']:
            src_f = os.path.join(temp_dir, folder)
            dst_f = os.path.join(data_dir, folder)
            if os.path.exists(src_f):
                if os.path.exists(dst_f):
                    shutil.rmtree(dst_f)
                shutil.copytree(src_f, dst_f)

    @staticmethod
    def prune_backups():
        """Prune old backup files based on the configured retention policy."""
        try:
            days_str = SystemSettings.get_setting(
                'backup_retention_days', '30')
            try:
                days = int(days_str)
            except ValueError:
                days = 30

            if days <= 0:
                return

            backup_dir = BackupService.get_backup_dir()

            if not os.path.exists(backup_dir):
                return

            now = time.time()
            cutoff = now - (days * 86400)

            count = 0
            for filename in os.listdir(backup_dir):
                if not filename.endswith('.zip'):
                    continue

                path = os.path.join(backup_dir, filename)
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        count += 1
                except OSError:
                    pass

            if count > 0:
                current_app.logger.info(
                    "Pruned %d old backups (> %d days)", count, days)

        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error("Pruning failed: %s", e)

    @staticmethod
    def schedule_backup_job(app):
        """Configure the Auto-Backup Scheduler Job."""
        if scheduler.get_job('auto_backup'):
            scheduler.remove_job('auto_backup')

        with app.app_context():
            interval = SystemSettings.get_setting('backup_interval', 'date')
            time_str = SystemSettings.get_setting('backup_time', '03:00')

        if interval == 'never':
            return

        try:
            hour, minute = map(int, time_str.split(':'))
        except ValueError:
            hour, minute = 3, 0

        trigger_args = {'hour': hour, 'minute': minute}
        if interval == 'weekly':
            trigger_args['day_of_week'] = 'mon'

        scheduler.add_job(
            id='auto_backup',
            func=BackupService.create_backup_context_aware,
            args=[app],
            trigger='cron',
            **trigger_args
        )
        # H-4 Fix: Use module-level logger; current_app not available in scheduler thread
        _logger.info(
            "Scheduled auto-backup: %s at %02d:%02d",
            interval, hour, minute
        )

    @staticmethod
    def create_backup_context_aware(app):
        """Wrap create_backup with app context for Scheduler."""
        with app.app_context():
            BackupService.create_backup()

    @staticmethod
    def _add_directory_to_zip(zipf, dir_path, data_dir):
        """Add all files from a directory to a zip archive."""
        if not os.path.exists(dir_path):
            return
        for root, _, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, data_dir)
                zipf.write(file_path, arcname)

    @staticmethod
    def create_backup():
        """Create a zip backup of critical data."""
        data_dir = Config.get_data_dir()
        timestamp = get_utc_now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_ticketsystem_{timestamp}.zip"
        backup_dir = os.path.join(data_dir, 'backups')
        backup_path = os.path.join(backup_dir, backup_filename)

        os.makedirs(backup_dir, exist_ok=True)

        try:
            try:
                db.session.execute(db.text("PRAGMA wal_checkpoint(FULL)"))
                db.session.commit()
            except Exception as e:  # pylint: disable=broad-exception-caught
                current_app.logger.warning("WAL checkpoint failed: %s", e)

            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                db_path = os.path.join(data_dir, 'werkzeug.db')
                if os.path.exists(db_path):
                    zipf.write(db_path, 'werkzeug.db')

                for ext in ['-wal', '-shm']:
                    p = os.path.join(data_dir, f'werkzeug.db{ext}')
                    if os.path.exists(p):
                        zipf.write(p, f'werkzeug.db{ext}')

                config_path = os.path.join(data_dir, 'config.yaml')
                ha_config_path = Config.get_ha_options_path()
                if os.path.exists(config_path):
                    zipf.write(config_path, 'config.yaml')
                elif os.path.exists(ha_config_path):
                    zipf.write(ha_config_path, 'options.json')

                BackupService._add_directory_to_zip(
                    zipf, os.path.join(data_dir, 'signatures'), data_dir)
                BackupService._add_directory_to_zip(
                    zipf, os.path.join(data_dir, 'reports'), data_dir)

            size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)
            current_app.logger.info(
                "Backup created: %s (%s MB)", backup_filename, size_mb)

            BackupService.prune_backups()

            return {
                "success": True,
                "filename": backup_filename,
                "path": backup_path,
                "size_mb": size_mb
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error("Backup creation failed: %s", e)
            if os.path.exists(backup_path):
                os.remove(backup_path)
            raise e

    @staticmethod
    def list_backups():
        """Return list of available backups."""
        backup_dir = BackupService.get_backup_dir()
        backups = []
        if os.path.exists(backup_dir):
            for f in os.listdir(backup_dir):
                if f.endswith('.zip') and f.startswith('backup_'):
                    path = os.path.join(backup_dir, f)
                    try:
                        stat = os.stat(path)
                    except OSError:
                        continue
                    backups.append({
                        'filename': f,
                        'size_mb': round(stat.st_size / (1024 * 1024), 2),
                        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
        return sorted(backups, key=lambda x: x['filename'], reverse=True)

    @staticmethod
    def rotate_backups(max_backups=10):
        """Keep only latest N backups."""
        backup_dir = BackupService.get_backup_dir()
        backups = sorted([
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith('backup_') and f.endswith('.zip')
        ])

        if len(backups) > max_backups:
            for f in backups[:-max_backups]:
                try:
                    os.remove(f)
                    current_app.logger.info("Rotated backup: %s", f)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    current_app.logger.error(
                        "Error rotating backup %s: %s", f, e)
