'use strict';

const CACHE_SCHEMA_VERSION = '4.27';
const PERIODIC_SYNC_TAG = 'viptrack-watchlist-refresh';
const STATIC_ASSETS = [
    'index.html',
    'sw.js',
    'cesium-frame.html',
    'manifest.json',
    'assets/viptrack-ui.css',
    'assets/logo/VIPTrack_Mark-16x16.png',
    'assets/logo/VIPTrack_Mark-32x32.png',
    'assets/logo/VIPTrack_Mark-48x48.png',
    'assets/logo/VIPTrack_Mark-128x128.png',
    'assets/logo/VIPTrack_Mark-192x192.png',
    'assets/logo/VIPTrack_Mark-512x512.png',
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css',
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js',
    'https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js',
    'https://cdn.jsdelivr.net/npm/dompurify@3.4.13/dist/purify.min.js',
    'assets/silhouettes/aircraft.png',
    'data/aircraft/registrations.json',
    'workers/registration-opfs-worker.js'
];
// Public reference files only: no watchlist identifiers, telemetry, or live
// aircraft queries are sent by the background refresh. Same-origin copies are
// refreshed first; the upstream plane-alert-db mirrors follow as the fallback.
const PERIODIC_REFRESH_ASSETS = [
    'data/military/plane-alert-mil.csv',
    'data/military/plane-alert-gov.csv',
    'data/military/plane-alert-pol.csv',
    'data/military/plane-alert-pia.csv',
    'https://raw.githubusercontent.com/sdr-enthusiasts/plane-alert-db/main/plane-alert-mil.csv',
    'https://raw.githubusercontent.com/sdr-enthusiasts/plane-alert-db/main/plane-alert-gov.csv',
    'https://raw.githubusercontent.com/sdr-enthusiasts/plane-alert-db/main/plane-alert-pol.csv',
    'https://raw.githubusercontent.com/sdr-enthusiasts/plane-alert-db/main/plane-alert-pia.csv'
];
const API_CACHE_TTL_MS = 60000;
const TILE_CACHE_LIMIT = 1000;
const CACHE_PREFIX = 'viptrack-';

function fnv1a(value) {
    let hash = 2166136261;
    for (const char of value) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
    return (hash >>> 0).toString(16).padStart(8, '0');
}

const MANIFEST_HASH = fnv1a(JSON.stringify({ schemaVersion: CACHE_SCHEMA_VERSION, staticAssets: STATIC_ASSETS, periodicAssets: PERIODIC_REFRESH_ASSETS }));
const CACHE_NAME = CACHE_PREFIX + CACHE_SCHEMA_VERSION + '-' + MANIFEST_HASH;
const TILE_CACHE_NAME = CACHE_NAME + '-tiles';

function isReferenceAsset(url) {
    return url.hostname.includes('githubusercontent.com') &&
        (url.pathname.includes('/data/') || url.pathname.includes('/assets/'));
}

function isStaticRequest(url) {
    return STATIC_ASSETS.some(asset => url.href === new URL(asset, self.location.href).href) ||
        url.hostname.includes('cdnjs.cloudflare.com') ||
        url.hostname.includes('cdn.jsdelivr.net') ||
        (url.hostname.includes('githubusercontent.com') && url.pathname.includes('/logo/'));
}

function isTileRequest(url) {
    return url.hostname.includes('tile') || url.hostname.includes('mt0.google') ||
        url.hostname.includes('mt1.google') || url.hostname.includes('mt2.google') ||
        url.hostname.includes('mt3.google') || url.pathname.includes('/tile/');
}

function isApiRequest(url, request) {
    if (request.method !== 'GET') return false;
    if (url.origin === self.location.origin) return url.pathname.includes('/api/');
    return !isReferenceAsset(url) && !isStaticRequest(url) && !isTileRequest(url);
}

async function cacheWithTimestamp(cache, request, response, headerName) {
    const headers = new Headers(response.headers);
    headers.set(headerName, String(Date.now()));
    ['content-encoding', 'content-length', 'transfer-encoding'].forEach(name => headers.delete(name));
    const body = await response.clone().arrayBuffer();
    await cache.put(request, new Response(body, { status: response.status, statusText: response.statusText, headers }));
}

async function freshApiCache(request) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    if (!cached) return null;
    const cachedAt = Number(cached.headers.get('X-VIPTrack-Cached-At'));
    if (!Number.isFinite(cachedAt) || Date.now() - cachedAt > API_CACHE_TTL_MS) {
        await cache.delete(request);
        return null;
    }
    return cached;
}

