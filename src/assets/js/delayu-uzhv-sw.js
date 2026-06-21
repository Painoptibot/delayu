/* Service Worker АИС УЖВ — push и клики по уведомлениям */
'use strict';

self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', function (event) {
  var payload = { title: 'АИС УЖВ', body: '', url: '/uzhv/' };
  if (event.data) {
    try {
      payload = Object.assign(payload, event.data.json());
    } catch (e) {
      payload.body = event.data.text();
    }
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/static/img/favicon/favicon.ico',
      badge: '/static/img/favicon/favicon.ico',
      data: { url: payload.url || '/uzhv/' },
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var target = (event.notification.data && event.notification.data.url) || '/uzhv/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if ('focus' in list[i]) {
          list[i].navigate(target);
          return list[i].focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(target);
      }
    })
  );
});

self.addEventListener('message', function (event) {
  if (!event.data || event.data.type !== 'uzhv-notify') return;
  var p = event.data.payload || {};
  event.waitUntil(
    self.registration.showNotification(p.title || 'АИС УЖВ', {
      body: p.body || '',
      icon: '/static/img/favicon/favicon.ico',
      data: { url: p.url || '/uzhv/' },
    })
  );
});
