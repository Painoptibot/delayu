'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const modalEl = document.getElementById('roleCardModal');
  const bodyEl = document.getElementById('roleCardModalBody');
  if (!modalEl || !bodyEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  function loadCard(url) {
    bodyEl.innerHTML = '<div class="text-center py-5 text-muted">Загрузка…</div>';
    modal.show();
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function (html) { bodyEl.innerHTML = html; })
      .catch(function () { bodyEl.innerHTML = '<div class="alert alert-danger">Ошибка загрузки</div>'; });
  }

  document.querySelectorAll('.role-open-card, .role-open-edit').forEach(function (btn) {
    btn.addEventListener('click', function () { loadCard(btn.getAttribute('data-modal-url')); });
  });

  const auto = document.querySelector('[data-auto-open-modal]');
  if (auto) loadCard(auto.getAttribute('data-modal-url'));

  const copyForm = document.getElementById('roleCopyForm');
  document.querySelectorAll('.role-copy-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      copyForm.action = btn.getAttribute('data-copy-url');
      document.getElementById('roleCopySource').textContent = 'Источник: ' + btn.getAttribute('data-role-name');
    });
  });
});
