"""
Authentication routes.

Handles admin authentication and session management.
"""
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import (
    render_template, request, redirect, url_for,
    flash, session
)
from werkzeug.security import check_password_hash
from models import SystemSettings


def _is_safe_redirect(target: str) -> bool:
    """Return True only if target stays on the same host."""
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ('http', 'https') and ref.netloc == test.netloc


def admin_required(f):
    """Decorate to require admin login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Bitte zuerst einloggen.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def login():
    """Handle admin login."""
    if request.method == 'POST':
        pin = request.form.get('pin')
        pin_hash = SystemSettings.get_setting('admin_pin_hash')

        # Fallback (should be seeded)
        if not pin_hash:
            flash('Systemfehler: PIN-Hash nicht gefunden.', 'error')
            return render_template('login.html')

        if check_password_hash(pin_hash, pin):
            session['is_admin'] = True
            flash('Erfolgreich eingeloggt.', 'success')
            raw_next = request.args.get('next') or request.form.get('next')
            next_url = raw_next if (raw_next and _is_safe_redirect(raw_next)) else None
            return redirect(next_url or url_for('main.index'))

        flash('Falscher PIN.', 'error')

    return render_template('login.html')


def logout():
    """Handle admin logout."""
    session.pop('is_admin', None)
    flash('Erfolgreich ausgeloggt.', 'info')
    return redirect(url_for('main.index'))


def register_routes(bp):
    """Register auth routes."""
    bp.add_url_rule('/login', view_func=login, methods=['GET', 'POST'])
    bp.add_url_rule('/logout', view_func=logout)
