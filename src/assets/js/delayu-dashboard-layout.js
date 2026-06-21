'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var widgets = window.DELAYU_LAYOUT;
  if (!widgets || !widgets.length) return;

  var allowed = {};
  widgets.forEach(function (w) {
    allowed[w.id] = w.col || 12;
  });

  document.querySelectorAll('[data-widget]').forEach(function (el) {
    var id = el.getAttribute('data-widget');
    if (!allowed[id]) {
      el.style.display = 'none';
    }
  });

  document.querySelectorAll('.row[data-widget-row]').forEach(function (row) {
    var children = row.querySelectorAll('[data-widget]');
    var anyVisible = false;
    children.forEach(function (child) {
      if (child.style.display !== 'none') {
        anyVisible = true;
      }
    });
    if (!anyVisible) {
      row.style.display = 'none';
    }
  });
});
