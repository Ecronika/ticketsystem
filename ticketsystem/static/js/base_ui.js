/* base_ui.js - Global UI Utilities for v1.2.0 Hardening */
(function() {
    // === SHARED INGRESS HELPER ===
    // Reads the Home Assistant ingress prefix from the page. Used by dashboard
    // bulk-delete Undo, session-warning, and any other module needing absolute
    // URLs. Falls back to an empty string so tests/dev-mode still work.
    window.getIngress = function () {
        return document.querySelector('.navbar')?.getAttribute('data-ingress')
            || document.querySelector('[data-ingress]')?.dataset.ingress
            || '';
    };

    // === GLOBAL UI ALERT UTILITY ===
    // Signature: showUiAlert(msg, type = 'danger', opts = {})
    //   opts.undoUrl       — when set, renders a "Rückgängig" button in the toast.
    //                        Clicking POSTs to the URL with CSRF, reloads on success.
    //   opts.undoLabel     — label for the undo button (default 'Rückgängig').
    //   opts.timeout       — auto-dismiss ms (default 6000; 8000 when undoUrl set).
    //   opts.onUndoSuccess — optional callback after successful undo (else reload).
    window.showUiAlert = function (msg, type, opts) {
        const safeTypes = ['danger', 'warning', 'success', 'info', 'primary', 'secondary'];
        const safeType = safeTypes.includes(type) ? type : 'danger';
        const options = opts || {};
        const hasUndo = Boolean(options.undoUrl);
        const timeout = options.timeout || (hasUndo ? 8000 : 6000);

        let container = document.querySelector('.position-fixed.top-0.end-0.p-3.z-toast');
        if (!container) {
            container = document.createElement('div');
            container.className = 'position-fixed top-0 end-0 p-3 z-toast';
            container.setAttribute('aria-live', 'assertive');
            container.setAttribute('aria-atomic', 'true');
            document.body.appendChild(container);
        }
        const id = 'ui-alert-' + Date.now();
        const alertEl = document.createElement('div');
        alertEl.id = id;
        alertEl.className = `alert alert-${safeType} alert-dismissible fade show shadow auto-dismiss-alert`;
        alertEl.setAttribute('role', 'alert');
        alertEl.setAttribute('aria-atomic', 'true');
        alertEl.dataset.timeout = String(timeout);

        const icon = document.createElement('i');
        icon.className = 'bi bi-exclamation-triangle-fill me-2';
        icon.setAttribute('aria-hidden', 'true');
        const msgNode = document.createTextNode(msg);
        alertEl.appendChild(icon);
        alertEl.appendChild(msgNode);

        if (hasUndo) {
            const undoBtn = document.createElement('button');
            undoBtn.type = 'button';
            undoBtn.className = 'btn btn-sm btn-link ms-2 undo-action-btn';
            undoBtn.dataset.undoUrl = options.undoUrl;
            if (options.onUndoSuccess) {
                // Stash callback on the element; the global click handler looks for it.
                undoBtn.__undoSuccessCallback = options.onUndoSuccess;
            }
            undoBtn.textContent = options.undoLabel || 'Rückgängig';
            alertEl.appendChild(undoBtn);
        }

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.setAttribute('data-bs-dismiss', 'alert');
        closeBtn.setAttribute('aria-label', 'Schließen');
        alertEl.appendChild(closeBtn);

        container.appendChild(alertEl);
        const announcer = document.getElementById('ajaxStatusAnnouncer');
        if (announcer) announcer.textContent = msg;

        setTimeout(() => {
            const el = document.getElementById(id);
            if (el) { try { bootstrap.Alert.getOrCreateInstance(el).close(); } catch(e) { el.remove(); } }
        }, timeout);
    };

    // Promise-based Confirm Function
    window.showConfirm = function(title, message, isDanger = true) {
        return new Promise((resolve) => {
            const modalEl = document.getElementById('globalConfirmModal');
            if (!modalEl) { resolve(confirm(message)); return; }
            const titleEl = document.getElementById('globalConfirmTitle');
            const messageEl = document.getElementById('globalConfirmMessage');
            const confirmBtn = document.getElementById('globalConfirmBtn');
            if (titleEl) titleEl.textContent = title || 'Bestätigung';
            if (messageEl) messageEl.textContent = message || 'Möchten Sie diese Aktion wirklich ausführen?';
            if (confirmBtn) confirmBtn.className = isDanger ? 'btn btn-danger px-4 py-2' : 'btn btn-primary px-4 py-2';
            const bsModal = new bootstrap.Modal(modalEl);
            const handleConfirm = () => { bsModal.hide(); cleanup(); resolve(true); };
            const handleCancel = () => { bsModal.hide(); cleanup(); resolve(false); };
            const cleanup = () => {
                confirmBtn?.removeEventListener('click', handleConfirm);
                modalEl.removeEventListener('hidden.bs.modal', handleCancel);
                modalEl.removeEventListener('shown.bs.modal', handleShown);
                if (typeof window.releaseFocus === 'function') window.releaseFocus();
            };
            // Bootstrap manages its own focus on show; run trapFocus after shown
            // so our keydown-based Tab cycling + data-focus-first priority win.
            const handleShown = () => {
                if (typeof window.trapFocus === 'function') window.trapFocus(modalEl);
            };
            confirmBtn?.addEventListener('click', handleConfirm);
            modalEl.addEventListener('hidden.bs.modal', handleCancel);
            modalEl.addEventListener('shown.bs.modal', handleShown);
            bsModal.show();
        });
    };

    // Event Delegation for Form Submissions
    document.addEventListener('submit', async function(e) {
        const form = e.target;
        const submitter = e.submitter;
        const needsConfirm = form.hasAttribute('data-confirm') || (submitter && submitter.hasAttribute('data-confirm'));
        if (needsConfirm) {
            if (!form.checkValidity()) { form.reportValidity(); return; }
            e.preventDefault();
            const message = (submitter && submitter.getAttribute('data-confirm-message')) || form.getAttribute('data-confirm-message') || 'Sind Sie sicher?';
            const title = (submitter && submitter.getAttribute('data-confirm-title')) || form.getAttribute('data-confirm-title') || 'Achtung';
            const isDanger = (submitter && (submitter.classList.contains('btn-danger') || submitter.classList.contains('text-danger'))) || form.querySelector('.btn-danger, .text-danger') !== null;
            const confirmed = await window.showConfirm(title, message, isDanger);
            if (confirmed) {
                form.removeAttribute('data-confirm');
                if (submitter) submitter.removeAttribute('data-confirm');
                if (submitter && (submitter.name || submitter.hasAttribute('formaction'))) {
                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = submitter.name;
                    hiddenInput.value = submitter.value;
                    form.appendChild(hiddenInput);
                    if (submitter.hasAttribute('formaction')) form.action = submitter.getAttribute('formaction');
                }
                form.submit();
            }
        }
    });

    document.addEventListener('DOMContentLoaded', () => {
        // Auto-Dismiss Alerts — honor data-timeout (set by base.html flash
        // rendering and by showUiAlert). Fallback for legacy alerts without
        // data-timeout: 12000ms if the alert contains a link, else 8000ms.
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(alert => {
            let delay;
            if (alert.dataset.timeout) {
                delay = parseInt(alert.dataset.timeout, 10) || 6000;
            } else {
                delay = alert.querySelector('a') ? 12000 : 8000;
            }
            setTimeout(() => {
                if (document.body.contains(alert)) {
                    try { (bootstrap.Alert.getInstance(alert) || new bootstrap.Alert(alert)).close(); } catch(e) { alert.remove(); }
                }
            }, delay);
        });

        // Global Undo-Button delegated handler. Works for server-flashed toasts
        // (base.html renders .undo-action-btn when payload.undo_url is set) and
        // for client-side toasts built by showUiAlert({undoUrl}). Gate against
        // double-registration because base_ui.js may be included more than once
        // in rare template overrides.
        if (!window.__undoHandlerAttached) {
            window.__undoHandlerAttached = true;
            document.addEventListener('click', async (ev) => {
                const btn = ev.target.closest('.undo-action-btn');
                if (!btn) return;
                ev.preventDefault();
                const url = btn.dataset.undoUrl;
                if (!url) return;
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                btn.disabled = true;
                try {
                    const resp = await fetch(url, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrfToken, 'Accept': 'application/json' },
                        credentials: 'same-origin',
                    });
                    if (!resp.ok) throw new Error('HTTP ' + resp.status);
                    const cb = btn.__undoSuccessCallback;
                    window.showUiAlert('Aktion rückgängig gemacht.', 'success');
                    if (typeof cb === 'function') {
                        try { cb(); } catch (_) { /* ignore */ }
                    } else {
                        setTimeout(() => window.location.reload(), 500);
                    }
                } catch (err) {
                    window.showUiAlert('Rückgängig fehlgeschlagen.', 'danger');
                    btn.disabled = false;
                }
            });
        }

        // PIN Toggle Logic (v1.10.3 - CSP Compatible)
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.pin-toggle');
            if (!btn) return;
            
            const targetId = btn.getAttribute('data-target') || 'pin';
            const input = document.getElementById(targetId);
            if (!input) return;
            
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            
            const icon = btn.querySelector('i');
            if (icon) {
                icon.classList.toggle('bi-eye', !isPassword);
                icon.classList.toggle('bi-eye-slash', isPassword);
            }
        });

    });

    // M-03: Session-Timeout-Warnung
    // Session lifetime = 8h (slides on each request). Warn 2 min before expiry after inactivity.
    (function initSessionWarning() {
        if (!document.getElementById('notificationDropdownContainer')) return;
        const SESSION_MS = 8 * 60 * 60 * 1000;
        const WARN_BEFORE_MS = 2 * 60 * 1000;
        const WARN_AT_MS = SESSION_MS - WARN_BEFORE_MS;
        let warnTimer = null;
        let expireTimer = null;
        let warningToastEl = null;

        const getIngress = window.getIngress;

        function getContainer() {
            return document.querySelector('.position-fixed.top-0.end-0.p-3.z-toast') || (function() {
                const c = document.createElement('div');
                c.className = 'position-fixed top-0 end-0 p-3 z-toast';
                document.body.appendChild(c);
                return c;
            })();
        }

        function showWarning() {
            if (warningToastEl && document.body.contains(warningToastEl)) return;
            warningToastEl = document.createElement('div');
            warningToastEl.className = 'alert alert-warning alert-dismissible shadow d-flex align-items-center gap-3';
            warningToastEl.setAttribute('role', 'alert');
            warningToastEl.innerHTML =
                '<i class="bi bi-clock-history fs-5 flex-shrink-0" aria-hidden="true"></i>' +
                '<div class="flex-grow-1">' +
                  '<strong>Sitzung läuft bald ab</strong><br>' +
                  '<small>Sie werden in 2 Minuten automatisch abgemeldet.</small>' +
                '</div>' +
                '<button type="button" id="sessionKeepAliveBtn" class="btn btn-sm btn-warning rounded-pill fw-bold flex-shrink-0">Angemeldet bleiben</button>' +
                '<button type="button" class="btn-close ms-1" data-bs-dismiss="alert" aria-label="Schließen"></button>';
            getContainer().appendChild(warningToastEl);

            document.getElementById('sessionKeepAliveBtn')?.addEventListener('click', function() {
                fetch(getIngress() + '/api/dashboard/summary', { credentials: 'same-origin' })
                    .then(function() {
                        warningToastEl?.remove();
                        warningToastEl = null;
                        resetTimers();
                    }).catch(function() {});
            });
        }

        function resetTimers() {
            clearTimeout(warnTimer);
            clearTimeout(expireTimer);
            warnTimer = setTimeout(showWarning, WARN_AT_MS);
            expireTimer = setTimeout(function() {
                window.location.href = getIngress() + '/logout';
            }, SESSION_MS);
        }

        ['click', 'keydown', 'scroll', 'mousemove', 'touchstart'].forEach(function(evt) {
            document.addEventListener(evt, function() {
                if (warningToastEl && document.body.contains(warningToastEl)) {
                    warningToastEl.remove();
                    warningToastEl = null;
                }
                resetTimers();
            }, { passive: true });
        });

        resetTimers();
    })();

})();
