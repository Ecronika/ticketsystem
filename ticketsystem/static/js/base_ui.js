/* base_ui.js - Global UI Utilities for v1.2.0 Hardening */
(function() {
    // === GLOBAL UI ALERT UTILITY ===
    window.showUiAlert = function (msg, type) {
        const safeTypes = ['danger', 'warning', 'success', 'info', 'primary', 'secondary'];
        const safeType = safeTypes.includes(type) ? type : 'danger';
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
        alertEl.className = `alert alert-${safeType} alert-dismissible fade show shadow`;
        alertEl.setAttribute('role', 'alert');
        alertEl.setAttribute('aria-atomic', 'true');
        const icon = document.createElement('i');
        icon.className = 'bi bi-exclamation-triangle-fill me-2';
        icon.setAttribute('aria-hidden', 'true');
        const msgNode = document.createTextNode(msg);
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.setAttribute('data-bs-dismiss', 'alert');
        closeBtn.setAttribute('aria-label', 'Schließen');
        alertEl.appendChild(icon);
        alertEl.appendChild(msgNode);
        alertEl.appendChild(closeBtn);
        container.appendChild(alertEl);
        const announcer = document.getElementById('ajaxStatusAnnouncer');
        if (announcer) announcer.textContent = msg;
        const delay = alertEl.querySelector('a') ? 12000 : 8000;
        setTimeout(() => {
            const el = document.getElementById(id);
            if (el) { try { bootstrap.Alert.getOrCreateInstance(el).close(); } catch(e) { el.remove(); } }
        }, delay);
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
            };
            confirmBtn?.addEventListener('click', handleConfirm);
            modalEl.addEventListener('hidden.bs.modal', handleCancel);
            bsModal.show();
            // P1-4 (v1.6.0): Focus the action button for WCAG 2.4.3
            setTimeout(() => confirmBtn?.focus(), 150);
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
        // Auto-Dismiss Alerts
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(alert => {
            const delay = alert.querySelector('a') ? 12000 : 8000;
            setTimeout(() => {
                if (document.body.contains(alert)) {
                    try { (bootstrap.Alert.getInstance(alert) || new bootstrap.Alert(alert)).close(); } catch(e) { alert.remove(); }
                }
            }, delay);
        });

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
})();
