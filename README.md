# VIPTrack

![Version](https://img.shields.io/badge/version-0.5.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Web%20%7C%20Android-4285F4)
![JavaScript](https://img.shields.io/badge/JavaScript-ES2020+-F7DF1E?logo=javascript&logoColor=black)
![Status](https://img.shields.io/badge/status-active-success)

> Real-time military and VIP aircraft tracker. All mil/VIP/PIA aircraft load globally on page open — no panning required.

<div align="center">

### [Launch VIPTrack](https://sysadmindoc.github.io/VIPTrack/)

[![Live Demo](https://img.shields.io/badge/LIVE-Track_VIP_%26_Military-0a66c2?style=for-the-badge&logoColor=white)](https://sysadmindoc.github.io/VIPTrack/)

</div>

## What is VIPTrack?

VIPTrack makes it easy to monitor military and VIP aircraft worldwide. Unlike general-purpose flight trackers that show every commercial flight, VIPTrack filters the noise — it fetches all military, government, VIP, and Privacy ICAO Address (PIA) aircraft globally and displays them on a single dark-themed map. Open the page and every tracked aircraft is already there.

## Quick Start

**Live:** Open [VIPTrack](https://sysadmindoc.github.io/VIPTrack/) in any browser.

**Self-hosted:**
```bash
git clone https://github.com/SysAdminDoc/VIPTrack.git
cd VIPTrack
# Open index.html in any browser for the 2D map — no build step or dependencies
# For the optional ?3d=1 globe, use any static HTTP server instead:
python -m http.server 8000
# Then open http://127.0.0.1:8000/index.html?3d=1
# Or use the opt-in GPU renderer: http://127.0.0.1:8000/index.html?renderer=webgl
```

Zero-build, dependency-free static web application. The normal Leaflet 2D map works from `index.html`; the optional Cesium globe (`?3d=1`) and MapLibre/deck.gl GPU renderer (`?renderer=webgl`) are lazy-loaded from pinned CDN assets and need HTTP(S) hosting. The WebGL lane accepts `?renderer=webgl&basemap=carto-voyager` or `?renderer=webgl&basemap=stadia-alidade-smooth-dark` for opt-in vector basemaps.

The Settings panel includes a language selector. Locale catalogs live in `data/i18n/{lang}.json`, are loaded only from the app's own origin, and fall back to the English catalog (or the embedded English UI defaults when opened directly as `file://`).

The `android/` project is a first-party Android app for the mockup-derived Map, Aircraft, Watch, and Settings workspace. It serves a compact copy of the mobile shell from an in-app HTTPS origin with AndroidX WebKit, retains the PWA cache, opens external links outside the app, and fetches live/large datasets over HTTPS. It does not require Chrome and deliberately packages neither the 192 MB aircraft-photo catalog nor the 85 MB FAA shard set. With JDK 17+ and the Android SDK configured, build unsigned artifacts with `gradlew.bat assembleRelease` and `gradlew.bat bundleRelease` from that directory. No release signing key is generated or committed.

## Features

### Mobile Operations Workspace

Phones get a purpose-built four-page workspace inspired by the checked-in design studies in `assets/mockups/`: a full-screen live Map with quick filters and selected-aircraft telemetry, a searchable/sortable Aircraft list, a Watch dashboard with per-aircraft alert controls and session activity, and categorized Settings with local search. The raised bottom navigation keeps all four pages one tap away, while tablet and desktop layouts retain the established map-first interface.

### Global Aircraft Loading
All military, VIP, and PIA aircraft load worldwide on page open. No viewport-based lazy loading — every tracked aircraft appears immediately regardless of where you're looking on the map.

### Intelligence Databases

| Database | Description | Size |
|----------|-------------|------|
| Military | Aircraft identified by hex range and registration | 11,383 aircraft + 7 hex ranges |
| VIP/Government | Heads of state, government, and notable private aircraft | 12,420 aircraft |
| PIA | Privacy ICAO Address — aircraft using anonymized transponders | 94 aircraft |
| Interesting | Chase planes, test aircraft, and other flagged aircraft | 4,530+ aircraft |
| Civilian Intel | Categorized civilian fleet with type/operator data | Self-hosted DB |
| FAA Registry | Privacy-minimized official owner/type lookup for non-PIA N-numbers | 315,211 records in 26 shards |
| OPFS Registration Cache | Dedicated-worker sync-handle cache for the compact registration index, with IndexedDB/CSV fallback | Warm HTTP(S) starts |
| OpenAIP Airspace | Optional Class A–G tile overlay with a user-supplied local API key and map legend | User-keyed tiles |
| Plugin Catalog | Manifest-backed curated GeoJSON/military-pattern extensions with explicit Load controls | 4 presets |
| Localisation | Same-origin, schema-validated UI catalogs with English, Spanish, French, German, Russian, and Ukrainian | 313 UI keys |
| Type Photos | Local representative aircraft-type images with a silhouette fallback | 522 manifest entries |

### Aircraft Type Photo Enrichment

The local type-photo catalog is generated from `data/aircraft/types.json` and served before the remote fallback. Run the documented PowerShell workflow from the repository root:

```powershell
pwsh -File tools/run_type_photo_enrichment.ps1
```

The default run processes the first 500 types, resumes existing JPGs and manifest entries, and writes the manifest after each successful download. Use `-AllTypes` to process the full local catalog or `-DryRun` to inspect the deterministic work list without network calls. The downloader tries public photo sources first and creates a small aircraft silhouette when no usable photo is available; review or replace generated images in `assets/type_photos/` before committing.

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
| Filter Modes | All Mil/VIP, Military Only, or VIP Only |
| Curated Mode | Show only plane-alert-db Interesting / Notable / Historic entries and Badger's Best aircraft; heuristic-only and commercial traffic stay out |
| Search | Find aircraft by hex, registration, callsign, type, or operator |
| Search Filters | Filter results by category, altitude range, and more |
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
| Share Flight | Generate a current-trail PNG for supported Web Share clients, with a copy-link fallback |
| Web Share Target | Accepts shared ICAO hexes or N-numbers and centers the map on a matching aircraft |
| Map Bookmarks | Save named camera positions locally and jump back to them from the bottom panel |
| Background Refresh | Installed Chromium PWAs may refresh public military, VIP, and PIA reference caches every 12 hours through Periodic Background Sync; no watchlist identifiers are transmitted |
| Follow Mode | Camera tracks the selected aircraft automatically |
| Weather Radar | Precipitation overlay from RainViewer |

### Data Sources

| Source | CORS | Priority | Endpoints |
|--------|------|----------|-----------|
| [ADSB One](https://adsb.one) | Yes | Primary | `/v2/mil`, `/v2/pia` |
| [ADSB.lol](https://adsb.lol) | No (proxied) | Secondary | `/v2/mil`, `/v2/pia` |
| [Airplanes.live](https://airplanes.live) | No (proxied) | Tertiary | `/v2/mil`, `/v2/ladd` |

VIPTrack uses dedicated military and PIA API endpoints that return all matching aircraft globally in a single request. Sources are tried in priority order with automatic failover. Data refreshes every 6 seconds.

Each selected aircraft shows the supplying feed, fetch time, position/message age, response latency, fallback chain, bounded quality/integrity metadata, rate budget, and source coverage limitations. Settings > Data Sources shows the same source health and budget information; “Copy source diagnostics” exports only source-level metadata and never aircraft records, registrations, operators, or tracks. Route predictions and track-shape hints remain explicitly inferred.

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

Remote GeoJSON overlays require an explicit Load action, public HTTPS, a bounded response, and valid GeoJSON geometry; URL parameters only prefill the field for review. Webhooks also require a public HTTPS URL, show a redacted payload preview, and stay disabled for automatic alerts until explicitly enabled.

The Historical Query Workspace accepts a version-1 JSON archive (`source` metadata with `id`, `name`, `license`, and `terms`, plus a `records` array) or CSV with the same fields declared in Settings. It keeps at most 20,000 normalized records / 8 MiB, supports time, bounding-box, hex, type, altitude, speed, and bearing filters, sorted pagination, gap summaries, source attribution, local query history, and CSV/JSON export. The existing OpenSky adapter remains a manual single-track source; it is never bulk-polled. Unsupported registration/operator/API fields are rejected, known PIA identities are redacted before IndexedDB caching and export, and no archive is fetched or redistributed automatically.

### Deployment security headers

GitHub Pages cannot attach response headers, so `index.html` retains a compatible meta CSP fallback. Cloudflare Pages and Netlify-style hosts can use the root `_headers` policy, which supplies HSTS, framing, permissions, MIME, referrer, enforcing CSP, and matching CSP Report-Only headers for the main page and isolated Cesium frame. Validate Report-Only violations in the deployed host before changing the policy; `python tools/check_security_headers.py` checks the committed policy and all dynamic HTML sinks. Do not apply HSTS to an HTTP-only local deployment.

### Local state backups

Settings > Storage provides a versioned JSON backup for supported configuration and analyst state: display settings, map position, bookmarks, watchlists, named rules, geofences, trail display/retention choices, heading projection, coincidence detection, and curated overlay selections. Files are capped at 1 MiB. Credentials, tokens, API keys, webhook or receiver endpoints, aircraft cache, trail observations, raw PIA/enrichment fields, and remote GeoJSON are excluded by design. Imports reject malformed, oversized, future-version, duplicate, out-of-range, and privacy-sensitive payloads before writing local storage; legacy schema migrations are deterministic and idempotent. Import is local-only and reloads the app after the validated state is persisted.

## Architecture

```
Static app files (`index.html` + `cesium-frame.html`)
    |
    |-- Data Layer
    |     |-- ADSB One / ADSB.lol / Airplanes.live (mil + pia endpoints)
    |     |-- CORS proxy failover for file:// protocol
    |     |-- 6-second refresh cycle with source failover
    |
    |-- Intelligence Layer
    |     |-- Military DB (hex ranges + registrations)
    |     |-- VIP DB (Badger's Best)
    |     |-- PIA DB, Interesting DB, Civilian DB
    |     |-- FAA Releasable Aircraft registry (26 lazy FNV shards; no addresses)
    |     |-- OPFS registration cache (dedicated worker; compact index, IndexedDB/CSV fallback)
    |     |-- Optional OpenAIP Class A–G airspace tiles (user-keyed, no aircraft telemetry)
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

Everything runs client-side in the static app files; `index.html` owns the application state, while the optional child frame isolates Cesium's renderer:

- **Leaflet 1.9.4** — 2D map rendering and markers
- **CesiumJS 1.143** — optional 3D globe renderer loaded only with `?3d=1`
- **MapLibre GL JS 5.24.0 + deck.gl 9.2.1** — optional GPU map, `IconLayer` aircraft, `TripsLayer` trails, and CARTO Voyager/Stadia Alidade Smooth Dark vector styles loaded only with `?renderer=webgl`
- **ServiceWorker** — Offline caching of assets
- **OPFS** — Dedicated-worker sync-handle cache for the compact registration index; unsupported or unavailable browsers fall back to IndexedDB and the source CSV
- **localStorage** — Settings, map position, aircraft cache persistence
- **IndexedDB** — Airport and registration database caching
- **FAA Releasable Aircraft Registry** — official 26-shard owner/type metadata; addresses and additional registrants are omitted, and PIA aircraft are excluded at lookup time
- **OpenAIP** — optional Class A–G airspace tile overlay; API keys stay in local storage and map attribution is included
- **Plugin catalog** — manifest-backed curated GeoJSON presets with version/license/data-class metadata, an allowlisted capability boundary, local load/unload provenance, and cleanup hooks; JavaScript modules are same-origin, disabled by default, and require an explicit Load action
- **AndroidX WebKit 1.16.0** — first-party Android host, secure local HTTPS asset loading, service-worker routing, and a Chrome-independent app surface; release outputs remain unsigned by policy

Leaflet and pako load from cdnjs.cloudflare.com; DOMPurify 3.4.13, Cesium, MapLibre, and deck.gl load from pinned jsDelivr URLs. `tools/cdn_dependencies.json` records each executable/style dependency's version, SRI, license/source, and reviewed advisory status; `python tools/check_cdn_dependencies.py` is the offline release gate and `--online` additionally re-hashes the pinned bytes. The FAA shards are generated by `tools/build_faa_registry.py` from the official Releasable Aircraft Database archive and fetched lazily from same-origin HTTP(S). No npm or bundler is required; use GitHub Pages or another static HTTP(S) server for either optional renderer.

## Browser Support

| Browser | Status |
|---------|--------|
| Chrome/Edge 90+ | Full support |
| Firefox 90+ | Full support |
| Safari 15+ | Full support |
| Mobile Chrome/Safari | Touch-optimized UI |

## FAQ

**Q: Where does the data come from?**
ADS-B (Automatic Dependent Surveillance-Broadcast) — aircraft broadcast their position, altitude, speed, and identity via transponder. Volunteer receiver networks collect and share this data through public APIs.

**Q: Why don't I see a specific military aircraft?**
Many military aircraft don't broadcast ADS-B, especially during operations. Some use Mode-C (altitude only) or transponder-off. Aircraft using Privacy ICAO Addresses appear with randomized hex codes that rotate periodically.

**Q: Can I run this offline?**
Partially. On HTTPS deployments and localhost, the checked-in same-origin `sw.js` caches the app after the first load. Aircraft data requires an internet connection; API fallbacks expire after 60 seconds, while previously loaded map tiles remain available offline up to a 1,000-tile least-recently-used cap. `file://` launches intentionally stay on the live-map path because browsers do not provide service-worker control there.

**Q: How is this different from SkyTrack?**
VIPTrack is purpose-built for military and VIP monitoring. It loads all mil/VIP/PIA aircraft globally on startup (no viewport panning needed), filters out commercial traffic entirely, and uses dedicated API endpoints for faster data delivery. SkyTrack is a general-purpose tracker that shows all aircraft.

## Contributing

Issues and PRs welcome. VIPTrack is a single-file application — all changes go into `index.html`.

- Maintain the single-file architecture
- Dark theme only — ensure new UI elements match
- Test with both hosted and `file://` protocol
- Verify CORS compatibility for any new data sources

## License

MIT License — see [LICENSE](LICENSE) for details.
