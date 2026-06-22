'use strict';

(function () {
  var STORAGE_KEY = 'delayuModuleHintsEnabled';

  function hintsGloballyEnabled() {
    return localStorage.getItem(STORAGE_KEY) !== '0';
  }

  window.delayuModuleHints = {
    STORAGE_KEY: STORAGE_KEY,
    isEnabled: hintsGloballyEnabled,
    setEnabled: function (enabled) {
      localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
      document.body.classList.toggle('delayu-module-hints-disabled', !enabled);
      var el = document.getElementById('delayuModuleHint');
      if (el && !enabled) {
        el.remove();
      }
    },
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (!hintsGloballyEnabled()) {
      document.body.classList.add('delayu-module-hints-disabled');
      var blocked = document.getElementById('delayuModuleHint');
      if (blocked) blocked.remove();
      return;
    }

    var el = document.getElementById('delayuModuleHint');
    if (!el) return;
    var code = el.getAttribute('data-hint-code') || 'default';
    var key = 'delayuHintDismiss:' + code;
    if (sessionStorage.getItem(key) === '1') {
      el.remove();
      return;
    }
    var close = el.querySelector('.delayu-module-hint-close');
    if (close) {
      close.addEventListener('click', function () {
        sessionStorage.setItem(key, '1');
        el.remove();
      });
    }
  });
})();
