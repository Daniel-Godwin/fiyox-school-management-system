/* Fiyox service worker — makes the app installable and gracefully offline.
 *
 * - Navigations: network-first (so new deploys are picked up), falling back to
 *   the cached page, then a friendly offline page.
 * - Static assets (Next build output, images, fonts): stale-while-revalidate.
 * - API calls (/api/*) are never cached — data must always be live.
 */
const VERSION = "fiyox-v1";
const PRECACHE = [
  "/offline.html",
  "/icon-192.png",
  "/icon-512.png",
  "/fiyox-logo-white.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // only same-origin
  if (url.pathname.startsWith("/api/")) return;       // never cache data

  // page navigations: network-first with an offline fallback
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("/offline.html")))
    );
    return;
  }

  // static assets: serve from cache, refresh in the background
  const isAsset = url.pathname.startsWith("/_next/") ||
    /\.(png|jpg|jpeg|gif|svg|ico|webp|woff2?|ttf|css|js)$/.test(url.pathname);
  if (isAsset) {
    event.respondWith(
      caches.match(req).then((hit) => {
        const network = fetch(req)
          .then((res) => {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(req, copy));
            return res;
          })
          .catch(() => hit);
        return hit || network;
      })
    );
  }
});
