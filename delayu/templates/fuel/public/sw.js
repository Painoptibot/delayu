/* eslint-disable no-restricted-globals */
'use strict';

var CACHE_NAME = 'fuel-citizen-v2';
var SCOPE = '{{ portal_root|escapejs }}/';
var PRECACHE = [
  SCOPE,
  '{{ static_css|escapejs }}',
  '{{ static_js_status|escapejs }}',
  '{{ static_js_offline|escapejs }}',
  '{{ static_js_parity|escapejs }}',
  '{{ static_js_apply|escapejs }}',
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(PRECACHE).catch(function () {});
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE_NAME; }).map(function (k) { return caches.delete(k); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

function isNavigation(request) {
  return request.mode === 'navigate'
    || (request.method === 'GET' && (request.headers.get('accept') || '').indexOf('text/html') !== -1);
}

function isStatic(request) {
  var url = request.url;
  return url.indexOf('/static/') !== -1;
}

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;

  if (isStatic(request)) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        var network = fetch(request).then(function (response) {
          if (response && response.ok) {
            caches.open(CACHE_NAME).then(function (cache) { cache.put(request, response.clone()); });
          }
          return response;
        });
        return cached || network;
      })
    );
    return;
  }

  if (!isNavigation(request)) return;
  if (request.url.indexOf(SCOPE) === -1) return;

  event.respondWith(
    fetch(request).then(function (response) {
      if (response && response.ok) {
        caches.open(CACHE_NAME).then(function (cache) { cache.put(request, response.clone()); });
      }
      return response;
    }).catch(function () {
      return caches.match(request).then(function (cached) {
        return cached || caches.match(SCOPE);
      });
    })
  );
});
