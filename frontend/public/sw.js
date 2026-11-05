/* Fiyox service worker — makes the app installable and gracefully offline.
 *
 * - Navigations: network-first (so new deploys are picked up), falling back to
 *   the cached page, then a friendly offline page.
 * - Static assets (Next build output, images, fonts): stale-while-revalidate.
 * - API calls (/api/*) are never cached — data must always be live.
 */
const VERSION = "fiyox-v2";
const SYNC_TAG = "fiyox-outbox";
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

/* ---- Background Sync: drain the write outbox even with no tab open ----
 *
 * The app mirrors the auth token and API base into the "meta" store when it
 * queues a write, so the worker can replay queued POSTs here. Writes are
 * idempotent on the server, so a replay that the app also sent is harmless.
 */
function openFiyoxDB() {
  return new Promise((resolve, reject) => {
    // no version → open whatever the app already created; never triggers upgrade
    const r = indexedDB.open("fiyox");
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

function idbReq(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function drainOutbox() {
  let db;
  try { db = await openFiyoxDB(); } catch { return; }
  if (!db.objectStoreNames.contains("outbox") || !db.objectStoreNames.contains("meta")) return;

  const meta = db.transaction("meta", "readonly").objectStore("meta");
  const token = await idbReq(meta.get("token")).catch(() => undefined);
  const apiBase = await idbReq(meta.get("apiBase")).catch(() => undefined);
  if (!apiBase) return;

  const ops = await idbReq(db.transaction("outbox", "readonly").objectStore("outbox").getAll())
    .catch(() => []);
  ops.sort((a, b) => a.createdAt - b.createdAt);

  let synced = 0;
  for (const op of ops) {
    try {
      const headers = { "Content-Type": "application/json", "X-Op-Id": op.id };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${apiBase}${op.path}`, { method: op.method, body: op.body, headers });
      if (res.ok) {
        await idbReq(db.transaction("outbox", "readwrite").objectStore("outbox").delete(op.id));
        synced++;
      } else if (res.status === 401) {
        break;                       // token expired — leave the queue for the app to re-auth
      } else {
        op.tries = (op.tries || 0) + 1;
        const store = db.transaction("outbox", "readwrite").objectStore("outbox");
        if (op.tries >= 5) await idbReq(store.delete(op.id));
        else await idbReq(store.put(op));
      }
    } catch {
      throw new Error("offline");    // reject so the browser retries this sync later
    }
  }

  if (synced > 0) {
    const clients = await self.clients.matchAll({ includeUncontrolled: true });
    for (const c of clients) c.postMessage({ type: "fiyox-synced", synced });
  }
}

self.addEventListener("sync", (event) => {
  if (event.tag === SYNC_TAG) event.waitUntil(drainOutbox());
});

// lets an open tab ask the worker to try a drain (e.g. a manual "Sync now")
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "fiyox-drain") event.waitUntil(drainOutbox());
});
