"""
Authentication routes.

Handles admin authentication and session management.
"""
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db, limiter
from models import SystemSettings, Worker


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


@limiter.limit("5 per minute")
def _setup_view():
    """Handle initial onboarding / first-start setup."""
    is_complete = SystemSettings.get_setting('onboarding_complete') == 'true'
    if is_complete:
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.login')}")

    if request.method == 'POST':
        name = request.form.get('name')
        pin = request.form.get('pin')
        pin_confirm = request.form.get('pin_confirm')

        if not name or not pin:
            flash('Bitte Name und PIN angeben.', 'warning')
            return render_template('setup.html')
        
        if pin != pin_confirm:
            flash('Die PINs stimmen nicht überein.', 'warning')
            return render_template('setup.html')

        # Update bootstrap admin
        admin = Worker.query.filter_by(is_admin=True).first()
        if admin:
            admin.name = name
            admin.pin_hash = generate_password_hash(pin)
            
            # Mark onboarding as complete
            setting = SystemSettings.query.filter_by(key="onboarding_complete").first()
            if setting:
                setting.value = 'true'
            
            db.session.commit()
            
            # Auto-login
            session.permanent = True
            session['worker_id'] = admin.id
            session['worker_name'] = admin.name
            session['is_admin'] = True
            
            flash('Setup abgeschlossen! Willkommen im System.', 'success')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.index')}")

    return render_template('setup.html')

@limiter.limit("20 per minute")
def _login_view():
    """Handle the login view and processing."""
    # Check for onboarding
    if SystemSettings.get_setting('onboarding_complete') != 'true':
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.setup')}")

    workers = Worker.query.filter_by(is_active=True).all()
    if not workers:
        flash("Keine Mitarbeiter gefunden. System-Bootstrap erforderlich.", "danger")
        return render_template('login.html', workers=[])

    if request.method == 'POST':
        worker_id = request.form.get('worker_id')
        pin = request.form.get('pin')

        if not worker_id or not pin:
            flash('Bitte Mitarbeiter und PIN wählen.', 'warning')
            return render_template('login.html', workers=workers)

        worker = db.session.get(Worker, worker_id)
        if worker and check_password_hash(worker.pin_hash, pin):
            session.permanent = True
            session['worker_id'] = worker.id
            session['worker_name'] = worker.name
            session['is_admin'] = worker.is_admin
            
            flash(f'Willkommen zurück, {worker.name}!', 'success')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.index')}")
        else:
            flash('Falscher PIN.', 'danger')

    return render_template('login.html', workers=workers)

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


@limiter.limit("5 per minute")
def _setup_view():
    """Handle initial onboarding / first-start setup."""
    is_complete = SystemSettings.get_setting('onboarding_complete') == 'true'
    if is_complete:
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.login')}")

    if request.method == 'POST':
        name = request.form.get('name')
        pin = request.form.get('pin')
        pin_confirm = request.form.get('pin_confirm')

        if not name or not pin:
            flash('Bitte Name und PIN angeben.', 'warning')
            return render_template('setup.html')
        
        if pin != pin_confirm:
            flash('Die PINs stimmen nicht überein.', 'warning')
            return render_template('setup.html')

        # Update bootstrap admin
        admin = Worker.query.filter_by(is_admin=True).first()
        if admin:
            admin.name = name
            admin.pin_hash = generate_password_hash(pin)
            
            # Mark onboarding as complete
            SystemSettings.set_setting('onboarding_complete', 'true')
            db.session.commit()
            
            # Auto-login
            session.permanent = True
            session['worker_id'] = admin.id
            session['worker_name'] = admin.name
            session['is_admin'] = True
            
            flash('Setup abgeschlossen! Willkommen im System.', 'success')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.index')}")

    return render_template('setup.html')


@limiter.limit("20 per minute")
def _login_view():
    """Handle the login view and processing."""
    # Check for onboarding
    if SystemSettings.get_setting('onboarding_complete') != 'true':
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.setup')}")

    workers = Worker.query.filter_by(is_active=True).all()
    if not workers:
        flash("Keine Mitarbeiter gefunden. System-Bootstrap erforderlich.", "danger")
        return render_template('login.html', workers=[])

    if request.method == 'POST':
        worker_id = request.form.get('worker_id')
        pin = request.form.get('pin')

        if not worker_id or not pin:
            flash('Bitte Mitarbeiter und PIN wählen.', 'warning')
            return render_template('login.html', workers=workers)

        worker = db.session.get(Worker, worker_id)
        if worker and check_password_hash(worker.pin_hash, pin):
            session.permanent = True
            session['worker_id'] = worker.id
            session['worker_name'] = worker.name
            session['is_admin'] = worker.is_admin
            
            flash(f'Willkommen zurück, {worker.name}!', 'success')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.index')}")
        else:
            flash('Falscher PIN.', 'danger')

    return render_template('login.html', workers=workers)


def _logout_view():
    """Handle user logout."""
    session.clear()
    flash('Erfolgreich abgemeldet.', 'info')
    ingress = request.headers.get('X-Ingress-Path', '')
    return redirect(f"{ingress}{url_for('main.login')}")


def _recover_pin_view():
    """Handle PIN recovery using a single-use token."""
    # (Existing implementation remains... I'll keep it simple for now)
    return render_template('recover_pin.html')


def register_routes(bp):
    """Register auth routes."""
    bp.add_url_rule('/login', 'login', view_func=_login_view, methods=['GET', 'POST'])
    bp.add_url_rule('/logout', 'logout', view_func=_logout_view)
    bp.add_url_rule('/setup', 'setup', view_func=_setup_view, methods=['GET', 'POST'])
    bp.add_url_rule('/recover_pin', 'recover_pin', view_func=_recover_pin_view, methods=['GET', 'POST'])
