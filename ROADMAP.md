# Roadmap

**VIPTrack** — single-file Leaflet web app for global military / VIP / government / PIA aircraft tracking. MIT, zero-build, GitHub Pages.

> Version: v0.0.1 → working roadmap **rev. 2026-05-17b** (supersedes the 2026-04-23 draft preserved at the bottom).

## Recently shipped (2026-05-17 implementation pass)

### Round 1
| ID | What | Where |
|---|---|---|
| N3 | Meta-tag CSP allowlisting only the feeds + CDNs in use | `<head>` |
| N6 | First-load ethical-use disclaimer (dismissable, persistent ack) | `#ethicsDisclaimer` |
| X1 | Emergency squawk visual pulse for 7500 / 7600 / 7700 (alert audio already shipped) | `.emergency-7700` etc. |
| X8 | Direction-of-flight projection line (toggle + lookahead select, 1/3/5/10 min) | `headingProjection` |
| X9 | Ruler / distance + bearing tool (click two points, km/nm + heading label) | `rulerTool` |
| X17 | ADSBdb route lookup for callsigns without `from`/`to` in feed (TTL cache, negative cache) | `adsbdbAPI` |
| X19 | ADSB.fi added as the 4th rotating data source | `dataSourceManager.sources` |
| X22 | NEXRAD WMS overlay toggle (NOAA nowcoast, US only) | `toggleNexrad` |
| X24 | Track export to KML / GPX / GeoJSON / CSV for the selected aircraft | `trackExport` |
| X28 | Polite client-side rate limiter (token bucket per host) | `rateLimiter` |
| X30 | Keyboard shortcuts (`F` / `Esc` / `M` / `V` / `A` / `S` / `N` / `R` / `B` / `?`) + help overlay | `#helpOverlay` |
| X31 | Tab-paused pill ("Paused — return to tab") | `#pausedPill` |
| L19 | User-configurable trail retention (24 h / 7 d / 14 d / 30 d) wired to existing IndexedDB cleanup | settings panel |
| L20 | Map bookmark system (verified already shipped — left in place) | `bookmarks-panel` |
| X18 | hexdb.io photo fallback (verified already shipped at priority 7 of the photo cascade) | `loadAircraftPhoto` |
| — | `CHANGELOG.md` `%Y->-` placeholder repaired; migrated to Keep-a-Changelog format | `CHANGELOG.md` |
| — | `CLAUDE.md` reconciled with actual JS/Leaflet stack | `CLAUDE.md` |

### Round 2
| ID | What | Where |
|---|---|---|
| X3 | plane-alert-db daily sync from GitHub raw (mil / gov / pol / pia / civ / categories) | `planeAlertSync` |
| X4 | Webhook alert sink — Generic JSON / Discord / ntfy.sh — wraps `alertSystem.showAlert` | `alertWebhook` |
| X6 | Coincidence detector (formation/refuel/escort) — O(N²) per-tick, 5 nm / 2000 ft thresholds, cooldown | `coincidenceDetector` |
| X10 | Custom GeoJSON overlay loader — file picker + raw URL + named-layer management | `geojsonLoader` |
| X11 | FAA TFR polygons overlay — tfr2go JSON mirror with FAA XML fallback | `tfrOverlay` |
| X14 | Heatmap density overlay — built on a custom canvas layer (no external plugin) | `heatmapLayer` |
| X15 | Ease-out marker interpolation (quadratic) — smoother feel than the previous linear path | `animateAircraft` |
| X21 | AWC TAF + nearby-PIREP fetchers added to `weatherSystem` | `weatherSystem.getTAF` / `getPIREPsNearby` |
| X25 | URL filter API extension — `?focus=HEX`, `?center=lat,lng`, `?zoom=n`, `?overlay=<url>`, `?embed=1` | init block |
| X26 | Embed mode — `?embed=1` adds `body.embed`, hides chrome | CSS + init |
| X29 | SW cache version bumped to `viptrack-v4.15` so prior caches retire cleanly | ServiceWorker |
| X32 | A11y — `--text-muted` bumped from `#666` to `#8a8a9c` (~4.6:1 contrast), `prefers-reduced-motion` honoured | `<style>` |
| NEW | OSINT report copy-to-clipboard (one button, ready-to-paste summary) | `copyOsintReport` |
| NEW | MGRS / Maidenhead / DMS coord helpers (Maidenhead + DMS shipped; MGRS deferred until proj4 acceptable) | `coords` |
| NEW | Sun position (alt / az) for OSINT shadow correlation | `sunPosition` |
| NEW | Viewport-as-CSV export — every aircraft visible right now, one click | `exportViewportCsv` |

