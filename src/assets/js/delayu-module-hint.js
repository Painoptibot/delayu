'use strict';

document.addEventListener('DOMContentLoaded', function () {
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
