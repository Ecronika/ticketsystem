const CACHE_NAME = 'ticketsystem-v1.6.0';
const ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/base_ui.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS);
    })
  );
});

self.addEventListener('fetch', event => {
  // Network-first strategy for API calls and pages
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
