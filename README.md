# VIPTrack

![Version](https://img.shields.io/badge/version-0.0.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Web-4285F4)
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

Zero-build, dependency-free static web application. The normal Leaflet 2D map works from `index.html`; the optional Cesium globe (`?3d=1`) and MapLibre/deck.gl GPU renderer (`?renderer=webgl`) are lazy-loaded from pinned CDN assets and need HTTP(S) hosting.

## Features

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
| External Links | Quick links to FlightAware, FlightRadar24, ADS-B Exchange, Planespotters |

### Search and Filtering

| Feature | Description |
|---------|-------------|
| Filter Modes | All Mil/VIP, Military Only, or VIP Only |
| Search | Find aircraft by hex, registration, callsign, type, or operator |
| Search Filters | Filter results by category, altitude range, and more |
| Search History | Recent searches saved for quick access |

### Monitoring and Alerts

| Feature | Description |
|---------|-------------|
| Watchlist | Track specific hex codes or registrations with real-time alerts |
| Military Alerts | Configurable radius-based alerts for nearby military activity |
| Notification Center | Alert history with sound and desktop notification support |

### Map and Visualization

| Feature | Description |
|---------|-------------|
| ESRI Dark Gray | Default dark basemap optimized for aircraft visibility |
| Smooth Animation | Interpolated aircraft movement between position updates |
| Aircraft Labels | Optional callsign labels on map markers |
| Sprite Icons | Type-accurate aircraft silhouettes from a sprite sheet (90+ types) |
| Color-Coded Markers | Military (green), VIP (gold), PIA (red), Government (blue) |
| 3D Globe | Optional Cesium 1.143 globe via `?3d=1`; current aircraft stay synchronized with the live feed and selected historical traces get a Cesium clock scrubber |
| WebGL Renderer | Optional MapLibre GL JS 5.24.0 + deck.gl 9.2.1 via `?renderer=webgl`; GPU `IconLayer` markers and `TripsLayer` history trails while Leaflet remains the default |
| Share Flight | Generate shareable links for specific aircraft |
| Follow Mode | Camera tracks the selected aircraft automatically |
| Weather Radar | Precipitation overlay from RainViewer |

### Data Sources

| Source | CORS | Priority | Endpoints |
|--------|------|----------|-----------|
| [ADSB One](https://adsb.one) | Yes | Primary | `/v2/mil`, `/v2/pia` |
| [ADSB.lol](https://adsb.lol) | No (proxied) | Secondary | `/v2/mil`, `/v2/pia` |
| [Airplanes.live](https://airplanes.live) | No (proxied) | Tertiary | `/v2/mil`, `/v2/ladd` |

VIPTrack uses dedicated military and PIA API endpoints that return all matching aircraft globally in a single request. Sources are tried in priority order with automatic failover. Data refreshes every 6 seconds.

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
    |     |-- Optional MapLibre GL JS 5.24.0 + deck.gl 9.2.1 (`?renderer=webgl`)
    |
    |-- UI
          |-- Aircraft detail sidebar (Overview / Aircraft / Route)
          |-- Search with filters and history
          |-- Watchlist and alert system
          |-- Settings panel
```

## Tech Stack

Everything runs client-side in the static app files; `index.html` owns the application state, while the optional child frame isolates Cesium's renderer:

- **Leaflet 1.9.4** — 2D map rendering and markers
- **CesiumJS 1.143** — optional 3D globe renderer loaded only with `?3d=1`
- **MapLibre GL JS 5.24.0 + deck.gl 9.2.1** — optional GPU map, `IconLayer` aircraft, and `TripsLayer` history loaded only with `?renderer=webgl`
- **ServiceWorker** — Offline caching of assets
- **localStorage** — Settings, map position, aircraft cache persistence
- **IndexedDB** — Airport and registration database caching

Leaflet and pako load from cdnjs.cloudflare.com; Cesium, MapLibre, and deck.gl load from pinned jsDelivr URLs. No npm or bundler is required; use GitHub Pages or another static HTTP(S) server for either optional renderer.

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
Partially. After the first load, the ServiceWorker caches the app itself. Aircraft data requires an internet connection; API fallbacks expire after 60 seconds, while previously loaded map tiles remain available offline up to a 1,000-tile least-recently-used cap.

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
