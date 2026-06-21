'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const modalEl = document.getElementById('auditModal');
  const bodyEl = document.getElementById('auditModalBody');
  if (!modalEl || !bodyEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  document.querySelectorAll('.audit-open').forEach(function (btn) {
    btn.addEventListener('click', function () {
      bodyEl.innerHTML = '<div class="text-center py-4 text-muted">Загрузка…</div>';
      modal.show();
      fetch(btn.getAttribute('data-modal-url'), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.text(); })
        .then(function (h) { bodyEl.innerHTML = h; });
    });
  });
});
