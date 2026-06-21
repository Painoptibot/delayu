'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var bar = document.getElementById('uzhvBulkBar');
  var form = document.getElementById('uzhvBulkForm');
  var idsWrap = document.getElementById('uzhvBulkIds');
  var countEl = document.getElementById('uzhvBulkCount');
  var table = document.querySelector('.uzhv-bulk-table');
  if (!bar || !form || !idsWrap || !table) return;

  var actionSelect = form.querySelector('.uzhv-bulk-action');
  var statusSelect = form.querySelector('.uzhv-bulk-status');
  var rowChecks = table.querySelectorAll('.uzhv-row-check');
  var selectAll = table.querySelector('.uzhv-select-all');

  function selected() {
    return Array.from(rowChecks).filter(function (c) { return c.checked; });
  }

  function syncBar() {
    var sel = selected();
    if (countEl) countEl.textContent = String(sel.length);
    idsWrap.innerHTML = '';
    sel.forEach(function (cb) {
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'ids';
      input.value = cb.value;
      idsWrap.appendChild(input);
    });
    if (sel.length) {
      bar.classList.remove('d-none');
      bar.classList.add('d-flex');
    } else {
      bar.classList.add('d-none');
      bar.classList.remove('d-flex');
    }
  }

  if (actionSelect) {
    actionSelect.addEventListener('change', function () {
      var action = actionSelect.value;
      if (statusSelect) {
        statusSelect.classList.toggle('d-none', action !== 'status');
      }
      var assigneeSelect = form.querySelector('.uzhv-bulk-assignee');
      if (assigneeSelect) {
        assigneeSelect.classList.toggle('d-none', action !== 'assign');
      }
      var meetsSelect = form.querySelector('.uzhv-bulk-meets');
      if (meetsSelect) {
        meetsSelect.classList.toggle('d-none', action !== 'meets_criteria');
      }
      var programSelect = form.querySelector('.uzhv-bulk-program');
      if (programSelect) {
        programSelect.classList.toggle('d-none', action !== 'program');
      }
    });
  }

  rowChecks.forEach(function (cb) {
    cb.addEventListener('click', function (e) { e.stopPropagation(); });
    cb.addEventListener('change', syncBar);
  });

  if (selectAll) {
    selectAll.addEventListener('change', function () {
      rowChecks.forEach(function (cb) { cb.checked = selectAll.checked; });
      syncBar();
    });
  }

  syncBar();
});
