'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const deptModal = document.getElementById('deptModal');
  const deptBody = document.getElementById('deptModalBody');
  const posModal = document.getElementById('posModal');
  const posBody = document.getElementById('posModalBody');

  function loadModal(modalEl, bodyEl, url) {
    if (!modalEl || !bodyEl) return;
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    bodyEl.innerHTML = '<div class="text-center py-4 text-muted">Загрузка…</div>';
    modal.show();
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function (html) { bodyEl.innerHTML = html; bindPosButtons(); })
      .catch(function () { bodyEl.innerHTML = '<div class="alert alert-danger">Ошибка</div>'; });
  }

  function bindPosButtons() {
    document.querySelectorAll('.struct-open-pos').forEach(function (btn) {
      btn.addEventListener('click', function () {
        loadModal(posModal, posBody, btn.getAttribute('data-modal-url'));
      });
    });
  }

  document.querySelectorAll('.struct-open-dept, .struct-open-dept-edit').forEach(function (btn) {
    btn.addEventListener('click', function () {
      loadModal(deptModal, deptBody, btn.getAttribute('data-modal-url'));
    });
  });

  const auto = document.querySelector('[data-auto-open-dept]');
  if (auto) loadModal(deptModal, deptBody, auto.getAttribute('data-modal-url'));
});
