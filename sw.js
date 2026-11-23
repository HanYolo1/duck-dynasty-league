// Duck Dynasty FF service worker.
// Network first for the page and league data, so everyone always sees the
// latest sync; if the network is slow (4 s) or down, the last copy saved on
// this device is shown instead. ESPN live-score requests are not touched.
const CACHE = 'ddff-v1';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png', 'icons/favicon-48.png'];
const NETWORK_TIMEOUT_MS = 4000;

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function cacheKey(request) {
  // Data files are fetched with ?t=<timestamp> to skip the HTTP cache; store
  // them without the query so the latest copy replaces the previous one.
  const url = new URL(request.url);
  return url.origin + url.pathname;
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const key = cacheKey(req);
    const network = fetch(req).then(res => {
      if (res.ok) cache.put(key, res.clone());
      return res;
    });
    const cached = await cache.match(key);
    if (!cached) return network;
    // Prefer fresh data, but don't keep a phone with a weak signal waiting.
    const timeout = new Promise(resolve => setTimeout(() => resolve(cached), NETWORK_TIMEOUT_MS));
    return Promise.race([network.catch(() => cached), timeout]);
  })());
});
