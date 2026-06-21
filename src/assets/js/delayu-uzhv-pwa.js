'use strict';

(function () {
  var root = document.getElementById('uzhvPwaRoot') || document.getElementById('uzhvHubRoot');
  if (!root) return;

  var alertsUrl = root.getAttribute('data-uzhv-alerts-url');
  var swUrl = root.getAttribute('data-uzhv-sw-url');
  var pushUrl = root.getAttribute('data-uzhv-push-url');
  var vapidKey = root.getAttribute('data-uzhv-vapid') || '';

  var standalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;
  var notifyEnabled = standalone || window.localStorage.getItem('uzhvPwaNotify') === '1';
  if (!notifyEnabled || !alertsUrl) return;

  var lastKey = 'uzhvPwaLastAlerts';
  var last = parseInt(window.localStorage.getItem(lastKey) || '0', 10);
  var swReg = null;

  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var raw = window.atob(base64);
    var arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; ++i) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  function showAlertNotification(data) {
    var parts = [];
    if (data.overdue_count) parts.push('просрочено: ' + data.overdue_count);
    if (data.unread_notifications) parts.push('непрочитано: ' + data.unread_notifications);
    var body = parts.join(', ') || 'Есть новые события';
    var url = data.hub_url || '/uzhv/?assignee=me';
    if (swReg && swReg.showNotification) {
      swReg.showNotification('АИС УЖВ', { body: body, data: { url: url }, icon: '/static/img/favicon/favicon.ico' });
      return;
    }
    if (swReg && swReg.active) {
      swReg.active.postMessage({ type: 'uzhv-notify', payload: { title: 'АИС УЖВ', body: body, url: url } });
      return;
    }
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('АИС УЖВ', { body: body });
    }
  }

  function subscribePush(reg) {
    if (!pushUrl || !vapidKey || !reg.pushManager) return;
    reg.pushManager.getSubscription().then(function (existing) {
      if (existing) return sendSubscription(existing.toJSON());
      return reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      }).then(function (sub) {
        return sendSubscription(sub.toJSON());
      });
    }).catch(function () {});
  }

  function sendSubscription(json) {
    return fetch(pushUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify(json),
    });
  }

  function getCsrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function poll() {
    fetch(alertsUrl, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var total = (data.overdue_count || 0) + (data.unread_notifications || 0);
        if (total > last) showAlertNotification(data);
        window.localStorage.setItem(lastKey, String(total));
        last = total;
      })
      .catch(function () {});
  }

  function startPolling() {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().finally(poll);
    } else {
      poll();
    }
    window.setInterval(poll, 120000);
  }

  if (swUrl && 'serviceWorker' in navigator) {
    navigator.serviceWorker.register(swUrl, { scope: '/' }).then(function (reg) {
      swReg = reg;
      subscribePush(reg);
      startPolling();
    }).catch(startPolling);
  } else {
    startPolling();
  }
})();
