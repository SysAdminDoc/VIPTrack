# Roadmap

Forward-looking plans for VIPTrack — real-time military / VIP / PIA aircraft tracker. Single-file zero-dependency web app, Leaflet-based, loads all tracked aircraft globally on page open. v0.0.1 today.

## Planned Features

### Data Sources
- Primary: ADS-B Exchange (unfiltered), tar1090 feeders
- Fallback: adsb.fi, airplanes.live, OpenSky Network (rate-limited, authenticated)
- Source picker with per-source latency + coverage indicator
- Optional user-supplied RTL-SDR / dump1090 feed URL for local ingest

### Intelligence Databases
- Community-updated mil/VIP/PIA list — GitHub-hosted JSON, CI-validated schema, daily sync
- Per-country military hex-range editor (UI to add/remove)
- Tail number to operator mapping for civilian intel list
- Historic flight archive (store last 72h of each tracked aircraft's track in IndexedDB)

### Map & Visualization
- Cesium 3D globe alternate view with terrain + satellite imagery
- Flight path playback / scrubbing with timeline
- Altitude heatmap color ramp toggle (current: operator color)
- Cluster markers at low zoom with category breakdown popover
- Heatmap / density overlay of historical mil activity

### Alerts & Search
- Saved alerts — "notify when Air Force One departs", "notify any mil aircraft enters FL ADIZ"
- Webhook / Discord / Telegram notification targets
- Search by callsign, hex, type, operator with fuzzy match
- Geofence alert (polygon draw on map → ping on entry)

### Analysis
- Per-aircraft detail pane: photos (Planespotters), operator, type, historical routes, last-seen
- Coincidence detector — flag when two tracked aircraft are colocated (refueling / escort)
- Export track as KML / GeoJSON / GPX

### Performance
- WebGL-backed marker layer (deck.gl) for > 2k concurrent aircraft
- Delta updates from the feed (only changed states) to cut bandwidth
- Tab-visibility pausing (already best-practice — formalize)

## Competitive Research

- **ADSB.lol / Globe.adsb.fi**: free community trackers with mil-mode filter. Our differentiator is the curated VIP + PIA databases loaded globally, not viewport-gated.
- **Radarbox / Flightradar24**: commercial, UI polish, 3D maps. We won't match their fleet size but can outdo on niche (mil/VIP only, no commercial noise).
- **JetAviators / @CivMilAir on X**: manual OSINT analysts — source inspiration for the "interesting aircraft" list additions.
- **tar1090 / Readsb**: the self-host stack. Document a "point VIPTrack at your tar1090 URL" path for home feeders.

## Nice-to-Haves

- Audio squawk alerts (tone on 7500/7600/7700 emergency codes)
- Satellite-era "where was Air Force One on [date]" historic lookup
- AI caption for each flagged aircraft ("E-6B Mercury, likely TACAMO mission, routing to KOFF")
- Embeddable widget for news sites
- Weather overlay (NEXRAD, TFRs, ADIZ boundaries)
- NOTAM feed integration

## Open-Source Research (Round 2)

### Related OSS Projects
- https://github.com/wiedehopf/tar1090 — gold-standard ADS-B web UI
- https://github.com/Ysurac/FlightAirMap — 2D/3D multi-source tracker
- https://github.com/amnesica/BelugaProject — multi-feeder aggregator UI
- https://github.com/antirez/dump1090 — canonical Mode-S decoder
- https://github.com/wiedehopf/readsb — preferred modern decoder (fork of dump1090-fa)
- https://github.com/rickstaa/awesome-adsb — curated list with API endpoints and images
- https://github.com/ketilmo/balena-ads-b — multi-aggregator feeder pattern
- https://github.com/flightaware/adsb-flight-scanner-android — Android ADS-B
- https://github.com/airframesio/acars-tools — ACARS plaintext dispatch feed
- https://github.com/opensky-network/opensky-api — OpenSky REST/Kafka public feed

### Features to Borrow
- 8-hour historical trace overlay (tar1090) — lets users see coverage/range
- CPR surface-position decoding for ground movements at airports (dump1090)
- Multi-source feed fusion: ADSBExchange + adsb.fi + airplanes.live + adsb.lol (balena-ads-b list) with per-source trust weight
- Military/VIP categorization via ICAO callsign regex + tail-number list (existing VIPTrack core; cross-reference ADSBExchange `mil=true` flag)
- OpenSky REST fallback when primary source is down (OpenSky API)
- 3D globe mode via Cesium (FlightAirMap 3D) alongside Leaflet 2D — toggle
- VRS (Virtual Radar Server) compatibility for import/export of aircraft databases (FlightAirMap)
- ACARS plaintext pane for flight-plan context on selected aircraft (acars-tools)
- Receiver-coverage polygon visualizer (tar1090) — shows where your feed catches signals
- Planespotters.net photo lookup by ICAO24 (balena-ads-b integrations list)

### Patterns & Architectures Worth Studying
- Source-abstraction adapter: each feed (ADSBExchange, adsb.fi, airplanes.live, OpenSky) implements a `fetch()` + `normalize()` with the same `Aircraft` shape
- Client-side dedup by ICAO24 with most-recent-timestamp winning (balena-ads-b pattern)
- SBS1 message format as the internal normalized shape (dump1090 convention) — widely supported downstream
- Tile-based basemap plumbing with dark CARTO + optional satellite; preload on idle (tar1090 perf trick)
- Tab Visibility API pauses live polling when tab hidden — reduces needless API calls (existing web-app best practice)
