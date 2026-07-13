'use strict';

/** Офлайн: очередь заявок жителя + кэш снимка АЗС (IndexedDB). */
(function () {
  var DB_NAME = 'fuel_citizen_offline_v1';
  var STORE_QUEUE = 'apply_queue';
  var STORE_SNAPSHOT = 'snapshots';

  var PENDING_STATUS_LABEL = 'Не принята · ожидает интернет';
  var PENDING_HINT =
    'Заявка ещё не принята системой. Отправится автоматически после подключения к интернету.';

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE_QUEUE)) {
          db.createObjectStore(STORE_QUEUE, { keyPath: 'local_id' });
        }
        if (!db.objectStoreNames.contains(STORE_SNAPSHOT)) {
          db.createObjectStore(STORE_SNAPSHOT, { keyPath: 'key' });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function uuid() {
    return 'app_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
  }

  function getCsrf() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function formatQueuedAt(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    var pad = function (n) { return String(n).padStart(2, '0'); };
    return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + d.getFullYear()
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  async function saveSnapshot(key, data) {
    var db = await openDb();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE_SNAPSHOT, 'readwrite');
      tx.objectStore(STORE_SNAPSHOT).put({
        key: key,
        data: data,
        saved_at: new Date().toISOString(),
      });
      tx.oncomplete = function () { resolve(true); };
      tx.onerror = function () { reject(tx.error); };
    });
  }

  async function getSnapshot(key) {
    var db = await openDb();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE_SNAPSHOT, 'readonly');
      var req = tx.objectStore(STORE_SNAPSHOT).get(key);
      req.onsuccess = function () { resolve(req.result ? req.result.data : null); };
      req.onerror = function () { reject(req.error); };
    });
  }

  async function enqueueApplication(payload) {
    var db = await openDb();
    var record = {
      local_id: uuid(),
      payload: payload,
      queued_at: new Date().toISOString(),
      status: 'pending',
    };
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE_QUEUE, 'readwrite');
      tx.objectStore(STORE_QUEUE).put(record);
      tx.oncomplete = function () { resolve(record); };
      tx.onerror = function () { reject(tx.error); };
    });
  }

  async function listQueue(status) {
    var db = await openDb();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE_QUEUE, 'readonly');
      var req = tx.objectStore(STORE_QUEUE).getAll();
      req.onsuccess = function () {
        var all = req.result || [];
        resolve(status ? all.filter(function (r) { return r.status === status; }) : all);
      };
      req.onerror = function () { reject(req.error); };
    });
  }

  async function setQueueStatus(localId, status) {
    var db = await openDb();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE_QUEUE, 'readwrite');
      var store = tx.objectStore(STORE_QUEUE);
      var getReq = store.get(localId);
      getReq.onsuccess = function () {
        var row = getReq.result;
        if (!row) { resolve(false); return; }
        row.status = status;
        store.put(row);
      };
      tx.oncomplete = function () { resolve(true); };
      tx.onerror = function () { reject(tx.error); };
    });
  }

  async function pendingCount() {
    var pending = await listQueue('pending');
    return pending.length;
  }

  function renderQueueItemHtml(item) {
    var plate = (item.payload && item.payload.plate) || '—';
    var shortId = (item.local_id || '').slice(-8);
    return ''
      + '<li class="fuel-offline-queue__item">'
      + '<div>'
      + '<div class="fuel-offline-queue__plate">' + plate + '</div>'
      + '<div class="fuel-offline-queue__meta">Черновик …' + shortId + ' · ' + formatQueuedAt(item.queued_at) + '</div>'
      + '</div>'
      + '<span class="fuel-status fuel-status--offline-pending">' + PENDING_STATUS_LABEL + '</span>'
      + '</li>';
  }

  function renderOfflineQueueUI(pending) {
    var panel = document.getElementById('fuel-offline-queue-panel');
    var list = document.getElementById('fuel-offline-queue-list');
    var count = pending ? pending.length : 0;

    if (panel && list) {
      if (count > 0) {
        panel.hidden = false;
        list.innerHTML = pending.map(renderQueueItemHtml).join('');
      } else {
        panel.hidden = true;
        list.innerHTML = '';
      }
    }

    var appsWrap = document.getElementById('fuel-offline-applications-wrap');
    var appsTable = document.getElementById('fuel-offline-applications-table');
    if (appsWrap && appsTable) {
      if (count > 0) {
        appsWrap.hidden = false;
        var rows = pending.map(function (item) {
          var plate = (item.payload && item.payload.plate) || '—';
          var shortId = (item.local_id || '').slice(-8);
          return ''
            + '<tr>'
            + '<td>…' + shortId + '</td>'
            + '<td>' + plate + '</td>'
            + '<td><span class="fuel-status fuel-status--offline-pending">' + PENDING_STATUS_LABEL + '</span></td>'
            + '</tr>';
        }).join('');
        appsTable.innerHTML = '<tr><th>№</th><th>ГРЗ</th><th>Статус</th></tr>' + rows;
      } else {
        appsWrap.hidden = true;
      }
    }
  }

  function updateBadge(count) {
    var el = document.getElementById('fuel-citizen-offline-badge');
    if (!el) return;
    if (count > 0) {
      el.hidden = false;
      el.textContent = count + ' заявок не приняты · '
        + (navigator.onLine ? 'отправятся при стабильной связи' : 'нужен интернет');
    } else {
      el.hidden = true;
    }
  }

  async function refreshOfflineUI() {
    var pending = await listQueue('pending');
    updateBadge(pending.length);
    renderOfflineQueueUI(pending);
    return pending;
  }

  function showApplyOfflineMessage(message, kind) {
    var box = document.getElementById('fuel-offline-apply-msg');
    if (!box) return;
    box.hidden = false;
    var cls = 'fuel-alert ';
    if (kind === 'error') cls += 'fuel-alert--error';
    else if (kind === 'info') cls += 'fuel-alert--info';
    else cls += 'fuel-alert--warn';
    box.className = cls;
    box.textContent = message;
  }

  function collectApplyForm(form) {
    var fd = new FormData(form);
    var preferred = form.querySelector('input[name=preferred_azs]:checked');
    return {
      category: fd.get('category') || '',
      plate: (fd.get('plate') || '').toString().trim(),
      vehicle_make: (fd.get('vehicle_make') || '').toString().trim(),
      inn: (fd.get('inn') || '').toString().trim(),
      org_name: (fd.get('org_name') || '').toString().trim(),
      requested_liters: (fd.get('requested_liters') || '').toString().trim(),
      preferred_azs: preferred ? preferred.value : (fd.get('preferred_azs') || ''),
      agree_rules: form.querySelector('#id_agree_rules') ? form.querySelector('#id_agree_rules').checked : true,
    };
  }

  function validateApplyPayload(payload) {
    if (!payload.category) return 'Выберите категорию';
    if (!payload.plate || payload.plate.length < 8) return 'Укажите госномер';
    if (!payload.agree_rules) return 'Подтвердите согласие с правилами';
    return '';
  }

  function bindApplyForm(syncUrl) {
    var form = document.getElementById('fuel-apply-form');
    if (!form || form.dataset.fuelOfflineBound === '1') return;
    form.dataset.fuelOfflineBound = '1';

    form.addEventListener('submit', function (e) {
      if (navigator.onLine) return;
      e.preventDefault();
      var payload = collectApplyForm(form);
      var err = validateApplyPayload(payload);
      if (err) {
        showApplyOfflineMessage(err, 'error');
        return;
      }
      enqueueApplication(payload).then(function (record) {
        showApplyOfflineMessage(
          'Заявка по ГРЗ ' + payload.plate + ' ещё не принята системой. '
          + 'Она сохранена на устройстве (…' + record.local_id.slice(-8) + ') '
          + 'и будет отправлена только после подключения к интернету.',
          'warn'
        );
        form.reset();
        refreshOfflineUI();
      }).catch(function () {
        showApplyOfflineMessage('Не удалось сохранить заявку на устройстве.', 'error');
      });
    });
  }

  async function syncApplications(syncUrl) {
    if (!navigator.onLine || !syncUrl) return { synced: 0 };
    var pending = await listQueue('pending');
    if (!pending.length) {
      await refreshOfflineUI();
      return { synced: 0 };
    }
    updateBadge(pending.length);
    var res = await fetch(syncUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'same-origin',
      body: JSON.stringify({
        items: pending.map(function (p) {
          return { local_id: p.local_id, payload: p.payload };
        }),
      }),
    });
    if (res.status === 401 || res.status === 403) {
      throw new Error('auth');
    }
    if (!res.ok) throw new Error('sync-failed');
    var data = await res.json();
    var synced = 0;
    for (var i = 0; i < (data.results || []).length; i++) {
      var row = data.results[i];
      if (row.ok) {
        await setQueueStatus(row.local_id, 'synced');
        synced++;
      } else if (row.duplicate) {
        await setQueueStatus(row.local_id, 'synced');
        synced++;
      } else {
        await setQueueStatus(row.local_id, 'failed');
      }
    }
    await refreshOfflineUI();
    if (synced > 0 && typeof window.showFuelOfflineSyncNotice === 'function') {
      window.showFuelOfflineSyncNotice(synced);
    }
    return { synced: synced };
  }

  function cacheAzsFromPage() {
    var el = document.getElementById('fuel-azs-snapshot-json');
    if (!el) return;
    try {
      var data = JSON.parse(el.textContent || '{}');
      if (data.azs_list && data.azs_list.length) {
        saveSnapshot('azs_list', data);
      }
    } catch (e) { /* ignore */ }
  }

  function init(options) {
    options = options || {};
    var syncUrl = options.syncUrl || '';
    bindApplyForm(syncUrl);
    cacheAzsFromPage();

    function refresh() {
      refreshOfflineUI().then(function () {
        if (navigator.onLine && syncUrl) {
          syncApplications(syncUrl).catch(function () {
            refreshOfflineUI();
          });
        }
      });
    }

    refresh();
    window.addEventListener('online', refresh);
    window.addEventListener('offline', function () { refreshOfflineUI(); });
    window.setInterval(refresh, 45000);
  }

  window.FuelCitizenOffline = {
    init: init,
    enqueueApplication: enqueueApplication,
    syncApplications: syncApplications,
    saveSnapshot: saveSnapshot,
    getSnapshot: getSnapshot,
    pendingCount: pendingCount,
    listQueue: listQueue,
    refreshOfflineUI: refreshOfflineUI,
  };
})();
