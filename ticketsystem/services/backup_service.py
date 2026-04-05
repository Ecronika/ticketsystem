"""Backup Service module.

Handles system backups, pruning, and restoration logic.
"""

import logging
import os
import shutil
import threading
import time
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, current_app
from flask_migrate import upgrade

from extensions import Config, db, scheduler
from models import SystemSettings
from utils import get_utc_now

from ._helpers import _remove_with_retry

_logger = logging.getLogger(__name__)


class BackupError(Exception):
    """Raised when a backup or restore operation fails."""


class ValidationError(Exception):
    """Raised when backup validation fails."""


class BackupService:
    """Service for handling system backups and restores."""

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_backup_dir() -> str:
        """Return the path to the backup directory, creating it if needed."""
        backup_dir = os.path.join(Config.get_data_dir(), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    @staticmethod
    def restore_backup(zip_path: str) -> bool:
        """Restore the system state from a ZIP backup."""
        data_dir = Config.get_data_dir()
        temp_dir = os.path.join(data_dir, "temp_restore")

        try:
            _extract_and_validate_zip(zip_path, temp_dir)
            _shutdown_sessions()
            _perform_restore_overwrite(data_dir, temp_dir)

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            _post_restore_actions()
            _schedule_delayed_restart()
            return True
        except (ValidationError, BackupError):
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise
        except Exception as exc:
            current_app.logger.error("Restore failed: %s", exc)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise BackupError(
                f"Unerwarteter Fehler bei der Wiederherstellung: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Backup creation
    # ------------------------------------------------------------------

    @staticmethod
    def create_backup() -> Dict[str, Any]:
        """Create a zip backup of critical data."""
        data_dir = Config.get_data_dir()
        timestamp = get_utc_now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_ticketsystem_{timestamp}.zip"
        backup_dir = os.path.join(data_dir, "backups")
        backup_path = os.path.join(backup_dir, backup_filename)

        os.makedirs(backup_dir, exist_ok=True)

        try:
            _checkpoint_wal()
            _write_zip_archive(backup_path, data_dir)

            size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)
            current_app.logger.info(
                "Backup created: %s (%s MB)", backup_filename, size_mb
            )
            BackupService.prune_backups()
            return {
                "success": True,
                "filename": backup_filename,
                "path": backup_path,
                "size_mb": size_mb,
            }
        except Exception as exc:
            current_app.logger.error("Backup creation failed: %s", exc)
            if os.path.exists(backup_path):
                os.remove(backup_path)
            raise

    @staticmethod
    def create_backup_context_aware(app: Flask) -> Dict[str, Any]:
        """Wrap :meth:`create_backup` with an app context for the scheduler."""
        with app.app_context():
            return BackupService.create_backup()

    # ------------------------------------------------------------------
    # Listing & pruning
    # ------------------------------------------------------------------

    @staticmethod
    def list_backups() -> List[Dict[str, Any]]:
        """Return list of available backups."""
        backup_dir = BackupService.get_backup_dir()
        backups: List[Dict[str, Any]] = []
        if not os.path.exists(backup_dir):
            return backups

        for filename in os.listdir(backup_dir):
            if not (filename.endswith(".zip") and filename.startswith("backup_")):
                continue
            path = os.path.join(backup_dir, filename)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            backups.append({
                "filename": filename,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "date": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            })
        return sorted(backups, key=lambda x: x["filename"], reverse=True)

    @staticmethod
    def prune_backups() -> None:
        """Prune old backup files based on the configured retention policy."""
        try:
            days = _retention_days()
            if days <= 0:
                return
            backup_dir = BackupService.get_backup_dir()
            if not os.path.exists(backup_dir):
                return

            cutoff = time.time() - (days * 86400)
            count = _remove_old_zips(backup_dir, cutoff)
            if count > 0:
                current_app.logger.info(
                    "Pruned %d old backups (> %d days)", count, days
                )
        except Exception as exc:
            current_app.logger.error("Pruning failed: %s", exc)

    @staticmethod
    def rotate_backups(max_backups: int = 10) -> None:
        """Keep only the latest *max_backups* backups."""
        backup_dir = BackupService.get_backup_dir()
        backups = sorted(
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith("backup_") and f.endswith(".zip")
        )
        if len(backups) <= max_backups:
            return
        for filepath in backups[:-max_backups]:
            try:
                os.remove(filepath)
                current_app.logger.info("Rotated backup: %s", filepath)
            except OSError as exc:
                current_app.logger.error(
                    "Error rotating backup %s: %s", filepath, exc
                )

    # ------------------------------------------------------------------
    # Scheduler integration
    # ------------------------------------------------------------------

    @staticmethod
    def schedule_backup_job(app: Flask) -> None:
        """Configure the auto-backup scheduler job."""
        if scheduler.get_job("auto_backup"):
            scheduler.remove_job("auto_backup")

        with app.app_context():
            interval = SystemSettings.get_setting("backup_interval", "date")
            time_str = SystemSettings.get_setting("backup_time", "03:00")

        if interval == "never":
            return

        hour, minute = _parse_time(time_str)
        trigger_args: Dict[str, Any] = {"hour": hour, "minute": minute}
        if interval == "weekly":
            trigger_args["day_of_week"] = "mon"

        scheduler.add_job(
            id="auto_backup",
            func=BackupService.create_backup_context_aware,
            args=[app],
            trigger="cron",
            **trigger_args,
        )
        _logger.info(
            "Scheduled auto-backup: %s at %02d:%02d", interval, hour, minute
        )


# ---------------------------------------------------------------------------
# Module-private helpers (extracted to reduce method complexity)
# ---------------------------------------------------------------------------

def _extract_and_validate_zip(zip_path: str, temp_dir: str) -> None:
    """Verify and extract ZIP with Zip Slip protection."""
    if not zipfile.is_zipfile(zip_path):
        raise ValidationError("Die Datei ist kein gültiges ZIP-Archiv.")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        if "werkzeug.db" not in zip_ref.namelist():
            raise ValidationError("Backup ungültig: 'werkzeug.db' fehlt.")

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        abs_root = os.path.abspath(temp_dir)
        for member in zip_ref.namelist():
            target_path = os.path.abspath(os.path.join(abs_root, member))
            if os.path.commonpath([abs_root, target_path]) != abs_root:
                raise ValidationError(
                    f"Sicherheitswarnung: Zip Slip Versuch erkannt bei {member}"
                )
            zip_ref.extract(member, abs_root)


def _shutdown_sessions() -> None:
    """Shut down DB sessions and scheduler for restore."""
    if scheduler.running:
        try:
            scheduler.pause()
        except Exception:  # scheduler may already be paused
            pass
    db.session.remove()
    db.engine.dispose()
    time.sleep(0.5)


def _post_restore_actions() -> None:
    """Resume scheduler and run migrations after restore."""
    if scheduler.running:
        try:
            scheduler.resume()
        except Exception:  # scheduler state may be inconsistent after restore
            pass
    try:
        upgrade()
    except Exception as exc:
        current_app.logger.error("Migration after restore failed: %s", exc)


def _perform_restore_overwrite(data_dir: str, temp_dir: str) -> None:
    """Overwrite current data with restored data using safe renaming."""
    _restore_database_files(data_dir, temp_dir)
    _restore_config_file(data_dir, temp_dir)
    _restore_directories(data_dir, temp_dir, ["signatures", "reports"])


def _restore_database_files(data_dir: str, temp_dir: str) -> None:
    """Restore the main DB file and its WAL/SHM companions."""
    db_dst = os.path.join(data_dir, "werkzeug.db")
    db_bak = db_dst + ".bak"

    try:
        if os.path.exists(db_dst):
            if os.path.exists(db_bak):
                os.remove(db_bak)
            os.rename(db_dst, db_bak)
    except OSError as exc:
        _logger.warning(
            "Could not rename live DB to .bak (likely locked): %s. "
            "Attempting direct overwrite.",
            exc,
        )

    shutil.copy2(os.path.join(temp_dir, "werkzeug.db"), db_dst)

    for ext in ("-wal", "-shm"):
        src = os.path.join(temp_dir, f"werkzeug.db{ext}")
        dst = os.path.join(data_dir, f"werkzeug.db{ext}")
        if os.path.exists(src):
            if os.path.exists(dst):
                _remove_with_retry(dst)
            shutil.copy2(src, dst)
        elif os.path.exists(dst):
            _remove_with_retry(dst)


def _restore_config_file(data_dir: str, temp_dir: str) -> None:
    """Copy config.yaml back if present in the backup."""
    src = os.path.join(temp_dir, "config.yaml")
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(data_dir, "config.yaml"))


