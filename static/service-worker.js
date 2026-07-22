const CACHE_NAME = 'familypet-v3';
const OFFLINE_URL = '/offline';

// App shell: assets essenciais, sem hash de cache-busting nem páginas dinâmicas
const PRECACHE_ASSETS = [
  OFFLINE_URL,
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/Design sem nome.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function ehAssetEstatico(url) {
  return url.pathname.startsWith('/static/') &&
         /\.(css|js|png|jpg|jpeg|gif|webp|svg|ico)$/i.test(url.pathname);
}

// Assets estáticos: stale-while-revalidate (serve do cache e atualiza em segundo plano)
function staleWhileRevalidate(event) {
  event.respondWith(
    caches.open(CACHE_NAME).then(cache =>
      cache.match(event.request, { ignoreSearch: true }).then(cached => {
        const fetchPromise = fetch(event.request).then(networkResponse => {
          // Remove a entrada antiga (com query string diferente) antes de gravar a nova,
          // pra não acumular versões antigas do mesmo asset indefinidamente.
          if (cached && cached.url !== event.request.url) {
            cache.delete(cached.url);
          }
          cache.put(event.request, networkResponse.clone());
          return networkResponse;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    )
  );
}

// Navegação (páginas HTML): network-first, com fallback para cache e depois offline.html
function networkFirstNavegacao(event) {
  event.respondWith(
    fetch(event.request)
      .then(networkResponse => {
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, networkResponse.clone()));
        return networkResponse;
      })
      .catch(() =>
        caches.match(event.request).then(cached => cached || caches.match(OFFLINE_URL))
      )
  );
}

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.protocol.startsWith('chrome-extension')) return;

  if (event.request.mode === 'navigate') {
    networkFirstNavegacao(event);
    return;
  }

  if (ehAssetEstatico(url)) {
    staleWhileRevalidate(event);
    return;
  }

  // Demais requisições (ex: chamadas de API/JSON): network-first sem cache
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
