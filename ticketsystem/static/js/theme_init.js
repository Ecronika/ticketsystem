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
            const themeIcon = document.getElementById('themeIcon');
            const toggleBtn = document.getElementById('themeToggle');
            if (themeIcon && toggleBtn) {
                if (theme === 'light') {
                    themeIcon.className = 'bi bi-moon-stars';
                    toggleBtn.title = 'Dark Mode aktivieren';
                } else {
                    themeIcon.className = 'bi bi-sun';
                    toggleBtn.title = 'Light Mode aktivieren';
                }
            }
        } catch (e) { console.error('Theme Script Error:', e); }
    };
    const savedTheme = localStorage.getItem('ui_theme') || 'auto';
    window.applyTheme(savedTheme);
})();
