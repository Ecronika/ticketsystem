// Minimal keyboard-shortcut layer.
// Keys: n (new ticket), / (focus search), ? (help dialog),
//       g d / g m / g a (go to dashboard / my queue / approvals).
// Disabled when a text input has focus.

(function () {
    'use strict';

    const GOTO_TIMEOUT_MS = 1500;
    let gotoPending = false;
    let gotoTimer = null;

    function isTypingTarget(el) {
        if (!el) return false;
        const tag = el.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
        if (el.isContentEditable) return true;
        return false;
    }

    function openHelp() {
        const dlg = document.getElementById('shortcutHelpDialog');
        if (!dlg || typeof dlg.showModal !== 'function') return;
        dlg.showModal();
        if (typeof window.trapFocus === 'function') window.trapFocus(dlg);
        dlg.addEventListener('close', () => {
            if (typeof window.releaseFocus === 'function') window.releaseFocus();
        }, { once: true });
    }

    function armGoto() {
        gotoPending = true;
        if (gotoTimer) clearTimeout(gotoTimer);
        gotoTimer = setTimeout(() => { gotoPending = false; }, GOTO_TIMEOUT_MS);
    }

    function resolveGoto(key) {
        gotoPending = false;
        if (gotoTimer) { clearTimeout(gotoTimer); gotoTimer = null; }
        const data = document.body.dataset;
        let url = null;
        if (key === 'd') url = data.gotoDashboardUrl;
        else if (key === 'm') url = data.gotoMyqueueUrl;
        else if (key === 'a') url = data.gotoApprovalsUrl;
        if (url) window.location.href = url;
    }

    document.addEventListener('keydown', (ev) => {
        if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
        if (isTypingTarget(document.activeElement)) return;

        if (gotoPending && (ev.key === 'd' || ev.key === 'm' || ev.key === 'a')) {
            ev.preventDefault();
            resolveGoto(ev.key);
            return;
        }

        if (ev.key === 'g') {
            ev.preventDefault();
            armGoto();
        } else if (ev.key === 'n') {
            if (document.body.dataset.shortcutsWritable !== 'true') return;
            ev.preventDefault();
            const url = document.body.dataset.newTicketUrl;
            if (url) window.location.href = url;
        } else if (ev.key === '/') {
            const search = document.getElementById('dashSearch') || document.getElementById('global-search');
            if (search) {
                ev.preventDefault();
                search.focus();
                if (typeof search.select === 'function') search.select();
            }
        } else if (ev.key === '?') {
            ev.preventDefault();
            openHelp();
        } else if (ev.key === 'Escape' && gotoPending) {
            gotoPending = false;
            if (gotoTimer) { clearTimeout(gotoTimer); gotoTimer = null; }
        }
    });
})();