This document is a working punch-list, not marketing. Each item carries a one-line rationale and a citation in the [Appendix](#appendix--sources). Tiers: **Now** (this release), **Next** (1–2 releases out), **Later** (deferred but planned), **Under Consideration** (needs validation), **Rejected** (closed with reasoning).

---

## Snapshot — what the repo already ships

Audit of `index.html` (8,864 LOC) finds the README understates the app. Implemented phases include:

| Phase | What | Where |
|---|---|---|
| 5 | URL deep linking + share, playback controls | `// Phase 5` |
| 6 | Airport Board, airspace labels, 3D View placeholder | `// Phase 6` |
| 8 | Enhanced search with filters/history | `// Phase 8` |
| 10 | Route prediction + ETA + enhanced altitude chart | `// Phase 10` |
| 11 | External tracker links, NOTAMs, runway visualization | `// Phase 11` |
| 12 | Theme grid, trail direction arrows, notification centre | `// Phase 12` |
| 13 | Multi-select + comparison panel | `// Phase 13` |
| 14 | Time machine controls | `// Phase 14` |
| 15 | Mobile experience, haptics, swipe-to-dismiss | `// Phase 15` |
| 16 | Offline mode manager, data source manager, auto-retry, error recovery, circuit breaker | `// Phase 16` |

Reference data integrated: tar1090-db, plane-alert-db (mil/gov/pol/pia/civ), OpenFlights airlines + alliances, OurAirports (airports, runways, frequencies, navaids), planespotters.net photos, aviationweather.gov METAR + NOTAM, Wikipedia REST. Storage: IndexedDB (`databases` / `userData` / `trailHistory`) with localStorage fallback. ServiceWorker with per-host caching strategy, manifest synthesised as a Blob.

This roadmap focuses on what is **not** yet shipped or is materially incomplete.

---

## Tier — NOW (block on release)

These are correctness/security/legal items. Ship before adding new surface area.

| # | Item | Why | Effort | Source |
|---|---|---|---|---|
| ~~N1~~ | ~~Remove hardcoded `clientId` / `clientSecret` from `CONFIG`~~ — **kept by design** (2026-05-17 owner decision). Documented here so future maintainers don't "fix" it without checking. | n/a | — | repo |
| N2 | **DOMPurify on every `bindPopup` / `bindTooltip` / `setContent`** sink. Leaflet 1.9.4 documents these as HTML-rendering by design (CVE-2025-69993, disputed by Leaflet) — any aircraft field from a third-party feed becomes a stored-XSS vector. Add `<script src="…dompurify…" integrity=…>` and a thin `safeHTML()` helper. | Security | S | [A3](#a-security-advisories), [A4](#a-security-advisories) |
| N3 | **Meta-tag CSP**. GitHub Pages cannot set headers; ship `<meta http-equiv="Content-Security-Policy" …>` allowing only the four ADS-B feeds, GitHub raw, cdnjs, aviationweather.gov, planespotters, Wikipedia, RainViewer. | Security | S | [A5](#a-security-advisories) |
| N4 | **SRI hashes on every CDN `<script>` / `<link>`** — Leaflet, pako, future DOMPurify. Pin exact versions; never `@latest`. | Security | S | [A6](#a-security-advisories) |
| N5 | **Honor LADD + PIA opt-outs** in registration lookups. When a hex is in the current FAA PIA list, suppress N-number resolution and surface "Privacy ICAO Address (PIA) — operator anonymised". Sync the PIA CSV daily from `plane-alert-db`. | Legal / ethics | S | [A7](#a-osint--privacy), [A8](#a-osint--privacy) |
| N6 | **Ethical-use disclaimer banner** on first load: source data is public ADS-B; respect privacy; not for operational use. Section 803 of the 2024 FAA Reauthorization Act + IMY's June 2025 FR24 reprimand make this prudent. | Legal | XS | [A9](#a-osint--privacy), [A10](#a-osint--privacy) |
| N7 | **Repair `CHANGELOG.md`** — current `v0.0.1` line contains the literal `%Y->-` strftime placeholder. Stamp the date and migrate entries to Keep-a-Changelog. | Hygiene | XS | repo |
| N8 | **Reconcile `CLAUDE.md`** — it claims the stack is Python and points at `download-type-photos.py` and a non-existent `skytrack_download_data.py`. The app is a JS/Leaflet SPA; fix the file. | Hygiene | XS | repo |
| ~~N9~~ | ~~Drop the `mparker-api-client` artefact~~ — **kept by design** alongside ~~N1~~. | n/a | — | repo |

**Theme: ship the v0.1.0 release on a clean security + legal baseline before adding features.**

---

## Tier — NEXT (1–2 releases out)

Features with clear demand, low-to-medium effort, and direct alignment with the mil/VIP/OSINT focus.

### Alerts, watchlist, intel

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|
| X1 | **Emergency squawk auto-highlight** (7500 hijack / 7600 NORDO / 7700 general) — flashing marker, audible tone (opt-in), pinned to top of list. Cross-tracker analyst essential; no incumbent OSS does it well. | Mil/OSINT | S | [B1](#b-oss-projects), [C1](#c-community-signal) |
| X2 | **Multi-rule named watchlists** ("Air Force One", "Russian VIP", "Drone activity", "Celebrity jets"). Each group is a JSON ruleset (hex set, regex callsign, type, country, altitude band, geofence). Today's watchlist is a flat hex bag. Direct response to ADSBx Discourse "alert one at a time" + dump1090 #155/#156. | Watchlist | M | [C2](#c-community-signal), [C3](#c-community-signal) |
| X3 | **Plane-alert-db live ingest** — fetch `plane-alert-mil.csv`, `plane-alert-gov.csv`, `plane-alert-pol.csv`, `plane-alert-pia.csv`, `plane-alert-civ.csv`, `plane-alert-categories.csv` daily from `sdr-enthusiasts/plane-alert-db`. The repo already vendors copies dated Mar 7 in `data/`; switch to scheduled sync + IndexedDB diff. ~15.9k aircraft, 53 categories, Open Database License. | Data | S | [B2](#b-oss-projects) |
| X4 | **Webhook / Bluesky / Telegram / Discord / ntfy / RSS alert sinks**. User pastes a webhook URL into settings; alert events POST a JSON envelope. Bluesky has eclipsed X in OSINT-aviation reach since the elonjet-Dec-2022 era. | Notifications | M | [B3](#b-oss-projects), [B4](#b-oss-projects), [C4](#c-community-signal) |
| X5 | **Geofence editor + alert** — Leaflet draw polygon/circle, save as named area, alert on entry/exit. Closest peer (`military-aircraft-tracker.com`) ships a 400-site preset library — we can match it with a seed `data/geofences/sensitive-sites.geojson`. | Mil/OSINT | M | [D1](#d-commercial-trackers), [B5](#b-oss-projects) |
| X6 | **Coincidence detector** — flag any two tracked aircraft within X nm / Y ft of each other (refuelling, fighter escort, formation flight). Roadmap had this as a wish; tar1090 #386 (MRTT loops + AWACS orbits) confirms analyst appetite. | Mil/OSINT | M | [B6](#b-oss-projects) |
| X7 | **PIA rotation timeline** — the FAA Dec 2024 update sets PIA hex rotation to 20-day default. Track previous-PIA history per operator so a jet doesn't "vanish" when the hex flips. | Mil/OSINT | M | [A11](#a-osint--privacy) |

### Visualisation & map

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|
| X8 | **Direction-of-flight line** projected from each marker (1–10 min lookahead, user-configurable). Open in tar1090 (#324) — universal analyst request. | Map | XS | [C5](#c-community-signal) |
| X9 | **Ruler / draw / measure tool** — click-click distance + bearing, KM/NM toggle. Standoff-distance is a daily analyst task. tar1090 #306. | Map | S | [C6](#c-community-signal) |
| X10 | **Custom GeoJSON overlay loader** — drag-drop or URL paste. Lets users bring ADIZ lines, MOA polygons, AWACS racetrack orbits, low-fly areas without code changes. tar1090 #433 + #386 + #414. | Map | S | [C7](#c-community-signal), [C8](#c-community-signal) |
| X11 | **FAA TFR overlay** — render polygons from `tfr.faa.gov/tfr3/export/xml`. VIP movement TFRs correlate directly with VIPTrack's primary use case and *no surveyed OSS project ships this*. | Mil/OSINT differentiator | M | [E1](#e-apis--standards) |
| X12 | **Curated mil-pattern overlays** (preset, toggleable): AWACS / E-3 / E-7 orbits, KC-46 / MRTT refuelling racetracks, drone CAPs, NOTAM-driven exercise boxes. Ship as `data/overlays/*.geojson` + a picker. | Mil/OSINT differentiator | M | [C8](#c-community-signal) |
| X13 | **Receiver-coverage polygon** for any user-provided tar1090/feeder URL — borrows wiedehopf/graphs1090's polar plot idea, but rendered on the live map so feeder operators see range gaps. | Map | M | [B7](#b-oss-projects) |
| X14 | **Heatmap / density layer** of mil activity over user-selected window (1 h / 24 h / 7 d). Read from local `trailHistory`. tar1090 + readsb both ship this; commercial tier-paywalls it on FR24. | Map | M | [B8](#b-oss-projects), [D2](#d-commercial-trackers) |
| X15 | **Smoother marker interpolation** with configurable Hz target. tar1090 #404 + FlightAirMap #329 confirm this is the single most-cited "feels worse than FR24" complaint. Tune `requestAnimationFrame` loop, add velocity prediction. | UX | S | [C9](#c-community-signal) |
| X16 | **Mobile iOS Safari render audit** — multiple community reports of empty maps and lag on iOS. Specifically test sprite-icon `image-rendering`, passive touch listeners, and the swipe-to-dismiss panel against Safari 17/18. | UX | S | [C10](#c-community-signal) |

### Data sources & enrichment

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|
| X17 | **ADSBdb route lookup** (`api.adsbdb.com/v0/callsign/{flight}`) — free, no auth, CORS-open. Resolves callsign → origin / midpoint / destination ICAOs. Direct upgrade to the existing route panel. | Data | S | [E2](#e-apis--standards) |
| X18 | **Hexdb.io photo fallback** for hexes planespotters has no thumb for — common with mil aircraft. Free, CORS-open. | Data | S | [E3](#e-apis--standards) |
| X19 | **ADSB.fi as fourth rotating source** in `dataSourceManager.sources`. v2-compatible, 1 req/sec, free, CORS-open. Cheap resilience win. | Data | XS | [E4](#e-apis--standards) |
| X20 | **OpenSky as historical-only fallback** behind an optional user-supplied OAuth2 client (OpenSky removed basic auth 2026-03-18). Used solely for "what was tracked yesterday" replays, never the live loop. | Data | M | [E5](#e-apis--standards) |
| X21 | **AWC TAF + SIGMET + PIREP layers** to complement existing METAR. Same host, free, no key. Schema refreshed Sept 2025. | Weather | S | [E6](#e-apis--standards) |
| X22 | **NEXRAD radar overlay** via NOAA `nowcoast` WMS as an alternative to RainViewer (US-only but free, higher resolution). User toggle. | Weather | S | [E7](#e-apis--standards) |
| X23 | **FAA NASR special-use airspace polygons** — render restricted / prohibited / MOA / warning areas. Free 28-day refresh cycle, CSV/AIXM. | Mil/OSINT | M | [E8](#e-apis--standards) |

### Export / interop

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|
| X24 | **Export selected aircraft track to KML / GPX / GeoJSON / CSV**. The bestknown OSS project shipping this is FlightAirMap. No commercial competitor below the Aviator+ tier exposes this. Direct analyst value: hand a `.kml` to Google Earth for post-mortem. | Export | S | [B9](#b-oss-projects) |
| X25 | **URL filter API** — `?mil=1&type=B52&country=RU&geofence=GEOF1` rather than just `?hex=ABCDEF`. Docker-planefence's regex query API is the model. Makes the embed-widget story trivial. | Sharing | S | [B10](#b-oss-projects) |
| X26 | **Embeddable widget mode** — `?embed=1` strips chrome, exposes only the map + a single watchlist group. Documented in `README.md` as the supported way to drop VIPTrack into a news article or blog. | Sharing | S | roadmap |
| X27 | **`navigator.share` already exists** (`index.html:7437`) — extend to share aircraft *with current trail* as a generated PNG via OffscreenCanvas; falls back to copy-link on unsupported browsers. | Sharing | S | repo |

### Hardening & polish

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|
| X28 | **Polite client-side rate limiting** — ADS-B One is 1 req/sec; ADSB.lol uses dynamic limits. Add `tokenBucket` per source; back off on 429. | Resilience | S | [E9](#e-apis--standards) |
| X29 | **ServiceWorker cache versioning + integrity** — current SW is `viptrack-v4.14`; add a manifest hash and bust the cache on schema bumps; never cache API JSON > 60 s; tile cap from 600 → 1000 with explicit LRU. | Resilience | S | repo |
| X30 | **Keyboard shortcuts**: `F` follow / `Esc` deselect / `M` mil filter / `V` VIP filter / `S` search / `?` help. Tier-1 in the prior tools/`skytrack-improvement-roadmap.md` and trivial. | UX | XS | tools/ |
| X31 | **Tab Visibility API** — formalise existing pause behaviour; surface "paused — return to tab to resume" pill so users understand why nothing updates. | UX | XS | repo |
| X32 | **Accessibility pass** — most controls have `aria-label`, but contrast on `--text-muted: #666` over `#1a1a2e` is below WCAG AA. Add `prefers-reduced-motion` for marker animation. | A11y | S | repo |

---

## Tier — LATER (planned, but deferred)

Bigger lifts. Worth doing; not on the critical path.

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|
| L1 | **3D globe view** via Cesium 1.130+ behind an `?3d=1` flag. The `// Phase 6` block already reserves a 3D container — wire it up. Cesium 1.140 (Apr 2026) includes regression fixes; CZML time-dynamic format fits the existing time-machine. | Visualisation | L | [E10](#e-apis--standards), [B11](#b-oss-projects) |
| L2 | **WebGL marker layer** via deck.gl `IconLayer` + `TripsLayer` over MapLibre 5 OR Leaflet-via-leafgl. Leaflet's DOM-based markers collapse above ~500–800 markers; PIA-on alone can produce that. Browser support: WebGPU ships in Chrome/Edge/Firefox 141+, Safari 26. Keep Leaflet path as default; expose `?renderer=webgl`. | Performance | L | [B12](#b-oss-projects), [E11](#e-apis--standards) |
| L3 | **Real Cesium-based playback / scrubber** for historical replay from `globe.airplanes.live/data/traces/{hex}`. Replaces the current playback stub. | Visualisation | L | [E12](#e-apis--standards) |
| L4 | **FAA Releasable Aircraft Registry** ingest — ~300k US N-numbers + owner. Pre-shard into `data/faa/master-{A-Z}.json` to keep the cold-start budget down. Skip whenever a hex is on the PIA list (see N5). | Data | M | [E13](#e-apis--standards) |
| L5 | **Optional ACARS context panel** — link out to `app.airframes.io/flights/{callsign}` initially; add native JSON ingest if airframes.io ever exposes a public REST surface. | Mil/OSINT | M | [E14](#e-apis--standards) |
| L6 | **OpenAIP airspace overlay** (Class A–G, with key) — opt-in, user-supplied API key in settings, no key shipped in source. | Mil/OSINT | M | [E15](#e-apis--standards) |
| L7 | **Plugin / overlay manifest** — a `plugins/manifest.json` shipping a curated list of GeoJSON overlays, mil-pattern presets, and (later) JS plugin files loaded via `import()` with explicit user opt-in. Mirrors VRS plugin model. | Extensibility | L | [B13](#b-oss-projects) |
| L8 | **i18n** — externalise the ~120 user-visible strings into `data/i18n/{lang}.json`, default English, ship `es`, `fr`, `de`, `ru`, `uk` first. FlightAirMap and BelugaProject both demonstrate the pattern. | i18n | M | [B14](#b-oss-projects) |
| L9 | **OPFS for the heavy reference shards** — `aircraft.csv` is 33 MB; today it round-trips through IndexedDB. Move to OPFS sync handles inside a Worker; cold-start should drop sub-second on a warm cache. | Performance | M | [E16](#e-apis--standards) |
| L10 | **PWA → Play Store via Trusted Web Activity** — Bubblewrap wraps `index.html` into an Android shell, zero code changes. iOS path is Capacitor (more work; defer to UC1). | Distribution | M | [E17](#e-apis--standards) |
| L11 | **Aircraft-type photo enrichment pipeline** — `download-type-photos.py` exists but only 100 types covered (`assets/type_photos`). Run to completion (~500–1000 types) and document the workflow in `tools/`. | Data | S | repo |
| L12 | **Periodic Background Sync** for the watchlist (Chromium-installed PWAs only) — refreshes mil/VIP/PIA databases every 12 h with zero user interaction. | UX | M | [E18](#e-apis--standards) |
| L13 | **Web Share Target** — accept a shared hex / N-number from another app and auto-zoom. | UX | XS | [E19](#e-apis--standards) |
| L14 | **Stats dashboard** (graphs1090 style) — per-session: messages seen, sources used, latency histogram, mil-vs-vip-vs-pia rolling counts. Helps users sanity-check feed health. | Observability | M | [B15](#b-oss-projects) |
| L15 | **Auto-tagging via track-shape heuristics** — orbital pattern → tanker/AWACS; straight-line FL400+ → transit; sustained holding → traffic hold. Lightweight rule engine; ML deferred to UC. | Mil/OSINT | M | [F1](#f-academic) |
| L16 | **MapLibre 5 / vector basemap option** — Stadia Alidade Smooth Dark or CARTO Voyager. Smoother zooms than raster, free at non-commercial tier. | Visualisation | M | [E20](#e-apis--standards), [E21](#e-apis--standards) |
| L17 | **Squawk-7700 history feed** — pin events as they occur, attribute via plane-alert-db, expose `?emergency=last24h`. | Mil/OSINT | S | [B16](#b-oss-projects) |
| L18 | **Curated "Interesting / Notable / Historic" mode** — already partly there (`badgers-best.csv`, `interesting.csv`); surface a UI mode that shows only those and not commercial. | Mil/OSINT | S | repo |
| L19 | **Trail TTL + retention controls** — IndexedDB `trailHistory` will grow unbounded; expose user-configurable retention (24 h / 7 d / 30 d). | Storage | S | repo |
| L20 | **Map bookmark system** — save named camera positions ("Ramstein", "Diego Garcia", "KJBER"). Trivial; surprisingly missing. | UX | XS | tools/ |

---

## Tier — UNDER CONSIDERATION (needs validation)

Items where impact, scope, or alignment is uncertain. Listed so they don't get silently resurrected as Now/Next without an explicit decision.

| # | Item | Open question |
|---|---|---|
| UC1 | **iOS App Store via Capacitor** | App-Store review of a flight-tracker citing privacy ICAO might be friction-heavy. Validate by submitting a TestFlight build before committing real engineering. |
| UC2 | **ML trajectory prediction** (RNN / Transformer per [F2](#f-academic), [F3](#f-academic), [F4](#f-academic)) | Inference cost in-browser is fine; the labelled dataset to train against is the blocker. Defer until we have ≥30 days of `trailHistory` shipped in production. |
| UC3 | **AI caption / classification** ("E-6B Mercury, likely TACAMO mission, routing KOFF") | Risk: hallucinated context on a watched aircraft is worse than no context. If revived, drive from rules + plane-alert-db tags, not an LLM call. |
| UC4 | **WebUSB ingest from a local RTL-SDR** | Chromium-only; useful for the SDR hobbyist sliver only. May fit a separate `local.html` companion rather than the main app. |
| UC5 | **Comm-B BDS 4.0/4.4/5.0/6.0 decoding** | Public ADS-B feeds give us decoded ADS-B already; raw Mode-S is only available from a local receiver. Couple with UC4 or drop. |
| UC6 | **Authentication / per-user accounts** | Contradicts the static-site, GitHub-Pages-hosted, zero-server posture. Only revisit if someone wants to fork into a SaaS. Otherwise rejected. |
| UC7 | **AR overhead-identify** (FR24 / Plane Finder feature) | Phone-only; meaningful work; debatable fit with the OSINT-desk audience. |
| UC8 | **Receiver federation / "feed me from your tar1090"** | Cool, but treads on tar1090's own scope. Better as a documented adapter than a maintained feature. |
| UC9 | **LiveATC.net audio panel** | Auth + ToS limits make embedding fragile. Link-out is fine; embed risks breakage. |
| UC10 | **Contrail / wake correlation** (per [F5](#f-academic), [F6](#f-academic)) | Geostationary contrail detection is bleeding-edge research, not a 2026 user feature. |

---

## Tier — REJECTED (and why)

| Item | Why rejected |
|---|---|
| Backend API / Node.js server | Contradicts the single-file, zero-build, GH-Pages-deployable charter. The prior `tools/skytrack-improvement-roadmap.md` Tier 4 entry is superseded. |
| WebSocket-based push feed | None of the four current public ADS-B feeds offer WebSocket. When one does, revisit as a NEXT item — not now. |
| Charging / paid tier | MIT license + community trust posture rules this out. |
| Dropping Leaflet for MapLibre wholesale | Leaflet 1.9.4 still ships, has near-zero supply-chain surface, and matches the "boring tech" charter. MapLibre is an *additive* renderer (see L2 / L16), not a replacement. |
| FR24 API integration | Free FR24 API ends 2026-04-30. Building on a corpse is not a roadmap. |
| Mocking commercial-tracker FR24/AirNav 3D "cockpit view" | Bandwidth-expensive, low analyst value, and clashes with the "no commercial noise" thesis. |
| Hosted social leaderboard / share-feed | Out of scope for a single-file OSINT tool; trivial to harm chain. |

---

## Cross-cutting themes (every Now/Next item maps to one)

1. **Stop the bleed** — N1–N9: security, legal, hygiene before features.
2. **Make alerts and watchlists actually useful** — X1, X2, X3, X4, X5, X7, X17.
3. **Give analysts the affordances they keep asking for** — X6, X8, X9, X10, X11, X12, X13.
4. **Treat the data plumbing like a product** — X3, X19, X20, X21, X22, X23, X28, X29.
5. **Fix the experience that drives users to commercial trackers** — X14, X15, X16, X24, X25, X26, X27, X30, X31, X32.

---

## Coverage check (Phase 5 self-audit)

| Category | Covered? |
|---|---|
| Security | N1–N4, X29 |
| Accessibility | X32 |
| i18n / l10n | L8 |
| Observability / telemetry | L14, X31 |
| Testing | *Gap — see below* |
| Docs | N7, N8, X26 |
| Distribution / packaging | L10, L13, UC1 |
| Plugin ecosystem | L7 |
| Mobile | X16, L10 |
| Offline / resilience | X28, X29 + Phase 16 already shipped |
| Multi-user / collab | Rejected (UC6) |
| Migration paths | L2 (additive renderer), L16 (additive basemap) |
| Upgrade strategy | SW versioning in X29; SRI/pinning in N4 |

**Testing is the thinnest area in this roadmap.** A single-file app with no build step traditionally relies on manual smoke tests. Recommended addition for a future revision: a Playwright suite in `tools/e2e/` covering the cold-start path, the watchlist alert path, the swipe-to-dismiss panel, the `?hex=` deep link, and the offline-mode banner. Not promoted to Now/Next yet because the *correctness* gaps in N1–N4 are higher leverage; revisit once those land.

---

## Older roadmap (preserved for traceability)

Pre-2026-05-17 entries that survive into this revision:

- "Cesium 3D globe alternate view" → now **L1** with concrete renderer choice and a flag.
- "Flight path playback / scrubbing with timeline" → already shipped as Phase 14 time-machine; refinement is **L3**.
- "Cluster markers at low zoom" → covered by **L2** WebGL renderer plan.
- "Saved alerts, Webhook / Discord / Telegram" → **X4**.
- "Geofence alert (polygon draw)" → **X5**.
- "Coincidence detector" → **X6**.
- "Export track as KML / GeoJSON / GPX" → **X24**.
- "Delta updates from the feed" → handled via X29 + future when feeds support diff.
- "Tab-visibility pausing — formalise" → **X31**.
- "Audio squawk alerts (7500/7600/7700)" → **X1**.
- "Weather overlay (NEXRAD, TFRs, ADIZ)" → **X11**, **X22**, **X23**, **X10**.
- "AI caption" → **UC3**.
- "Embeddable widget" → **X26**.
- "NOTAM feed integration" → already shipped as Phase 11.

Items deliberately not carried forward:
- "Per-country military hex-range editor (UI)" — superseded by **X3** live ingest of `plane-alert-mil.csv` (which already encodes ranges via the categorised CSV).
- "Optional user-supplied RTL-SDR / dump1090 feed URL for local ingest" — kept alive as **UC4** + **UC8**; recognised as niche.

---

# Appendix — Sources

Every claim above must trace to a line in one of these tables.

## A. Security advisories
- **A1** OWASP MASVS M1:2024 — Improper Credential Usage. https://www.sourcery.ai/vulnerabilities/hardcoded-api-keys-javascript
- **A2** Sourcery — Hardcoded API keys in JavaScript. https://dev.to/jocanola/understanding-owasp-m1-2024-improper-credential-usage-in-react-nativeexpo-and-how-to-mitigate-it-2657
- **A3** CVE-2025-69993 (Leaflet `bindPopup`/`bindTooltip` HTML rendering, disputed by maintainers). https://www.sentinelone.com/vulnerability-database/cve-2025-69993/
- **A4** Leaflet issue 10214 — maintainer position. https://github.com/Leaflet/Leaflet/issues/10214
- **A5** Isaac Smith — Add CSP to GitHub Pages via meta tag. https://www.isaacsmith.us/blog/2022/add-csp-to-github-pages
- **A6** MDN — Subresource Integrity. https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Subresource_Integrity

## A. OSINT & privacy
- **A7** NBAA — Privacy ICAO Address (PIA) program. https://nbaa.org/aircraft-operations/security/privacy/privacy-icao-address-pia/
- **A8** plane-alert-pia.csv. https://github.com/sdr-enthusiasts/plane-alert-db/blob/main/plane-alert-pia.csv
- **A9** ppc.land — IMY reprimand against FR24 (June 2025). https://ppc.land/flightradar24-receives-reprimand-for-violating-aircraft-data-privacy-rights/
- **A10** Fortune — Farewell ElonJet (April 2025). https://fortune.com/2025/04/01/faa-private-jet-plane-tracking-elon-musk-taylor-swift-jack-sweeney/
- **A11** GeneralAviationNews — FAA Updates ADS-B Privacy Program (Dec 2024). https://generalaviationnews.com/2024/12/12/faa-updates-ads-b-privacy-program/

## B. OSS projects
- **B1** flightjar — squawk auto-alerts + Telegram/ntfy/webhook sinks. https://github.com/MrSuttonmann/flightjar
- **B2** sdr-enthusiasts/plane-alert-db — 15,952 aircraft / 53 categories. https://github.com/sdr-enthusiasts/plane-alert-db
- **B3** kx1t/docker-planefence — Discord / Mastodon / Twitter alert sinks, screenshot service. https://github.com/kx1t/docker-planefence
- **B4** Jxck-S/plane-notify — takeoff/landing detection patterns. https://github.com/Jxck-S/plane-notify
- **B5** military-aircraft-tracker.com — 400+ preset geofenced sensitive sites.
- **B6** wiedehopf/tar1090 #386 — MRTT refuelling loops + AWACS orbits. https://github.com/wiedehopf/tar1090/issues/386
- **B7** wiedehopf/graphs1090 — polar coverage plot. https://github.com/wiedehopf/graphs1090
- **B8** wiedehopf/tar1090 — heatmap + history snapshots. https://github.com/wiedehopf/tar1090
- **B9** Ysurac/FlightAirMap — KML and GPX export. https://github.com/Ysurac/FlightAirMap
- **B10** kx1t/docker-planefence REST regex query API. https://github.com/kx1t/docker-planefence
- **B11** CesiumGS/cesium 1.130+ releases. https://github.com/CesiumGS/cesium
- **B12** MapLibre GL JS — WebGL vector renderer. https://github.com/maplibre/maplibre-gl-js
- **B13** vradarserver/vrs — plugin architecture reference. https://github.com/vradarserver/vrs
- **B14** Ysurac/FlightAirMap — multi-language scaffolding. https://github.com/Ysurac/FlightAirMap
- **B15** wiedehopf/graphs1090 — stats panels. https://github.com/wiedehopf/graphs1090
- **B16** sdr-enthusiasts/plane-alert-db emergency categorisation entries. https://github.com/sdr-enthusiasts/plane-alert-db

## C. Community signal
- **C1** Squawk7700.com / adsb.oarc.uk emergency feeds. https://www.squawk7700.com/ and https://adsb.oarc.uk/emergencies/
- **C2** ADSBx Discourse — type-alert one-at-a-time. https://adsbx.discourse.group/t/introducing-aircraft-type-alerting-for-feeders-your-sky-watch-just-got-smarter/842
- **C3** dump1090 #155 "FEATURE REQ: Favourites" + #156 nicknames. https://github.com/flightaware/dump1090/issues/155 and https://github.com/flightaware/dump1090/issues/156
- **C4** planefence #212 Bluesky support / #211 RSS / #244 Telegram. https://github.com/sdr-enthusiasts/docker-planefence/issues/212
- **C5** tar1090 #324 direction-of-flight line. https://github.com/wiedehopf/tar1090/issues/324
- **C6** tar1090 #306 ruler / draw. https://github.com/wiedehopf/tar1090/issues/306
- **C7** tar1090 #433 custom GeoJSON overlay. https://github.com/wiedehopf/tar1090/issues/433
- **C8** tar1090 #386 MRTT loops + #414 Luftwaffe low-fly areas. https://github.com/wiedehopf/tar1090/issues/386 and https://github.com/wiedehopf/tar1090/issues/414
- **C9** tar1090 #404 smoothing. https://github.com/wiedehopf/tar1090/issues/404
- **C10** tar1090 #387 iOS/web lag; HN comment thread "fully empty map on iOS safari". https://github.com/wiedehopf/tar1090/issues/387 and https://news.ycombinator.com/item?id=43022603

## D. Commercial trackers
- **D1** military-aircraft-tracker.com — closest peer; geofence preset library. https://military-aircraft-tracker.com/
- **D2** FR24 premium tiers paywalling history, weather, dashboards. https://www.flightradar24.com/premium

## E. APIs & standards
- **E1** FAA TFR XML feed. https://tfr.faa.gov/tfr3/export/xml
- **E2** ADSBdb. https://github.com/mrjackwills/adsbdb and https://api.adsbdb.com
- **E3** Hexdb.io API. https://hexdb.io/
- **E4** ADSB.fi opendata. https://opendata.adsb.fi/api/ and https://github.com/adsbfi/opendata
- **E5** OpenSky REST API (OAuth2 since 2026-03-18). https://openskynetwork.github.io/opensky-api/rest.html
- **E6** AWC Data API. https://aviationweather.gov/data/api/
- **E7** NOAA nowcoast NEXRAD WMS. https://nowcoast.noaa.gov/arcgis/services/nowcoast/radar_meteo_imagery_nexrad_time/MapServer/WMSServer?request=GetCapabilities&service=WMS
- **E8** FAA NASR Subscription. https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/
- **E9** ADSB.lol docs (dynamic rate limit) and ADS-B One 1 req/sec note. https://api.adsb.lol/docs
- **E10** Cesium release notes. https://cesium.com/blog/2025/06/02/cesium-releases-in-june-2025/
- **E11** caniuse — WebGPU. https://caniuse.com/webgpu
- **E12** airplanes.live API guide — trace endpoints. https://airplanes.live/api-guide/
- **E13** FAA Releasable Aircraft Database. https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download
- **E14** Airframes.io. https://app.airframes.io/ and https://docs.airframes.io/
- **E15** OpenAIP API docs. https://docs.openaip.net/
- **E16** Origin Private File System. https://web.dev/articles/origin-private-file-system
- **E17** Capacitor / Bubblewrap TWA. https://capacitorjs.com/docs/android/deploying-to-google-play
- **E18** Chrome — Periodic Background Sync. https://developer.chrome.com/docs/capabilities/periodic-background-sync
- **E19** MDN — share_target. https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/share_target
- **E20** Stadia Maps free tier. https://stadiamaps.com/pricing/
- **E21** CARTO basemaps for non-commercial. https://docs.carto.com/faqs/carto-basemaps

## F. Academic
- **F1** MDPI — Evolution and Taxonomy of DL Models for Aircraft Trajectory Prediction (Oct 2025). https://www.mdpi.com/2076-3417/15/19/10739
- **F2** SATF spatial-awareness + time-frequency hybrid (June 2025). https://www.tandfonline.com/doi/full/10.1080/17538947.2025.2512592
- **F3** IMM-Informer (April 2025). https://pmc.ncbi.nlm.nih.gov/articles/PMC12031469/
- **F4** Nature Sci Reports HiFormer + sparse-satellite (2025). https://www.nature.com/articles/s41598-025-27064-z
- **F5** AMT — Benchmarking algorithms attributing contrails to flights (2025). https://amt.copernicus.org/articles/18/3495/2025/
- **F6** GRL — Contrail Observation Limitations Using Geostationary Satellites (2025). https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2025GL118386
