/* "Drukuj" button on printable pages — a file, not an inline handler, so CSP stays strict. */
(function () {
  'use strict';
  document.querySelectorAll('[data-print]').forEach(function (button) {
    button.addEventListener('click', function () { window.print(); });
  });
})();
