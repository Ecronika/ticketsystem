import os
import time
import base64
import zipfile
from datetime import datetime
from flask import current_app
from extensions import db
from models import Check, CheckType, Werkzeug, Azubi
from pdf_utils import generate_handover_pdf

class CheckService:
    @staticmethod
    def get_data_dir():
        """Helper to get data directory"""
        # Prioritize App Config (set by app.py from config.yaml or env)
        if current_app and 'DATA_DIR' in current_app.config:
            return current_app.config['DATA_DIR']
            
        return os.environ.get('DATA_DIR', os.path.join(os.getcwd(), 'data'))

    @staticmethod
    def generate_unique_session_id():
        """Generate a unique session ID for grouping checks"""
        import uuid
        return str(uuid.uuid4())

    @staticmethod
    def save_signature(signature_data: str, session_id: str, suffix: str) -> str:
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
            
            header, encoded = signature_data.split(",", 1)
            try:
                data = base64.b64decode(encoded)
            except Exception as e:
                current_app.logger.error(f"Invalid signature data: {e}")
                return None
            
            filename = f"{session_id}_{suffix}.png"
            path = os.path.join(data_dir, 'signatures', filename)
            
            with open(path, "wb") as f:
                f.write(data)
                
            return path
        except Exception as e:
            current_app.logger.error(f"Error saving signature: {e}")
            return None

    @staticmethod
    def process_check_submission(
        azubi_id: int,
        examiner_name: str,
        tool_ids: list[int],
        form_data: dict,
        check_date: datetime = None,
        check_type: CheckType = CheckType.CHECK
    ) -> dict:
        """
        Process a full check submission.
        
        Returns:
            dict with:
                - success: bool
                - message: str
                - session_id: str
                - pdf_path: str (optional)
        """
        start_time = time.time()
        
        if not check_date:
            check_date = datetime.now()
            
        # 0. Validate Azubi
        azubi = Azubi.query.get(azubi_id)
        if not azubi:
             current_app.logger.error(f"CheckService: Azubi {azubi_id} not found")
             raise ValueError(f"Azubi mit ID {azubi_id} nicht gefunden")
            
        # 1. Setup Session
        session_id = CheckService.generate_unique_session_id()
        data_dir = CheckService.get_data_dir()
        
        # 2. Handle Signatures
        sig_azubi_path = CheckService.save_signature(
            form_data.get('signature_azubi_data'), session_id, 'azubi'
        )
        sig_examiner_path = CheckService.save_signature(
            form_data.get('signature_examiner_data'), session_id, 'examiner'
        )
        
        # 3. Fetch Data Efficiently
        werkzeuge = Werkzeug.query.filter(Werkzeug.id.in_(tool_ids)).all()
        werkzeug_dict = {w.id: w for w in werkzeuge}
        
        reports_to_create = []
        selected_tools = []
        global_bemerkung = form_data.get('bemerkung')
        
        # 4. Create Database Records
        for tool_id in tool_ids:
            werkzeug = werkzeug_dict.get(tool_id)
            if not werkzeug:
                continue
                
            # Extract per-tool form data
            status = form_data.get(f'tool_{tool_id}')
            tech_val = form_data.get(f'tech_param_{tool_id}')
            incident_reason = form_data.get(f'incident_reason_{tool_id}')
            
            full_bemerkung = f"Status: {status}"
            if global_bemerkung:
                full_bemerkung += f" | {global_bemerkung}"
            
            new_check = Check(
                session_id=session_id,
                azubi_id=azubi_id,
                werkzeug_id=werkzeug.id,
                bemerkung=full_bemerkung,
                tech_param_value=tech_val,
                incident_reason=incident_reason,
                datum=check_date,
                check_type=check_type.value, # Store as string
                examiner=examiner_name,
                signature_azubi=sig_azubi_path,
                signature_examiner=sig_examiner_path,
                report_path=None # Will update later
            )
            
            db.session.add(new_check)
            reports_to_create.append(new_check)
            
            selected_tools.append({
                'id': werkzeug.id,
                'name': werkzeug.name,
                'category': werkzeug.material_category,
                'status': status,
                'incident_reason': incident_reason
            })
            
        # 5. Commit Check Data
        # 5. Flush Check Data (Optimistic)
        try:
            db.session.flush()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"DB Error preparation checks: {e}")
            raise e
            
        # 6. Generate PDF (If tools selected)
        pdf_path = None
        # 6. Generate PDF (If tools selected)
        pdf_path = None
        if selected_tools:
            try:
                # Azubi already validated at start
                # azubi object needs to be re-fetched? No, we can use the one from start if we keep it.
                # But typically better to stick to ID lookup or ensure object is attached to session.
                # Since we committed, the session might be clean. Safe to re-fetch or use if bound.
                # simpler to just re-fetch or rely on previous variable if scope allows.
                # The 'azubi' variable from start IS in scope!
                pass 

                pdf_filename = f"Protokoll_{check_type.value}_{azubi.name.replace(' ', '_')}_{check_date.strftime('%Y%m%d_%H%M')}.pdf"
                pdf_path = os.path.join(data_dir, 'reports', pdf_filename)
                
                generate_handover_pdf(
                    azubi_name=azubi.name,
                    examiner_name=examiner_name,
                    tools=selected_tools,
                    check_type=check_type,
                    signature_paths={'azubi': sig_azubi_path, 'examiner': sig_examiner_path},
                    output_path=pdf_path
                )
                
                # 7. Update Records with PDF Path (In-Memory)
                for r in reports_to_create:
                    r.report_path = pdf_path
                
                # 8. Commit Everything (All-or-Nothing)
                db.session.commit()
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Submission failed (PDF Error): {e}")
                
                # Cleanup: Delete PDF if it was created
                if pdf_path and os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except:
                        pass
                        
                raise e # Re-raise to alert caller
        else:
             # No tools selected, but we still commit the session
             try:
                db.session.commit()
             except Exception as e:
                db.session.rollback()
                raise e
        
        duration = time.time() - start_time
        current_app.logger.info(f"CheckService: Processed {len(reports_to_create)} checks in {duration:.3f}s")
        
        return {
            "success": True,
            "session_id": session_id,
            "count": len(reports_to_create),
            "pdf_path": pdf_path
        }

    @staticmethod
    def process_tool_exchange(
        azubi_id: int,
        tool_id: int,
        reason: str,
        is_payable: bool,
        signature_data: str
    ) -> dict:
        """
        Handles One-Click Tool Exchange (Return Old -> Issue New).
        Atomically creates two records and one PDF.
        """
        start_time = time.time()
        
        # 1. Validation
        azubi = Azubi.query.get(azubi_id)
        if not azubi:
            raise ValueError(f"Azubi mit ID {azubi_id} nicht gefunden")
            
        tool = Werkzeug.query.get(tool_id)
        if not tool:
            raise ValueError(f"Werkzeug mit ID {tool_id} nicht gefunden")
            
        data_dir = CheckService.get_data_dir()
        session_id = CheckService.generate_unique_session_id()
        check_date = datetime.now()
        
        # 2. Save Signature
        sig_path = CheckService.save_signature(signature_data, session_id, 'azubi')
        
        # 3. Create Records (Memory)
        # Return Entry
        ret_entry = Check(
            session_id=session_id,
            azubi_id=azubi_id,
            werkzeug_id=tool_id,
            check_type=CheckType.RETURN.value,
            bemerkung=f'Austausch (Altteil): {reason}' + (' (Kostenpflichtig)' if is_payable else ''),
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
            bemerkung='Austausch (Neuteil)' + (' (Kostenpflichtig)' if is_payable else ''),
            incident_reason='Ersatzbeschaffung',
            datum=check_date,
            tech_param_value='Neu',
            signature_azubi=sig_path,
            report_path=None
        )
        
        db.session.add(ret_entry)
        db.session.add(issue_entry)
        
        # 4. Generate PDF
        pdf_path = None
        try:
            tools_list = [
                {'name': tool.name, 'category': tool.material_category, 'status': f'Rückgabe ({reason})'},
                {'name': tool.name, 'category': tool.material_category, 'status': 'Ausgabe (Neu)'}
            ]
            
            pdf_filename = f"austausch_{session_id}.pdf"
            pdf_path = os.path.join(data_dir, 'reports', pdf_filename)
            
            generate_handover_pdf(
                azubi_name=azubi.name, 
                examiner_name="System", 
                tools=tools_list, 
                check_type=CheckType.EXCHANGE, 
                signature_paths={'azubi': sig_path},
                output_path=pdf_path
            )
            
            ret_entry.report_path = pdf_path
            issue_entry.report_path = pdf_path
            
            # 5. Commit Atomically
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            # If PDF failed, we rollback DB. If DB failed, we rollback.
            # Cleanup Signature? Not strictly necessary but clean.
            current_app.logger.error(f"Exchange failed: {e}")
            raise e
            
        duration = time.time() - start_time
        current_app.logger.info(f"ExchangeService: Completed for {azubi.name} in {duration:.3f}s")
        
        return {
            "success": True,
            "session_id": session_id,
            "pdf_path": pdf_path
        }

    @staticmethod
    def process_single_check(
        azubi_id: int,
        examiner_id: int,
        check_date: datetime,
        remarks: str,
        signature_azubi_data: str,
        signature_examiner_data: str
    ) -> dict:
        """
        Processes a single check submission (e.g., a general check without specific tools).
        Creates one check record and a PDF.
        """
        start_time = time.time()

        # 0. Validate Azubi and Examiner
        azubi = Azubi.query.get(azubi_id)
        if not azubi:
            current_app.logger.error(f"CheckService: Azubi {azubi_id} not found")
            raise ValueError(f"Azubi mit ID {azubi_id} nicht gefunden")
        
        examiner = Examiner.query.get(examiner_id)
        if not examiner:
            current_app.logger.error(f"CheckService: Examiner {examiner_id} not found")
            raise ValueError(f"Prüfer mit ID {examiner_id} nicht gefunden")

        # 1. Setup Session
        session_id = CheckService.generate_unique_session_id()
        data_dir = CheckService.get_data_dir()

        # 2. Handle Signatures
        sig_azubi_path = CheckService.save_signature(
            signature_azubi_data, session_id, 'azubi'
        )
        sig_examiner_path = CheckService.save_signature(
            signature_examiner_data, session_id, 'examiner'
        )
        
        # 3. Save to DB (but don't commit yet!)
        try:
            new_check = Check(
                session_id=session_id,
                azubi_id=azubi.id,
                werkzeug_id=None, # Wird bei Einzelprüfungen nicht gesetzt
                check_type=CheckType.CHECK.value,
                bemerkung=remarks,
                datum=check_date,
                tech_param_value=None,
                signature_azubi=sig_azubi_path,
                signature_examiner=sig_examiner_path,
                report_path=None # Wird gleich gesetzt
            )
            
            db.session.add(new_check)
            
            # 4. Generate PDF
            pdf_filename = f"pruefung_{session_id}.pdf"
            pdf_path = os.path.join(data_dir, 'reports', pdf_filename)
            
            # Tools data preparation
            # ... (Logic needs to fetch tool details if we want them in PDF, 
            # ideally passed from route or fetched here. 
            # For now assuming we just generate the check protocol)
            
            generate_check_pdf(
                azubi_name=azubi.name,
                examiner_name=examiner.name,
                date_str=check_date.strftime("%d.%m.%Y"),
                remarks=remarks,
                signature_paths={
                    'azubi': sig_azubi_path, 
                    'examiner': sig_examiner_path
                },
                output_path=pdf_path
            )
            
            # Update record
            new_check.report_path = pdf_path
            
            # 5. Commit Check AND Items
            # Note: Items are currently not passed to this service method in logic flow
            # The current routes.py implementation iterates and saves items SEPARATELY.
            # This is a larger architectural flaw. BUT for this method:
            
            db.session.commit()
            
            duration = time.time() - start_time
            current_app.logger.info(f"CheckService: Processed in {duration:.3f}s")
            
            return {
                "success": True, 
                "session_id": session_id,
                "pdf_path": pdf_path
            }

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Check submission failed: {e}")
            raise e

