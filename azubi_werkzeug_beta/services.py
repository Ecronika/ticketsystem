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
            data = base64.b64decode(encoded)
            
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
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"DB Error fetching/saving checks: {e}")
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
                
                # 7. Update Records with PDF Path
                check_ids = [r.id for r in reports_to_create]
                Check.query.filter(Check.id.in_(check_ids)).update(
                    {'report_path': pdf_path},
                    synchronize_session=False
                )
                db.session.commit()
                
            except Exception as e:
                current_app.logger.error(f"PDF Generation failed: {e}")
                # Don't rollback DB, just log error. PDF is secondary.
        
        duration = time.time() - start_time
        current_app.logger.info(f"CheckService: Processed {len(reports_to_create)} checks in {duration:.3f}s")
        
        return {
            "success": True,
            "session_id": session_id,
            "count": len(reports_to_create),
            "pdf_path": pdf_path
        }

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
    def create_backup():
        """Creates a zip backup of critical data."""
        data_dir = current_app.config.get('DATA_DIR', os.path.dirname(__file__))
        backup_dir = BackupService.get_backup_dir()
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{timestamp}.zip"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        current_app.logger.info(f"Starting backup: {backup_path}")
        
        items_to_backup = [
            'werkzeug.db',
            'config.yaml',
            'signatures',
            'reports'
        ]
        
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for item in items_to_backup:
                    # Item path relative to DATA_DIR
                    full_path = os.path.join(data_dir, item)
                    
                    # config.yaml exception: it might be in root, not data_dir in some setups
                    if item == 'config.yaml' and not os.path.exists(full_path):
                        # Try root dir (cwd)
                        root_path = os.path.join(os.getcwd(), 'config.yaml')
                        if os.path.exists(root_path):
                            full_path = root_path
                    
                    if os.path.exists(full_path):
                        if os.path.isdir(full_path):
                            for root, dirs, files in os.walk(full_path):
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    # Archive name should be relative to data_dir usually
                                    # ex: signatures/file.png
                                    arcname = os.path.relpath(file_path, data_dir)
                                    zipf.write(file_path, arcname)
                        else:
                            arcname = os.path.basename(full_path)
                            zipf.write(full_path, arcname)
                    else:
                        current_app.logger.warning(f"Backup: Item not found {full_path}")
            
            # Rotation
            BackupService.rotate_backups()
            return backup_filename
            
        except Exception as e:
            current_app.logger.error(f"Backup failed: {e}", exc_info=True)
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
