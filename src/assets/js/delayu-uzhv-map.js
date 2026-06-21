'use strict';

/**
 * Карта УЖВ на API Яндекс.Карт 2.1.
 * points: [{ lat, lng, title, address, color, modal_url, detail_url, badge, layer, case_id }]
 * Координаты: широта lat, долгота lng (как в БД).
 */
(function () {
  var apiLoadPromise = null;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showMapMessage(container, html) {
    container.innerHTML = html;
    container.classList.add('uzhv-yandex-map', 'd-flex', 'align-items-center', 'justify-content-center');
    container.style.minHeight = container.getAttribute('data-height')
      ? container.getAttribute('data-height') + 'px'
      : '220px';
  }

  function ensureYandexApi() {
    if (!window.UZHV_YANDEX_MAPS_API_KEY) {
      return Promise.reject(new Error('no-api-key'));
    }
    if (typeof ymaps !== 'undefined') {
      return new Promise(function (resolve) {
        ymaps.ready(resolve);
      });
    }
    if (apiLoadPromise) {
      return apiLoadPromise;
    }
    apiLoadPromise = new Promise(function (resolve, reject) {
      var script = document.createElement('script');
      script.type = 'text/javascript';
      script.src =
        'https://api-maps.yandex.ru/2.1/?apikey=' +
        encodeURIComponent(window.UZHV_YANDEX_MAPS_API_KEY) +
        '&lang=ru_RU';
      script.onload = function () {
        if (typeof ymaps === 'undefined') {
          reject(new Error('ymaps-missing'));
          return;
        }
        ymaps.ready(resolve);
      };
      script.onerror = function () {
        reject(new Error('script-error'));
      };
      document.head.appendChild(script);
    });
    return apiLoadPromise;
  }

  function balloonHtml(p) {
    var html = '<strong>' + escapeHtml(p.title || '') + '</strong>';
    if (p.address) html += '<br>' + escapeHtml(p.address);
    if (p.badge) html += '<br><span class="badge bg-label-secondary">' + escapeHtml(p.badge) + '</span>';
    if (p.layer) html += '<br><span class="text-muted small">' + escapeHtml(p.layer) + '</span>';
    if (p.modal_url) {
      html +=
        '<br><a href="#" class="uzhv-modal-link" data-modal-url="' +
        escapeHtml(p.modal_url) +
        '" data-modal-title="' +
        escapeHtml(p.title || '') +
        '">Карточка</a>';
    }
    if (p.detail_url) {
      html += ' · <a href="' + escapeHtml(p.detail_url) + '">Подробнее</a>';
    }
    if (p.case_id) {
      html += '<br><a href="/cases/' + p.case_id + '/">Дело #' + p.case_id + '</a>';
    }
    return html;
  }

  function initMap(container, points, options) {
    if (!container) return null;
    options = options || {};
    var height = parseInt(options.height || container.getAttribute('data-height') || '280', 10);
    container.style.height = height + 'px';
    container.style.minHeight = height + 'px';
    container.classList.add('uzhv-yandex-map');
    container.innerHTML = '';

    if (!window.UZHV_YANDEX_MAPS_API_KEY) {
      showMapMessage(
        container,
        '<div class="alert alert-warning mb-0 mx-3 text-center small">' +
          'Укажите <code>YANDEX_MAPS_API_KEY</code> в файле <code>.env</code> ' +
          '(ключ JavaScript API и HTTP Геокодер на developer.tech.yandex.ru).' +
          '</div>'
      );
      return null;
    }

    ensureYandexApi()
      .then(function () {
        if (container._uzhvMap) {
          container._uzhvMap.destroy();
          container._uzhvMap = null;
        }

        var center = options.center || [45.035, 38.975];
        var map = new ymaps.Map(
          container,
          {
            center: center,
            zoom: options.zoom || 12,
            controls: ['zoomControl', 'fullscreenControl', 'geolocationControl'],
          },
          { suppressMapOpenBlock: true }
        );

        var placemarks = [];
        (points || []).forEach(function (p) {
          if (p.lat == null || p.lng == null) return;
          var pm = new ymaps.Placemark(
            [p.lat, p.lng],
            { balloonContent: balloonHtml(p) },
            {
              preset: 'islands#circleIcon',
              iconColor: p.color || '#7367f0',
            }
          );
          placemarks.push(pm);
        });

        if (placemarks.length > 1) {
          var clusterer = new ymaps.Clusterer({
            preset: 'islands#invertedVioletClusterIcons',
            groupByCoordinates: false,
            clusterDisableClickZoom: false,
          });
          clusterer.add(placemarks);
          map.geoObjects.add(clusterer);
          var bounds = clusterer.getBounds();
          if (bounds) {
            map.setBounds(bounds, { checkZoomRange: true, zoomMargin: 40 });
          }
        } else if (placemarks.length === 1) {
          map.geoObjects.add(placemarks[0]);
          map.setCenter(placemarks[0].geometry.getCoordinates(), options.singleZoom || 16);
        }

        container._uzhvMap = map;
        return map;
      })
      .catch(function () {
        showMapMessage(
          container,
          '<div class="alert alert-danger mb-0 mx-3 text-center small">Не удалось загрузить Яндекс.Карты. Проверьте ключ API и доступ к api-maps.yandex.ru.</div>'
        );
      });

    return null;
  }

  window.uzhvInitMap = initMap;

  window.uzhvInitMapsIn = function (root) {
    if (!root) return;
    var els = root.querySelectorAll('[data-uzhv-map]');
    if (!els.length) return;

    ensureYandexApi()
      .then(function () {
        els.forEach(function (el) {
          var points = [];
          var center = null;
          try {
            points = JSON.parse(el.getAttribute('data-points') || '[]');
          } catch (e) {
            points = [];
          }
          try {
            center = JSON.parse(el.getAttribute('data-center') || 'null');
          } catch (e2) {
            center = null;
          }
          initMap(el, points, {
            center: center,
            height: parseInt(el.getAttribute('data-height') || '220', 10),
            zoom: parseInt(el.getAttribute('data-zoom') || '12', 10),
            singleZoom: parseInt(el.getAttribute('data-single-zoom') || '16', 10),
          });
        });
      })
      .catch(function () {
        els.forEach(function (el) {
          showMapMessage(
            el,
            '<div class="alert alert-warning mb-0 mx-2 small text-center">Яндекс.Карты недоступны</div>'
          );
        });
      });
  };
})();
