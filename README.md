# VIPTrack

![Version](https://img.shields.io/badge/version-0.8.2-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Web%20%7C%20Android-4285F4)
![JavaScript](https://img.shields.io/badge/JavaScript-ES2020+-F7DF1E?logo=javascript&logoColor=black)
![Status](https://img.shields.io/badge/status-active-success)

> Real-time military and VIP aircraft tracker. Every mil/VIP/PIA aircraft in the world loads when the page opens, with no panning.

<div align="center">

### [Launch VIPTrack](https://sysadmindoc.github.io/VIPTrack/)

[![Live Demo](https://img.shields.io/badge/LIVE-Track_VIP_%26_Military-0a66c2?style=for-the-badge&logoColor=white)](https://sysadmindoc.github.io/VIPTrack/)

<p align="center">
  <a href="https://ko-fi.com/X8K126YVER">
    <img height="42" src="https://storage.ko-fi.com/cdn/kofi2.png?v=3" alt="Buy me a coffee on Ko-fi" />
  </a>
</p>

<p align="center">
  <sub><em>If this project helps you, a coffee helps me keep working on it.</em></sub>
</p>

</div>

## What is VIPTrack?

VIPTrack shows military, government, VIP and Privacy ICAO Address (PIA) aircraft worldwide on one dark map, and leaves out the airliners a general flight tracker is full of. Open the page and every tracked aircraft is already there.

## Quick Start

**Live:** Open [VIPTrack](https://sysadmindoc.github.io/VIPTrack/) in any browser.

**Self-hosted:**
```bash
git clone https://github.com/SysAdminDoc/VIPTrack.git
cd VIPTrack
# Open index.html in any browser for the 2D map. No build step or dependencies.
# For the optional ?3d=1 globe, use any static HTTP server instead:
python -m http.server 8000
# Then open http://127.0.0.1:8000/index.html?3d=1
# Or use the opt-in GPU renderer: http://127.0.0.1:8000/index.html?renderer=webgl
```

Reference data (aircraft, airlines, airports, military/government catalogues, images) is served from this repository, so a checkout is self-contained and `file://` works without reaching a second repo. The upstream `plane-alert-db` mirrors remain configured as fallbacks.

The aircraft database is a vendored build of [tar1090-db](https://github.com/wiedehopf/tar1090-db) (ODbL-1.0). Refresh it with `py -3.13 tools/refresh_reference_data.py`, or add `--check` to report its age without downloading. The contract suite fails once the recorded build is more than 120 days old. `data/aircraft/manifest.json` records the upstream version, row count and refresh date.

There's no build step and no npm dependency. The normal Leaflet 2D map works straight from `index.html`. The optional Cesium globe (`?3d=1`) and the MapLibre/deck.gl GPU renderer (`?renderer=webgl`) lazy-load pinned CDN assets and need HTTP(S) hosting. The WebGL lane also accepts `?renderer=webgl&basemap=carto-voyager` or `?renderer=webgl&basemap=stadia-alidade-smooth-dark` for opt-in vector basemaps.

The Settings panel includes a language selector. Locale catalogs live in `data/i18n/{lang}.json`, are loaded only from the app's own origin, and fall back to the English catalog (or the embedded English UI defaults when opened directly as `file://`).

Two test lanes run locally. `py -3.13 tools/test_viptrack.py` is the offline contract suite over the shipped sources, and `py -3.13 tools/test_runtime.py` boots the page in headless Chromium with the network stubbed from the captures in `tools/fixtures/` and asserts observable behaviour. The runtime lane needs `playwright` plus its Chromium build and skips cleanly when either is missing.

The `android/` project is a native Android app around the same Map, Aircraft, Watch and Settings workspace phones get on the web. It serves a compact copy of the mobile shell from an in-app HTTPS origin through AndroidX WebKit, keeps the PWA cache, opens external links outside the app, and pulls live and large datasets over HTTPS. It doesn't need Chrome. The 192 MB aircraft-photo catalog and the 85 MB FAA shard set stay out of the package on purpose. With JDK 17+ and the Android SDK configured, build unsigned artifacts with `gradlew.bat assembleRelease` and `gradlew.bat bundleRelease` from that directory. No release signing key is generated or committed.

## Features

### Mobile Operations Workspace

On a phone, VIPTrack switches to a four-page layout based on the design studies in `assets/mockups/`. Map is a full-screen live map with quick filters and telemetry for the selected aircraft. Aircraft is a searchable, sortable list. Watch holds per-aircraft alert controls and session activity, and Settings is grouped by category with its own search. A raised bottom bar keeps all four pages one tap away. Tablets and desktops keep the map-first layout.

### Global Aircraft Loading
All military, VIP and PIA aircraft load worldwide when the page opens. Nothing waits on the viewport, so an aircraft on the far side of the world is already loaded before you pan there.

### Intelligence Databases

| Database | Description | Size |
|----------|-------------|------|
| Military | Aircraft identified by hex range and registration | 11,383 aircraft + 7 hex ranges |
| VIP/Government | Heads of state, government, and notable private aircraft | 12,420 aircraft |
| PIA | Privacy ICAO Address (aircraft using anonymized transponders) | 94 aircraft |
| Interesting | Chase planes, test aircraft, and other flagged aircraft | 4,530+ aircraft |
| Civilian Intel | Categorized civilian fleet with type/operator data | Self-hosted DB |
| FAA Registry | Privacy-minimized official owner/type lookup for non-PIA N-numbers. Owner identity is labelled with the snapshot age after 90 days and withheld entirely after 180, because FAA §803 withholding requests are continuous; regenerate with `python tools/build_faa_registry.py` | 315,211 records in 26 shards |
| OPFS Registration Cache | Dedicated-worker sync-handle cache for the compact registration index, with IndexedDB/CSV fallback | Warm HTTP(S) starts |
| OpenAIP Airspace | Optional Class A to G tile overlay with a user-supplied local API key and map legend | User-keyed tiles |
| Plugin Catalog | Manifest-backed curated GeoJSON/military-pattern extensions with explicit Load controls | 4 presets |
| Localisation | Same-origin, schema-validated UI catalogs with English, Spanish, French, German, Russian, and Ukrainian | 360+ UI keys |
| Type Photos | Local representative aircraft-type images with a silhouette fallback | 522 manifest entries |

### Aircraft Type Photo Enrichment

The local type-photo catalog is generated from `data/aircraft/types.json` and served before the remote fallback. Run the documented PowerShell workflow from the repository root:

```powershell
pwsh -File tools/run_type_photo_enrichment.ps1
```

The default run processes the first 500 types, resumes existing JPGs and manifest entries, and writes the manifest after each successful download. Use `-AllTypes` to process the full local catalog or `-DryRun` to inspect the deterministic work list without network calls. The downloader tries public photo sources first and draws a small aircraft silhouette when no usable photo turns up. Review or replace generated images in `assets/type_photos/` before committing.

### Aircraft Detail Panel

| Feature | Description |
|---------|-------------|
| Overview Tab | Callsign, operator, type, altitude, speed, heading, squawk, and quick-glance stats |
| Aircraft Tab | Registration, ICAO hex, type designator, aircraft specs, and Wikipedia summary |
| Route Tab | Origin/destination with route progress, airport codes, and distance remaining |
| Aircraft Photos | Auto-fetched from planespotters.net with fallback silhouettes |
| Airline Banners | Airline branding displayed for identified carriers |
| Altitude Chart | Live altitude profile showing climb/descent phases |
| History Trail | Altitude-colored flight path rendered on the map |
| Track-shape Heuristics | Local, unverified orbit, sustained-hold, and high-altitude transit hints from the in-memory trail; no ML or PIA correlation |
| External Links | Quick links to Airframes.io ACARS context, FlightAware, FlightRadar24, ADS-B Exchange, Planespotters |

### Search and Filtering

| Feature | Description |
|---------|-------------|
| Filter Modes | All Mil/VIP, Military Only, Government, VIP Only, or LADD |
| LADD | FAA Limiting Aircraft Data Displayed, read from the feed's `dbFlags` and its `/v2/ladd` endpoint where the source publishes one (adsb.fi does not) |
| Curated Mode | Show only plane-alert-db Interesting / Notable / Historic entries and Badger's Best aircraft; heuristic-only and commercial traffic stay out |
| Search | Find aircraft by hex, registration, callsign, type, or operator |
| Search Filters | Filter results by category, altitude range, and more |
| ADS-B positions only | Exclude MLAT, TIS-B and ADS-R tracks, keeping only positions the aircraft reported itself |
| Shareable views | A share link carries the whole filter state (altitude and speed bands, airport, airline, regex, categories, ADS-B-only and capture mode), so whoever opens it sees the view you had |
| Capture mode | `?freeze=1` holds positions at a stated UTC time while pan, zoom and selection stay live, so a screenshot cites a frame that did not move under you |
| Search History | Recent searches saved for quick access |

### Monitoring and Alerts

| Feature | Description |
|---------|-------------|
| Watchlist | Track specific hex codes or registrations with real-time alerts |
| Military Alerts | Configurable radius-based alerts for nearby military activity |
| Squawk 7700 History | Pinned local 24-hour emergency feed attributed from plane-alert-db; open `?emergency=last24h` to isolate recent incidents |
| Notification Center | Alert history with sound and desktop notification support |
| Session Statistics | In-memory graphs1090-style feed health: messages seen, refresh latency histogram, source usage, and rolling mil/VIP/PIA counts |

### Map and Visualization

| Feature | Description |
|---------|-------------|
| ESRI Dark Gray | Default dark basemap optimized for aircraft visibility |
| Smooth Animation | Interpolated aircraft movement between position updates |
| Aircraft Labels | Optional callsign labels on map markers |
| Sprite Icons | Type-accurate aircraft silhouettes from a sprite sheet (90+ types) |
| Color-Coded Markers | Military (green), VIP (gold), PIA (red), Government (blue) |
| 3D Globe | Optional Cesium 1.143 globe via `?3d=1`; current aircraft stay synchronized with the live feed and selected historical traces get a Cesium clock scrubber |
| WebGL Renderer | Optional MapLibre GL JS 5.24.0 + deck.gl 9.2.1 via `?renderer=webgl`; GPU `IconLayer` markers, `TripsLayer` history trails, and opt-in CARTO Voyager or Stadia Alidade Smooth Dark vector basemaps while Leaflet remains the default |
| Self-Hosted Basemap | Optional PMTiles archive served from your own origin, removing every third-party basemap host. See [Self-hosted basemap](#self-hosted-basemap) |
| Share Flight | Generate a current-trail PNG for supported Web Share clients, with a copy-link fallback |
| Web Share Target | Accepts shared ICAO hexes or N-numbers and centers the map on a matching aircraft |
| Map Bookmarks | Save named camera positions locally and jump back to them from the bottom panel |
| Background Refresh | Installed Chromium PWAs may refresh public military, VIP, and PIA reference caches every 12 hours through Periodic Background Sync; no watchlist identifiers are transmitted |
| Follow Mode | Camera tracks the selected aircraft automatically |
| Weather Radar | Precipitation overlay from RainViewer |
| Coverage View | Persistent tracks or a density heatmap built from this browser's own observations over a selectable window. See [Coverage view](#coverage-view) |

### Data Sources

| Source | Sends CORS headers | Priority | Endpoints |
|--------|--------------------|----------|-----------|
| [ADSB.lol](https://adsb.lol) | No | 1 | `/v2/mil`, `/v2/pia`, `/v2/ladd`, `/v2/hex/…` |
| [ADSB.fi](https://adsb.fi) | No | 2 | `/api/v2/mil`, `/api/v2/hex/…` |
| [ADSB One](https://adsb.one) | No | 3 | `/v2/mil`, `/v2/pia`, `/v2/ladd`, `/v2/hex/…` |
| [Airplanes.live](https://airplanes.live) | No | 9 (disabled) | `/v2/mil`, `/v2/pia`, `/v2/ladd` (off, since the public API now needs approved access and answers HTTP 403) |

**Not one of them sends `Access-Control-Allow-Origin`.** A browser can't fetch any of these directly, so every request goes through a relay, on the hosted site as much as from `file://`. That makes the relay the hardest dependency in the app. The hosted site uses its own relay at `viptrack-relay.getparkerai.com`. See [Data relay](#data-relay) for how it works and how to run your own.

Sources are tried in measured-health order with automatic failover, and data refreshes every 6 seconds. `/mil`, `/pia` and `/ladd` return every matching aircraft globally in one request each. Government and police aircraft appear in none of those, so their catalogues are swept separately in rotating `/hex/` batches, one batch per refresh. adsb.fi publishes no `/ladd` endpoint and is not asked for one.

Each selected aircraft shows the supplying feed, fetch time, position/message age, response latency, fallback chain, bounded quality/integrity metadata, rate budget, and source coverage limitations. Settings > Data Sources shows the same source health and budget information. “Copy source diagnostics” exports only source-level metadata, never aircraft records, registrations, operators or tracks. Route predictions and track-shape hints are always marked as inferred.

## Settings

Access via the gear icon. All settings persist in localStorage.

| Setting | Default | Description |
|---------|---------|-------------|
| Show Labels | On | Callsign labels on aircraft markers |
| Follow Mode | Off | Camera tracks selected aircraft |
| Compact Mode | Off | Dense UI for smaller screens |
| Show Wikipedia | On | Wikipedia summaries in aircraft detail |
| Military Alert Radius | 50nm | Distance trigger for military alerts |
| Sound Alerts | Off | Audio notifications |
| Desktop Notifications | Off | Browser notification popups |
| Trail Retention | 7 days | Remove older IndexedDB trail history on startup or on demand (24 h / 7 d / 14 d / 30 d) |
| Map Bookmarks | None | Save named map camera positions in local storage |

Remote GeoJSON overlays require an explicit Load action, public HTTPS, a bounded response, and valid GeoJSON geometry. A URL parameter only prefills the field for you to review. Webhooks also require a public HTTPS URL, show a redacted payload preview, and stay disabled for automatic alerts until explicitly enabled.

The Historical Query Workspace accepts a version-1 JSON archive (`source` metadata with `id`, `name`, `license`, and `terms`, plus a `records` array) or CSV with the same fields declared in Settings. It keeps at most 20,000 normalized records / 8 MiB, supports time, bounding-box, hex, type, altitude, speed, and bearing filters, sorted pagination, gap summaries, source attribution, local query history, and CSV/JSON export. The existing OpenSky adapter stays a manual single-track source and is never bulk-polled. Unsupported registration/operator/API fields are rejected, known PIA identities are redacted before IndexedDB caching and export, and no archive is fetched or redistributed automatically.

### Coverage view

The live map answers "where is it now". The coverage view answers "where has traffic been". Enable it in **Settings > Map & Tools > Coverage view**.

Two styles are available: **density heatmap**, which shades how often aircraft have been observed over each patch of ground, and **persistent tracks**, which draws the accumulated paths themselves. Both read a selectable window covering the last hour, 6 hours, 24 hours, or 7 days. The sample interval is configurable from 15 seconds to 5 minutes. A **Clear** control empties the store.

Everything it draws comes from what this browser has already observed. It fetches and sends nothing, and no other user's data is involved. Turning the view on starts sampling, and a **Record coverage samples** toggle stops it again, so position history only builds up while you leave it on. Privacy-protected aircraft are dropped when sampled and again when drawn, so a store written before a hex became known-PIA still redacts it. The status line reports how many points were withheld. Sampling only records a position that actually changed, so a parked aircraft costs one row rather than one per tick, and retention follows the existing trail retention setting.

Points are aggregated into cells as the store is read rather than held as a raw set, so a redraw costs the same whether the window holds a thousand points or a hundred thousand. The walk stops at 250,000 points and says so in the status line instead of locking the tab. The active style and window travel in a shared view link (`?coverage=density&coverageWindow=24`), but no identities do. The layer draws on the standard Leaflet map. Under `?renderer=webgl` it says so instead of silently drawing nothing.

### Self-hosted basemap

Every basemap VIPTrack ships with belongs to somebody else. Esri serves the Leaflet default, OpenStreetMap serves the Cesium globe, CARTO and Stadia serve the optional vector styles, and each of them reserves the right to block a busy third-party site without notice. A [PMTiles](https://docs.protomaps.com/pmtiles/) archive removes that risk. It's a single file on your own origin, read with HTTP range requests, with no tile server and no API key.

Build one from the repository root, then pick **Settings > Appearance > Basemap > Self-hosted PMTiles** or open `?renderer=webgl&basemap=pmtiles-dark`:

```bash
py -3.13 tools/build_basemap_pmtiles.py          # world, zoom 0-6, ~43 MB
py -3.13 tools/build_basemap_pmtiles.py --check  # report what is installed
```

The archive is **not** committed. It is a rebuildable binary, and every refresh would add its full size to git history permanently, so `data/basemap/` is gitignored and you deploy it alongside the site. Without it the option stays disabled and the app keeps its normal basemap.

Sizes measured against the Protomaps daily planet build (127.9 GB) on 2026-08-18:

| Build | Size | Verdict |
|-------|------|---------|
| World, zoom 0 to 6 | 42.7 MB | Default. Vector tiles overzoom, so it still draws past zoom 6 with coarser detail. |
| World, zoom 0 to 7 | 178.4 MB | Fits, but consumes a third of the remaining GitHub Pages budget. |
| CONUS, zoom 0 to 10 | 361.1 MB | Rejected because US-only coverage uses most of the budget. |

The published tree is roughly 466 MB against the GitHub Pages 1 GB soft limit, which is why the build script refuses zoom levels above 6 and archives above 96 MB unless you pass `--allow-large`. Cold load of the zoom 0 to 6 world archive costs 10 range requests and about 480 KB. The client never downloads the whole file. The style carries no labels. Glyph files would have to come from another external host, the very dependency the archive exists to remove, so the app's own aircraft and airport labels sit on plain geometry.

The archive path must be same-origin. `connect-src` is a real allowlist, so a cross-origin archive is blocked by the app's own CSP; hosting elsewhere means adding that host to both the meta CSP in `index.html` and `_headers`. Note also that `python -m http.server` ignores `Range` headers. Use a static host that answers 206 (GitHub Pages does) when testing locally.

### Data relay

No public ADS-B aggregator sends `Access-Control-Allow-Origin`, so a static browser-only build can't read a feed directly. The free public relays are no help. `corsproxy.io` answers HTTP 401 without an account key, and `api.allorigins.win` returns 5xx errors.

The hosted site goes through `https://viptrack-relay.getparkerai.com`, a small Node server running `workers/cors-relay.js` behind `workers/node-relay.mjs`. It fetches only the hosts VIPTrack already lists in its own `connect-src`, never a private address, and only with GET or HEAD. Pages from other origins get a 403. A successful feed response is held for five seconds, so any number of viewers cost the feeds one request per URL per five seconds. When a feed itself refuses a request, the relay says so with a 502 and an `X-Relay-Upstream-Status` header, and the app keeps using the relay for the other feeds.

To run your own (for a fork, or to stop sharing the hosted one), use a server with an address of its own.

```bash
ALLOWED_ORIGINS=https://you.github.io RELAY_DNS_ORDER=ipv6first node workers/node-relay.mjs
```

Behind a reverse proxy, set `RELAY_PROXY_ADDRESSES` to the proxy's address so the per-client rate limit sees real clients. `RELAY_DNS_ORDER=ipv6first` matters on a host with IPv6, because adsb.lol's IPv4 front end accepts connections and then never answers. The header of `node-relay.mjs` lists every setting.

A Cloudflare Worker doesn't work as the host. `cors-relay.js` still exports a Worker handler, but adsb.fi and ADSB One answer Worker traffic with a block page, and adsb.lol rate-limits it because every Worker shares the same outbound addresses.

Paste your relay's URL into **Settings > Data Relay**. It's stored in your browser only and tried before the hosted relay. Like the webhook, overlay and receiver hosts below, the relay host also has to be in `connect-src` in `index.html` and `_headers`, since the page's own CSP refuses hosts it hasn't been told about. The app names the host it needs when that happens.

### Allowlisting your own hosts

The CSP's `connect-src` lists every host the page may fetch, and nothing else gets through. Bare `https:` was taken out on purpose, because a scheme source matches every origin and would make the rest of the list pointless. A fixed list suits the app's own feeds. Four features fetch hosts only you know, though, so you add those yourself.

| Feature | What you must allowlist |
|---------|------------------------|
| Alert webhook (Settings > Alert Webhook) | Your webhook host, e.g. `https://discord.com` or your ntfy server |
| Remote GeoJSON overlay (Settings > Overlays) | The host serving the `.geojson` file |
| Receiver coverage (Settings > Receiver Coverage) | Your tar1090/readsb feeder host |
| Data relay (Settings > Data Relay) | Your relay host, e.g. `https://relay.example.org` |

Add the host to **both** the `Content-Security-Policy` meta tag in `index.html` and the `connect-src` line in `_headers`, then redeploy. Without that, the browser refuses the request before it reaches the network and the feature reports the refusal, naming the host to add.

Receiver coverage has a second constraint that no CSP change fixes. A page served over HTTPS can't fetch an `http://` address at all, because the browser refuses it as mixed content. A LAN feeder on plain HTTP is only reachable if you also open VIPTrack over HTTP (a local copy), or put the feeder behind HTTPS.

### Deployment security headers

GitHub Pages cannot attach response headers, so `index.html` retains a compatible meta CSP fallback. Cloudflare Pages and Netlify-style hosts can use the root `_headers` policy, which supplies HSTS, framing, permissions, MIME, referrer, enforcing CSP, and matching CSP Report-Only headers for the main page and isolated Cesium frame. Check the Report-Only violations on the deployed host before changing the policy. `python tools/check_security_headers.py` checks the committed policy and every dynamic HTML sink. Don't apply HSTS to an HTTP-only local deployment.

### Local state backups

Settings > Storage provides a versioned JSON backup for supported configuration and analyst state: display settings, map position, bookmarks, watchlists, named rules, geofences, trail display/retention choices, heading projection, coincidence detection, and curated overlay selections. Files are capped at 1 MiB. Credentials, tokens, API keys, webhook or receiver endpoints, aircraft cache, trail observations, raw PIA/enrichment fields, and remote GeoJSON are excluded by design. Imports reject malformed, oversized, future-version, duplicate, out-of-range, and privacy-sensitive payloads before writing local storage, and legacy schema migrations are deterministic and idempotent. Import stays local and reloads the app once the validated state is saved.

## Architecture

```
Static app files (`index.html` + `cesium-frame.html`)
    |
    |-- Data Layer
    |     |-- ADSB.lol / ADSB.fi / ADSB One (mil + pia + ladd + hex batches)
    |     |-- CORS relay (required for every request, not just file://)
    |     |-- 6-second refresh cycle with source failover
    |
    |-- Intelligence Layer
    |     |-- Military DB (hex ranges + registrations)
    |     |-- VIP DB (Badger's Best)
    |     |-- PIA DB, Interesting DB, Civilian DB
    |     |-- FAA Releasable Aircraft registry (26 lazy FNV shards; no addresses)
    |     |-- OPFS registration cache (dedicated worker; compact index, IndexedDB/CSV fallback)
    |     |-- Optional OpenAIP Class A to G airspace tiles (user-keyed, no aircraft telemetry)
    |     |-- Plugin catalog (`plugins/manifest.json`, capability/provenance contract, same-origin opt-in)
    |     |-- Track-shape heuristics (local in-memory trail rules; unverified labels)
    |     |-- Airline DB (5,800+), Callsign Prefixes (5,774)
    |     |-- Registration DB, Alliance DB
    |
    |-- Rendering (Leaflet 2D Map)
    |     |-- Sprite-based aircraft icons (90+ types)
    |     |-- Smooth marker animation (requestAnimationFrame)
    |     |-- Grid decimation at low zoom for performance
    |     |-- Altitude-colored history trails
    |     |-- Optional Cesium 1.143 globe (`?3d=1`, lazy-loaded, no ion token)
    |     |     |-- `globe.airplanes.live` trace samples become a Cesium clock + scrubber
    |     |-- Optional MapLibre GL JS 5.24.0 + deck.gl 9.2.1 (`?renderer=webgl`, CARTO/Stadia vector styles)
    |
    |-- UI
          |-- Aircraft detail sidebar (Overview / Aircraft / Route)
          |-- Search with filters and history
          |-- Watchlist and alert system
          |-- Settings panel and localised catalogs (`data/i18n/`)

Android app (`android/`)
    |-- Native Activity with branded launch/offline state
    |-- Secure AndroidX WebKit in-app HTTPS asset origin
    |-- Mockup-derived Map / List / Watch / Settings workspace
    |-- HTTPS deep links, Android share target, file import, and on-demand location
    |-- Compact generated web bundle; bulk datasets remain on-demand
    |-- Unsigned APK/App Bundle build lane
```

## Tech Stack

Everything runs client-side in the static app files. `index.html` owns the application state, and the optional child frame keeps Cesium's renderer isolated.

- **Leaflet 1.9.4** handles 2D map rendering and markers.
- **CesiumJS 1.143** provides the optional 3D globe renderer loaded only with `?3d=1`.
- **MapLibre GL JS 5.24.0 + deck.gl 9.2.1** provide the optional GPU map, `IconLayer` aircraft, `TripsLayer` trails, and CARTO Voyager/Stadia Alidade Smooth Dark vector styles loaded only with `?renderer=webgl`.
- **ServiceWorker** caches assets for offline use.
- **OPFS** provides a dedicated-worker sync-handle cache for the compact registration index. Browsers without it fall back to IndexedDB and the source CSV.
- **localStorage** holds settings, map position, and persistent aircraft cache data.
- **IndexedDB** caches airport and registration databases.
- **FAA Releasable Aircraft Registry** supplies the official 26-shard owner/type metadata. Addresses and additional registrants are left out, and PIA aircraft are excluded at lookup time.
- **OpenAIP** supplies the optional Class A to G airspace tile overlay. API keys stay in local storage, and the map carries the attribution.
- **Plugin catalog** contains manifest-backed curated GeoJSON presets with version/license/data-class metadata, an allowlisted capability boundary, local load/unload provenance, and cleanup hooks. JavaScript modules are same-origin, disabled by default, and require an explicit Load action.
- **AndroidX WebKit 1.16.0** provides the first-party Android host, secure local HTTPS asset loading, service-worker routing, and a Chrome-independent app surface. Release outputs remain unsigned by policy.

Leaflet and pako load from cdnjs.cloudflare.com; DOMPurify 3.4.13, Cesium, MapLibre, and deck.gl load from pinned jsDelivr URLs. `tools/cdn_dependencies.json` records each executable/style dependency's version, SRI, license/source, and reviewed advisory status. `python tools/check_cdn_dependencies.py` is the offline release gate, and `--online` also re-hashes the pinned bytes. The FAA shards are generated by `tools/build_faa_registry.py` from the official Releasable Aircraft Database archive and fetched lazily from same-origin HTTP(S). No npm or bundler is needed. Either optional renderer does need GitHub Pages or another static HTTP(S) server.

## Browser Support

| Browser | Status |
|---------|--------|
| Chrome/Edge 90+ | Full support |
| Firefox 90+ | Full support |
| Safari 15+ | Full support |
| Mobile Chrome/Safari | Touch-optimized UI |

## FAQ

**Q: Where does the data come from?**
ADS-B (Automatic Dependent Surveillance-Broadcast) lets aircraft broadcast their position, altitude, speed, and identity via transponder. Volunteer receiver networks collect and share this data through public APIs.

**Q: Why don't I see a specific military aircraft?**
Many military aircraft don't broadcast ADS-B, especially during operations. Some use Mode-C (altitude only) or transponder-off. Aircraft using Privacy ICAO Addresses appear with randomized hex codes that rotate periodically.

**Q: Can I run this offline?**
Partially. On HTTPS deployments and localhost, the checked-in same-origin `sw.js` caches the app after the first load. Aircraft data needs an internet connection. API fallbacks expire after 60 seconds, while previously loaded map tiles remain available offline up to a 1,000-tile least-recently-used cap. `file://` launches intentionally stay on the live-map path because browsers do not provide service-worker control there.

**Q: How is this different from SkyTrack?**
VIPTrack is built only for military and VIP monitoring. It loads all mil/VIP/PIA aircraft globally on startup (no viewport panning needed), filters out commercial traffic entirely, and uses dedicated API endpoints for faster data delivery. SkyTrack is a general-purpose tracker that shows all aircraft.

## Contributing

Issues and PRs are welcome. The web app lives in `index.html`, with the Cesium globe split out into `cesium-frame.html`, so most changes land there.

- Keep it plain static files with no build step.
- Dark theme only, so new UI should match it.
- Test both the hosted site and a `file://` copy.
- A new data source goes through the relay, so add its host to `ALLOWED_TARGET_HOSTS` in `workers/cors-relay.js` as well as to `connect-src`.

## License

MIT License. See [LICENSE](LICENSE) for details.
