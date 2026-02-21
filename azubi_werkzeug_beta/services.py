"""
Services module.

Encapsulates business logic for Checks, Backups, and Tools.
"""
import os
import time
import base64
import zipfile
import shutil
import uuid
from datetime import datetime

from threading import Lock
from flask import current_app, session
from extensions import db, Config, scheduler
from models import Check, CheckType, Werkzeug, Azubi, SystemSettings
from pdf_utils import generate_handover_pdf, parse_check_type

# Cache for assigned tools to reduce DB load
_assigned_tools_cache = {}
_cache_lock = Lock()


class CheckService:
    """
    Service for handling Check and Tool Exchange logic.

    Encapsulates business logic for checks, backups, and tool transactions.
    """

    @staticmethod
    def get_data_dir():
        """Return the data directory from config."""
        return Config.get_data_dir()

    @staticmethod
    def get_assigned_tools_batch(azubi_ids: list) -> dict:
        """Return {azubi_id: set(tool_ids)} for all given IDs in 2 queries."""
        checks = Check.query.filter(Check.azubi_id.in_(azubi_ids)).order_by(Check.datum.asc()).all()
        result = {aid: set() for aid in azubi_ids}
        for check in checks:
            ct = parse_check_type(check.check_type)
            if ct == CheckType.ISSUE:
                result[check.azubi_id].add(check.werkzeug_id)
            elif ct == CheckType.RETURN:
                result[check.azubi_id].discard(check.werkzeug_id)
        return result

    @staticmethod
    def get_assigned_tools(azubi_id):
        """
        Return a set of tool IDs currently assigned to the Azubi.

        Uses caching to improve performance.
        """
        cache_key = f"assigned_{azubi_id}"

        # Check cache
        with _cache_lock:
            if cache_key in _assigned_tools_cache:
                # Basic expiry check (optional, but good practice if we add
                # timestamps later)
                return _assigned_tools_cache[cache_key]

        # Calculate from DB
        checks = Check.query.filter_by(
            azubi_id=azubi_id).order_by(
            Check.datum.asc()).all()
        assigned_tools = set()

        for check in checks:
            # Use safe comparison
            # Use safe comparison via helper (handles Enum/String mismatch)
            c_type = parse_check_type(check.check_type)
            if c_type == CheckType.ISSUE:
                assigned_tools.add(check.werkzeug_id)
            elif c_type == CheckType.RETURN:
                assigned_tools.discard(check.werkzeug_id)
            elif c_type == CheckType.EXCHANGE:
                # Exchange is effectively a swap, but if we track items
                # precisely we might need to know WHICH tool was returned
                # and issued. Current implementation splits Exchange into
                # RETURN + ISSUE records.
                # So pure 'EXCHANGE' type might not be in DB for tool
                # tracking if logical split exists.
                # However, if it IS in DB:
                pass

        # Update cache (Double-Check)
        # Avoid overwriting if another thread already populated it
        # This helps slightly with race conditions, though strict generation
        # tracking would be better
        with _cache_lock:
            if cache_key not in _assigned_tools_cache:
                _assigned_tools_cache[cache_key] = assigned_tools

        return assigned_tools

    @staticmethod
    def invalidate_cache(azubi_id=None):
        """Invalidates cache for a specific Azubi or globally."""
        with _cache_lock:
            if azubi_id:
                _assigned_tools_cache.pop(f"assigned_{azubi_id}", None)
                current_app.logger.debug(
                    f"Cache invalidated for azubi {azubi_id}")
            else:
                _assigned_tools_cache.clear()
                current_app.logger.warning(
                    "Global assigned_tools cache cleared.")

    @staticmethod
    def generate_unique_session_id():
        """Generate a unique session ID for grouping checks."""
        return str(uuid.uuid4())

    @staticmethod
    def detect_exchange_type(checks):
        """Detect if a session is an exchange based on check types."""
        from models import parse_check_type
        
        check_types = [parse_check_type(c.check_type) for c in checks]
        has_return = CheckType.RETURN in check_types
        has_issue = CheckType.ISSUE in check_types
        
        if has_return and has_issue and len(checks) >= 2:
            return 'exchange'
        if any('Austausch' in (c.bemerkung or '') for c in checks):
            return 'exchange'
        return None

    @staticmethod
    def parse_check_bemerkung(bemerkung):
        """Parse status and comment from a check's bemerkung field."""
        status_code = "ok"
        comment = ""
        parts = (bemerkung or "").split('|')
        for p in parts:
            p = p.strip()
            if p.startswith("Status:"):
                status_code = p.replace("Status:", "").strip()
            elif p:
                comment = p
        return status_code, comment

    @staticmethod
    def group_checks_into_sessions(all_checks):
        """Group flat check list into session dicts."""
        sessions_dict = {}
        for check in all_checks:
            sid = check.session_id if check.session_id else (
                f"LEGACY_{check.azubi_id}_"
                f"{int(check.datum.timestamp())}")
            if sid not in sessions_dict:
                sessions_dict[sid] = {
                    'session_id': (
                        check.session_id if check.session_id else sid),
                    'datum': check.datum,
                    'azubi_name': check.azubi.name,
                    'checks': [],
                    'is_ok': True}
            sessions_dict[sid]['checks'].append(check)
            if "Status: missing" in (check.bemerkung or "") or \
               "Status: broken" in (check.bemerkung or ""):
                sessions_dict[sid]['is_ok'] = False
        return [
            {
                'session_id': sd['session_id'],
                'datum': sd['datum'],
                'azubi_name': sd['azubi_name'],
                'is_ok': sd['is_ok'],
                'count': len(sd['checks'])
            }
            for sd in sessions_dict.values()
        ]

    @staticmethod
    def cleanup_session_files(files_to_delete):
        """Delete a list of file paths, return count of deleted."""
        deleted_count = 0
        for f_path in files_to_delete:
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    deleted_count += 1
                except OSError as e:
                    current_app.logger.warning(
                        f"Failed to delete file {f_path}: {e}")
        return deleted_count

    @staticmethod
    def collect_tool_ids(form_data):
        """Extract tool IDs from form keys matching 'tool_<id>'."""
        tool_ids = []
        for key in form_data:
            if key.startswith('tool_'):
                try:
                    tool_ids.append(int(key.split('_')[1]))
                except (IndexError, ValueError):
                    continue
        return tool_ids

    @staticmethod
    def save_signature(
            signature_data: str,
            session_id: str,
            suffix: str) -> str:
        """
        Save base64 signature to disk.

        Args:
            signature_data: Base64 string from canvas
            session_id: Unique session ID
            suffix: 'azubi' or 'examiner'

        Returns:
            Absolute path to saved signature file
        """
        if not signature_data or ',' not in signature_data:
            return None

        try:
            data_dir = CheckService.get_data_dir()
            os.makedirs(os.path.join(data_dir, 'signatures'), exist_ok=True)

            _, encoded = signature_data.split(",", 1)
            try:
                data = base64.b64decode(encoded)
            except Exception as e:  # pylint: disable=broad-exception-caught
                current_app.logger.error(f"Invalid signature data: {e}")
                return None

            filename = f"{session_id}_{suffix}.png"
            path = os.path.join(data_dir, 'signatures', filename)

            with open(path, "wb") as f:
                f.write(data)

            return path
        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Error saving signature: {e}")
            return None

    @staticmethod
    def _prepare_check_records(
        tool_ids, werkzeug_dict, form_data, check_context
    ):
        """Prepare Check DB records and tool data for PDF generation."""
        records = []
        selected_tools = []
        global_bemerkung = form_data.get('bemerkung')

        for tool_id in tool_ids:
            werkzeug = werkzeug_dict.get(tool_id)
            if not werkzeug:
                continue
            status = form_data.get(f'tool_{tool_id}')
            tech_val = form_data.get(f'tech_param_{tool_id}')
            incident_reason = form_data.get(f'incident_reason_{tool_id}')
            full_bemerkung = f"Status: {status}"
            if global_bemerkung:
                full_bemerkung += f" | {global_bemerkung}"
            records.append(Check(
                session_id=check_context['session_id'],
                azubi_id=check_context['azubi'].id,
                werkzeug_id=werkzeug.id,
                bemerkung=full_bemerkung,
                tech_param_value=tech_val,
                incident_reason=incident_reason,
                datum=check_context['check_date'],
                check_type=check_context['check_type'].value,
                examiner=check_context['examiner_name'],
                signature_azubi=check_context['sig_azubi_path'],
                signature_examiner=check_context['sig_examiner_path'],
                report_path=None
            ))
            selected_tools.append({
                'id': werkzeug.id,
                'name': werkzeug.name,
                'category': werkzeug.material_category,
                'status': status,
                'incident_reason': incident_reason
            })
        return records, selected_tools

    @staticmethod
    def _cleanup_on_error(checks, pdf_path):
        """Cleanup files if DB commit fails."""
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass

        if checks:
            first_check = checks[0]
            for sig_path in [first_check.signature_azubi,
                             first_check.signature_examiner]:
                if sig_path and os.path.exists(sig_path):
                    try:
                        os.remove(sig_path)
                    except OSError:
                        pass

    @staticmethod
    def _commit_checks_or_cleanup(checks, pdf_path):
        """Commit check records to DB; clean up PDF on failure."""
        try:
            for check in checks:
                db.session.add(check)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"DB Commit failed: {e}")
            db.session.rollback()
            CheckService._cleanup_on_error(checks, pdf_path)
            raise e

    @staticmethod
    def _build_check_context(
        azubi, examiner_name, check_date, check_type,
        session_id, sig_azubi_path, sig_examiner_path
    ):
        """Build context dict for check processing."""
        # pylint: disable=too-many-arguments,too-many-positional-arguments
        return {
            'session_id': session_id,
            'azubi': azubi,
            'check_date': check_date,
            'check_type': check_type,
            'examiner_name': examiner_name,
            'sig_azubi_path': sig_azubi_path,
            'sig_examiner_path': sig_examiner_path
        }

    @staticmethod
    def _fetch_tools_dict(tool_ids):
        """Fetch tools and return as dict."""
        werkzeuge = Werkzeug.query.filter(Werkzeug.id.in_(tool_ids)).all()
        return {w.id: w for w in werkzeuge}

    @staticmethod
    def _handle_signatures(form_data, session_id):
        """Handle signature saving and validation."""
        sig_azubi_path = CheckService.save_signature(
            form_data.get('signature_azubi_data'), session_id, 'azubi')

        is_migration = session.get('migration_mode', False)

        if not sig_azubi_path and not is_migration:
            raise ValueError("Fehler beim Speichern der Azubi-Signatur")

        sig_examiner_path = CheckService.save_signature(
            form_data.get('signature_examiner_data'), session_id, 'examiner')

        if not sig_examiner_path and not is_migration:
            if os.path.exists(sig_azubi_path) if sig_azubi_path else False:
                try:
                    os.remove(sig_azubi_path)
                except OSError:
                    pass
            raise ValueError("Fehler beim Speichern der Ausbilder-Signatur")

        return sig_azubi_path, sig_examiner_path

    @staticmethod
    def process_check_submission(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        azubi_id: int,
        examiner_name: str,
        tool_ids: list[int],
        form_data: dict,
        check_date: datetime = None,
        check_type: CheckType = CheckType.CHECK
    ) -> dict:
        """Process a full check submission."""
        # pylint: disable=too-many-locals
        if not check_date:
            check_date = datetime.now()

        session_id = CheckService.generate_unique_session_id()

        sig_azubi_path, sig_examiner_path = CheckService._handle_signatures(
            form_data, session_id)

        azubi = Azubi.query.get(azubi_id)
        if not azubi:
            current_app.logger.error(
                f"CheckService: Azubi {azubi_id} not found")
            raise ValueError(f"Azubi mit ID {azubi_id} nicht gefunden")

        check_context = CheckService._build_check_context(
            azubi, examiner_name, check_date, check_type,
            session_id, sig_azubi_path, sig_examiner_path)

        # 3. Fetch Data Efficiently
        werkzeug_dict = CheckService._fetch_tools_dict(tool_ids)

        # 4. Prepare Data for DB and PDF
        reports_to_create, selected_tools = CheckService._prepare_check_records(
            tool_ids, werkzeug_dict, form_data, check_context)

        # 5. Generate PDF (BEFORE DB Transaction)
        pdf_path = None
        if selected_tools:
            try:
                pdf_path = CheckService._generate_and_link_pdf(
                    check_context, selected_tools, reports_to_create
                )
            except Exception as e:
                current_app.logger.error(f"PDF Gen failed: {e}")
                raise e

        # 6. Commit to DB (Fast Transaction)
        CheckService._commit_checks_or_cleanup(reports_to_create, pdf_path)

        current_app.logger.info(
            f"CheckService: Processed {len(reports_to_create)} checks")

        return {
            "success": True,
            "session_id": check_context['session_id'],
            "count": len(reports_to_create),
            "pdf_path": pdf_path
        }

    @staticmethod
    def _generate_and_link_pdf(
        check_context, selected_tools, reports_to_create
    ):
        """Generate PDF and link it to checks."""
        data_dir = CheckService.get_data_dir()
        azubi = check_context['azubi']
        name_clean = azubi.name.replace(' ', '_')
        check_date = check_context['check_date']
        check_type = check_context['check_type']

        date_str = check_date.strftime('%Y%m%d_%H%M')
        pdf_filename = f"Protokoll_{check_type.value}_{name_clean}_{date_str}.pdf"
        pdf_path = os.path.join(data_dir, 'reports', pdf_filename)

        generate_handover_pdf(
            azubi_name=azubi.name,
            examiner_name=check_context['examiner_name'],
            tools=selected_tools,
            check_type=check_type,
            signature_paths={
                'azubi': check_context['sig_azubi_path'],
                'examiner': check_context['sig_examiner_path']},
            output_path=pdf_path)

        # Update records with PDF path
        for r in reports_to_create:
            r.report_path = pdf_path

        return pdf_path

    @staticmethod
    def _create_exchange_records(
        session_id, azubi_id, tool_id, reason, is_payable, check_date, sig_path
    ):
        """Create exchange records."""
        # pylint: disable=too-many-arguments,too-many-positional-arguments
        # Return Entry
        ret_entry = Check(
            session_id=session_id,
            azubi_id=azubi_id,
            werkzeug_id=tool_id,
            check_type=CheckType.RETURN.value,
            bemerkung=f'Austausch (Altteil): {reason}' +
            (' (Kostenpflichtig)' if is_payable else ''),
            incident_reason=reason,
            datum=check_date,
            tech_param_value='Austausch',
            signature_azubi=None,
            report_path=None
        )

        # Issue Entry
        issue_entry = Check(
            session_id=session_id,
            azubi_id=azubi_id,
            werkzeug_id=tool_id,
            check_type=CheckType.ISSUE.value,
            bemerkung='Austausch (Neuteil)' +
            (' (Kostenpflichtig)' if is_payable else ''),
            incident_reason='Ersatzbeschaffung',
            datum=check_date,
            tech_param_value='Neu',
            signature_azubi=sig_path,
            report_path=None
        )
        return ret_entry, issue_entry

    @staticmethod
    def _generate_exchange_pdf(
        azubi, tool, reason, session_id, sig_path, price=0.0
    ):
        """Generate exchange PDF."""
        # pylint: disable=too-many-arguments,too-many-positional-arguments
        tools_list = [{'name': tool.name,
                       'category': tool.material_category,
                       'status': f'Rückgabe ({reason})'},
                      {'name': tool.name,
                       'category': tool.material_category,
                       'status': 'Ausgabe (Neu)'}]

        data_dir = CheckService.get_data_dir()
        pdf_filename = f"austausch_{session_id}.pdf"
        pdf_path = os.path.join(data_dir, 'reports', pdf_filename)

        extra_lines = []
        if price > 0:
            extra_lines.append(f"Geschätzter Ersatzwert: {price:.2f} EUR")

        generate_handover_pdf(
            azubi_name=azubi.name,
            examiner_name="System",
            tools=tools_list,
            check_type=CheckType.EXCHANGE,
            signature_paths={'azubi': sig_path},
            output_path=pdf_path,
            extra_lines=extra_lines
        )
        return pdf_path

    @staticmethod
    def _cleanup_exchange_files(sig_path, pdf_path):
        """Cleanup files on error."""
        if sig_path and os.path.exists(sig_path):
            try:
                os.remove(sig_path)
            except OSError:
                pass

        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass

    @staticmethod
    def process_tool_exchange(
        azubi_id: int,
        tool_id: int,
        reason: str,
        is_payable: bool,
        signature_data: str
    ) -> dict:
        """
        Handle One-Click Tool Exchange (Return Old -> Issue New).

        Atomically creates two records and one PDF.
        """
        # 1. Validation
        azubi = Azubi.query.get(azubi_id)
        if not azubi:
            raise ValueError(f"Azubi mit ID {azubi_id} nicht gefunden")

        tool = Werkzeug.query.get(tool_id)
        if not tool:
            raise ValueError(f"Werkzeug mit ID {tool_id} nicht gefunden")

        session_id = CheckService.generate_unique_session_id()
        check_date = datetime.now()

        # Calculate Price (Estimate)
        price = 0.0
        if is_payable and tool.price:
            price = tool.price

        # 2. Save Signature
        sig_path = CheckService.save_signature(
            signature_data, session_id, 'azubi')

        pdf_path = None
        try:
            # 3. Create Records (Memory)
            ret_entry, issue_entry = CheckService._create_exchange_records(
                session_id, azubi_id, tool_id, reason, is_payable, check_date, sig_path)

            db.session.add(ret_entry)
            db.session.add(issue_entry)

            # 4. Generate PDF
            pdf_path = CheckService._generate_exchange_pdf(
                azubi, tool, reason, session_id, sig_path, price)

            ret_entry.report_path = pdf_path
            issue_entry.report_path = pdf_path

            # 5. Commit Atomically
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Exchange failed: {e}")
            CheckService._cleanup_exchange_files(sig_path, pdf_path)
            raise e

        current_app.logger.info(
            f"ExchangeService: Completed for {azubi.name}")

        return {
            "success": True,
            "session_id": session_id,
            "pdf_path": pdf_path,
            "price": price
        }


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
            os.makedirs(backup_dir)
        return backup_dir

    @staticmethod
    def restore_backup(zip_path):
        """
        Restore the system state from a ZIP backup.

        This method safely extracts the backup, validating against Zip Slip attacks,
        and restores the database, configuration, signatures, and reports.

        Args:
            zip_path (str): Absolute path to the backup ZIP file.

        Returns:
            bool: True if restore was successful.

        Raises:
            ValueError: If the backup is invalid or security checks fail.
            Exception: For any other restore failures.
        """
        data_dir = CheckService.get_data_dir()
        temp_dir = os.path.join(data_dir, 'temp_restore')

        try:
            # 1. Verify ZIP
            if not zipfile.is_zipfile(zip_path):
                raise ValueError("Die Datei ist kein gültiges ZIP-Archiv.")

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Basic validation
                if 'werkzeug.db' not in zip_ref.namelist():
                    raise ValueError("Backup ungültig: 'werkzeug.db' fehlt.")

                # 2. Extract to temp (with Zip Slip protection)
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)

                for member in zip_ref.namelist():
                    # ZIP SLIP PROTECTION
                    # Resolve the target path and check if it starts with the
                    # temp_dir
                    target_path = os.path.join(temp_dir, member)
                    # Use abspath to normalize, but don't resolve symlinks yet
                    # (realpath requires existence)
                    abs_target = os.path.abspath(target_path)
                    abs_root = os.path.abspath(temp_dir)

                    # Must ensure commonprefix is exactly the root directory
                    # (trailing slash check)
                    if not abs_target.startswith(os.path.join(abs_root, '')):
                        raise ValueError(
                            f"Sicherheitswarnung: Zip Slip Versuch erkannt bei {member}")

                    zip_ref.extract(member, temp_dir)

            # CRITICAL: Close SQLAlchemy connection to old DB file BEFORE overwriting check
            # This ensures file locks are released on Windows
            db.session.remove()
            db.engine.dispose()

            # 3. Overwrite Data (Critical Section)
            BackupService._perform_restore_overwrite(data_dir, temp_dir)

            # Cleanup
            shutil.rmtree(temp_dir)

            # Ensure all tables exist (older backups may lack newer tables)
            # This implicitly re-creates the connection
            db.create_all()

            # CRITICAL: Clear Cache after restore
            current_app.logger.warning("Clearing all caches after restore.")
            CheckService.invalidate_cache()

            current_app.logger.info("Restore successful. Requesting restart.")
            return True

        except Exception as e:
            current_app.logger.error(f"Restore failed: {e}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise e

    @staticmethod
    def _perform_restore_overwrite(data_dir, temp_dir):
        """Overwrite current data with restored data."""
        # DB & Config
        shutil.copy2(
            os.path.join(
                temp_dir, 'werkzeug.db'), os.path.join(
                data_dir, 'werkzeug.db'))

        # Handle Config (Optional in backup)
        if os.path.exists(os.path.join(temp_dir, 'config.yaml')):
            shutil.copy2(
                os.path.join(
                    temp_dir, 'config.yaml'), os.path.join(
                    data_dir, 'config.yaml'))

        # Signatures
        src_sig = os.path.join(temp_dir, 'signatures')
        dst_sig = os.path.join(data_dir, 'signatures')
        if os.path.exists(src_sig):
            if os.path.exists(dst_sig):
                shutil.rmtree(dst_sig)
            shutil.copytree(src_sig, dst_sig)

        # Reports
        src_rep = os.path.join(temp_dir, 'reports')
        dst_rep = os.path.join(data_dir, 'reports')
        if os.path.exists(src_rep):
            if os.path.exists(dst_rep):
                shutil.rmtree(dst_rep)
            shutil.copytree(src_rep, dst_rep)

    @staticmethod
    def prune_backups():
        """
        Prune old backup files based on the configured retention policy.

        Reads 'backup_retention_days' from SystemSettings.
        Deletes ZIP files in the backup directory older than the cutoff.
        """
        try:
            # Get retention days (Default: 30)
            days_str = SystemSettings.get_setting(
                'backup_retention_days', '30')
            try:
                days = int(days_str)
            except ValueError:
                days = 30

            if days <= 0:
                return  # 0 means keep forever

            data_dir = CheckService.get_data_dir()
            backup_dir = os.path.join(data_dir, 'backups')

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
                    pass  # Ignore errors for individual files

            if count > 0:
                current_app.logger.info(
                    f"Pruned {count} old backups (> {days} days)")

        except Exception as e:  # pylint: disable=broad-exception-caught
            current_app.logger.error(f"Pruning failed: {e}")

    @staticmethod
    def schedule_backup_job(app):
        """
        Configure the Auto-Backup Scheduler Job.

        Reads settings (interval, time) from SystemSettings and adds/updates
        the 'auto_backup' job in Flask-APScheduler.

        Args:
             app: The Flask application instance (needed for context).
        """
        # Remove existing if any
        if scheduler.get_job('auto_backup'):
            scheduler.remove_job('auto_backup')

        # Get settings
        with app.app_context():
            # 'daily', 'weekly', 'never', 'date' (fixed time)
            interval = SystemSettings.get_setting('backup_interval', 'date')
            time_str = SystemSettings.get_setting(
                'backup_time', '03:00')  # HH:MM

        if interval == 'never':
            return

        # Parse time
        try:
            hour, minute = map(int, time_str.split(':'))
        except ValueError:
            hour, minute = 3, 0

        trigger_args = {'hour': hour, 'minute': minute}

        if interval == 'weekly':
            # Monday at HH:MM
            trigger_args['day_of_week'] = 'mon'

        # Add Job
        scheduler.add_job(
            id='auto_backup',
            func=BackupService.create_backup_context_aware,  # Helper needed for APP Context
            args=[app],
            trigger='cron',
            **trigger_args
        )
        current_app.logger.info(
            f"Scheduled auto-backup: {interval} at {hour:02d}:{minute:02d}")

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
        """
        Create a zip backup of critical data (DB, Config, Signatures, Reports).

        Returns:
            dict: {success, filename, path, size_mb}
        """
        data_dir = CheckService.get_data_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_azubi_werkzeug_{timestamp}.zip"
        backup_dir = os.path.join(data_dir, 'backups')
        backup_path = os.path.join(backup_dir, backup_filename)

        os.makedirs(backup_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 1. Database
                db_path = os.path.join(data_dir, 'werkzeug.db')
                if os.path.exists(db_path):
                    zipf.write(db_path, 'werkzeug.db')

                # 2. Config (HA Add-on support)
                config_path = os.path.join(data_dir, 'config.yaml')
                ha_config_path = Config.get_ha_options_path()
                if os.path.exists(config_path):
                    zipf.write(config_path, 'config.yaml')
                elif os.path.exists(ha_config_path):
                    zipf.write(ha_config_path, 'options.json')

                # 3. Signatures + Reports
                BackupService._add_directory_to_zip(
                    zipf, os.path.join(data_dir, 'signatures'), data_dir)
                BackupService._add_directory_to_zip(
                    zipf, os.path.join(data_dir, 'reports'), data_dir)

            size_mb = round(
                os.path.getsize(backup_path) / (1024 * 1024), 2)
            current_app.logger.info(
                f"Backup created: {backup_filename} ({size_mb} MB)")

            BackupService.prune_backups()

            return {
                "success": True,
                "filename": backup_filename,
                "path": backup_path,
                "size_mb": size_mb
            }

        except Exception as e:
            current_app.logger.error(f"Backup creation failed: {e}")
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
        # Sort by filename (timestamp) desc
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
                    current_app.logger.info(f"Rotated backup: {f}")
                except Exception as e:  # pylint: disable=broad-exception-caught
                    current_app.logger.error(f"Error rotating backup {f}: {e}")
