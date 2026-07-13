'use strict';

/** Онлайн-обновление панели оператора «Топливный пропуск». */
(function () {
  var POLL_MS = 20000;

  function fmtTime(iso) {
    if (!iso) return '—';
    try {
      var d = new Date(iso);
      return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return iso;
    }
  }

  function setUpdatedLabel(iso) {
    document.querySelectorAll('[data-fuel-live-updated]').forEach(function (el) {
      el.textContent = 'Обновлено ' + fmtTime(iso);
    });
  }

  function updateStats(stats) {
    if (!stats) return;
    document.querySelectorAll('[data-fuel-live-stats] [data-stat]').forEach(function (el) {
      var key = el.getAttribute('data-stat');
      if (stats[key] !== undefined && stats[key] !== null) {
        el.textContent = stats[key];
      }
    });
  }

  function renderPendingApps(apps) {
    var tbody = document.getElementById('fuel-pending-apps-tbody');
    if (!tbody) return;
    if (!apps || !apps.length) {
      tbody.innerHTML = '<tr data-empty-row><td colspan="5" class="text-muted">Нет заявок на проверке</td></tr>';
      return;
    }
    var html = '';
    apps.forEach(function (a) {
      html +=
        '<tr data-app-id="' + a.id + '">' +
        '<td><a href="/fuel/applications/?highlight=' + a.id + '">' + a.number + '</a></td>' +
        '<td>' + (a.citizen || '') + '</td>' +
        '<td>' + a.plate + '</td>' +
        '<td>' + a.category + '</td>' +
        '<td class="text-muted small">в очереди</td></tr>';
    });
    tbody.innerHTML = html;
  }

  function renderRedeems(redeems) {
    var tbody = document.getElementById('fuel-recent-redeems-tbody');
    if (!tbody) return;
    if (!redeems || !redeems.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-muted">Отпусков пока нет</td></tr>';
      return;
    }
    var html = '';
    redeems.forEach(function (r) {
      html +=
        '<tr><td>' + fmtTime(r.created_at) + '</td>' +
        '<td>' + r.plate + '</td>' +
        '<td>' + r.azs + '</td>' +
        '<td><strong>' + r.liters + '</strong></td>' +
        '<td>' + r.permit + '</td></tr>';
    });
    tbody.innerHTML = html;
  }

  function updateAzsStations(stations) {
    if (!stations) return;
    stations.forEach(function (s) {
      var row = document.querySelector('tr[data-station-id="' + s.id + '"]');
      if (!row) return;
      var stock = row.querySelector('[data-station-stock]');
      var queue = row.querySelector('[data-station-queue]');
      if (stock) {
        stock.innerHTML = s.fuel_stock_summary
          ? '<small>' + s.fuel_stock_summary + '</small>'
          : s.stock_liters + ' л';
      }
      if (queue) queue.textContent = s.queue_minutes + ' мин';
      var accepting = row.querySelector('[data-fuel-accepting-cell]');
      if (accepting) {
        accepting.innerHTML = s.is_accepting_permits
          ? '<span class="text-success">Да</span>'
          : '<span class="text-danger">Стоп</span>';
      }
      var blockedCell = row.querySelector('[data-portal-blocked-cell]');
      if (blockedCell) {
        blockedCell.innerHTML = s.portal_blocked
          ? '<span class="text-danger">Заблокирован</span>'
          : '<span class="text-success">Активен</span>';
        row.classList.toggle('table-warning', !!s.portal_blocked);
      }
    });
  }

  function pollLive(root) {
    var url = root.getAttribute('data-fuel-live-url');
    var mode = root.getAttribute('data-fuel-live-mode') || 'hub';
    if (!url) return;
    fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) return;
        setUpdatedLabel(data.updated_at);
        updateStats(data.stats);
        if (mode === 'hub') {
          renderPendingApps(data.pending_apps);
          renderRedeems(data.recent_redeems);
        }
        if (mode === 'azs' || mode === 'hub') {
          updateAzsStations(data.stations);
        }
        if (mode === 'stats' || mode === 'hub') {
          updateStats(data.stats);
        }
      })
      .catch(function () {
        document.querySelectorAll('[data-fuel-live-dot]').forEach(function (el) {
          el.className = 'badge bg-secondary';
          el.textContent = '● офлайн';
        });
      });
  }

  function init() {
    document.querySelectorAll('[data-fuel-live]').forEach(function (root) {
      pollLive(root);
      setInterval(function () { pollLive(root); }, POLL_MS);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
