'use strict';

/** Переключатель подсказок модулей в панели «Настройка интерфейса». */
(function () {
  var STORAGE_KEY = 'delayuModuleHintsEnabled';

  function isEnabled() {
    return localStorage.getItem(STORAGE_KEY) !== '0';
  }

  function setEnabled(enabled) {
    if (window.delayuModuleHints && typeof window.delayuModuleHints.setEnabled === 'function') {
      window.delayuModuleHints.setEnabled(enabled);
    } else {
      localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
      document.body.classList.toggle('delayu-module-hints-disabled', !enabled);
      var el = document.getElementById('delayuModuleHint');
      if (el && !enabled) el.remove();
    }
  }

  function injectSwitch() {
    var customizer = document.getElementById('template-customizer');
    if (!customizer || customizer.querySelector('.template-customizer-moduleHints')) return false;

    var theming = customizer.querySelector('.template-customizer-theming');
    if (!theming) return false;

    var hr = theming.querySelector('hr');
    var wrap = document.createElement('div');
    wrap.className = 'template-customizer-moduleHints';
    wrap.innerHTML =
      '<div class="m-0 px-6 pb-2 w-100 d-flex justify-content-between align-items-center pe-12">' +
      '<span class="form-label mb-0">Подсказки модулей</span>' +
      '<label class="switch mb-0">' +
      '<input type="checkbox" class="template-customizer-module-hints-switch switch-input"' +
      (isEnabled() ? ' checked' : '') +
      ' />' +
      '<span class="switch-toggle-slider"><span class="switch-on"></span><span class="switch-off"></span></span>' +
      '</label>' +
      '</div>' +
      '<p class="px-6 small text-muted pb-4 mb-0">Всплывающие подсказки внизу экрана при входе в раздел модуля.</p>';

    if (hr) {
      theming.insertBefore(wrap, hr);
    } else {
      theming.appendChild(wrap);
    }

    var input = wrap.querySelector('.template-customizer-module-hints-switch');
    if (input) {
      input.addEventListener('change', function () {
        setEnabled(!!input.checked);
      });
    }
    return true;
  }

  function tryInject() {
    if (injectSwitch()) return;
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1;
      if (injectSwitch() || attempts > 40) {
        window.clearInterval(timer);
      }
    }, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInject);
  } else {
    tryInject();
  }
})();
