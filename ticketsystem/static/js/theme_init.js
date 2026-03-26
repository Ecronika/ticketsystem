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
            if (dropdownIcon) {
                dropdownIcon.className = isDark ? 'bi bi-sun me-2' : 'bi bi-moon-stars me-2';
            }
        } catch (e) { console.error('Theme Script Error:', e); }
    };

    function toggleTheme() {
        const current = localStorage.getItem('ui_theme') || 'auto';
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const isCurrentlyDark = current === 'dark' || (current === 'auto' && prefersDark);
        const next = isCurrentlyDark ? 'light' : 'dark';
        localStorage.setItem('ui_theme', next);
        window.applyTheme(next);
    }

    const savedTheme = localStorage.getItem('ui_theme') || 'auto';
    window.applyTheme(savedTheme);

    // H-5 Fix: Wire up both toggle buttons (navbar + avatar dropdown) after DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        ['themeToggle', 'themeToggleDropdown'].forEach(function(id) {
            const btn = document.getElementById(id);
            if (btn) btn.addEventListener('click', toggleTheme);
        });
    });
})();
