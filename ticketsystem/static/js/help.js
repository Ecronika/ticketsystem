/**
 * TicketSystem – Kontextsensitive Hilfe
 *
 * Aufgaben:
 * 1. Bootstrap Popovers für alle .help-icon-btn initialisieren
 * 2. Seiten-Hilfe Offcanvas automatisch öffnen (einmalig je Seite)
 * 3. "Nicht mehr anzeigen" pro Seite in localStorage speichern
 */
(function () {
  'use strict';

  const LS_PREFIX = 'ts_help_dismissed_';

  /** Aktuellen Seiten-Schlüssel aus data-page-key lesen */
  function getPageKey() {
    const el = document.getElementById('pageHelpOffcanvas');
    return el ? (el.dataset.pageKey || '') : '';
  }

  /** Wurde die Hilfe für diese Seite bereits weggeklickt? */
  function isHelpDismissed(pageKey) {
    if (!pageKey) return true;
    return localStorage.getItem(LS_PREFIX + pageKey) === '1';
  }

  /** Hilfe für diese Seite dauerhaft ausblenden */
  function dismissHelp(pageKey) {
    if (pageKey) localStorage.setItem(LS_PREFIX + pageKey, '1');
  }

  /** Hilfe für alle Seiten zurücksetzen (kann vom Nutzermenü aufgerufen werden) */
  window.tsResetAllHelp = function () {
    Object.keys(localStorage)
      .filter(function (k) { return k.startsWith(LS_PREFIX); })
      .forEach(function (k) { localStorage.removeItem(k); });
  };

  document.addEventListener('DOMContentLoaded', function () {

    // 1. Popovers initialisieren
    document.querySelectorAll('[data-bs-toggle="popover"]').forEach(function (el) {
      new bootstrap.Popover(el, { container: 'body' });
    });

    // Alle anderen Popovers schließen wenn ein neuer geöffnet wird
    document.addEventListener('click', function (e) {
      if (!e.target.closest('[data-bs-toggle="popover"]')) {
        document.querySelectorAll('[data-bs-toggle="popover"]').forEach(function (el) {
          var pop = bootstrap.Popover.getInstance(el);
          if (pop) pop.hide();
        });
      }
    });

    // 2. Seiten-Hilfe Offcanvas
    var offcanvasEl = document.getElementById('pageHelpOffcanvas');
    if (!offcanvasEl) return;

    var pageKey = getPageKey();
    var offcanvas = new bootstrap.Offcanvas(offcanvasEl);

    // Automatisch öffnen falls noch nicht dismissed
    if (!isHelpDismissed(pageKey)) {
      // Kurze Verzögerung damit die Seite vollständig geladen ist
      setTimeout(function () { offcanvas.show(); }, 600);
    }

    // "Nicht mehr anzeigen"-Button
    var dismissBtn = document.getElementById('dismissHelpBtn');
    if (dismissBtn) {
      dismissBtn.addEventListener('click', function () {
        dismissHelp(pageKey);
      });
    }

    // Hilfe-Button in Navbar
    document.querySelectorAll('[data-open-page-help]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        offcanvas.show();
      });
    });
  });
}());
