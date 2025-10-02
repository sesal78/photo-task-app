const CACHE_NAME = "photo-task-cache-v1";
const urlsToCache = ["/","/manifest.json","/static/icon-192.png","/static/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)));
});

self.addEventListener("fetch", e => {
  e.respondWith(caches.match(e.request).then(resp => resp || fetch(e.request)));
});