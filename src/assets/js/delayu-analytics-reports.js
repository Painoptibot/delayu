'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var modalEl = document.getElementById('reportModal');
  var bodyEl = document.getElementById('reportModalBody');
  if (!modalEl || !bodyEl) return;
  var modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  document.querySelectorAll('.report-open').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.getAttribute('data-modal-url');
      bodyEl.innerHTML = '<div class="text-center py-4 text-muted">Загрузка…</div>';
      modal.show();
      fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
        .then(function (h) { bodyEl.innerHTML = h; })
        .catch(function () { bodyEl.innerHTML = '<div class="alert alert-danger">Ошибка</div>'; });
    });
  });
});
