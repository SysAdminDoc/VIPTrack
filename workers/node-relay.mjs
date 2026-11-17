/*
 * Runs workers/cors-relay.js as a plain Node HTTP server (Node 20+), for a host
 * with an address of its own. The relay's Worker handler does all the deciding;
 * this file only translates between node:http and the fetch Request/Response pair
 * and keeps any one client from spending the feeds' patience for everybody.
 *
 *     ALLOWED_ORIGINS=https://sysadmindoc.github.io node workers/node-relay.mjs
 *
 * Environment:
 *   PORT, HOST              where to listen (default 0.0.0.0:8790)
 *   ALLOWED_ORIGINS         page origins allowed to use the relay, comma separated
 *   RELAY_PROXY_ADDRESSES   reverse proxies whose X-Forwarded-For is believed,
 *                           comma separated (default: none, use the socket address)
 *   RELAY_RATE_PER_MINUTE   requests one client may make per minute (default 240)
 *   RELAY_DNS_ORDER         ipv6first, ipv4first or verbatim (default: Node's own).
 *                           api.adsb.lol's IPv4 front end accepts connections and
 *                           then never answers (2026-11-17), so a host with IPv6
 *                           should set ipv6first. Hosts without an AAAA record
 *                           still resolve to IPv4.
 *
 * GET /healthz answers 200 for container health checks.
 */
import dns from 'node:dns';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import relay from './cors-relay.js';

const PORT = Number(process.env.PORT || 8790);
const HOST = process.env.HOST || '0.0.0.0';
const env = { ALLOWED_ORIGINS: process.env.ALLOWED_ORIGINS || '' };
const trustedProxies = new Set(String(process.env.RELAY_PROXY_ADDRESSES || '')
    .split(',').map(entry => entry.trim()).filter(Boolean));
const RATE_PER_MINUTE = Number(process.env.RELAY_RATE_PER_MINUTE || 240);

// The page polls about 40 times a minute per viewer. A client far past that is a
// script, and the feeds would ban this server's address for it, not the script's.
const windows = new Map();

export function clientAddress(req, proxies = trustedProxies) {
    const peer = String(req.socket?.remoteAddress || '').replace(/^::ffff:/, '');
    if (!proxies.has(peer)) return peer;
    const forwarded = String(req.headers['x-forwarded-for'] || '').split(',').map(part => part.trim()).filter(Boolean);
    return forwarded.length ? forwarded[forwarded.length - 1] : peer;
}

export function overLimit(address, now = Date.now(), limit = RATE_PER_MINUTE) {
    const minute = Math.floor(now / 60000);
    const entry = windows.get(address);
    if (!entry || entry.minute !== minute) {
        windows.set(address, { minute, count: 1 });
        if (windows.size > 10000) {
            for (const [key, value] of windows) if (value.minute !== minute) windows.delete(key);
        }
        return false;
    }
    entry.count += 1;
    return entry.count > limit;
}

async function handle(req, res) {
    const url = new URL(req.url || '/', 'http://relay.invalid');
    if (url.pathname === '/healthz') {
        res.writeHead(200, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' });
        res.end('ok');
        return;
    }

    const headers = new Headers();
    if (req.headers.origin) headers.set('Origin', String(req.headers.origin));
    if (req.headers.accept) headers.set('Accept', String(req.headers.accept));

    if (req.method !== 'OPTIONS' && overLimit(clientAddress(req))) {
        const origin = headers.get('Origin') || '';
        res.writeHead(429, {
            'Content-Type': 'application/json',
            'Retry-After': '60',
            ...(origin ? { 'Access-Control-Allow-Origin': origin, 'Vary': 'Origin' } : {})
        });
        res.end(JSON.stringify({ error: 'Too many requests from this client' }));
        return;
    }

    const request = new Request(url.href, { method: req.method, headers });
    const response = await relay.fetch(request, env);
    res.writeHead(response.status, Object.fromEntries(response.headers));
    res.end(req.method === 'HEAD' ? undefined : Buffer.from(await response.arrayBuffer()));
}

export function createServer() {
    return http.createServer((req, res) => {
        handle(req, res).catch(() => {
            if (!res.headersSent) res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Relay error' }));
        });
    });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    const dnsOrder = String(process.env.RELAY_DNS_ORDER || '').trim();
    if (dnsOrder) {
        if (!['ipv6first', 'ipv4first', 'verbatim'].includes(dnsOrder)) {
            console.error(`RELAY_DNS_ORDER must be ipv6first, ipv4first or verbatim, not "${dnsOrder}"`);
            process.exit(1);
        }
        dns.setDefaultResultOrder(dnsOrder);
    }
    createServer().listen(PORT, HOST, () => {
        const origins = env.ALLOWED_ORIGINS || 'any origin';
        console.log(`viptrack relay on ${HOST}:${PORT} for ${origins}; X-Forwarded-For from ${[...trustedProxies].join(', ') || 'nobody'}; DNS order ${dnsOrder || 'default'}`);
    });
}
