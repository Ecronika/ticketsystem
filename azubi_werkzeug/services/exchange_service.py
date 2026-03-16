"""Service for handling Tool Exchange logic."""
import os
from datetime import datetime, timezone
from flask import current_app

from extensions import db
from models import Azubi, Check, Werkzeug
from enums import CheckType
from exceptions import ValidationError, SignatureError, DatabaseError
from pdf_utils import generate_handover_pdf


class ExchangeService:  # pylint: disable=too-few-public-methods
    """Service for handling Tool Exchange logic."""

    @staticmethod
    def process_tool_exchange_batch(
        azubi_id, exchange_data, is_payable, signature_data
    ):  # pylint: disable=too-many-locals
        """Atomic batch processing for multiple tool exchanges."""
        from .check_service import CheckService  # pylint: disable=import-outside-toplevel
        azubi = db.session.get(Azubi, azubi_id)
        if not azubi:
            raise ValidationError(f"Azubi mit ID {azubi_id} nicht gefunden")

        session_id = CheckService.generate_unique_session_id()
        check_date = datetime.now(timezone.utc)
        sig_path = CheckService.save_signature(
            signature_data, session_id, 'azubi')
        pdf_path = None
        total_price = 0.0

        try:
            items = []
            for item in exchange_data:
                tool_id = item.get('tool_id')
                reason = item.get('reason')
                tool = db.session.get(Werkzeug, tool_id)
                if not tool:
                    raise ValidationError(f"Werkzeug mit ID {tool_id} nicht gefunden")

                if is_payable and tool.price:
                    total_price += tool.price

                ret_entry, issue_entry = ExchangeService._create_exchange_records(
                    session_id=session_id, azubi_id=azubi_id, tool_id=tool_id,
                    reason=reason, is_payable=is_payable, check_date=check_date,
                    sig_path=sig_path
                )
                db.session.add(ret_entry)
                db.session.add(issue_entry)
                items.append({'tool': tool, 'reason': reason,
                             'ret_entry': ret_entry, 'issue_entry': issue_entry})

            pdf_path = ExchangeService._generate_exchange_pdf_batch(
                azubi, items, session_id, sig_path, total_price)
            for item in items:
                item['ret_entry'].report_path = pdf_path
                item['issue_entry'].report_path = pdf_path
            db.session.commit()
            current_app.logger.info(
                "ExchangeService: Completed for %s", azubi.name)
            return {
                "success": True,
                "session_id": session_id,
                "pdf_path": pdf_path,
                "total_price": total_price
            }
        except Exception as e:
            db.session.rollback()
            ExchangeService._cleanup_exchange_files(sig_path, pdf_path)
            if isinstance(e, (ValidationError, SignatureError, DatabaseError)):
                raise
            current_app.logger.error("Exchange failed: %s", e)
            raise DatabaseError(f"Unerwarteter Fehler beim Austausch: {e}") from e

    @staticmethod
    def _create_exchange_records(
        *, session_id, azubi_id, tool_id, reason, is_payable, check_date, sig_path
    ):  # pylint: disable=too-many-arguments
        """Create Return and Issue records for exchange."""
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
            price=0.0
        )

        werkzeug = db.session.get(Werkzeug, tool_id)
        current_price = werkzeug.price if werkzeug else 0.0

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
            price=current_price if is_payable else 0.0
        )
        return ret_entry, issue_entry

    @staticmethod
    def _generate_exchange_pdf_batch(azubi, tools_for_pdf, session_id, sig_path, total_price=0.0):
        """Batch PDF generation for tool exchange."""
        tools_list = []
        for item in tools_for_pdf:
            tool = item['tool']
            reason = item['reason']
            tools_list.append({
                'name': tool.name, 'category': tool.material_category,
                'status': f'Rückgabe ({reason})'
            })
            tools_list.append({
                'name': tool.name, 'category': tool.material_category,
                'status': 'Ausgabe (Neu)'
            })

        from extensions import Config  # pylint: disable=import-outside-toplevel
        data_dir = Config.get_data_dir()
        pdf_filename = f"austausch_{session_id}.pdf"
        pdf_path = os.path.join(data_dir, 'reports', pdf_filename)

        extra = [
            f"Geschätzter Gesamtersatzwert: {total_price:.2f} EUR"] if total_price > 0 else []

        generate_handover_pdf(
            azubi_name=azubi.name, examiner_name="System",
            tools=tools_list, check_type=CheckType.EXCHANGE,
            signature_paths={'azubi': sig_path}, output_path=pdf_path,
            extra_lines=extra
        )
        return pdf_path

    @staticmethod
    def _cleanup_exchange_files(sig_path, pdf_path):
        """Cleanup logic for exchange errors."""
        for p in [sig_path, pdf_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
