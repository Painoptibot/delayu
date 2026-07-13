'use strict';

/** Переключение приёма пропусков на АЗС без перезагрузки страницы. */
(function () {
  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function setButtonState(btn, accepting) {
    btn.disabled = false;
    btn.textContent = accepting ? 'Стоп' : 'Пуск';
    btn.classList.remove('btn-outline-danger', 'btn-outline-success', 'btn-danger', 'btn-success');
    if (accepting) {
      btn.classList.add('btn-outline-danger');
    } else {
      btn.classList.add('btn-outline-success');
    }
    btn.dataset.accepting = accepting ? '1' : '0';
  }

  function updateAcceptingCell(row, accepting) {
    if (!row) return;
    var cell = row.querySelector('[data-fuel-accepting-cell]');
    if (!cell) return;
    cell.className = accepting ? 'text-success' : 'text-danger';
    cell.textContent = accepting ? 'Да' : 'Стоп';
  }

  function flashToast(message, ok) {
    var host = document.getElementById('fuel-operator-toast');
    if (!host) {
      host = document.createElement('div');
      host.id = 'fuel-operator-toast';
      host.className = 'position-fixed bottom-0 end-0 p-3';
      host.style.zIndex = '1080';
      document.body.appendChild(host);
    }
    host.innerHTML =
      '<div class="alert alert-' + (ok ? 'success' : 'danger') + ' shadow-sm mb-0 py-2 px-3 small">' +
      message + '</div>';
    setTimeout(function () { host.innerHTML = ''; }, 3200);
  }

  function bindToggleForms() {
    document.querySelectorAll('form[data-fuel-azs-toggle]').forEach(function (form) {
      if (form.dataset.fuelBound) return;
      form.dataset.fuelBound = '1';
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = form.querySelector('button[type=submit]');
        if (!btn || btn.disabled) return;
        btn.disabled = true;
        var row = form.closest('tr');
        var fd = new FormData(form);
        fetch(form.action, {
          method: 'POST',
          body: fd,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            Accept: 'application/json',
          },
          credentials: 'same-origin',
        })
          .then(function (r) {
            if (!r.ok) throw new Error('http-' + r.status);
            return r.json();
          })
          .then(function (data) {
            if (!data.ok) throw new Error(data.error || 'fail');
            setButtonState(btn, data.is_accepting_permits);
            updateAcceptingCell(row, data.is_accepting_permits);
            flashToast(data.message, true);
            document.dispatchEvent(
              new CustomEvent('fuel:azs-toggle', { detail: data })
            );
          })
          .catch(function () {
            btn.disabled = false;
            flashToast('Не удалось переключить приём пропусков', false);
          });
      });
    });
  }

  function bindPortalBlockForms() {
    document.querySelectorAll('form[data-fuel-portal-block]').forEach(function (form) {
      if (form.dataset.fuelBoundBlock) return;
      form.dataset.fuelBoundBlock = '1';
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = form.querySelector('button[type=submit]');
        if (btn) btn.disabled = true;
        var row = form.closest('tr');
        var fd = new FormData(form);
        fetch(form.action, {
          method: 'POST',
          body: fd,
          headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
          credentials: 'same-origin',
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!data.ok) throw new Error('fail');
            if (btn) {
              btn.disabled = false;
              btn.textContent = data.portal_blocked ? 'Разблокировать' : 'Блок';
              btn.classList.toggle('btn-outline-warning', !data.portal_blocked);
              btn.classList.toggle('btn-outline-success', !!data.portal_blocked);
            }
            var cell = row && row.querySelector('[data-portal-blocked-cell]');
            if (cell) {
              cell.innerHTML = data.portal_blocked
                ? '<span class="text-danger">Заблокирован</span>'
                : '<span class="text-success">Активен</span>';
            }
            if (row) row.classList.toggle('table-warning', !!data.portal_blocked);
            flashToast(data.message, true);
          })
          .catch(function () {
            if (btn) btn.disabled = false;
            flashToast('Не удалось изменить доступ', false);
          });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      bindToggleForms();
      bindPortalBlockForms();
      bindBlacklistMasks();
    });
  } else {
    bindToggleForms();
    bindPortalBlockForms();
    bindBlacklistMasks();
  }

  function bindBlacklistMasks() {
    var plate = document.querySelector('form input[name="plate"]');
    if (plate) {
      plate.addEventListener('input', function () {
        var v = plate.value.toUpperCase().replace(/[^АВЕКМНОРСТУХA-Z0-9]/g, '');
        if (v.length > 9) v = v.slice(0, 9);
        plate.value = v;
      });
    }
    var inn = document.querySelector('form input[name="inn"]');
    if (inn) {
      inn.addEventListener('input', function () {
        inn.value = inn.value.replace(/\D/g, '').slice(0, 12);
      });
    }
  }
})();
