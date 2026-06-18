const CACHE_NAME = 'familypet-v1';

// Instala o service worker sem pré-cachear nada
self.addEventListener('install', event => {
  self.skipWaiting();
});

// Ativa e limpa caches antigos
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Estratégia: network first, sem cache — garante dados sempre atualizados
self.addEventListener('fetch', event => {
  // Ignora requisições não-GET e extensões do Chrome
  if (event.request.method !== 'GET') return;
  if (event.request.url.startsWith('chrome-extension')) return;

  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match(event.request)
    )
  );
});
