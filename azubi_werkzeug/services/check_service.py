"""
Check Service module.

Handles tool check submissions, tool tracking, signature handling,
and PDF report linking.
"""
import base64
import os
import uuid
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import func

from dto import CheckSubmissionContext
from enums import CheckType
from exceptions import (
    AzubiWerkzeugError, ValidationError, SignatureError, DatabaseError
)
from extensions import Config, db
from models import Azubi, Check, Werkzeug
from pdf_utils import generate_handover_pdf, parse_check_type


class CheckService:
    """Service for handling Check and Tool Exchange logic."""

    @staticmethod
    def get_data_dir():
        """Return the data directory from config."""
        return Config.get_data_dir()

    @staticmethod
    def get_assigned_tools_batch(azubi_ids: list) -> dict:
        """Optimized SQL determination of assigned tools per Azubi."""
        if not azubi_ids:
            return {}

        subq = db.session.query(
            Check.azubi_id,
            Check.werkzeug_id,
            func.max(Check.datum).label('last_datum')
        ).filter(Check.azubi_id.in_(azubi_ids)).group_by(
            Check.azubi_id, Check.werkzeug_id
        ).subquery()

        latest_checks = db.session.query(
            Check.azubi_id, Check.werkzeug_id, Check.check_type
        ).join(subq, (Check.azubi_id == subq.c.azubi_id) &
               (Check.werkzeug_id == subq.c.werkzeug_id) &
               (Check.datum == subq.c.last_datum)).all()

        result = {aid: set() for aid in azubi_ids}

        for azubi_id, werkzeug_id, raw_check_type in latest_checks:
            c_type = parse_check_type(raw_check_type)
            if c_type != CheckType.RETURN:
                result[azubi_id].add(werkzeug_id)

        return result

    @staticmethod
    def get_tool_anomalies_batch(azubi_ids: list, assigned_tools_batch: dict) -> dict:
        """Return missing/broken counts and tool names for assigned tools per Azubi."""
        if not azubi_ids:
            return {}

        subq = (
            db.session.query(
                Check.azubi_id,
                Check.werkzeug_id,
                func.max(Check.datum).label('last_datum')
            )
            .filter(Check.azubi_id.in_(azubi_ids))
            .group_by(Check.azubi_id, Check.werkzeug_id)
            .subquery()
        )

        latest_checks = (
            db.session.query(Check, Werkzeug)
            .join(Werkzeug, Check.werkzeug_id == Werkzeug.id)
            .join(subq, (Check.azubi_id == subq.c.azubi_id) &
                        (Check.werkzeug_id == subq.c.werkzeug_id) &
                        (Check.datum == subq.c.last_datum))
            .all()
        )

        anomalies = {aid: {
            'missing': 0, 'broken': 0,
            'missing_tools': [], 'broken_tools': [],
            'missing_tool_ids': [], 'broken_tool_ids': []
        } for aid in azubi_ids}

        for check, werkzeug in latest_checks:
            assigned_for_azubi = assigned_tools_batch.get(
                check.azubi_id, set())
            if check.werkzeug_id in assigned_for_azubi:
                bemerkung = check.bemerkung or ""
                if 'Status: missing' in bemerkung:
                    anomalies[check.azubi_id]['missing'] += 1
                    anomalies[check.azubi_id]['missing_tools'].append(
                        werkzeug.name)
                    anomalies[check.azubi_id]['missing_tool_ids'].append(
                        werkzeug.id)
                elif 'Status: broken' in bemerkung:
                    anomalies[check.azubi_id]['broken'] += 1
                    anomalies[check.azubi_id]['broken_tools'].append(
                        werkzeug.name)
                    anomalies[check.azubi_id]['broken_tool_ids'].append(
                        werkzeug.id)

        return anomalies

    @staticmethod
    def get_assigned_tools(azubi_id):
        """Return a set of tool IDs currently assigned to the Azubi."""
        subq = db.session.query(
            Check.werkzeug_id,
            func.max(Check.datum).label('last_datum')
        ).filter(Check.azubi_id == azubi_id).group_by(
            Check.werkzeug_id
        ).subquery()

        latest_checks = db.session.query(Check.werkzeug_id, Check.check_type)\
            .join(subq, (Check.werkzeug_id == subq.c.werkzeug_id) &
                        (Check.datum == subq.c.last_datum)).all()

        assigned_tools = set()
        for werkzeug_id, raw_check_type in latest_checks:
            c_type = parse_check_type(raw_check_type)
            if c_type != CheckType.RETURN:
                assigned_tools.add(werkzeug_id)

        return assigned_tools

    @staticmethod
    def generate_unique_session_id():
        """Generate a unique session ID."""
        return str(uuid.uuid4())

    @staticmethod
    def detect_exchange_type(checks):
        """Detect if a session is an exchange."""
        check_types = [parse_check_type(c.check_type) for c in checks]
        has_return = CheckType.RETURN in check_types
        has_issue = CheckType.ISSUE in check_types

        if has_return and has_issue and len(checks) >= 2:
            return CheckType.EXCHANGE
        if any('Austausch' in (c.bemerkung or '') for c in checks):
            return CheckType.EXCHANGE
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
    def ensure_price_backfill():
        """Bulk SQL backfill for missing price snapshots."""
        import sqlalchemy as sa
        try:
            stmt = sa.select(sa.func.count()).select_from(Check).where(  # pylint: disable=not-callable
                Check.price.is_(None)
            ).limit(1)
            count_needed = db.session.execute(stmt).scalar() or 0
            if count_needed == 0:
                return 0
        except Exception:  # pylint: disable=broad-exception-caught
            return 0

        try:
            price_subquery = sa.select(sa.func.coalesce(Werkzeug.price, 0.0))\
                .where(Werkzeug.id == Check.werkzeug_id)\
                .scalar_subquery()

            result = db.session.execute(
                sa.update(Check)
                .where(Check.price.is_(None))
                .values(price=price_subquery)
            )
            db.session.commit()
            count = result.rowcount
            if count > 0:
                current_app.logger.info(
                    "Database: Bulk-backfilled %d checks.", count)
            return count
        except sa.exc.SQLAlchemyError as e:
            current_app.logger.error("Price backfill failed: %s", e)
            db.session.rollback()
            return 0

    @staticmethod
    def cleanup_session_files(files_to_delete):
        """Delete a list of file paths."""
        deleted_count = 0
        for f_path in files_to_delete:
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    deleted_count += 1
                except OSError as e:
                    current_app.logger.warning(
                        "Failed to delete file %s: %s", f_path, e)
        return deleted_count

    @staticmethod
    def collect_tool_ids(form_data):
        """Extract tool IDs from form keys."""
        tool_ids = []
        for key in form_data:
            if key.startswith('tool_'):
                try:
                    tool_ids.append(int(key.split('_')[1]))
                except (IndexError, ValueError):
                    continue
        return tool_ids

    @staticmethod
    def save_signature(signature_data: str, session_id: str, suffix: str) -> str:
        """Save base64 signature to disk."""
        if not signature_data or ',' not in signature_data:
            return None

        try:
            data_dir = Config.get_data_dir()
            os.makedirs(os.path.join(data_dir, 'signatures'), exist_ok=True)

            _, encoded = signature_data.split(",", 1)
            try:
                data = base64.b64decode(encoded)
            except Exception as e:  # pylint: disable=broad-exception-caught
                current_app.logger.error("Invalid signature data: %s", e)
                return None

            filename = f"{session_id}_{suffix}.png"
            path = os.path.join(data_dir, 'signatures', filename)
            with open(path, "wb") as f:
                f.write(data)
            return path
        except Exception as e:
            current_app.logger.error("Error saving signature: %s", e)
            raise SignatureError(
                f"Fehler beim Speichern der Signatur: {e}") from e

    @staticmethod
    def _prepare_check_records(tool_ids, werkzeug_dict, form_data, check_context):
        """Prepare Check DB records and data for PDF."""
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
            manufacturer = form_data.get(f'manufacturer_{tool_id}')

            full_bemerkung = f"Status: {status}"
            if global_bemerkung:
                full_bemerkung += f" | {global_bemerkung}"

            records.append(Check(
                session_id=check_context['session_id'],
                azubi_id=check_context.azubi_id,
                werkzeug_id=werkzeug.id,
                bemerkung=full_bemerkung,
                tech_param_value=tech_val,
                incident_reason=incident_reason,
                manufacturer=manufacturer,
                datum=check_context.datum,
                check_type=check_context.check_type.value,
                examiner=check_context.examiner_name,
                signature_azubi=check_context.sig_azubi_path,
                signature_examiner=check_context.sig_examiner_path,
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
        """Cleanup files on error."""
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        if checks:
            first = checks[0]
            for p in [first.signature_azubi, first.signature_examiner]:
                if p and os.path.exists(p) and 'signature' in p:
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    @staticmethod
    def _commit_checks_or_cleanup(checks, pdf_path):
        """Commit records or cleanup."""
        try:
            for check in checks:
                db.session.add(check)
            db.session.commit()
        except Exception as e:
            current_app.logger.error("DB Commit failed: %s", e)
            db.session.rollback()
            CheckService._cleanup_on_error(checks, pdf_path)
            raise DatabaseError(
                f"Datenbankfehler beim Speichern der Prüfung: {e}") from e

    @staticmethod
    def _build_check_context(
        azubi,
        examiner_name,
        check_date,
        check_type,
        session_id,
        sig_azubi_path,
        sig_examiner_path
    ):
        """Build check context DTO."""
        from app_state import is_migration_active
        return CheckSubmissionContext(
            azubi_id=azubi.id,
            azubi_name=azubi.name,
            examiner_name=examiner_name,
            datum=check_date,
            check_type=check_type,
            session_id=session_id,
            sig_azubi_path=sig_azubi_path,
            sig_examiner_path=sig_examiner_path,
            is_migration=is_migration_active()
        )

    @staticmethod
    def _fetch_tools_dict(tool_ids):
        """Fetch tools by ID."""
        werkzeuge = Werkzeug.query.filter(Werkzeug.id.in_(tool_ids)).all()
        return {w.id: w for w in werkzeuge}

    @staticmethod
    def _handle_signatures(form_data, session_id):
        """Handle signature validation."""
        sig_azubi_path = CheckService.save_signature(
            form_data.get('signature_azubi_data'), session_id, 'azubi')

        from app_state import is_migration_active
        is_migration = is_migration_active()

        if not sig_azubi_path and not is_migration:
            raise SignatureError("Fehler beim Speichern der Azubi-Signatur")

        sig_examiner_path = CheckService.save_signature(
            form_data.get('signature_examiner_data'), session_id, 'examiner')

        if not sig_examiner_path and not is_migration:
            if sig_azubi_path and os.path.exists(sig_azubi_path):
                try:
                    os.remove(sig_azubi_path)
                except OSError:
                    pass
            raise SignatureError(
                "Fehler beim Speichern der Ausbilder-Signatur")

        return sig_azubi_path, sig_examiner_path

    @staticmethod
    def process_check_submission(
        azubi_id,
        examiner_name,
        tool_ids,
        form_data,
        check_date=None,
        check_type=CheckType.CHECK
    ):
        """Process check submission logic."""
        if not check_date:
            check_date = datetime.now(timezone.utc)

        session_id = CheckService.generate_unique_session_id()
        sig_azubi_path, sig_examiner_path = CheckService._handle_signatures(
            form_data, session_id)

        azubi = CheckService._get_azubi_or_raise(azubi_id)
        check_context = CheckService._build_check_context(
            azubi, examiner_name, check_date, check_type,
            session_id, sig_azubi_path, sig_examiner_path)

        werkzeug_dict = CheckService._fetch_tools_dict(tool_ids)
        return CheckService._execute_submission_flow(
            tool_ids, werkzeug_dict, form_data, check_context)

    @staticmethod
    def _get_azubi_or_raise(azubi_id):
        """Fetch Azubi or raise ValidationError."""
        azubi = db.session.get(Azubi, azubi_id)
        if not azubi:
            current_app.logger.error(
                "CheckService: Azubi %d not found", azubi_id)
            raise ValidationError(f"Azubi mit ID {azubi_id} nicht gefunden")
        return azubi

    @staticmethod
    def _execute_submission_flow(tool_ids, werkzeug_dict, form_data, context):
        """Execute the core submission workflow (PDF + DB)."""
        pdf_path = None
        reports_to_create = []

        try:
            reports_to_create, selected_tools = CheckService._prepare_check_records(
                tool_ids, werkzeug_dict, form_data, context)

            pdf_path = CheckService._generate_submission_pdf(context, selected_tools)

            # Update paths in memory before commit
            for check in reports_to_create:
                check.report_path = pdf_path

            CheckService._commit_checks_or_cleanup(reports_to_create, pdf_path)

            return {
                'success': True,
                'session_id': context.session_id,
                'pdf_path': pdf_path,
                'count': len(reports_to_create)
            }
        except Exception as e:   # pylint: disable=broad-exception-caught
            CheckService._cleanup_on_error(reports_to_create, pdf_path)
            CheckService._rethrow_as_domain_exception(e)
            return None

    @staticmethod
    def _generate_submission_pdf(context, selected_tools):
        """Generate the handover PDF."""
        reports_dir = os.path.join(current_app.config['DATA_DIR'], 'reports')
        name_clean = context.azubi_name.replace(' ', '_')
        date_str = context.datum.strftime('%Y%m%d_%H%M')
        pdf_filename = f"Protokoll_{context.check_type.value}_{name_clean}_{date_str}.pdf"
        pdf_path = os.path.join(reports_dir, pdf_filename)

        generate_handover_pdf(
            azubi_name=context.azubi_name,
            examiner_name=context.examiner_name,
            tools=selected_tools,
            check_type=context.check_type,
            signature_paths={
                'azubi': context.sig_azubi_path,
                'examiner': context.sig_examiner_path
            },
            output_path=pdf_path
        )
        return pdf_path

    @staticmethod
    def _rethrow_as_domain_exception(e):
        """Standardize exception handling for submission flow."""
        if isinstance(e, AzubiWerkzeugError):
            raise e
        raise DatabaseError(f"Interner Fehler bei der Verarbeitung: {e}") from e
