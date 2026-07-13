'use strict';

(function () {
  function syncMaxField() {
    var channel = document.getElementById('id_notify_channel');
    var wrap = document.getElementById('fuel-max-id-field');
    if (!channel || !wrap) return;
    var show = channel.value === 'max' || channel.value === 'both';
    wrap.hidden = !show;
  }

  function init() {
    var channel = document.getElementById('id_notify_channel');
    if (channel) {
      channel.addEventListener('change', syncMaxField);
      syncMaxField();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
