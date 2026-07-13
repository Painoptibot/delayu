'use strict';

/** Офлайн-очередь отпусков на АЗС (IndexedDB, UI-3). */
(function () {
  var DB_NAME = 'fuel_azs_offline_v1';
  var STORE = 'redeem_queue';

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'local_id' });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function uuid() {
    return 'q_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
  }

  function getCsrf() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function parseQrOffline(payload) {
    try {
      var data = JSON.parse(payload);
      if (!data.plate || !data.until) return null;
      if (new Date(data.until) < new Date()) {
        return { expired: true, plate: data.plate };
      }
      return {
        ok: true,
        plate: data.plate,
        permit_number: data.num || '',
        permit_id: data.pid || null,
        max_liters: data.rem || data.max,
      };
    } catch (e) {
      return null;
    }
  }

  async function enqueue(item) {
    var db = await openDb();
    var record = {
      local_id: uuid(),
      qr_payload: item.qr_payload || '',
      permit_id: item.permit_id || null,
      liters: item.liters,
      operator_note: item.operator_note || '',
      plate: item.plate || '',
      queued_at: new Date().toISOString(),
      status: 'pending',
    };
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(record);
      tx.oncomplete = function () { resolve(record); };
      tx.onerror = function () { reject(tx.error); };
    });
  }

  async function listByStatus(status) {
    var db = await openDb();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE, 'readonly');
      var req = tx.objectStore(STORE).getAll();
      req.onsuccess = function () {
        var all = req.result || [];
        resolve(status ? all.filter(function (r) { return r.status === status; }) : all);
      };
      req.onerror = function () { reject(req.error); };
    });
  }

  async function setStatus(localId, status) {
    var db = await openDb();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE, 'readwrite');
      var store = tx.objectStore(STORE);
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
    var pending = await listByStatus('pending');
    return pending.length;
  }

  function updateBadge(count) {
    var el = document.getElementById('fuel-offline-badge');
    if (!el) return;
    if (count > 0) {
      el.hidden = false;
      el.textContent = 'Офлайн-очередь: ' + count + ' · ' + (navigator.onLine ? 'синхронизация…' : 'нет сети');
    } else {
      el.hidden = true;
    }
  }

  async function sync(syncUrl) {
    if (!navigator.onLine || !syncUrl) return { synced: 0 };
    var pending = await listByStatus('pending');
    if (!pending.length) {
      updateBadge(0);
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
          return {
            local_id: p.local_id,
            qr_payload: p.qr_payload,
            permit_id: p.permit_id,
            liters: p.liters,
            operator_note: p.operator_note,
          };
        }),
      }),
    });
    if (!res.ok) throw new Error('sync-failed');
    var data = await res.json();
    var synced = 0;
    for (var i = 0; i < (data.results || []).length; i++) {
      var row = data.results[i];
      if (row.ok) {
        await setStatus(row.local_id, 'synced');
        synced++;
      } else {
        await setStatus(row.local_id, 'failed');
      }
    }
    var left = await pendingCount();
    updateBadge(left);
    return { synced: synced, failed: (data.results || []).length - synced };
  }

  function init(options) {
    options = options || {};
    var syncUrl = options.syncUrl;
    function refresh() {
      pendingCount().then(updateBadge);
      if (navigator.onLine) {
        sync(syncUrl).catch(function () { pendingCount().then(updateBadge); });
      }
    }
    refresh();
    window.addEventListener('online', refresh);
    setInterval(refresh, 30000);
  }

  window.FuelAzsOffline = {
    enqueue: enqueue,
    sync: sync,
    init: init,
    parseQrOffline: parseQrOffline,
    pendingCount: pendingCount,
  };
})();
