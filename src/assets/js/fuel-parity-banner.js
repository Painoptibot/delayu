'use strict';

/** Закрываемый баннер чётности госномеров. */
(function () {
  function storageKey(subsystem) {
    return 'fuel-parity-dismiss:' + subsystem;
  }

  function initBanner(banner) {
    var subsystem = banner.getAttribute('data-subsystem');
    var version = banner.getAttribute('data-version');
    if (!subsystem || !version) return;

    if (localStorage.getItem(storageKey(subsystem)) === version) {
      banner.remove();
      return;
    }

    banner.hidden = false;
    var closeBtn = banner.querySelector('[data-fuel-parity-close]');
    if (!closeBtn) return;
    closeBtn.addEventListener('click', function () {
      localStorage.setItem(storageKey(subsystem), version);
      banner.remove();
    });
  }

  function init() {
    document.querySelectorAll('[data-fuel-parity-banner]').forEach(initBanner);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
