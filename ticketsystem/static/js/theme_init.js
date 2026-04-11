/* theme_init.js - Early theme application to prevent FOUC */
(function() {
    /* Safe localStorage wrapper — in HA Ingress iframes localStorage may be
       blocked by third-party storage partitioning (SecurityError). Fall back
       to an in-memory store so the toggle still works within the session. */
    var _memStore = {};
    function storageGet(key) {
        try { return localStorage.getItem(key); } catch (e) { return _memStore[key] || null; }
    }
    function storageSet(key, val) {
        try { localStorage.setItem(key, val); } catch (e) { /* ignore */ }
        _memStore[key] = val;
    }

    window.applyTheme = function (themeParam) {
        try {
            var theme = themeParam;
            if (theme === 'auto') {
                if (window.matchMedia('(prefers-contrast: more)').matches) {
                    theme = 'hc';
                } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
                    theme = 'dark';
                } else {
                    theme = 'light';
                }
            }
            document.documentElement.setAttribute('data-theme', theme);
            var bsTheme = theme === 'hc' ? 'dark' : theme;
            document.documentElement.setAttribute('data-bs-theme', bsTheme);
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: theme }));

            var isDark = theme !== 'light';
            // Update legacy standalone toggle (if present)
            var themeIcon = document.getElementById('themeIcon');
            var toggleBtn = document.getElementById('themeToggle');
            if (themeIcon && toggleBtn) {
                themeIcon.className = isDark ? 'bi bi-sun' : 'bi bi-moon-stars';
                toggleBtn.title = isDark ? 'Light Mode aktivieren' : 'Dark Mode aktivieren';
            }
            // Update avatar dropdown toggle icon
            var dropdownIcon = document.getElementById('themeIconDropdown');
            var dropdownText = document.getElementById('themeTextDropdown');
            if (dropdownIcon) {
                dropdownIcon.className = isDark ? 'bi bi-sun me-2' : 'bi bi-moon-stars me-2';
            }
            if (dropdownText) {
                dropdownText.textContent = isDark ? 'Hellmodus' : 'Dunkelmodus';
            }
        } catch (e) { console.error('Theme Script Error:', e); }
    };

    function persistThemeServer(theme) {
        try {
            var csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
            var ingress = document.querySelector('[data-ingress]')?.dataset.ingress || '';
            fetch(ingress + '/api/user/theme', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ theme: theme }),
                keepalive: true,
            }).catch(function() {});
        } catch (e) { /* non-critical */ }
    }

    function toggleTheme() {
        var current = storageGet('ui_theme') || 'auto';
        var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        var isCurrentlyDark = current === 'dark' || (current === 'auto' && prefersDark);
        var next = isCurrentlyDark ? 'light' : 'dark';
        storageSet('ui_theme', next);
        window.applyTheme(next);
        persistThemeServer(next);
    }

    // Prefer server-side saved theme (injected as data-saved-theme on <html>)
    var serverTheme = document.documentElement.dataset.savedTheme;
    var savedTheme = serverTheme || storageGet('ui_theme') || 'auto';
    if (serverTheme) storageSet('ui_theme', serverTheme);
    window.applyTheme(savedTheme);

    // Wire up toggle buttons via event delegation (robust against late DOM ready)
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('#themeToggle, #themeToggleDropdown');
        if (btn) {
            e.preventDefault();
            toggleTheme();
        }
    });
})();
