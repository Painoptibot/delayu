'use strict';

/** Дашборд штаба: фильтр районов и автообновление метрик. */
(function () {
  function bindDistrictFilter() {
    var mapId = 'fuel-dashboard-map';
    document.querySelectorAll('[data-fuel-district]').forEach(function (el) {
      el.addEventListener('click', function () {
        var district = el.getAttribute('data-fuel-district') || '';
        document.querySelectorAll('[data-fuel-district]').forEach(function (n) {
          n.classList.remove('active', 'border-primary');
        });
        el.classList.add('active', 'border-primary');
        if (window.filterFuelAzsMap) {
          window.filterFuelAzsMap(mapId, district || null);
        }
      });
    });
  }

  function refreshMapPoints(mapId, points) {
    var container = document.getElementById(mapId);
    if (!container || !window.initFuelAzsMap) return;
    initFuelAzsMap(mapId, points || [], {
      center: container._fuelMapCenter || [44.723, 37.768],
      height: container.style.minHeight ? parseInt(container.style.minHeight, 10) : 380,
      zoom: 12,
    });
  }

  function pollMetrics(apiUrl) {
    if (!apiUrl) return;
    fetch(apiUrl, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) return;
        var map = {
          'metric-avg-queue': data.avg_queue_minutes,
          'metric-empty-azs': data.empty_azs_count,
          'metric-denials': data.denials_today,
          'metric-gap': data.gap_pct + '%',
        };
        Object.keys(map).forEach(function (id) {
          var node = document.getElementById(id);
          if (node) node.textContent = map[id];
        });
        var stamp = document.getElementById('fuel-metrics-updated');
        if (stamp && data.updated_at) {
          var d = new Date(data.updated_at);
          stamp.textContent = 'Обновлено: ' + d.toLocaleString('ru-RU');
        }
        if (data.map_points) {
          refreshMapPoints('fuel-dashboard-map', data.map_points);
        }
      })
      .catch(function () {});
  }

  function init() {
    bindDistrictFilter();
    var root = document.getElementById('fuel-dashboard-root');
    if (!root) return;
    var apiUrl = root.getAttribute('data-metrics-api');
    if (apiUrl) {
      setInterval(function () { pollMetrics(apiUrl); }, 60000);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
