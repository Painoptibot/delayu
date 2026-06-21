'use strict';

document.addEventListener('DOMContentLoaded', function () {
  function bindFormModal(modalId, bodyId, triggerSelector) {
    var modalEl = document.getElementById(modalId);
    var bodyEl = document.getElementById(bodyId);
    if (!modalEl || !bodyEl) return;
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    var titleEl = modalEl.querySelector('.modal-title');

    function openForm(url, title) {
      if (titleEl && title) titleEl.textContent = title;
      bodyEl.innerHTML = '<div class="text-center py-4 text-muted">Загрузка…</div>';
      modal.show();
      fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
        .then(function (html) {
          bodyEl.innerHTML = html;
          if (window.delayuInitDatePickers) window.delayuInitDatePickers(bodyEl);
          var form = bodyEl.querySelector('form');
          if (form) bindSubmit(form);
        })
        .catch(function () {
          bodyEl.innerHTML = '<div class="alert alert-danger mb-0">Не удалось загрузить форму</div>';
        });
    }

    function bindSubmit(form) {
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var fd = new FormData(form);
        fetch(form.action, {
          method: 'POST',
          body: fd,
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
          .then(function (r) {
            if (r.ok && r.headers.get('content-type') && r.headers.get('content-type').indexOf('json') >= 0) {
              return r.json().then(function (d) { if (d.ok) return 'reload'; throw new Error(); });
            }
            if (r.ok) return 'reload';
            return r.text().then(function (h) {
              bodyEl.innerHTML = h;
              if (window.delayuInitDatePickers) window.delayuInitDatePickers(bodyEl);
              var f = bodyEl.querySelector('form');
              if (f) bindSubmit(f);
              throw new Error('validation');
            });
          })
          .then(function (action) {
            if (action === 'reload') window.location.reload();
          })
          .catch(function (e) {
            if (e && e.message !== 'validation') {
              bodyEl.insertAdjacentHTML('afterbegin', '<div class="alert alert-danger">Ошибка сохранения</div>');
            }
          });
      });
    }

    document.querySelectorAll(triggerSelector).forEach(function (btn) {
      btn.addEventListener('click', function () {
        openForm(btn.getAttribute('data-form-modal-url'), btn.getAttribute('data-form-modal-title') || 'Форма');
      });
    });
  }

  bindFormModal('recordFormModal', 'recordFormModalBody', '.rec-form-open');
  window.delayuBindFormModal = bindFormModal;
});
