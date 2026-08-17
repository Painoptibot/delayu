/* eslint-disable no-restricted-globals */
'use strict';

var CACHE_NAME = 'fuel-ufo-v1';
var PRECACHE = [
  '/fuel/ufo/app/',
  '/fuel/api/ufo/meta/',
  '/fuel/api/ufo/status/'
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

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;
  var url = request.url;
  if (url.indexOf('/fuel/ufo/') === -1 && url.indexOf('/fuel/api/ufo/') === -1) return;

  event.respondWith(
    fetch(request).then(function (response) {
      if (response && response.ok) {
        caches.open(CACHE_NAME).then(function (cache) { cache.put(request, response.clone()); });
      }
      return response;
    }).catch(function () {
      return caches.match(request).then(function (cached) {
        return cached || caches.match('/fuel/ufo/app/');
      });
    })
  );
});
