"""
Authentication routes.

Handles admin authentication and session management.
"""
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from extensions import limiter
from models import SystemSettings


def _is_safe_redirect(target: str) -> bool:
    """Return True only if target stays on the same host or Ingress proxy."""
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    if test.scheme not in ('http', 'https'):
        return False
    # Direct same-host match (standalone / local access)
    if ref.netloc == test.netloc:
        return True
    # Behind Ingress: the target URL carries the external hostname.
    # Trust it if it contains the Ingress path prefix so we stay on the
    # same add-on and don't redirect to a foreign site.
    ingress = request.headers.get('X-Ingress-Path', '')
    if ingress and test.path.startswith(ingress):
        return True
    return False


def admin_required(f):
    """Decorate to require admin permissions."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            if request.path.startswith('/api/'):
                from flask import jsonify
                return jsonify({'success': False, 'error': 'Admin-Rechte erforderlich.'}), 403

            flash('Diese Aktion erfordert Administrator-Rechte.', 'warning')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.login', next=request.url)}")
        return f(*args, **kwargs)
    return decorated_function


def worker_required(f):
    """Decorate to require a worker login session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('worker_id'):
            if request.path.startswith('/api/'):
                from flask import jsonify
                return jsonify({'success': False, 'error': 'Bitte zuerst einloggen.'}), 401

            flash('Bitte loggen Sie sich ein.', 'info')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.login', next=request.url)}")
        return f(*args, **kwargs)
    return decorated_function


from models import Worker

def _login_view():
    """Handle worker login with Dropdown and PIN."""
    if request.method == 'POST':
        worker_id = request.form.get('worker_id')
        pin = request.form.get('pin')

        if not worker_id or not pin:
            flash('Bitte Mitarbeiter auswählen und PIN eingeben.', 'warning')
            return render_template('login.html', workers=Worker.query.filter_by(is_active=True).all())

        worker = db.session.get(Worker, worker_id)
        if worker and worker.pin_hash and check_password_hash(worker.pin_hash, pin):
            session.clear()
            session['worker_id'] = worker.id
            session['worker_name'] = worker.name
            session['is_admin'] = worker.is_admin
            session.permanent = True
            
            flash(f'Willkommen zurück, {worker.name}!', 'success')
            raw_next = request.args.get('next') or request.form.get('next')
            ingress = request.headers.get('X-Ingress-Path', '')
            next_url = raw_next if (raw_next and _is_safe_redirect(raw_next)) else None
            return redirect(next_url or f"{ingress}{url_for('main.index')}")

        flash('Falscher PIN oder Mitarbeiter nicht gefunden.', 'error')

    active_workers = Worker.query.filter_by(is_active=True).all()
    # If no workers exist yet, we might need a way to create the first admin or fallback to system pin
    if not active_workers:
        flash('Keine aktiven Mitarbeiter gefunden. Bitte System-Administrator kontaktieren.', 'warning')

    return render_template('login.html', workers=active_workers)


def _logout_view():
    """Handle worker logout."""
    session.clear()
    flash('Erfolgreich ausgeloggt.', 'info')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.index')}")


def _recover_pin_view():
    """Handle PIN recovery using a single-use token."""
    if request.method == 'POST':
        token = request.form.get('token', '').strip().upper()

        # Load existing hashes
        saved_hashes_str = SystemSettings.get_setting(
            'recovery_tokens_hash', '')
        if not saved_hashes_str:
            flash('Keine Recovery-Tokens im System hinterlegt.', 'error')
            return render_template('recover_pin.html')

        hashed_tokens = saved_hashes_str.split(',')
        valid_index = -1

        for idx, h in enumerate(hashed_tokens):
            if check_password_hash(h, token):
                valid_index = idx
                break

        if valid_index >= 0:
            # Valid token found! Remove it from the list
            hashed_tokens.pop(valid_index)
            SystemSettings.set_setting(
                'recovery_tokens_hash', ','.join(hashed_tokens))

            session['is_admin'] = True
            session.permanent = True

            flash(
                'Erfolgreich eingeloggt. Bitte ändern Sie jetzt Ihren PIN!', 'success')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.index')}")


        flash('Ungültiger oder bereits verwendeter Token.', 'error')

    return render_template('recover_pin.html')


def register_routes(bp):
    """Register auth routes."""
    # Rate-limit applied via @bp.route so the decorator chain is respected.
    login_view = limiter.limit("5 per minute")(_login_view)
    login_view.__name__ = 'login'
    bp.add_url_rule('/login', view_func=login_view, methods=['GET', 'POST'])

    logout_view = _logout_view
    logout_view.__name__ = 'logout'
    bp.add_url_rule('/logout', view_func=logout_view, methods=['POST'])

    recover_pin_view = limiter.limit("5 per minute")(_recover_pin_view)
    recover_pin_view.__name__ = 'recover_pin'
    bp.add_url_rule('/recover_pin', view_func=recover_pin_view,
                    methods=['GET', 'POST'])