async function touchTile(cache, request, response) {
    await cacheWithTimestamp(cache, request, response, 'X-VIPTrack-Tile-Last-Used');
}

async function evictTiles(cache) {
    const requests = await cache.keys();
    if (requests.length <= TILE_CACHE_LIMIT) return;
    const entries = await Promise.all(requests.map(async request => {
        const response = await cache.match(request);
        return { request, lastUsed: Number(response?.headers.get('X-VIPTrack-Tile-Last-Used')) || 0 };
    }));
    entries.sort((a, b) => a.lastUsed - b.lastUsed);
    await Promise.all(entries.slice(0, entries.length - TILE_CACHE_LIMIT).map(entry => cache.delete(entry.request)));
}

async function refreshPeriodicAssets() {
    const cache = await caches.open(CACHE_NAME);
    const results = await Promise.all(PERIODIC_REFRESH_ASSETS.map(async asset => {
        try {
            const request = new Request(asset, { method: 'GET', cache: 'no-cache', credentials: 'omit' });
            const response = await fetch(request);
            if (!response.ok || response.type === 'opaque') return false;
            await cache.put(request, response.clone());
            return true;
        } catch (error) {
            return false;
        }
    }));
    return results.filter(Boolean).length;
}

self.addEventListener('install', event => {
    event.waitUntil((async () => {
        try {
            const cache = await caches.open(CACHE_NAME);
            const sameOriginAssets = STATIC_ASSETS.filter(asset => new URL(asset, self.location.href).origin === self.location.origin);
            await cache.addAll(sameOriginAssets);
            await Promise.all(STATIC_ASSETS.filter(asset => !sameOriginAssets.includes(asset)).map(async asset => {
                try { await cache.add(asset); } catch (error) { /* optional cross-origin asset */ }
            }));
        } catch (error) {
            // A partial/offline install must not make the app unusable.
        }
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(keys
            .filter(key => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME && key !== TILE_CACHE_NAME)
            .map(key => caches.delete(key)));
        await self.clients.claim();
    })());
});

self.addEventListener('periodicsync', event => {
    if (event.tag !== PERIODIC_SYNC_TAG) return;
    event.waitUntil(refreshPeriodicAssets());
});

self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET') return;
    const url = new URL(request.url);

    if (isApiRequest(url, request)) {
        event.respondWith(
            fetch(request).then(response => {
                if (response.ok && response.type !== 'opaque') {
                    event.waitUntil(caches.open(CACHE_NAME).then(cache => cacheWithTimestamp(cache, request, response, 'X-VIPTrack-Cached-At')).catch(() => {}));
                }
                return response;
            }).catch(() => freshApiCache(request).then(cached => cached || Response.error()))
        );
        return;
    }

    if (isReferenceAsset(url)) {
        event.respondWith(
            caches.open(CACHE_NAME).then(cache => cache.match(request)).then(cached => {
                const fetchPromise = fetch(request).then(response => {
                    if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone())).catch(() => {});
                    return response;
                }).catch(() => cached);
                return cached || fetchPromise;
            })
        );
        return;
    }

    if (isStaticRequest(url)) {
        event.respondWith(
            caches.open(CACHE_NAME).then(cache => cache.match(request)).then(cached => {
                if (cached) return cached;
                return fetch(request).then(response => {
                    if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone())).catch(() => {});
                    return response;
                });
            })
        );
        return;
    }

    if (isTileRequest(url)) {
        event.respondWith(
            caches.open(TILE_CACHE_NAME).then(async cache => {
                const cached = await cache.match(request);
                if (cached) {
                    event.waitUntil(touchTile(cache, request, cached).catch(() => {}));
                    return cached;
                }
                const response = await fetch(request);
                if (response.ok && response.type !== 'opaque') {
                    await cacheWithTimestamp(cache, request, response, 'X-VIPTrack-Tile-Last-Used');
                    await evictTiles(cache);
                }
                return response;
            }).catch(() => caches.open(TILE_CACHE_NAME).then(cache => cache.match(request)).then(cached => cached || Response.error()))
        );
        return;
    }

    event.respondWith(
        fetch(request).then(response => {
            if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone())).catch(() => {});
            return response;
        }).catch(() => caches.open(CACHE_NAME).then(cache => cache.match(request)).then(cached => cached || Response.error()))
    );
});
