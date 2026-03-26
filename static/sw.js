/**
 * Control Center Service Worker
 *
 * Caching strategy:
 *   - Static assets (CSS, JS, fonts, icons): cache-first, network fallback
 *   - Navigation (HTML pages): network-first, offline fallback
 *   - HTMX / API requests: network-only (never cache dynamic data)
 *   - Images/media: cache-first, network fallback (capped at 50 entries)
 *
 * Auth-aware: never caches redirects (Authelia forward-auth flow must pass through).
 */

var CACHE_STATIC = 'cc-static-v1';
var CACHE_IMAGES = 'cc-images-v1';
var OFFLINE_URL = '/offline/';

// Pre-cache the offline page on install
self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_STATIC).then(function(cache) {
            return cache.add(OFFLINE_URL);
        })
    );
    self.skipWaiting();
});

// Clean up old caches on activate
self.addEventListener('activate', function(event) {
    var keep = [CACHE_STATIC, CACHE_IMAGES];
    event.waitUntil(
        caches.keys().then(function(names) {
            return Promise.all(
                names.filter(function(n) { return keep.indexOf(n) === -1; })
                     .map(function(n) { return caches.delete(n); })
            );
        }).then(function() { return self.clients.claim(); })
    );
});

self.addEventListener('fetch', function(event) {
    var request = event.request;
    var url = new URL(request.url);

    // Only handle same-origin requests — let cross-origin (Authelia) pass through
    if (url.origin !== self.location.origin) return;

    // Never cache POST/PUT/DELETE
    if (request.method !== 'GET') return;

    // HTMX requests — always network-only (dynamic partial content)
    if (request.headers.get('HX-Request')) return;

    // Navigation requests — network-first with offline fallback
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).then(function(response) {
                // Don't cache redirects (Authelia auth flow) or errors
                if (response.redirected || !response.ok) return response;
                return response;
            }).catch(function() {
                return caches.match(OFFLINE_URL);
            })
        );
        return;
    }

    // Static assets — cache-first
    if (isStaticAsset(url.pathname)) {
        event.respondWith(
            caches.match(request).then(function(cached) {
                if (cached) return cached;
                return fetch(request).then(function(response) {
                    if (!response.ok || response.redirected) return response;
                    var clone = response.clone();
                    caches.open(CACHE_STATIC).then(function(cache) {
                        cache.put(request, clone);
                    });
                    return response;
                });
            })
        );
        return;
    }

    // Images/media — cache-first with size cap
    if (isImageAsset(url.pathname)) {
        event.respondWith(
            caches.match(request).then(function(cached) {
                if (cached) return cached;
                return fetch(request).then(function(response) {
                    if (!response.ok || response.redirected) return response;
                    var clone = response.clone();
                    caches.open(CACHE_IMAGES).then(function(cache) {
                        cache.put(request, clone);
                        trimCache(CACHE_IMAGES, 50);
                    });
                    return response;
                });
            })
        );
        return;
    }

    // Everything else — network-only (API calls, JSON, etc.)
});

function isStaticAsset(path) {
    return /\/static\/.*\.(css|js|woff2?|ttf|eot|ico|json)(\?.*)?$/.test(path);
}

function isImageAsset(path) {
    return /\.(png|jpg|jpeg|gif|svg|webp)(\?.*)?$/.test(path) || /^\/media\//.test(path);
}

function trimCache(name, max) {
    caches.open(name).then(function(cache) {
        cache.keys().then(function(keys) {
            if (keys.length <= max) return;
            // Delete oldest entries (first in list)
            var excess = keys.length - max;
            for (var i = 0; i < excess; i++) {
                cache.delete(keys[i]);
            }
        });
    });
}
