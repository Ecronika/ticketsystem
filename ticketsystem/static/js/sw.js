const CACHE_NAME = 'ticketsystem-v1.24.0';
// Statische Assets, die für offline-fähigen Erststart vorab gecacht werden.
// In Home-Assistant-Ingress-Setups schlägt der hartkodierte Pfad evtl. fehl —
// deswegen werden zusätzlich im fetch-Handler alle erfolgreich abgerufenen
// /static/-Responses on-the-fly in den Cache geschrieben.
const ASSETS = [
  '/static/css/style.css',
  '/static/js/base_ui.js',
  '/static/js/theme_init.js',
  '/static/js/focus_trap.js',
  '/static/js/form_validation.js',
  '/static/js/shortcuts.js',
  '/static/js/notifications.js',
  '/static/js/help.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      // addAll() bricht ab, wenn auch nur eine URL fehlschlägt (z.B. unter
      // Ingress-Präfix). Einzelnes add() ist fehlertoleranter.
      return Promise.all(ASSETS.map(url => cache.add(url).catch(() => null)));
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

  // Cache-first für statische Assets. Bei Cache-Miss: holen, dann in den
  // Cache schreiben — dadurch füllt sich der Cache auch unter Ingress-Pfaden,
  // wo die addAll-Vorab-Befüllung u.U. nicht greift.
  if (url.pathname.includes('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response && response.ok && response.type === 'basic') {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        });
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
