"""
Authentication routes.

Handles admin authentication and session management.
"""
from functools import wraps
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

from flask import flash, redirect, render_template, request, session, url_for, make_response, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db, limiter
from models import SystemSettings, Worker


def is_safe_url(target):
    """Robustly check if a redirect target is safe (on the same host/ingress)."""
    if not target:
        return False
        
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    
    # Check if target is same host
    if test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc:
        return True
        
    # Check if it matches Ingress path
    ingress = request.headers.get('X-Ingress-Path', '')
    if ingress and target.startswith(ingress):
        return True
        
    return False


def redirect_to(endpoint, **kwargs):
    """Helper for Ingress-aware redirects."""
    ingress = request.headers.get('X-Ingress-Path', '')
    target = url_for(endpoint, **kwargs)
    
    # Ensure no double slashes
    if ingress.endswith('/') and target.startswith('/'):
        target = target[1:]
    elif not ingress.endswith('/') and not target.startswith('/'):
        target = '/' + target
        
    return redirect(f"{ingress}{target}")


def admin_required(f):
    """Decorate to require admin permissions."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            if request.path.startswith('/api/'):
                from flask import jsonify
                return jsonify({'success': False, 'error': 'Admin-Rechte erforderlich.'}), 403

            flash('Diese Aktion erfordert Administrator-Rechte.', 'warning')
            return redirect_to('main.login', next=request.url)
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
            return redirect_to('main.login', next=request.url)
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
            # SEC-01: Explicitly use pbkdf2:sha256 with 600k iterations (standard in Werkzeug 3.x)
            admin.pin_hash = generate_password_hash(pin, method='pbkdf2:sha256', salt_length=16)
            
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
            return redirect_to('main.index')

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
        worker_name = (request.form.get('worker_name') or '').strip()
        pin = (request.form.get('pin') or '').strip()

        if not worker_name or not pin:
            flash('Bitte Name und PIN angeben.', 'warning')
            return render_template('login.html', workers=workers)

        # Naive UTC lookup for SQLite compatibility
        _now = datetime.now(timezone.utc).replace(tzinfo=None)
        worker = Worker.query.filter(Worker.name.ilike(worker_name), Worker.is_active == True).with_for_update().first()
        if worker:
            # Check for active lockout
            if worker.locked_until and worker.locked_until > _now:
                time_diff = worker.locked_until - _now
                minutes_left = int(time_diff.total_seconds() // 60) + 1
                flash(f'Konto vorübergehend gesperrt. Bitte in {minutes_left} Min. erneut versuchen.', 'danger')
                return render_template('login.html', workers=workers)

            if check_password_hash(worker.pin_hash, pin):
                # Reset lockout on success
                worker.failed_login_count = 0
                worker.locked_until = None
                worker.last_active = datetime.now(timezone.utc).replace(tzinfo=None)
                db.session.commit()

                session.permanent = True
                session['worker_id'] = worker.id
                session['worker_name'] = worker.name
                session['is_admin'] = (worker.role == 'admin')  # SEC-07: Use role as single source of truth
                session['role'] = worker.role or 'worker'

                if worker.needs_pin_change:
                    flash('Bitte ändern Sie zu Ihrer Sicherheit zuerst Ihren PIN.', 'info')
                    return redirect_to('main.change_pin')

                flash(f'Willkommen zurück, {worker.name}!', 'success')
                
                # SEC-06: Safe Redirect
                next_url = request.args.get('next') or request.form.get('next')
                if next_url and is_safe_url(next_url):
                    return redirect(next_url)
                    
                return redirect_to('main.my_queue')
            else:
                # Log failure to console for admin diagnostics
                current_app.logger.debug("Login FAILED for '%s' - PIN mismatch.", worker.name)
                
                # Increment failed attempts
                worker.failed_login_count += 1
                if worker.failed_login_count >= 5:
                    worker.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15)
                    flash('Zu viele Fehlversuche. Konto für 15 Minuten gesperrt.', 'danger')
                else:
                    flash(f'Falscher PIN. (Versuch {worker.failed_login_count}/5)', 'danger')
                db.session.commit()
                return render_template('login.html', workers=workers)
        else:
            flash('Mitarbeiter nicht gefunden oder inaktiv.', 'danger')
            return render_template('login.html', workers=workers)

    return render_template('login.html', workers=workers)

def _logout_view():
    """Handle worker logout with thorough session clearing."""
    
    # Clear session data
    session.clear()
    session.modified = True
    flash('Erfolgreich ausgeloggt.', 'info')
    
    response = make_response(redirect_to('main.login'))
    
    # SEC-09: Explicitly expire session cookie
    response.set_cookie(current_app.config['SESSION_COOKIE_NAME'], '', expires=0)
    
    # GDPR & Shopfloor Security: Clear all local data on logout
    response.headers['Clear-Site-Data'] = '"cache", "cookies", "storage"'
    return response


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

            # Patch H-1: Fix inconsistent auth state by binding to an admin account
            admin = Worker.query.filter_by(is_admin=True, is_active=True).first()
            if admin:
                # SEC-02: Protect against Session Fixation
                session.clear()
                session['worker_id'] = admin.id
                session['worker_name'] = admin.name
                session['is_admin'] = True
                session.permanent = True

                # Force PIN change for recovered account
                admin.needs_pin_change = True
                db.session.commit()

                flash('Recovery erfolgreich. Bitte ändern Sie jetzt Ihren PIN!', 'success')
                return redirect_to('main.index')
            else:
                flash('Kein aktiver Administrator gefunden, Wiederherstellung fehlgeschlagen.', 'danger')
                return render_template('recover_pin.html')
        flash('Ungültiger oder bereits verwendeter Token.', 'error')

    return render_template('recover_pin.html')


def _change_pin_view():
    """Handle PIN change by the worker themselves."""
    if not session.get('worker_id'):
        ingress = request.headers.get('X-Ingress-Path', '')
        return redirect(f"{ingress}{url_for('main.login')}")

    if request.method == 'POST':
        new_pin = request.form.get('new_pin')
        new_pin_confirm = request.form.get('new_pin_confirm')

        if not new_pin or len(new_pin) < 4:
            flash('Der PIN muss mindestens 4 Ziffern lang sein.', 'warning')
            return render_template('change_pin.html')

        if new_pin != new_pin_confirm:
            flash('Die PINs stimmen nicht überein.', 'warning')
            return render_template('change_pin.html')

        worker = db.session.get(Worker, session['worker_id'])
        if worker:
            # SEC-01: Explicitly use pbkdf2:sha256
            worker.pin_hash = generate_password_hash(new_pin, method='pbkdf2:sha256', salt_length=16)
            worker.needs_pin_change = False
            db.session.commit()
            flash('PIN erfolgreich geändert.', 'success')
            return redirect_to('main.index')

    return render_template('change_pin.html')


def register_routes(bp):
    """Register auth routes."""
    bp.add_url_rule('/login', 'login', view_func=_login_view, methods=['GET', 'POST'])
    bp.add_url_rule('/logout', 'logout', view_func=_logout_view, methods=['POST'])
    bp.add_url_rule('/setup', 'setup', view_func=_setup_view, methods=['GET', 'POST'])
    bp.add_url_rule('/recover_pin', 'recover_pin', view_func=_recover_pin_view, methods=['GET', 'POST'])
    bp.add_url_rule('/change-pin', 'change_pin', view_func=_change_pin_view, methods=['GET', 'POST'])
