'use strict';

/** Фильтры реестров УЖВ: debounce-поиск, сохранение параметров в URL. */
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.uzhv-filter-form').forEach(function (form) {
    var searchInput = form.querySelector('input[name="q"]');
    if (searchInput) {
      var timer = null;
      searchInput.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          if (typeof form.requestSubmit === 'function') {
            form.requestSubmit();
          } else {
            form.submit();
          }
        }, 450);
      });
    }
  });
});
