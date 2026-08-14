/* Service worker — Messes en France
 * Cache l'essentiel pour un fonctionnement hors-ligne + chargement rapide.
 * Version manuelle : incrémenter CACHE à chaque changement important. */
const CACHE = "messes-fr-v1";
const CORE = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/data.js",
  "/messes-en-latin.html",
  "/rites-orientaux.html",
  "/a-propos.html",
  "/departements/index.html",
  "/villes/index.html"
];

// Installation : pré-cache du noyau
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(CORE)).then(() => self.skipWaiting())
  );
});

// Activation : purge des anciens caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Stratégie : réseau d'abord (fraîcheur), cache en secours (hors-ligne)
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Ne pas intercepter les requêtes cross-origin (fonts, Google Maps, messes.info)
  if (url.origin !== location.origin) return;
  // Ne pas cacher les données énormes qui changent souvent (data.js est déjà gros :
  // on le sert depuis le réseau, cache en dernier recours hors-ligne)
  if (event.request.mode === "navigate" || event.request.destination === "document") {
    event.respondWith(
      fetch(event.request).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return resp;
      }).catch(() => caches.match(event.request).then((m) => m || caches.match("/index.html")))
    );
    return;
  }
  // Autres ressources même origine : cache d'abord, réseau en secours
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((resp) => {
        if (resp && resp.status === 200) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
        }
        return resp;
      }).catch(() => cached);
    })
  );
});
