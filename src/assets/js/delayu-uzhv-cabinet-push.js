'use strict';

(function () {
  var root = document.getElementById('uzhvCabinetPushRoot');
  if (!root) return;

  var pushUrl = root.getAttribute('data-push-url');
  var testUrl = root.getAttribute('data-test-url');
  var swUrl = root.getAttribute('data-sw-url');
  var vapidKey = root.getAttribute('data-vapid') || '';
  var statusEl = document.getElementById('uzhvPushStatusText');
  var btnOn = document.getElementById('uzhvPushEnableBtn');
  var btnOff = document.getElementById('uzhvPushDisableBtn');
  var btnTest = document.getElementById('uzhvPushTestBtn');

  function getCsrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var raw = window.atob(base64);
    var arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; ++i) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  function setStatus(text, ok) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = 'small ' + (ok ? 'text-success' : 'text-muted');
  }

  function sendSubscription(json) {
    return fetch(pushUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify(json),
    }).then(function (r) { return r.json(); });
  }

  function enablePush() {
    if (!vapidKey) {
      setStatus('VAPID-ключи не настроены на сервере', false);
      return;
    }
    if (!('Notification' in window) || !('serviceWorker' in navigator)) {
      setStatus('Браузер не поддерживает уведомления', false);
      return;
    }
    Notification.requestPermission().then(function (perm) {
      if (perm !== 'granted') {
        setStatus('Разрешение на уведомления не выдано', false);
        return;
      }
      window.localStorage.setItem('uzhvPwaNotify', '1');
      navigator.serviceWorker.register(swUrl, { scope: '/' }).then(function (reg) {
        if (!reg.pushManager) {
          setStatus('PushManager недоступен', false);
          return;
        }
        return reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidKey),
        }).then(function (sub) {
          return sendSubscription(sub.toJSON());
        });
      }).then(function (data) {
        if (data && data.ok) {
          setStatus('Push подключён', true);
          window.location.reload();
        } else {
          setStatus('Не удалось сохранить подписку', false);
        }
      }).catch(function () {
        setStatus('Ошибка подписки Push', false);
      });
    });
  }

  function disablePush() {
    fetch(pushUrl, {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': getCsrf() },
    }).then(function () {
      window.localStorage.removeItem('uzhvPwaNotify');
      setStatus('Push отключён', false);
      window.location.reload();
    });
  }

  function testPush() {
    if (!testUrl) return;
    fetch(testUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': getCsrf() },
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (data && data.push) {
        setStatus('Тестовое push отправлено', true);
      } else if (data && data.ok) {
        setStatus('Тест выполнен (push не доставлен — проверьте VAPID)', false);
      } else {
        setStatus('Тест не удался', false);
      }
    }).catch(function () {
      setStatus('Ошибка теста', false);
    });
  }

  if (btnOn) btnOn.addEventListener('click', enablePush);
  if (btnOff) btnOff.addEventListener('click', disablePush);
  if (btnTest) btnTest.addEventListener('click', testPush);
})();
