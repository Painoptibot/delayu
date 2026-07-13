'use strict';

(function () {
  var STALE_MINUTES = 30;
  var AUTO_REFRESH_MS = 60000;
  var STORAGE_VERSION = 'v2';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseIso(value) {
    if (!value) return null;
    var date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatDisplay(date) {
    if (!date) return 'Дата обновления неизвестна';
    var pad = function (n) { return String(n).padStart(2, '0'); };
    return 'Проверено '
      + pad(date.getDate()) + '.' + pad(date.getMonth() + 1) + '.' + date.getFullYear()
      + ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes());
  }

  function minutesAgo(date) {
    if (!date) return null;
    return Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  }

  function portalRoot() {
    return document.body.getAttribute('data-fuel-portal-root') || '';
  }

  function buildApplyUrl(azsId) {
    var root = portalRoot();
    var apply = root + '/apply/?azs=' + azsId;
    if (document.body.getAttribute('data-fuel-is-citizen') === '1') {
      return apply;
    }
    return root + '/login/?next=' + encodeURIComponent(apply);
  }

  function statusBadgeHtml(azs) {
    var labels = {
      ok: ['ok', 'Есть ' + escapeHtml(azs.fuel_grade || 'АИ-95')],
      low: ['warn', 'Мало'],
      busy: ['bad', 'Перегрузка'],
      empty: ['bad', 'Нет бензина'],
    };
    var item = labels[azs.status] || labels.empty;
    return '<span class="fuel-status fuel-status--' + item[0] + '">● ' + item[1] + '</span>';
  }

  function setOnlineState(card, online) {
    var dot = card.querySelector('[data-fuel-status-dot]');
    var text = card.querySelector('[data-fuel-status-text]');
    var action = card.querySelector('[data-fuel-status-action]');
    if (dot) {
      dot.classList.toggle('fuel-footer__dot--online', online);
      dot.classList.toggle('fuel-footer__dot--offline', !online);
    }
    if (text) {
      text.textContent = online ? 'Сервис: онлайн' : 'Сервис: офлайн';
    }
    if (action && !card.classList.contains('fuel-status-card--loading')) {
      action.textContent = online ? 'Обновить' : 'Нет сети';
    }
    card.classList.toggle('fuel-status-card--offline', !online);
  }

  function storageKey() {
    return 'fuel_portal_refreshed:' + STORAGE_VERSION + ':' + portalRoot();
  }

  function storageDataKey() {
    return storageKey() + ':snapshot';
  }

  function saveStoredRefresh(data) {
    if (!data) return;
    try {
      sessionStorage.setItem(
        storageKey(),
        JSON.stringify({
          checked_at: data.checked_at,
          checked_at_display: data.checked_at_display,
        })
      );
      if (data.recommended_azs || data.azs_list) {
        sessionStorage.setItem(storageDataKey(), JSON.stringify(data));
      }
    } catch (e) { /* ignore */ }
  }

  function loadStoredSnapshot() {
    try {
      var raw = sessionStorage.getItem(storageDataKey());
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function markClientFresh(card, data) {
    card.setAttribute('data-fuel-user-refreshed', '1');
    if (data && data.checked_at) {
      card.setAttribute('data-fuel-checked-at', data.checked_at);
    }
    if (data) {
      saveStoredRefresh(data);
    }
    setStaleState(card, false, 0, false);
  }

  function isClientFresh(card) {
    if (card.getAttribute('data-fuel-user-refreshed') === '1') {
      return true;
    }
    try {
      return !!sessionStorage.getItem(storageKey());
    } catch (e) {
      return false;
    }
  }

  function setStaleState(card, stale, staleMinutes, offline) {
    var staleEl = card.querySelector('[data-fuel-status-stale]');
    if (!staleEl) return;
    card.classList.toggle('fuel-status-card--stale', stale && !offline);
    if (!stale || offline) {
      staleEl.hidden = true;
      staleEl.textContent = '';
      return;
    }
    staleEl.hidden = false;
    staleEl.textContent =
      'Данные с АЗС обновлялись более ' + staleMinutes + ' мин. назад и могут быть неактуальны. '
      + 'Подключитесь к интернету и нажмите «Обновить».';
  }

  function applyStatusData(card, data, options) {
    options = options || {};
    var updatedEl = card.querySelector('[data-fuel-status-updated]');
    var checked = parseIso(data.checked_at);
    if (updatedEl && checked) {
      updatedEl.textContent = formatDisplay(checked);
    }
    if (data.checked_at) {
      card.setAttribute('data-fuel-checked-at', data.checked_at);
    }
    if (data.updated_at) {
      card.setAttribute('data-fuel-updated-at', data.updated_at);
    }
    if (options.userRefreshed || isClientFresh(card)) {
      setStaleState(card, false, 0, !navigator.onLine);
      return;
    }
    setStaleState(card, !!data.stale, data.stale_minutes || 0, !navigator.onLine);
  }

  function updateSubtitles(data) {
    document.querySelectorAll('[data-fuel-azs-subtitle]').forEach(function (el) {
      var text = el.textContent || '';
      var base = text.split('· обновлено')[0].split('· обновлено')[0];
      if (text.indexOf('кнопка «Пробки»') !== -1) {
        base = 'Статусы заправок · обновление онлайн';
        if (data.checked_at_display) {
          el.innerHTML = base + ' · обновлено ' + escapeHtml(data.checked_at_display)
            + ' · <strong>кнопка «Пробки»</strong> на карте';
        }
      } else if (data.checked_at_display) {
        el.textContent = 'Статус заправок и очередь · обновление онлайн · обновлено '
          + data.checked_at_display;
      }
    });
  }

  function renderHomeRecommended(container, items) {
    if (!container) return;
    if (!items || !items.length) {
      container.innerHTML = '<p class="fuel-muted">Список АЗС загружается…</p>';
      return;
    }
    container.innerHTML = items.map(function (azs, index) {
      return ''
        + '<a href="' + escapeHtml(buildApplyUrl(azs.id)) + '"'
        + ' class="fuel-azs-item fuel-azs-item--link' + (index === 0 ? ' fuel-azs-item--selected' : '') + '"'
        + ' data-azs-id="' + azs.id + '">'
        + '<h3>' + escapeHtml(azs.name) + '</h3>'
        + '<p>' + statusBadgeHtml(azs) + ' · очередь ~' + azs.queue_minutes + ' мин</p>'
        + '<p class="fuel-muted">' + escapeHtml(azs.address) + '</p>'
        + '<span class="fuel-azs-item__hint">Выбрать для заявки →</span>'
        + '</a>';
    }).join('');
  }

  function renderMapItem(azs, options) {
    options = options || {};
    var routeBtn = '';
    if (azs.latitude && azs.longitude) {
      routeBtn = ''
        + '<button type="button" class="fuel-btn fuel-btn--secondary fuel-route-btn"'
        + ' data-lat="' + azs.latitude + '" data-lng="' + azs.longitude + '"'
        + ' data-title="' + escapeHtml(azs.name) + '"'
        + ' data-address="' + escapeHtml(azs.address) + '">Маршрут</button>';
    }
    var title = options.recommended
      ? '★ ' + escapeHtml(azs.name)
      : escapeHtml(azs.name);
    var meta = options.recommended
      ? statusBadgeHtml(azs) + ' · ~' + azs.queue_minutes + ' мин'
      : 'Очередь ~' + azs.queue_minutes + ' мин · ' + azs.stock_liters + ' л'
        + (azs.is_accepting_permits ? '' : ' · <strong>стоп пропусков</strong>');
    var address = options.recommended
      ? '<p class="fuel-muted fuel-azs-item__map-address">' + escapeHtml(azs.address) + '</p>'
      : '<p class="fuel-muted fuel-azs-item__map-address">' + escapeHtml(azs.district)
        + ' · ' + escapeHtml(azs.address) + '</p>';
    return ''
      + '<div class="fuel-azs-item fuel-azs-item--map fuel-azs-item--actionable'
      + (options.recommended && options.index === 0 ? ' fuel-azs-item--selected' : '') + '"'
      + ' data-apply-url="' + escapeHtml(buildApplyUrl(azs.id)) + '" data-azs-id="' + azs.id + '">'
      + '<div class="fuel-azs-item__content" data-fuel-azs-apply>'
      + '<h3 class="fuel-azs-item__map-title">' + title + '</h3>'
      + '<p class="fuel-azs-item__map-meta">' + meta + '</p>'
      + address
      + '</div>'
      + routeBtn
      + '</div>';
  }

  function renderMapLists(data) {
    var rec = document.querySelector('[data-fuel-azs-recommended]');
    if (rec && data.recommended_azs) {
      rec.innerHTML = data.recommended_azs.map(function (azs, index) {
        return renderMapItem(azs, { recommended: true, index: index });
      }).join('');
    }
    var all = document.querySelector('[data-fuel-azs-all]');
    if (all && data.azs_list) {
      all.innerHTML = data.azs_list.map(function (azs) {
        return renderMapItem(azs, { recommended: false });
      }).join('');
    }
    if (typeof window.initFuelAzsActions === 'function') {
      window.initFuelAzsActions({
        mapContainerId: 'fuel-citizen-map',
        routePanelId: 'fuel-route-panel',
      });
    }
    if (typeof window.initFuelAzsMap === 'function' && data.map_points) {
      window.initFuelAzsMap('fuel-citizen-map', data.map_points, { height: 320, zoom: 12 });
    }
  }

  function applyPortalData(data) {
    updateSubtitles(data);
    renderHomeRecommended(document.querySelector('[data-fuel-azs-recommended]'), data.recommended_azs);
    renderMapLists(data);
  }

  function showSuccess(card) {
    card.classList.add('fuel-status-card--fresh');
    window.setTimeout(function () {
      card.classList.remove('fuel-status-card--fresh');
    }, 2500);
  }

  function refreshCard(card) {
    var offline = !navigator.onLine;
    setOnlineState(card, !offline);
    var checked = parseIso(card.getAttribute('data-fuel-checked-at'));
    var updatedEl = card.querySelector('[data-fuel-status-updated]');
    if (updatedEl && checked) {
      updatedEl.textContent = formatDisplay(checked);
    }
    if (offline) {
      var staleEl = card.querySelector('[data-fuel-status-stale]');
      if (staleEl) {
        staleEl.hidden = false;
        staleEl.textContent =
          'Нет подключения к интернету. Подключитесь к сети и нажмите «Обновить».';
      }
      card.classList.remove('fuel-status-card--stale');
      return;
    }
    if (isClientFresh(card)) {
      setStaleState(card, false, 0, false);
      return;
    }
    var dataUpdated = parseIso(card.getAttribute('data-fuel-updated-at'));
    var mins = minutesAgo(dataUpdated);
    setStaleState(card, mins !== null && mins > STALE_MINUTES, mins || 0, false);
  }

  function fetchPortalData(card, options) {
    options = options || {};
    var apiUrl = card.getAttribute('data-fuel-status-api');
    var action = card.querySelector('[data-fuel-status-action]');
    if (!navigator.onLine) {
      setOnlineState(card, false);
      return Promise.reject(new Error('offline'));
    }
    if (!apiUrl) return Promise.reject(new Error('no-api'));
    if (options.showLoading && action) action.textContent = 'Обновление…';
    if (options.showLoading) card.classList.add('fuel-status-card--loading');
    var url = apiUrl + (apiUrl.indexOf('?') === -1 ? '?' : '&') + 'refresh=1&_=' + Date.now();
    return fetch(url, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('status');
        return res.json();
      })
      .then(function (data) {
        card.classList.remove('fuel-status-card--loading');
        var hasAzs = (data.recommended_azs && data.recommended_azs.length)
          || (data.azs_list && data.azs_list.length);
        if (hasAzs) {
          applyPortalData(data);
        }
        applyStatusData(card, data, { userRefreshed: true });
        markClientFresh(card, data);
        if (options.showLoading) {
          if (action) action.textContent = 'Обновлено';
          showSuccess(card);
          window.setTimeout(function () {
            if (action) action.textContent = 'Обновить';
          }, 2000);
        } else if (action && action.textContent === 'Обновление…') {
          action.textContent = 'Обновить';
        }
        return data;
      })
      .catch(function () {
        card.classList.remove('fuel-status-card--loading');
        if (options.showLoading) {
          if (action) action.textContent = 'Обновить';
          var errEl = card.querySelector('[data-fuel-status-stale]');
          if (errEl) {
            errEl.hidden = false;
            errEl.textContent =
              'Не удалось обновить данные. Проверьте подключение к интернету и попробуйте снова.';
          }
        }
        throw new Error('fetch-failed');
      });
  }

  function handleRefresh(card) {
    var action = card.querySelector('[data-fuel-status-action]');
    if (!navigator.onLine) {
      setOnlineState(card, false);
      var staleEl = card.querySelector('[data-fuel-status-stale]');
      if (staleEl) {
        staleEl.hidden = false;
        staleEl.textContent =
          'Нет подключения к интернету. Подключитесь к сети и нажмите «Обновить».';
      }
      return;
    }
    fetchPortalData(card, { showLoading: true }).catch(function () {});
  }

  function syncStorageFromCard(card) {
    if (card.getAttribute('data-fuel-user-refreshed') !== '1') return;
    var checked = card.getAttribute('data-fuel-checked-at');
    var updatedEl = card.querySelector('[data-fuel-status-updated]');
    if (!checked || !updatedEl) return;
    var display = updatedEl.textContent.replace(/^Проверено\s+/, '');
    saveStoredRefresh({ checked_at: checked, checked_at_display: display });
  }

  function init() {
    var snapshot = loadStoredSnapshot();
    document.querySelectorAll('[data-fuel-portal-status]').forEach(function (card) {
      refreshCard(card);
      syncStorageFromCard(card);
      var btn = card.querySelector('[data-fuel-status-refresh]');
      if (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          handleRefresh(card);
        });
      }
    });

    if (snapshot && (snapshot.recommended_azs || snapshot.azs_list)) {
      var statusCard = document.querySelector('[data-fuel-portal-status]');
      var serverTs = statusCard ? parseIso(statusCard.getAttribute('data-fuel-checked-at')) : null;
      var snapTs = snapshot.checked_at ? parseIso(snapshot.checked_at) : null;
      if (!serverTs || (snapTs && snapTs > serverTs)) {
        applyPortalData(snapshot);
      }
    }

    window.addEventListener('online', function () {
      document.querySelectorAll('[data-fuel-portal-status]').forEach(function (card) {
        setOnlineState(card, true);
        if (isClientFresh(card)) {
          setStaleState(card, false, 0, false);
        } else {
          refreshCard(card);
        }
      });
    });
    window.addEventListener('offline', function () {
      document.querySelectorAll('[data-fuel-portal-status]').forEach(function (card) {
        setOnlineState(card, false);
        var staleEl = card.querySelector('[data-fuel-status-stale]');
        if (staleEl) {
          staleEl.hidden = false;
          staleEl.textContent =
            'Нет подключения к интернету. Подключитесь к сети и нажмите «Обновить».';
        }
      });
    });

    document.querySelectorAll('[data-fuel-portal-status]').forEach(function (card) {
      if (navigator.onLine) {
        window.setTimeout(function () {
          fetchPortalData(card, { showLoading: false }).catch(function () {});
        }, 800);
        window.setInterval(function () {
          if (navigator.onLine && document.visibilityState === 'visible') {
            fetchPortalData(card, { showLoading: false }).catch(function () {});
          }
        }, AUTO_REFRESH_MS);
      }
    });

    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState !== 'visible' || !navigator.onLine) return;
      document.querySelectorAll('[data-fuel-portal-status]').forEach(function (card) {
        fetchPortalData(card, { showLoading: false }).catch(function () {});
      });
    });
  }

  window.fuelPortalApplyRefresh = applyPortalData;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