def _restore_directories(
    data_dir: str, temp_dir: str, folders: List[str]
) -> None:
    """Copy sub-directories (signatures, reports) from the backup."""
    for folder in folders:
        src = os.path.join(temp_dir, folder)
        dst = os.path.join(data_dir, folder)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)


def _schedule_delayed_restart() -> None:
    """Trigger a background restart to apply the restored database."""
    def _delayed_restart() -> None:
        time.sleep(1)
        _logger.info("Restarting application after restore...")
        os._exit(0)  # noqa: WPS421 — intentional fast exit after restore

    threading.Thread(target=_delayed_restart, daemon=True).start()


def _checkpoint_wal() -> None:
    """Run a WAL checkpoint before backup for data integrity."""
    try:
        db.session.execute(db.text("PRAGMA wal_checkpoint(FULL)"))
        db.session.commit()
    except Exception as exc:
        current_app.logger.warning("WAL checkpoint failed: %s", exc)


def _write_zip_archive(backup_path: str, data_dir: str) -> None:
    """Write all critical data into a ZIP file."""
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        _add_db_files(zipf, data_dir)
        _add_config_files(zipf, data_dir)
        _add_directory_to_zip(zipf, os.path.join(data_dir, "signatures"), data_dir)
        _add_directory_to_zip(zipf, os.path.join(data_dir, "reports"), data_dir)


