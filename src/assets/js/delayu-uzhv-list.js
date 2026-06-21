'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var modalEl = document.getElementById('uzhvModal');
  var bodyEl = document.getElementById('uzhvModalBody');
  var titleEl = document.getElementById('uzhvModalTitle');
  if (!modalEl || !bodyEl) return;
  var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  var rows = Array.from(document.querySelectorAll('tbody tr[data-modal-url]'));
  var activeIdx = -1;

  function isInteractive(target) {
    return target.closest('a, button, input:not(.uzhv-row-check):not(.uzhv-select-all), select, textarea, label, .form-check, .btn');
  }

  function openIdFromUrl(url) {
    var m = url && url.match(/\/(\d+)\/modal\/?$/);
    return m ? m[1] : null;
  }

  function syncOpenParam(id) {
    try {
      var u = new URL(window.location.href);
      if (id) {
        u.searchParams.set('open', id);
      } else {
        u.searchParams.delete('open');
      }
      window.history.replaceState({}, '', u.toString());
    } catch (e) { /* ignore */ }
  }

  function setActiveRow(idx) {
    rows.forEach(function (row, i) {
      row.classList.toggle('table-active', i === idx);
    });
    activeIdx = idx;
    if (idx >= 0 && rows[idx]) {
      rows[idx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  function load(url, title) {
    if (!url) return;
    if (titleEl && title) titleEl.textContent = title;
    bodyEl.innerHTML = '<div class="text-center py-5 text-muted">Загрузка…</div>';
    modal.show();
    syncOpenParam(openIdFromUrl(url));
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function (h) {
        bodyEl.innerHTML = h;
        if (window.uzhvInitMapsIn) {
          window.uzhvInitMapsIn(bodyEl);
        }
        bodyEl.querySelectorAll('.uzhv-qr-details').forEach(function (el) {
          el.addEventListener('toggle', function () {
            if (!el.open) return;
            bodyEl.querySelectorAll('.uzhv-qr-details[open]').forEach(function (other) {
              if (other !== el) other.open = false;
            });
          });
        });
      })
      .catch(function () {
        bodyEl.innerHTML = '<div class="alert alert-danger mb-0">Ошибка загрузки карточки</div>';
      });
  }

  bodyEl.addEventListener('click', function (e) {
    var link = e.target.closest('.uzhv-modal-link');
    if (!link) return;
    e.preventDefault();
    load(link.getAttribute('data-modal-url'), link.getAttribute('data-modal-title'));
  });

  document.addEventListener('click', function (e) {
    var copyBtn = e.target.closest('[data-uzhv-copy]');
    if (!copyBtn) return;
    var sel = copyBtn.getAttribute('data-uzhv-copy');
    var input = sel ? document.querySelector(sel) : null;
    var text = input ? input.value : copyBtn.getAttribute('data-uzhv-copy-text');
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        copyBtn.classList.add('btn-success');
        setTimeout(function () { copyBtn.classList.remove('btn-success'); }, 1200);
      });
    } else if (input) {
      input.select();
      document.execCommand('copy');
    }
  });

  document.querySelectorAll('.uzhv-open').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var row = btn.closest('tr[data-modal-url]');
      if (row) {
        activeIdx = rows.indexOf(row);
        setActiveRow(activeIdx);
      }
      load(
        btn.getAttribute('data-modal-url'),
        row ? row.getAttribute('data-modal-title') : btn.getAttribute('data-modal-title')
      );
    });
  });

  rows.forEach(function (row, idx) {
    row.classList.add('cursor-pointer');
    row.addEventListener('click', function (e) {
      if (isInteractive(e.target)) return;
      activeIdx = idx;
      setActiveRow(activeIdx);
      load(row.getAttribute('data-modal-url'), row.getAttribute('data-modal-title'));
    });
  });

  modalEl.addEventListener('hidden.bs.modal', function () {
    syncOpenParam(null);
  });

  document.addEventListener('keydown', function (e) {
    if (!rows.length) return;
    var tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (modalEl.classList.contains('show')) {
      if (e.key === 'Escape') return;
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      var next = activeIdx < 0 ? 0 : Math.min(activeIdx + 1, rows.length - 1);
      setActiveRow(next);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      var prev = activeIdx <= 0 ? 0 : activeIdx - 1;
      setActiveRow(prev);
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault();
      var row = rows[activeIdx];
      load(row.getAttribute('data-modal-url'), row.getAttribute('data-modal-title'));
    }
  });

  var auto = document.querySelector('[data-auto-open-modal]');
  if (auto) {
    activeIdx = rows.indexOf(auto);
    if (activeIdx >= 0) setActiveRow(activeIdx);
    load(auto.getAttribute('data-modal-url'), auto.getAttribute('data-modal-title'));
  }
});
