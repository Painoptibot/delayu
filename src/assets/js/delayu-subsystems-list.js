'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const modalEl = document.getElementById('subCardModal');
  const bodyEl = document.getElementById('subCardModalBody');
  if (!modalEl || !bodyEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  function load(url) {
    bodyEl.innerHTML = '<div class="text-center py-5 text-muted">Загрузка…</div>';
    modal.show();
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function (h) { bodyEl.innerHTML = h; })
      .catch(function () { bodyEl.innerHTML = '<div class="alert alert-danger">Ошибка загрузки</div>'; });
  }

  document.querySelectorAll('.sub-open, .sub-open-edit').forEach(function (btn) {
    btn.addEventListener('click', function () { load(btn.getAttribute('data-modal-url')); });
  });
  const auto = document.querySelector('[data-auto-open-modal]');
  if (auto) load(auto.getAttribute('data-modal-url'));

  const cloneForm = document.getElementById('subCloneForm');
  document.querySelectorAll('.sub-clone-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      cloneForm.action = btn.getAttribute('data-copy-url');
      document.getElementById('subCloneSource').textContent = 'Источник: ' + btn.getAttribute('data-sub-name');
    });
  });
});
