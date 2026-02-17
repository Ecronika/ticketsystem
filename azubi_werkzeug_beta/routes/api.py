"""
API routes.

"""
# pylint: disable=duplicate-code
from datetime import datetime

from flask import request, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError

from extensions import db, limiter, csrf
from models import Azubi, Werkzeug, Examiner, Check
from forms import AzubiForm, ExaminerForm, WerkzeugForm
from services import CheckService


def register_routes(bp):
    """Register API routes on the given blueprint."""

    @bp.route('/api/stats')
    @limiter.limit("30 per minute")
    @csrf.exempt
    def api_stats():
        """Return basic statistics for dashboard."""
        total_tools = Werkzeug.query.count()
        total_azubis = Azubi.query.filter_by(
            is_archived=False).count()
        start_of_day = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        checks_today = Check.query.filter(
            Check.datum >= start_of_day).count()

        return jsonify({
            'total_tools': total_tools,
            'total_azubis': total_azubis,
            'checks_today': checks_today,
            'generated_at': datetime.now().isoformat()
        })

    @bp.route('/api/assigned_tools/<int:azubi_id>')
    def api_get_assigned_tools(azubi_id):
        """API to get assigned tools for dropdown."""
        tool_ids = CheckService.get_assigned_tools(
            azubi_id)
        found_tools = Werkzeug.query.filter(
            Werkzeug.id.in_(tool_ids)).order_by(
            Werkzeug.name).all()
        return jsonify(
            [{'id': t.id, 'name': t.name}
             for t in found_tools])

    @bp.route('/api/werkzeug', methods=['POST'])
    def api_add_werkzeug():
        """AJAX endpoint for adding werkzeug."""
        try:
            form = WerkzeugForm(request.form)
            if not form.validate():
                return jsonify(
                    {'success': False,
                     'errors': form.errors}), 400
            new_werkzeug = Werkzeug(
                name=form.name.data,
                material_category=(
                    form.material_category.data),
                tech_param_label=(
                    form.tech_param_label.data))
            db.session.add(new_werkzeug)
            db.session.commit()
            return jsonify({
                'success': True,
                'werkzeug': {
                    'id': new_werkzeug.id,
                    'name': new_werkzeug.name,
                    'category': (
                        new_werkzeug.material_category),
                    'param': (
                        new_werkzeug.tech_param_label
                        or '')
                }
            })
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"API add werkzeug error: {e}")
            return jsonify({
                'success': False,
                'error': 'Datenbankfehler beim '
                         'Hinzufügen des Werkzeugs'
            }), 500
        except Exception as e:  # pylint: disable=broad-exception-caught
            db.session.rollback()
            current_app.logger.error(
                f"API add werkzeug unexpected: {e}")
            return jsonify({
                'success': False,
                'error': 'Ein unbekannter Fehler '
                         'ist aufgetreten.'
            }), 500

    @bp.route('/api/azubi', methods=['POST'])
    def api_add_azubi():
        """AJAX endpoint for adding azubi."""
        try:
            form = AzubiForm(request.form)
            if not form.validate():
                return jsonify(
                    {'success': False,
                     'errors': form.errors}), 400
            new_azubi = Azubi(
                name=form.name.data,
                lehrjahr=form.lehrjahr.data)
            db.session.add(new_azubi)
            db.session.commit()
            return jsonify({
                'success': True,
                'azubi': {
                    'id': new_azubi.id,
                    'name': new_azubi.name,
                    'lehrjahr': new_azubi.lehrjahr,
                    'is_archived': new_azubi.is_archived
                }
            })
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"API add azubi error: {e}")
            return jsonify({
                'success': False,
                'error': 'Datenbankfehler beim '
                         'Hinzufügen des Azubis'
            }), 500
        except Exception as e:  # pylint: disable=broad-exception-caught
            db.session.rollback()
            current_app.logger.error(
                f"API add azubi unexpected: {e}")
            return jsonify({
                'success': False,
                'error': 'Ein unbekannter Fehler '
                         'ist aufgetreten.'
            }), 500

    @bp.route('/api/examiner', methods=['POST'])
    def api_add_examiner():
        """AJAX endpoint for adding examiner."""
        try:
            form = ExaminerForm(request.form)
            if not form.validate():
                return jsonify(
                    {'success': False,
                     'errors': form.errors}), 400
            new_examiner = Examiner(
                name=form.name.data)
            db.session.add(new_examiner)
            db.session.commit()
            return jsonify({
                'success': True,
                'examiner': {
                    'id': new_examiner.id,
                    'name': new_examiner.name
                }
            })
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"API add examiner error: {e}")
            return jsonify({
                'success': False,
                'error': 'Datenbankfehler beim '
                         'Hinzufügen des Prüfers'
            }), 500
        except Exception as e:  # pylint: disable=broad-exception-caught
            db.session.rollback()
            current_app.logger.error(
                f"API add examiner unexpected: {e}")
            return jsonify({
                'success': False,
                'error': 'Ein unbekannter Fehler '
                         'ist aufgetreten.'
            }), 500