def _add_db_files(zipf: zipfile.ZipFile, data_dir: str) -> None:
    """Add the database and WAL/SHM files to the archive."""
    db_path = os.path.join(data_dir, "werkzeug.db")
    if os.path.exists(db_path):
        zipf.write(db_path, "werkzeug.db")
    for ext in ("-wal", "-shm"):
        path = os.path.join(data_dir, f"werkzeug.db{ext}")
        if os.path.exists(path):
            zipf.write(path, f"werkzeug.db{ext}")


def _add_config_files(zipf: zipfile.ZipFile, data_dir: str) -> None:
    """Add configuration files to the archive."""
    config_path = os.path.join(data_dir, "config.yaml")
    ha_config_path = Config.get_ha_options_path()
    if os.path.exists(config_path):
        zipf.write(config_path, "config.yaml")
    elif os.path.exists(ha_config_path):
        zipf.write(ha_config_path, "options.json")


def _add_directory_to_zip(
    zipf: zipfile.ZipFile, dir_path: str, data_dir: str
) -> None:
    """Add all files from a directory to a zip archive."""
    if not os.path.exists(dir_path):
        return
    for root, _, files in os.walk(dir_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            arcname = os.path.relpath(file_path, data_dir)
            zipf.write(file_path, arcname)


def _retention_days() -> int:
    """Read and parse the backup retention setting."""
    days_str = SystemSettings.get_setting("backup_retention_days", "30")
    try:
        return int(days_str)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 30


def _remove_old_zips(backup_dir: str, cutoff: float) -> int:
    """Delete ZIP files older than *cutoff* (epoch seconds)."""
    count = 0
    for filename in os.listdir(backup_dir):
        if not filename.endswith(".zip"):
            continue
        path = os.path.join(backup_dir, filename)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                count += 1
        except OSError:
            pass
    return count


def _parse_time(time_str: str) -> tuple:
    """Parse an ``HH:MM`` string, falling back to 03:00."""
    try:
        hour, minute = map(int, time_str.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 3, 0
    return hour, minute
