'use strict';

/** Глобальный поиск Cmd+K / Ctrl+K (#33). */
document.addEventListener('DOMContentLoaded', function () {
  var modalEl = document.getElementById('delayuGlobalSearchModal');
  if (!modalEl) return;
  var input = modalEl.querySelector('#delayuGlobalSearchInput');
  var resultsEl = modalEl.querySelector('#delayuGlobalSearchResults');
  var searchUrl = modalEl.getAttribute('data-search-url');
  var modal = window.bootstrap && bootstrap.Modal ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;
  var timer = null;
  var items = [];
  var activeIdx = -1;

  function render(list) {
    items = list || [];
    activeIdx = -1;
    if (!resultsEl) return;
    if (!items.length) {
      resultsEl.innerHTML = '<p class="text-muted mb-0 px-2">Ничего не найдено</p>';
      return;
    }
    resultsEl.innerHTML = items
      .map(function (it, idx) {
        return (
          '<a href="' +
          it.url +
          '" class="list-group-item list-group-item-action delayu-search-hit' +
          (idx === activeIdx ? ' active' : '') +
          '" data-idx="' +
          idx +
          '">' +
          '<span class="badge bg-label-secondary me-2">' +
          it.type_label +
          '</span>' +
          it.title +
          '</a>'
        );
      })
      .join('');
  }

  function setActive(idx) {
    if (!items.length) return;
    activeIdx = Math.max(0, Math.min(idx, items.length - 1));
    var links = resultsEl.querySelectorAll('.delayu-search-hit');
    links.forEach(function (el, i) {
      el.classList.toggle('active', i === activeIdx);
    });
    var activeEl = links[activeIdx];
    if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });
  }

  function fetchResults(q) {
    if (!searchUrl || q.length < 2) {
      render([]);
      return;
    }
    fetch(searchUrl + '?q=' + encodeURIComponent(q), { headers: { Accept: 'application/json' } })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        render(data.results || []);
      })
      .catch(function () {
        render([]);
      });
  }

  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      if (modal) {
        modal.show();
        if (input) {
          input.value = '';
          input.focus();
          render([]);
        }
      }
      return;
    }
    if (!modalEl.classList.contains('show')) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(activeIdx + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(activeIdx <= 0 ? 0 : activeIdx - 1);
    } else if (e.key === 'Enter' && activeIdx >= 0 && items[activeIdx]) {
      e.preventDefault();
      window.location.href = items[activeIdx].url;
    }
  });

  if (input) {
    input.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        fetchResults(input.value.trim());
      }, 250);
    });
  }

  modalEl.querySelectorAll('.delayu-search-type').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!input) return;
      var prefix = btn.getAttribute('data-prefix') || '';
      input.value = prefix;
      input.focus();
      fetchResults(prefix);
    });
  });

  if (resultsEl) {
    resultsEl.addEventListener('mousemove', function (e) {
      var hit = e.target.closest('.delayu-search-hit');
      if (hit && hit.dataset.idx) setActive(parseInt(hit.dataset.idx, 10));
    });
  }
});
