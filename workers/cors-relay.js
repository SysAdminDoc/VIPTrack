/*
 * VIPTrack CORS relay — deploy this yourself, don't depend on a public one.
 *
 * Every public ADS-B aggregator stopped sending Access-Control-Allow-Origin, so a
 * static browser-only build cannot read a feed directly. The public relays that
 * filled that gap have since closed: corsproxy.io answers 401 without an account
 * key (and its free tier is 10,000 requests/month, which this app's ~20 requests a
 * minute exhausts in under nine hours), and api.allorigins.win has had no commit
 * since 2023-01-11 and returns HTTP 522 under load.
 *
 * Run it on a server with an address of its own: `node workers/node-relay.mjs`
 * (see that file). The hosted build uses one at viptrack-relay.getparkerai.com.
 *
 * A Cloudflare Worker is the wrong host for it. Tested 2026-11-17 from a deployed
 * Worker: opendata.adsb.fi and api.adsb.one answer Worker subrequests with a WAF
 * block page (403), and api.adsb.lol answers 429 because every Worker shares the
 * same egress addresses. The module still exports the Worker `fetch` handler, so
 * it deploys unchanged if those feeds ever stop blocking Workers.
 *
 * Whatever host you pick goes in Settings > Data Relay, and in `connect-src` in
 * index.html and _headers, exactly like the webhook, overlay and receiver hosts:
 * the page's own CSP refuses anything it has not been told about.
 *
 * ALLOWED_ORIGINS (an environment binding) is a comma-separated list of page
 * origins allowed to use the relay. Leave it unset while testing; set it once
 * deployed so the relay is not a free open proxy for anyone who finds the URL.
 *
 * Usage: GET /?url=<percent-encoded absolute https URL>
 *
 * When the feed itself refuses or fails (401, 403, 429, 5xx, timeout), the relay
 * answers 502 and names the feed's status in X-Relay-Upstream-Status. The page
 * retires a relay that answers 401/403 three times, so passing a feed's refusal
 * through unchanged would let one blocked feed retire the relay every other feed
 * depends on.
 */

// Targets this relay will fetch. Deliberately narrow: an open relay is an abuse
// liability, and every host here is one the VIPTrack page already declares in its
// own connect-src. tools/test_viptrack.py fails the build if the two drift apart.
export const ALLOWED_TARGET_HOSTS = [
    'api.adsb.one',
    'api.adsb.lol',
    'api.airplanes.live',
    'opendata.adsb.fi',
    'api.adsbdb.com',
    'hexdb.io',
    'airport-data.com',
    'aviationweather.gov',
    'tfr.faa.gov',
    'en.wikipedia.org'
];

const MAX_TARGET_URL_LENGTH = 2048;

// The feeds see one client for every viewer, so it says who it is.
const RELAY_USER_AGENT = 'VIPTrack-relay/1.0 (+https://github.com/SysAdminDoc/VIPTrack)';

const UPSTREAM_TIMEOUT_MS = 25000;

// Every viewer polls the same few feed URLs every six seconds. Holding a finished
// response briefly turns any number of viewers into one upstream request per URL per
// window, which keeps a shared relay inside adsb.fi's 1 request/second public limit.
// Misses for one URL that arrive together share a single upstream fetch.
export const CACHE_TTL_MS = 5000;
const CACHE_MAX_ENTRIES = 64;
const CACHE_MAX_BODY_BYTES = 2 * 1024 * 1024;
const responseCache = new Map();
const pendingFetches = new Map();

export function isUpstreamFault(status) {
    return status === 401 || status === 403 || status === 429 || status >= 500;
}

async function fetchUpstream(target, accept) {
    const response = await fetch(target, {
        method: 'GET',
        headers: { 'Accept': accept, 'User-Agent': RELAY_USER_AGENT },
        redirect: 'follow',
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)
    });
    return {
        status: response.status,
        contentType: response.headers.get('Content-Type') || '',
        body: await response.arrayBuffer()
    };
}

function cachedUpstream(target, accept) {
    const hit = responseCache.get(target);
    if (hit && hit.expires > Date.now()) return Promise.resolve(hit.entry);
    if (pendingFetches.has(target)) return pendingFetches.get(target);
    const work = fetchUpstream(target, accept).then(entry => {
        if (entry.status === 200 && entry.body.byteLength <= CACHE_MAX_BODY_BYTES) {
            responseCache.delete(target);
            responseCache.set(target, { expires: Date.now() + CACHE_TTL_MS, entry });
            while (responseCache.size > CACHE_MAX_ENTRIES) {
                responseCache.delete(responseCache.keys().next().value);
            }
        }
        return entry;
    }).finally(() => pendingFetches.delete(target));
    pendingFetches.set(target, work);
    return work;
}

