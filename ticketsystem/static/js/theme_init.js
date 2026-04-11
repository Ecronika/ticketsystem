/* theme_init.js - Early theme application to prevent FOUC */
(function() {
    window.applyTheme = function (themeParam) {
        try {
            let theme = themeParam;
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
            const bsTheme = theme === 'hc' ? 'dark' : theme;
            document.documentElement.setAttribute('data-bs-theme', bsTheme);
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: theme }));

            const isDark = theme !== 'light';
            // Update legacy standalone toggle (if present)
            const themeIcon = document.getElementById('themeIcon');
            const toggleBtn = document.getElementById('themeToggle');
            if (themeIcon && toggleBtn) {
                themeIcon.className = isDark ? 'bi bi-sun' : 'bi bi-moon-stars';
                toggleBtn.title = isDark ? 'Light Mode aktivieren' : 'Dark Mode aktivieren';
            }
            // Update avatar dropdown toggle icon
            const dropdownIcon = document.getElementById('themeIconDropdown');
            const dropdownText = document.getElementById('themeTextDropdown');
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
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
            const ingress = document.querySelector('[data-ingress]')?.dataset.ingress || '';
            fetch(ingress + '/api/user/theme', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ theme: theme }),
                keepalive: true,
            }).catch(() => {});
        } catch (e) { /* non-critical */ }
    }

    function toggleTheme() {
        const current = localStorage.getItem('ui_theme') || 'auto';
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const isCurrentlyDark = current === 'dark' || (current === 'auto' && prefersDark);
        const next = isCurrentlyDark ? 'light' : 'dark';
        localStorage.setItem('ui_theme', next);
        window.applyTheme(next);
        persistThemeServer(next);
    }

    // Prefer server-side saved theme (injected as data-saved-theme on <html>)
    const serverTheme = document.documentElement.dataset.savedTheme;
    const savedTheme = serverTheme || localStorage.getItem('ui_theme') || 'auto';
    if (serverTheme) localStorage.setItem('ui_theme', serverTheme);
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
