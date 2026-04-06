const CACHE_NAME = 'ticketsystem-v1.23.0';
const ASSETS = [
  '/static/css/style.css',
  '/static/js/base_ui.js',
  '/static/js/theme_init.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Cache-first for static assets
  if (url.pathname.includes('/static/')) {
    event.respondWith(
      caches.match(event.request).then(response => {
        return response || fetch(event.request);
      })
    );
  } else {
    // Network-first for everything else
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match(event.request);
      })
    );
  }
});

// ---------------------------------------------------------------------------
// WebPush: show OS-level notification on push event
// ---------------------------------------------------------------------------

self.addEventListener('push', event => {
  let data = { title: 'Ticketsystem', body: 'Neue Benachrichtigung', url: '/' };
  try {
    if (event.data) data = { ...data, ...JSON.parse(event.data.text()) };
  } catch(e) {}

  const options = {
    body: data.body,
    icon: '/static/img/icon-192.png',
    badge: '/static/img/icon-192.png',
    tag: 'ticketsystem-push',
    renotify: true,
    data: { url: data.url },
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (const client of windowClients) {
        if (client.url.includes(url) && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
