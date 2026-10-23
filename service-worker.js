// Cache only the application shell. Match data and HTML must always use the network.
const CACHE = 'sisu-shell-v1';
const SHELL = ['./manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png', './icons/apple-touch-icon.png', './assets/logo.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate' || /\.(?:json|html)$/.test(url.pathname)) return;
  if (!SHELL.some(path => url.pathname === new URL(path, self.registration.scope).pathname)) return;
  event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request)));
});
