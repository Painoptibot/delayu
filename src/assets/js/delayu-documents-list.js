'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const modalEl = document.getElementById('docModal');
  const bodyEl = document.getElementById('docModalBody');
  if (!modalEl || !bodyEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  function load(url) {
    bodyEl.innerHTML = '<div class="text-center py-5 text-muted">Загрузка…</div>';
    modal.show();
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function (h) { bodyEl.innerHTML = h; })
      .catch(function () { bodyEl.innerHTML = '<div class="alert alert-danger">Ошибка</div>'; });
  }

  document.querySelectorAll('.doc-open').forEach(function (btn) {
    btn.addEventListener('click', function () { load(btn.getAttribute('data-modal-url')); });
  });
  const auto = document.querySelector('[data-auto-open]');
  if (auto) load(auto.getAttribute('data-modal-url'));
});
