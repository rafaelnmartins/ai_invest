/* Stockgaide service worker — Phase 1: installable PWA + offline shell.
 * Phase 2 (push notifications) hooks are stubbed at the bottom, commented out,
 * so we can light them up later without restructuring.
 *
 * Bump CACHE_VERSION whenever you change cached assets so clients refresh.
 */
const CACHE_VERSION = "stockgaide-v1";
const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// Install: pre-cache the app shell.
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

// Activate: clean up old caches.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

/* Fetch strategy:
 * - Navigations & same-origin GETs: network-first, fall back to cache (so the
 *   app opens offline but always prefers fresh data when online).
 * - API/dynamic calls (worker endpoints like /alerts, /options-dashboard):
 *   network-only — we never want stale trade data served from cache.
 */
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  const isApiLike =
    url.pathname.startsWith("/alerts") ||
    url.pathname.startsWith("/options-dashboard") ||
    url.pathname.startsWith("/dashboard") ||
    url.pathname.startsWith("/stock/") ||
    url.pathname.startsWith("/analyze") ||
    url.pathname.startsWith("/kimi") ||
    url.pathname.startsWith("/webhook");

  // Never cache dynamic/data endpoints — always go to network.
  if (isApiLike) {
    event.respondWith(fetch(req).catch(() => new Response("", { status: 503 })));
    return;
  }

  // App shell / static: network-first, cache fallback.
  event.respondWith(
    fetch(req)
      .then((res) => {
        // Cache a copy of successful same-origin GETs.
        if (res && res.status === 200 && url.origin === self.location.origin) {
          const copy = res.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/")))
  );
});

/* ──────────────────────────────────────────────────────────────────────────
 * PHASE 2 — PUSH NOTIFICATIONS (stubbed; enable later)
 * When we build push, uncomment and wire these. They're here so the structure
 * is ready and you can see what's coming.
 *
 * self.addEventListener("push", (event) => {
 *   let data = {};
 *   try { data = event.data.json(); } catch { data = { title: "Stockgaide", body: event.data && event.data.text() }; }
 *   const title = data.title || "Stockgaide";
 *   const options = {
 *     body: data.body || "New signal",
 *     icon: "/icons/icon-192.png",
 *     badge: "/icons/icon-192.png",
 *     data: { url: data.url || "/" },
 *     tag: data.tag || "signal",
 *   };
 *   event.waitUntil(self.registration.showNotification(title, options));
 * });
 *
 * self.addEventListener("notificationclick", (event) => {
 *   event.notification.close();
 *   const target = (event.notification.data && event.notification.data.url) || "/";
 *   event.waitUntil(
 *     clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
 *       for (const w of wins) { if (w.url.includes(target) && "focus" in w) return w.focus(); }
 *       return clients.openWindow(target);
 *     })
 *   );
 * });
 * ────────────────────────────────────────────────────────────────────────── */
