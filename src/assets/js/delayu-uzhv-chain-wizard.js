'use strict';

document.addEventListener('DOMContentLoaded', function () {
  function syncMode() {
    var mode = document.querySelector('input[name="citizen_mode"]:checked');
    var existing = document.getElementById('chainExisting');
    var fresh = document.getElementById('chainNew');
    if (!mode || !existing || !fresh) return;
    var isExisting = mode.value === 'existing';
    existing.style.display = isExisting ? '' : 'none';
    fresh.style.display = isExisting ? 'none' : '';
    existing.querySelectorAll('input, select, textarea').forEach(function (el) {
      el.disabled = !isExisting;
    });
    fresh.querySelectorAll('input, select, textarea').forEach(function (el) {
      el.disabled = isExisting;
    });
  }

  function syncToggle(checkboxId, panelId) {
    var cb = document.getElementById(checkboxId);
    var panel = document.getElementById(panelId);
    if (!cb || !panel) return;
    function apply() {
      var on = cb.checked;
      panel.style.opacity = on ? '1' : '0.45';
      panel.querySelectorAll('input, select, textarea').forEach(function (el) {
        if (el === cb) return;
        el.disabled = !on;
      });
    }
    cb.addEventListener('change', apply);
    apply();
  }

  document.querySelectorAll('input[name="citizen_mode"]').forEach(function (el) {
    el.addEventListener('change', syncMode);
  });
  syncMode();
  syncToggle('id_create_case', 'chainCaseFields');
  syncToggle('id_create_appeal', 'chainAppealFields');
});
