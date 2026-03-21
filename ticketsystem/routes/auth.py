"""
Authentication routes.

Handles admin authentication and session management.
"""
from functools import wraps
from datetime import datetime, timezone, timedelta
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
        worker_name = (request.form.get('worker_name') or '').strip()
        pin = (request.form.get('pin') or '').strip()

        if not worker_name or not pin:
            flash('Bitte Name und PIN angeben.', 'warning')
            return render_template('login.html', workers=workers)

        # Case-insensitive lookup for better UX
        worker = Worker.query.filter(Worker.name.ilike(worker_name), Worker.is_active == True).first()
        if worker:
            # Check for active lockout
            if worker.locked_until and worker.locked_until > datetime.now(timezone.utc):
                time_diff = worker.locked_until - datetime.now(timezone.utc)
                minutes_left = int(time_diff.total_seconds() // 60) + 1
                flash(f'Konto vorübergehend gesperrt. Bitte in {minutes_left} Min. erneut versuchen.', 'danger')
                return render_template('login.html', workers=workers)

            if check_password_hash(worker.pin_hash, pin):
                # Reset lockout on success
                worker.failed_login_count = 0
                worker.locked_until = None
                db.session.commit()

                session.permanent = True
                session['worker_id'] = worker.id
                session['worker_name'] = worker.name
                session['is_admin'] = (worker.role == 'admin' or worker.is_admin)
                session['role'] = worker.role or ('admin' if worker.is_admin else 'worker')

                if worker.needs_pin_change:
                    flash('Bitte ändern Sie zu Ihrer Sicherheit zuerst Ihren PIN.', 'info')
                    ingress = request.headers.get('X-Ingress-Path', '')
                    return redirect(f"{ingress}{url_for('main.change_pin')}")

                flash(f'Willkommen zurück, {worker.name}!', 'success')
                ingress = request.headers.get('X-Ingress-Path', '')
                return redirect(f"{ingress}{url_for('main.index')}")
            else:
                # Log failure to console for admin diagnostics
                import sys
                print(f"DEBUG: Login FAILED for '{worker.name}' - PIN mismatch.", file=sys.stderr, flush=True)
                
                # Increment failed attempts
                worker.failed_login_count += 1
                if worker.failed_login_count >= 5:
                    worker.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
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
    """Handle worker logout with Clear-Site-Data for shared terminals."""
    from flask import make_response
    session.clear()
    flash('Erfolgreich ausgeloggt.', 'info')
    ingress = request.headers.get('X-Ingress-Path', '')
    response = make_response(redirect(f"{ingress}{url_for('main.index')}"))
    
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
                session['worker_id'] = admin.id
                session['worker_name'] = admin.name
                session['is_admin'] = True
                session.permanent = True

                # Force PIN change for recovered account
                admin.needs_pin_change = True
                db.session.commit()

                flash('Recovery erfolgreich. Bitte ändern Sie jetzt Ihren PIN!', 'success')
                ingress = request.headers.get('X-Ingress-Path', '')
                return redirect(f"{ingress}{url_for('main.index')}")
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
            worker.pin_hash = generate_password_hash(new_pin)
            worker.needs_pin_change = False
            db.session.commit()
            flash('PIN erfolgreich geändert.', 'success')
            ingress = request.headers.get('X-Ingress-Path', '')
            return redirect(f"{ingress}{url_for('main.index')}")

    return render_template('change_pin.html')


def register_routes(bp):
    """Register auth routes."""
    bp.add_url_rule('/login', 'login', view_func=_login_view, methods=['GET', 'POST'])
    bp.add_url_rule('/logout', 'logout', view_func=_logout_view, methods=['POST'])
    bp.add_url_rule('/setup', 'setup', view_func=_setup_view, methods=['GET', 'POST'])
    bp.add_url_rule('/recover_pin', 'recover_pin', view_func=_recover_pin_view, methods=['GET', 'POST'])
    bp.add_url_rule('/change-pin', 'change_pin', view_func=_change_pin_view, methods=['GET', 'POST'])
