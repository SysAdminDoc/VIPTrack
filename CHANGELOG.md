# Changelog

All notable changes to VIPTrack will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- DOMPurify-backed HTML sink sanitization with a fail-closed escaped fallback and SRI-pinned CDN delivery.
- Daily cached PIA/LADD protection data that suppresses registration enrichment, registration-based photo lookups, and operator display for protected aircraft.
- Persisted named watchlists with AND-matched hex, callsign regex, type, country, altitude, and geofence rules, plus independent alert cooldowns.
- Local geofence editor with persisted circle/polygon geometry, map drawing controls, visibility toggles, and entry/exit alerts.
- Privacy-safe PIA rotation timeline retaining public hex sightings for a local 20-day callsign/type profile without registration or operator correlation.
- Opt-in curated military pattern templates backed by explicit unverified GeoJSON presets for AWACS, tanker, drone CAP, and exercise annotations.
- Direct tar1090/readsb receiver coverage adapter with 36-sector observed range polygon, optional stats max-range outline, URL persistence, and coordinate fallbacks.
- Manual OpenSky historical track replay using user-supplied OAuth2 client credentials, 30-day validation, and no live-loop or proxy use.
- Manual FAA NASR/ADDS special-use airspace overlay for restricted, prohibited, MOA, and warning polygons, with a 28-day IndexedDB cache and stale-data refusal.
- Opt-in CesiumJS 1.143 3D globe via `?3d=1`, with a same-origin child CSP, SRI-pinned lazy loading, OpenStreetMap imagery, current aircraft entities, and click-through selection.
- Opt-in MapLibre GL JS 5.24.0 + deck.gl 9.2.1 WebGL renderer via `?renderer=webgl`, with GPU `IconLayer` aircraft and `TripsLayer` history while Leaflet remains the default.
- ServiceWorker cache names now include a SHA-256 asset-manifest hash and schema version; cross-origin API fallbacks expire after 60 seconds and tile storage uses a 1,000-entry last-used LRU.
- ADSB.fi as a fourth rotating live-data source with health tracking.
- Emergency squawk auto-highlight for 7500 (hijack) / 7600 (NORDO) / 7700 (general) with optional audible tone.
- ADSBdb route lookup (`api.adsbdb.com/v0/callsign/{flight}`) to enrich the route panel with origin / midpoint / destination ICAO when public.
- Hexdb.io thumbnail fallback when planespotters.net has no photo for a hex (common for military aircraft).
- NEXRAD radar overlay via NOAA `nowcoast` WMS as an opt-in alternative to RainViewer (US only).
- FAA TFR polygons overlay (tfr2go JSON mirror, FAA XML fallback) — see active VIP/security TFRs alongside live tracks.
- Custom GeoJSON overlay loader (file picker + raw URL) with named-layer management — bring your own ADIZ / MOA / orbit polygons.
- Heatmap / density overlay rendered on a custom canvas layer (no external plugin) from accumulated trail history.
- Coincidence detector — flags any two tracked (mil / VIP / interesting) aircraft within 5 nm and 2000 ft of each other (formation, refuelling, escort) with cooldown.
- Webhook alert sinks: Generic JSON, Discord, ntfy.sh — extends the existing alert system with no infrastructure of its own.
- Daily plane-alert-db sync (mil / gov / pol / pia / civ / categories) from GitHub raw, stored in IndexedDB.
- AWC TAF + nearby-PIREP fetchers added to the weather subsystem.
- AWC weather rate-limited (100 req/min) via the new token bucket.
- Track export to KML, GPX, GeoJSON, and CSV for the selected aircraft.
- Viewport CSV export — one click snapshots every aircraft currently visible.
- OSINT report copy-to-clipboard — selected aircraft summarised as a ready-to-paste note including DMS, Maidenhead grid, and sun-position (alt / az).
- Polite client-side rate limiting (token bucket per host) to respect ADS-B One's 1 req/sec, ADSB.lol's dynamic limits, and AWC's 100 req/min.
- Ease-out (quadratic) marker interpolation in place of linear — smoother apparent motion, closer to FR24/tar1090 feel.
- Keyboard shortcuts: `F` follow, `Esc` deselect / close, `M` military, `V` VIP, `A` all mil+VIP, `S` focus search, `N` NEXRAD, `R` ruler, `B` bookmark, `?` help.
- Ruler / distance-and-bearing tool (click two points, km / nm + heading label).
- Direction-of-flight projection line per marker, with configurable lookahead (1 / 3 / 5 / 10 min).
- Tab-visibility "paused — return to tab" pill.
- Trail retention setting (24 h / 7 d / 14 d / 30 d) wired to the existing IndexedDB cleanup path.
- Embed mode — `?embed=1` strips chrome for drop-in widget use.
- URL params: `?focus=HEX`, `?center=lat,lng`, `?zoom=n`, `?overlay=<url>`, `?embed=1`.
- Meta-tag CSP allowlisting only the feeds and CDNs the app actually uses.
- First-load ethical-use disclaimer (dismissable; respects PIA / LADD).
- Accessibility: `--text-muted` raised to AA contrast on the dark background; `prefers-reduced-motion` honoured (emergency pulse and other animations stilled).

### Changed
- PIA aircraft now display an explicit anonymised-operator label instead of a registration or operator resolved from the public database.
- CSP now includes the FAA TFR JSON mirror used by the overlay.
- ServiceWorker cache version `viptrack-v4.14` → `viptrack-v4.15` so prior caches retire cleanly on first load.
- `CHANGELOG.md` migrated to Keep-a-Changelog format; previous `%Y->-` placeholder repaired.
- `CLAUDE.md` reconciled with actual JS/Leaflet stack (the file previously claimed Python).

## [v0.0.1] - 2026-04-13

- Fixed: MIL filter including VIP aircraft.
- Fixed: Aircraft disappearing when panning around the globe.
- Removed: Mobile context menu; onboarding popup updated.
- Aircraft info panel now overlays the map instead of pushing it.
- Pull-to-dismiss aircraft info panel from anywhere in content.
- Added: Swipe-down-to-dismiss on aircraft info panel (mobile).
- Fixed: Info panel not showing on mobile when clicking aircraft.
- Fixed: Mobile top bar — hide header, give filter bar full width.
- Optimised responsive layout for desktop and mobile.
- Rewrote README for VIPTrack.
