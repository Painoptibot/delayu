'use strict';

/** Карта АЗС — API Яндекс.Карт 2.1 */
(function () {
  var apiLoadPromise = null;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function ensureYandexApi() {
    var key = window.FUEL_YANDEX_MAPS_API_KEY;
    if (!key) return Promise.reject(new Error('no-api-key'));
    if (typeof ymaps !== 'undefined') {
      return new Promise(function (resolve) { ymaps.ready(resolve); });
    }
    if (apiLoadPromise) return apiLoadPromise;
    apiLoadPromise = new Promise(function (resolve, reject) {
      var script = document.createElement('script');
      script.src = 'https://api-maps.yandex.ru/2.1/?apikey=' + encodeURIComponent(key) + '&lang=ru_RU';
      script.onload = function () {
        if (typeof ymaps === 'undefined') reject(new Error('ymaps-missing'));
        else ymaps.ready(resolve);
      };
      script.onerror = function () { reject(new Error('script-error')); };
      document.head.appendChild(script);
    });
    return apiLoadPromise;
  }

  function balloonHtml(p) {
    var html = '<strong>' + escapeHtml(p.title || '') + '</strong>';
    if (p.address) html += '<br>' + escapeHtml(p.address);
    if (p.badge) html += '<br><span style="font-size:12px;color:#64748b">' + escapeHtml(p.badge) + '</span>';
    if (p.apps_submitted !== undefined) {
      html += '<br><span style="font-size:12px">Заявок подано: <b>' + p.apps_submitted + '</b>';
      if (p.apps_redeemed_today !== undefined) {
        html += ' · заправлено сегодня: <b>' + p.apps_redeemed_today + '</b>';
      }
      if (p.apps_remaining !== undefined) {
        html += ' · осталось: <b>' + p.apps_remaining + '</b>';
      }
      html += '</span>';
    }
    if (p.status) html += '<br>' + escapeHtml(p.status);
    if (!p.accepting) html += '<br><span style="color:#dc2626">Новые пропуска не принимаются</span>';
    return html;
  }

  window.initFuelAzsMap = function (containerId, points, options) {
    var container = document.getElementById(containerId);
    if (!container) return;
    options = options || {};
    var height = options.height || 360;
    container.style.height = height + 'px';
    container.style.minHeight = height + 'px';
    container.classList.add('fuel-yandex-map');

    if (!window.FUEL_YANDEX_MAPS_API_KEY) {
      container.innerHTML =
        '<div style="padding:20px;text-align:center;color:#64748b;font-size:13px">' +
        'Карта доступна при наличии <code>YANDEX_MAPS_API_KEY</code> в .env</div>';
      return;
    }

    ensureYandexApi().then(function () {
      if (container._fuelMap) {
        container._fuelMap.destroy();
        container._fuelMap = null;
      }
      var center = options.center || [44.723, 37.768];
      var controls = ['zoomControl', 'geolocationControl'];
      if (options.traffic !== false) {
        controls.push('trafficControl');
      }
      var map = new ymaps.Map(container, {
        center: center,
        zoom: options.zoom || 12,
        controls: controls,
      }, { suppressMapOpenBlock: true });

      var bounds = [];
      var placemarks = [];
      (points || []).forEach(function (p) {
        if (!p.lat || !p.lng) return;
        var coords = [p.lat, p.lng];
        bounds.push(coords);
        var pm = new ymaps.Placemark(coords, {
          balloonContent: balloonHtml(p),
          hintContent: p.title,
        }, {
          preset: 'islands#circleDotIcon',
          iconColor: p.color || '#2563eb',
        });
        pm.properties.set('fuelDistrict', p.district || '');
        map.geoObjects.add(pm);
        placemarks.push(pm);
      });

      container._fuelMap = map;
      container._fuelPlacemarks = placemarks;
      container._fuelAllPoints = points || [];
      container._fuelMapCenter = center;

      if (bounds.length > 1) {
        map.setBounds(ymaps.util.bounds.fromPoints(bounds), { checkZoomRange: true, zoomMargin: 40 });
      } else if (bounds.length === 1) {
        map.setCenter(bounds[0], 14);
      }
    }).catch(function () {
      container.innerHTML = '<div style="padding:20px;text-align:center;color:#dc2626">Не удалось загрузить Яндекс.Карты</div>';
    });
  };

  window.filterFuelAzsMap = function (containerId, district) {
    var container = document.getElementById(containerId);
    if (!container || !container._fuelPlacemarks) return;
    var map = container._fuelMap;
    if (!map) return;
    map.geoObjects.removeAll();
    var bounds = [];
    container._fuelPlacemarks.forEach(function (pm) {
      var d = pm.properties.get('fuelDistrict') || '';
      if (!district || d === district) {
        map.geoObjects.add(pm);
        bounds.push(pm.geometry.getCoordinates());
      }
    });
    if (bounds.length > 1) {
      map.setBounds(ymaps.util.bounds.fromPoints(bounds), { checkZoomRange: true, zoomMargin: 40 });
    } else if (bounds.length === 1) {
      map.setCenter(bounds[0], 14);
    }
  };

  window.buildRouteToAzs = function (containerId, lat, lng, options) {
    options = options || {};
    var container = document.getElementById(containerId);
    var panel = document.getElementById(options.routePanelId || 'fuel-route-panel');
    var titleEl = panel ? panel.querySelector('[data-fuel-route-title]') : null;
    var addressEl = panel ? panel.querySelector('[data-fuel-route-address]') : null;
    var metaEl = panel ? panel.querySelector('[data-fuel-route-meta]') : null;

    function showPanel(message) {
      if (!panel) return;
      panel.hidden = false;
      if (titleEl) titleEl.textContent = options.title || 'Маршрут до АЗС';
      if (addressEl) addressEl.textContent = options.address || '';
      if (metaEl) metaEl.textContent = message || 'Построение маршрута…';
    }

    if (!container || !container._fuelMap || typeof ymaps === 'undefined') {
      showPanel('Карта недоступна');
      return;
    }

    var map = container._fuelMap;
    window.clearFuelRoute(containerId, options.routePanelId);

    showPanel('Определяем ваше местоположение…');

    ymaps.geolocation.get({ provider: 'auto', mapStateAutoApply: false }).then(function (res) {
      var start = res.geoObjects.position;
      var multiRoute = new ymaps.multiRouter.MultiRoute(
        {
          referencePoints: [start, [lat, lng]],
          params: { routingMode: 'auto' },
        },
        {
          boundsAutoApply: true,
          wayPointVisible: false,
          viaPointVisible: false,
        }
      );

      map.geoObjects.add(multiRoute);
      container._fuelRoute = multiRoute;

      multiRoute.model.events.add('requestsuccess', function () {
        var route = multiRoute.getActiveRoute();
        if (!route || !metaEl) return;
        var distance = route.properties.get('distance');
        var duration = route.properties.get('duration');
        var parts = [];
        if (duration && duration.text) parts.push(duration.text);
        if (distance && distance.text) parts.push(distance.text);
        metaEl.textContent = parts.length
          ? 'В пути: ' + parts.join(' · ')
          : 'Маршрут построен на карте';
      });

      multiRoute.model.events.add('requestfail', function () {
        if (metaEl) metaEl.textContent = 'Не удалось построить маршрут. Проверьте геолокацию.';
      });

      if (metaEl) metaEl.textContent = 'Маршрут строится на карте…';
    }).catch(function () {
      map.setCenter([lat, lng], 14);
      showPanel('Геолокация недоступна — на карте показана только точка АЗС.');
    });
  };

  window.clearFuelRoute = function (containerId, routePanelId) {
    var container = document.getElementById(containerId);
    if (container && container._fuelRoute && container._fuelMap) {
      container._fuelMap.geoObjects.remove(container._fuelRoute);
      container._fuelRoute = null;
    }
    var panel = document.getElementById(routePanelId || 'fuel-route-panel');
    if (panel) panel.hidden = true;
  };
})();
