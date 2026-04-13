// Minimal keyboard-shortcut layer.
// Keys: n (new ticket), / (focus search), ? (help dialog).
// Disabled when a text input has focus.

(function () {
    'use strict';

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

    document.addEventListener('keydown', (ev) => {
        if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
        if (isTypingTarget(document.activeElement)) return;

        if (ev.key === 'n') {
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
        }
    });
})();
