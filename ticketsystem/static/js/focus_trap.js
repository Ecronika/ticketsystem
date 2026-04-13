// Focus-Trap for <dialog> and modal-like containers.
// Usage:
//   trapFocus(dialogEl);  // on open
//   releaseFocus();       // on close (or let Escape do it)
//
// Exposes window.trapFocus / window.releaseFocus.
// Not a full a11y solution — pairs with <dialog>.showModal() / .close()
// and Bootstrap modals.

(function () {
    'use strict';
    const FOCUSABLE = [
        'a[href]',
        'button:not([disabled])',
        'textarea:not([disabled])',
        'input:not([disabled])',
        'select:not([disabled])',
        '[tabindex]:not([tabindex="-1"])',
    ].join(',');

    let activeContainer = null;
    let previousFocus = null;
    let keydownHandler = null;

    function getFocusable(container) {
        return Array.from(container.querySelectorAll(FOCUSABLE))
            .filter(el => !el.closest('[aria-hidden="true"]') && el.offsetParent !== null);
    }

    window.trapFocus = function (container) {
        if (!container) return;
        releaseFocusInternal();
        activeContainer = container;
        previousFocus = document.activeElement;

        // Priority focus target (e.g. primary action button) wins over first focusable
        const firstPriority = container.querySelector('[data-focus-first]');
        const items = getFocusable(container);
        if (firstPriority && typeof firstPriority.focus === 'function') {
            firstPriority.focus();
        } else if (items.length) {
            items[0].focus();
        }

        keydownHandler = (ev) => {
            if (ev.key === 'Escape') {
                if (typeof container.close === 'function') {
                    container.close();
                }
                releaseFocusInternal();
                return;
            }
            if (ev.key !== 'Tab') return;
            const nodes = getFocusable(container);
            if (!nodes.length) { ev.preventDefault(); return; }
            const first = nodes[0];
            const last = nodes[nodes.length - 1];
            if (ev.shiftKey && document.activeElement === first) {
                ev.preventDefault();
                last.focus();
            } else if (!ev.shiftKey && document.activeElement === last) {
                ev.preventDefault();
                first.focus();
            }
        };
        container.addEventListener('keydown', keydownHandler);
    };

    function releaseFocusInternal() {
        if (activeContainer && keydownHandler) {
            activeContainer.removeEventListener('keydown', keydownHandler);
        }
        if (previousFocus && typeof previousFocus.focus === 'function') {
            try { previousFocus.focus(); } catch (_) { /* element may be gone */ }
        }
        activeContainer = null;
        previousFocus = null;
        keydownHandler = null;
    }

    window.releaseFocus = releaseFocusInternal;
})();
