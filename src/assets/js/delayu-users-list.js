/**
 * M03 — загрузка карточки пользователя в модальное окно.
 */
'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const modalEl = document.getElementById('userCardModal');
  const bodyEl = document.getElementById('userCardModalBody');
  if (!modalEl || !bodyEl) return;

  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  function loadCard(url) {
    bodyEl.innerHTML = '<div class="text-center py-5 text-muted">Загрузка…</div>';
    modal.show();
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        if (!r.ok) throw new Error('load failed');
        return r.text();
      })
      .then(function (html) {
        bodyEl.innerHTML = html;
      })
      .catch(function () {
        bodyEl.innerHTML = '<div class="alert alert-danger">Не удалось загрузить карточку</div>';
      });
  }

  document.querySelectorAll('.user-open-card, .user-open-edit').forEach(function (btn) {
    btn.addEventListener('click', function () {
      loadCard(btn.getAttribute('data-modal-url'));
    });
  });

  const openRow = document.querySelector('[data-auto-open-modal]');
  if (openRow) {
    loadCard(openRow.getAttribute('data-modal-url'));
  }
});
