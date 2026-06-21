'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var order = window.DELAYU_CABINET_LAYOUT;
  var root = document.getElementById('cabinetWidgetsRoot');
  if (!order || !order.length || !root) return;

  var allowed = {};
  order.forEach(function (id) {
    allowed[id] = true;
  });

  root.querySelectorAll('[data-cabinet-widget]').forEach(function (el) {
    var id = el.getAttribute('data-cabinet-widget');
    if (!allowed[id]) {
      el.style.display = 'none';
    }
  });

  order.forEach(function (id) {
    var el = root.querySelector('[data-cabinet-widget="' + id + '"]');
    if (el && el.style.display !== 'none') {
      root.appendChild(el);
    }
  });
});