// Mirrors egressPolicy._isPrivateHost in index.html. A relay that will fetch a
// private address on request is an SSRF pivot into whatever network runs it.
function isPrivateHost(hostname) {
    const host = String(hostname || '').toLowerCase().replace(/^\[|\]$/g, '');
    if (!host) return true;
    if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') ||
        host.endsWith('.internal') || host.endsWith('.home.arpa') || host.endsWith('.lan') ||
        host.endsWith('.test') || host.endsWith('.invalid') || host.endsWith('.example') ||
        host === 'metadata.google.internal') return true;
    if (host.startsWith('::ffff:')) return isPrivateHost(host.slice(7));
    const ipv4 = host.split('.').map(Number);
    if (ipv4.length === 4 && ipv4.every(Number.isInteger) && ipv4.every(value => value >= 0 && value <= 255)) {
        const [a, b] = ipv4;
        return a === 0 || a === 10 || a === 127 || (a === 100 && b >= 64 && b <= 127) ||
            (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) ||
            (a === 198 && (b === 18 || b === 19)) || a >= 224;
    }
    return host === '::1' || host.startsWith('fc') || host.startsWith('fd') || host.startsWith('fe80:');
}

// Exported so the repository's contract suite can exercise the decision directly
// rather than asserting that a guard appears in the source text.
export function isAllowedTarget(value) {
    const raw = String(value || '').trim();
    if (!raw || raw.length > MAX_TARGET_URL_LENGTH) return false;
    let url;
    try { url = new URL(raw); } catch (e) { return false; }
    if (url.protocol !== 'https:') return false;
    if (url.username || url.password) return false;
    if (url.port && url.port !== '443') return false;
    if (isPrivateHost(url.hostname)) return false;
    return ALLOWED_TARGET_HOSTS.includes(url.hostname.toLowerCase());
}

function allowedOrigins(env) {
    return String(env?.ALLOWED_ORIGINS || '')
        .split(',')
        .map(entry => entry.trim())
        .filter(Boolean);
}

function corsHeaders(request, env) {
    const configured = allowedOrigins(env);
    const origin = request.headers.get('Origin') || '';
    // With no ALLOWED_ORIGINS binding the relay stays open to any page, which is
    // fine for a personal deployment and wrong for a shared one.
    const allow = configured.length === 0 ? '*' : (configured.includes(origin) ? origin : '');
    const headers = {
        'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
        'Access-Control-Max-Age': '86400',
        'Access-Control-Expose-Headers': 'X-Relay-Upstream-Status',
        'Vary': 'Origin'
    };
    if (allow) headers['Access-Control-Allow-Origin'] = allow;
    return { headers, allowed: Boolean(allow) };
}

function deny(status, message, cors) {
    return new Response(JSON.stringify({ error: message }), {
        status,
        headers: { ...cors.headers, 'Content-Type': 'application/json' }
    });
}

export default {
    async fetch(request, env) {
        const cors = corsHeaders(request, env);

        if (request.method === 'OPTIONS') {
            return new Response(null, { status: cors.allowed ? 204 : 403, headers: cors.headers });
        }
        if (!cors.allowed) return deny(403, 'Origin is not permitted to use this relay', cors);
        if (request.method !== 'GET' && request.method !== 'HEAD') {
            return deny(405, 'Only GET and HEAD are relayed', cors);
        }

        const target = new URL(request.url).searchParams.get('url');
        if (!target) return deny(400, 'Missing url parameter', cors);
        if (!isAllowedTarget(target)) {
            return deny(403, 'Target host is not in this relay allowlist', cors);
        }

        let upstream;
        try {
            upstream = await cachedUpstream(target, request.headers.get('Accept') || '*/*');
        } catch (error) {
            upstream = null;
        }

        if (!upstream || isUpstreamFault(upstream.status)) {
            const status = upstream ? upstream.status : 504;
            const response = deny(502, 'Upstream answered HTTP ' + status, cors);
            response.headers.set('X-Relay-Upstream-Status', String(status));
            return response;
        }

        const headers = new Headers(cors.headers);
        if (upstream.contentType) headers.set('Content-Type', upstream.contentType);
        headers.set('Cache-Control', 'no-store');
        const bodyless = request.method === 'HEAD' || [204, 205, 304].includes(upstream.status);
        return new Response(bodyless ? null : upstream.body, { status: upstream.status, headers });
    }
};