class BackupService:
    @staticmethod
    def get_backup_dir():
        """Returns the path to the backup directory."""
        data_dir = current_app.config.get('DATA_DIR', os.path.dirname(__file__))
        backup_dir = os.path.join(data_dir, 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        return backup_dir

    @staticmethod
    def restore_backup(zip_path):
        """
        Restores the system from a ZIP file.
        WARNING: Overwrites current data!
        Includes Zip Slip protection.
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
                    import shutil
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)
                
                for member in zip_ref.namelist():
                    # ZIP SLIP PROTECTION
                    # Resolve the target path and check if it starts with the temp_dir
                    target_path = os.path.realpath(os.path.join(temp_dir, member))
                    if not target_path.startswith(os.path.realpath(temp_dir)):
                        raise ValueError(f"Sicherheitswarnung: Zip Slip Versuch erkannt bei {member}")
                        
                    zip_ref.extract(member, temp_dir)
                
            # 3. Overwrite Data (Critical Section)
            import shutil
            
            # DB & Config
            shutil.copy2(os.path.join(temp_dir, 'werkzeug.db'), os.path.join(data_dir, 'werkzeug.db'))
            
            # Handle Config (Optional in backup)
            if os.path.exists(os.path.join(temp_dir, 'config.yaml')):
                shutil.copy2(os.path.join(temp_dir, 'config.yaml'), os.path.join(data_dir, 'config.yaml'))
            
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
                
            # Cleanup
            shutil.rmtree(temp_dir)
            current_app.logger.info("Restore successful. Requesting restart.")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Restore failed: {e}")
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
            raise e

    @staticmethod
    def prune_backups():
        """
        Deletes old backups based on retention policy.
        """
        try:
            # Get retention days (Default: 30)
            from models import SystemSettings
            days_str = SystemSettings.get_setting('backup_retention_days', '30')
            try:
                days = int(days_str)
            except ValueError:
                days = 30
                
            if days <= 0:
                return # 0 means keep forever
                
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
                    pass # Ignore errors for individual files
                    
            if count > 0:
                current_app.logger.info(f"Pruned {count} old backups (> {days} days)")
                
        except Exception as e:
            current_app.logger.error(f"Pruning failed: {e}")

    @staticmethod
    def schedule_backup_job(app):
        """
        Configures the APScheduler job based on settings.
        """
        from extensions import scheduler
        from models import SystemSettings
        
        # Remove existing if any
        if scheduler.get_job('auto_backup'):
            scheduler.remove_job('auto_backup')
            
        # Get settings
        with app.app_context():
            interval = SystemSettings.get_setting('backup_interval', 'date') # 'daily', 'weekly', 'never', 'date' (fixed time)
            time_str = SystemSettings.get_setting('backup_time', '03:00') # HH:MM
            
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
            func=BackupService.create_backup_context_aware, # Helper needed for APP Context
            args=[app],
            trigger='cron',
            **trigger_args
        )
        current_app.logger.info(f"Scheduled auto-backup: {interval} at {hour:02d}:{minute:02d}")

    @staticmethod
    def create_backup_context_aware(app):
        """Wraps create_backup with app context for Scheduler"""
        with app.app_context():
            BackupService.create_backup()

    @staticmethod
    def create_backup():
        """Creates a zip backup of critical data."""
        data_dir = current_app.config.get('DATA_DIR', os.path.dirname(__file__))
        backup_dir = BackupService.get_backup_dir()
        """
        Creates a ZIP backup of:
        - werkzeug.db
        - config.yaml
        - signatures/
        - reports/
        
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
                ha_config_path = '/data/options.json'
                
                if os.path.exists(config_path):
                    zipf.write(config_path, 'config.yaml')
                elif os.path.exists(ha_config_path):
                    zipf.write(ha_config_path, 'options.json')
                
                # 3. Signatures
                sig_dir = os.path.join(data_dir, 'signatures')
                if os.path.exists(sig_dir):
                    for root, dirs, files in os.walk(sig_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, data_dir)
                            zipf.write(file_path, arcname)

                # 4. Reports (PDFs) - NEW in v2.7.0
                reports_dir = os.path.join(data_dir, 'reports')
                if os.path.exists(reports_dir):
                    for root, dirs, files in os.walk(reports_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, data_dir)
                            zipf.write(file_path, arcname)
                            
            size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)
            current_app.logger.info(f"Backup created: {backup_filename} ({size_mb} MB)")
            
            # Auto-Prune after successful creation
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
        """Returns list of available backups."""
        backup_dir = BackupService.get_backup_dir()
        backups = []
        if os.path.exists(backup_dir):
            for f in os.listdir(backup_dir):
                if f.endswith('.zip') and f.startswith('backup_'):
                    path = os.path.join(backup_dir, f)
                    stat = os.stat(path)
                    backups.append({
                        'filename': f,
                        'size_mb': round(stat.st_size / (1024 * 1024), 2),
                        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
        # Sort by filename (timestamp) desc
        return sorted(backups, key=lambda x: x['filename'], reverse=True)

    @staticmethod
    def rotate_backups(max_backups=10):
        """Keeps only latest N backups."""
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
                except Exception as e:
                    current_app.logger.error(f"Error rotating backup {f}: {e}")
