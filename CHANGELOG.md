# Changelog

## [Unreleased]

### Added
- One settings surface for API credentials. Every key slot (OpenAIP, OpenSky OAuth2) is listed with whether a key is held, why the service needs one, and where to get it, with a Clear control per slot. The registry never returns a stored value — only whether one is present — and a runtime test plants sentinel keys and asserts none reach the local-state backup, the diagnostics export, the source stats, or the settings surface itself.

- The regex filter now reaches the type code and type description, so tar1090-style patterns work — `B73.` for the 737 family, `H..` for helicopters, `L2J` for twinjets, `B739|B39M`, `^(?!A320)`. It previously matched only callsign and registration, which left the most useful patterns inert. Patterns are length-bounded, nested quantifiers are refused before compiling, an invalid pattern reports inline against the input instead of as a transient toast, and a live count shows how many tracked aircraft the pattern matches.

- Analyst views are shareable as links. A "Copy view link" control in the toolbar produces a URL carrying the filter mode, search query, map centre and zoom, and the selected aircraft, and opening it restores all of them — so a desk finding can be handed to someone else instead of described. A privacy-protected aircraft is never named in the URL, which a runtime test checks against the marker the product actually reads.

### Fixed
- In-app back navigation works on Android 16. From API 33 the platform stops calling `onBackPressed()` once predictive back is enabled, and on API 36 — which this app targets — that is the default, so the back gesture was bypassing the WebView history handler entirely. Back now registers through `OnBackInvokedDispatcher` with the override kept for API 24–32, and the manifest opts in explicitly. The upgraded lint is what surfaced this.

### Changed
- Android toolchain moved to AGP 8.13.2 and Gradle 8.14.3 (from 8.9.1 / 8.11.1).

### Accessibility
- Meets WCAG 2.2 SC 2.5.7 (Dragging Movements, AA): a Leaflet map can only be panned by dragging, so the map now carries single-pointer pan controls beside the zoom control, each labelled and keyboard-operable.
- Meets WCAG 2.2 SC 2.5.8 (Target Size Minimum, AA): the mobile filter chips rendered 21px tall and the mobile settings search input 17px. Both now clear 24×24 CSS px, and a runtime test checks every visible interactive target at desktop and phone widths.


## [v0.6.0] - 2026-08-18

### Fixed
- Restored live aircraft loading. Every public ADS-B aggregator has dropped `Access-Control-Allow-Origin`, and the source manager was short-circuiting relayed sources to "degraded" on GitHub Pages, so the hosted build could not reach a single feed. All four feeds are now marked relay-only and checked through the CORS relay.
- Reordered the CORS relay list and removed `api.codetabs.com`, which no longer answers and only consumed the request timeout.
- Corrected the ADSB.fi endpoint shape: it serves `/lat/{lat}/lon/{lon}/dist/{d}`, not `/point/...`, so every health check against it had been failing with HTTP 400. ADSB.fi has no `/pia` endpoint, which is now modelled rather than fetched twice.
- The connectivity probe followed two hardcoded hosts that now answer HTTP 403, reporting "offline" on a healthy connection. It now probes whichever source the manager currently prefers.
- Dropped the Android-only pin to Airplanes.live, which now requires approved API access; every platform follows measured source health.
- Skipped the guaranteed-to-fail direct fetch before relaying for hosts known not to send CORS headers, removing one failed round-trip per poll.
- Repaired the weather radar overlay. NOAA retired the nowCOAST ArcGIS MapServer path (HTTP 403); the layer now uses the GeoServer `base_reflectivity_mosaic`, which also covers Alaska, Hawaii, the Caribbean and Guam. A tile failure now falls back to RainViewer's global mosaic instead of leaving the overlay blank, and the toggle and its button state track whichever layer is live.

### Accessibility
- Pinch zoom works again: the viewport meta carried `maximum-scale=1.0, user-scalable=no`, a WCAG 2.1 SC 1.4.4 failure that mattered more once the mobile flight deck became a first-class surface.
- Added a skip link as the first element in the body; it becomes visible on focus and moves focus to the map, which Leaflet keeps keyboard-operable.
- `prefers-reduced-motion` is now honoured in `assets/viptrack-ui.css`, which owns the mobile deck and had no handling at all, and aircraft marker interpolation snaps to position instead of animating.
- Added `forced-colors: active` support so borders, focus rings and status dots survive Windows High Contrast, where author colours are discarded and several controls are distinguished by colour alone; `prefers-contrast: more` raises border and dim-text contrast.

### Added
- `tools/refresh_reference_data.py` refreshes the vendored aircraft database from tar1090-db and records its provenance in `data/aircraft/manifest.json` (upstream version, licence, row count, refresh date). `--check` reports the age without downloading, and a contract test fails once the recorded build is more than 120 days old — the checked-in copy had drifted five months behind with nothing to notice.

- `tools/test_runtime.py`: behavioural acceptance that boots the real page in Chromium with the network stubbed from captured fixtures. Eight tests cover feed rendering, filter switching, the aircraft detail panel, the degraded-source indicator, keyboard operation of the status panel, a settings toggle actually changing and persisting the setting it names, radar on/off, and a `file://` boot. Service workers are blocked at the context level so nothing reaches the real network. Mutation-verified: with two regressions injected the runtime suite fails while the 51-test static suite stays green.
- Android watchlist alerts now raise real notifications. WebView implements no Web Notifications API, so `new Notification(...)` was silently inert in the app; alerts route through a `VIPTrackAndroid.notifyAlert` bridge that creates a high-importance channel, requests `POST_NOTIFICATIONS` on first use rather than at launch, and deep-links back to the aircraft that fired. One notification per aircraft, so repeats replace instead of stacking.
- A live feed status control. The reliability indicator existed but was switched off with a global `display: none`, so an outage looked exactly like normal operation. It is now visible, colour-coded healthy/degraded/unhealthy, counts only enabled sources, and opens a panel listing every source with its status, last success age, recent error count, whether it is relayed, and — for a disabled source — why. The panel also shows how old the plotted aircraft data is. Closes on Escape or an outside click and stays clear of the ethics notice and the mobile aircraft peek card.

### Documentation
- Corrected the design and version contract in the working notes. The palette resolves through three layers — the inline `:root`, `assets/viptrack-ui.css`, then `applyMidnightTheme()` setting six tokens inline on `documentElement` — and the shipped colours are `--bg #0a0a14` / `--accent #00d4ff`, not the values previously documented. Each layer now says where it sits in that order. Also corrected the README's localisation key count (342, not 313).

### Removed
- Deleted `data/interesting/` and `data/aircraft/aircraft.csv`. Every file in `data/interesting/` was byte-identical to a copy already served from its canonical path, and `aircraft.csv` was a byte-identical duplicate of `registrations.csv`, which is the one the app reads. About 47 MB of the published site was the same bytes twice.

- Dropped the sources a browser cannot reach. Planespotters' public photo API now requires a descriptive `User-Agent` — a header `fetch()` forbids the page from setting — and it refuses relayed requests, so it is unreachable from a browser-only app by construction; its two priorities left the photo chain and the working `airport-data.com`/`hexdb.io`/local-silhouette fallbacks remain. `globe.airplanes.live` answers 403 through every relay, so remote trace fetching is disabled (`traceUrl: null`, still the switch to re-enable it) and trails come from the locally recorded history with an honest status message instead of two dead round-trips per selection. Its `aircraft_sil` and `airline_banners` paths answer 404 and were replaced with the SkyTrack mirrors. The link-outs to planespotters.net still work. Both hosts left the CSP.

- Untracked and deleted four artifacts that were published with the site but are not part of it: `index.html.bak2` (533 KB), a 1.1 MB `.mhtml` page capture, a 1.3 MB root `icon.png`, and the `photo-audit.html` dev page. `.gitignore` covered `*.bak` but not `*.bak2`; it now covers `*.bak[0-9]` and `*.mhtml`.

### Security
- `connect-src` is an allowlist again. Both the meta policy and `_headers` carried bare `http:` and `https:` sources, which match every origin and made the 28-entry list that followed them decorative. Removed them, added the vector-basemap and OurAirports hosts the app actually fetches, and added `object-src 'none'` to the meta policy. `img-src` deliberately stays scheme-wide, documented in place.

### Changed
- Refreshed the aircraft database from tar1090-db 3.14.1687 (2026-03-07) to 3.14.1713 (614,965 rows).

- A throttled relay no longer reads as dead feeds. Every aggregator is reached through the CORS relay, so one relay-side HTTP 429 used to mark all four sources unhealthy and the app reported "No sources" while the feeds were fine. Relay health is now tracked separately: a relayed source that fails while the relay is unhealthy is held at `degraded` and flagged `blockedByRelay` rather than counted out, the relay gets its own row in the status panel naming the active host and its error, a 429 backs off for two minutes instead of retrying every six seconds, and the indicator tooltip says "No source reachable: <relay> …" when the relay is the cause.

- The FAA registry snapshot now ages out of owner identity. FAA §803 (FAA Reauthorization Act of 2024) lets private owners request withholding at any time, so a frozen shard set drifts from "privacy-minimised" toward holding records an owner has since asked to be withheld. Owner details are labelled with the snapshot age after 90 days and withheld entirely after 180, while type, model and year — which no withholding request covers — survive indefinitely. The aircraft panel shows the snapshot date wherever owner identity appears, and the README documents the regeneration command.

- Reference data now loads from this repository instead of a sibling one. Every dataset was configured with `primary:` pointing at `raw.githubusercontent.com/SysAdminDoc/SkyTrack/main/…`, with no local path anywhere in the chain — so a tagged release's behaviour could change without a VIPTrack commit, `file://` and offline never really worked, and every user's browser hit a personal repo's raw endpoint. All 21 dataset primaries, the six image base URLs and the silhouette sprite now resolve same-origin, with the upstream `plane-alert-db` mirrors kept as fallbacks and the SkyTrack mirrors retained only for hosts that trim the bulk media trees (the Android bundle ships neither photos nor silhouettes). `sw.js` caches the same-origin copies too. Outbound requests to `raw.githubusercontent.com` on a cold load drop from 28 to 6.

- Airplanes.live is disabled by default and carries a machine-readable reason: its public endpoint returns HTTP 403 pending approved API access.


All notable changes to VIPTrack will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [v0.5.0] - 2026-08-12

### Added
- Added a coordinated ImageGen flight-deck reference board for the Map, Aircraft, Watch, and Settings mobile workspaces.
- Added deterministic Android debug-QA aircraft, watchlist, and activity fixtures so every mobile page can be rendered and compared without depending on live ADS-B availability.

### Changed
- Re-imagined the mobile interface as a compact midnight flight deck with squared instrument surfaces, monospaced telemetry, technical grid texture, flatter navigation, denser aircraft manifests, and a shared command frame across all pages.
- Renamed the mobile List destination to Aircraft, promoted Government to a first-class functional filter, and aligned mockup-facing counts, routes, category colors, settings copy, and navigation order.
- Bumped the web/PWA cache schema to 4.26 and synchronized the web title/about surface, README badge, Android metadata, and release tests for v0.5.0.

### Fixed
- Prevented Settings from opening the software keyboard on entry, kept search clear controls compact and hidden when empty, and preserved compact switch visuals inside full-size touch targets.

## [v0.4.3] - 2026-08-12

### Accessibility
- Converted settings toggles into keyboard-operable switch buttons with translated label associations, visible focus styling, and synchronized `aria-checked` state.
- Added consistent dialog semantics, focus return, Escape/Tab handling, and mobile bottom-sheet state for aircraft details, settings, onboarding, bookmarks, ethics, and keyboard help.
- Added tab, radio-filter, and toggle-button semantics with synchronized selection state, arrow-key tab navigation, and expanded-state feedback for search and mobile controls.
- Normalized action controls with explicit button types, labels for dynamic dismiss/remove actions, and synchronized watchlist pressed state.
- Added expanded/hidden state, Escape handling, and ArrowDown focus entry for the desktop Map and Tools dropdowns.

### Changed
- Drained the actionable roadmap after shipping the security/privacy, analyst, data-plumbing, mobile, export, offline, and accessibility work; operator-gated publication and deferred research remain in `Roadmap_Blocked.md`.
- Bumped the web/PWA cache schema to 4.25 and synchronized the web title/about surface, README badge, Android metadata, and release tests for v0.4.3.

## [v0.4.2] - 2026-08-08

### Fixed
- Kept the phone workspace active in landscape by detecting coarse-pointer devices from their short side instead of portrait width alone.
- Reserved the real bottom safe-area inset for maps, panels, aircraft details, floating controls, notices, and navigation so gesture bars cannot cover content.
- Switched the in-app header to the high-resolution brand mark for sharper rendering on dense Android displays.

## [v0.4.1] - 2026-08-08

### Changed
- Replaced the text-heavy square Android artwork with a text-free adaptive radar/aircraft icon, including legacy-round, Android 13 themed, native splash, Play-store, PWA, favicon, notification, and in-app brand variants.
- Removed obsolete duplicate raster launcher, notification, and splash resources; Android launcher lint now validates the canonical vector icon system without shape or duplicate warnings.
- Bumped the web/PWA cache schema and synchronized web, README, changelog, and Android metadata for the 0.4.1 release.

## [v0.4.0] - 2026-08-08

### Added
- Added a first-party Android application for the mockup-derived Map, List, Watch, and Settings workspace, with a branded native launch/offline surface, HTTPS app links, Android text sharing, local-state file import, and permission-on-demand location handling.
- Added a secure AndroidX WebKit asset host and deterministic Gradle sync/verification lane that packages the UI shell, local catalogs, compact registration index, worker, and type photos into the APK.
- Added local JVM coverage for Android URL allowlisting, hosted-link remapping, share-target encoding, and external-scheme rejection.

### Changed
- Replaced the Bubblewrap/Chrome Trusted Web Activity with a Chrome-independent WebView host while retaining the same mobile workspace, service-worker caching, and canonical public share links.
- Kept the Android bundle compact by excluding the bulk aircraft-photo catalog and FAA shards; those datasets continue loading on demand over HTTPS.
- Prioritized the CORS-compatible Airplanes.live feed in the Android runtime to eliminate failed legacy probes and shorten clean startup.
- Bumped the web/PWA cache schema and synchronized web, README, changelog, and Android metadata for the 0.4.0 release.

### Security
- Disabled cleartext traffic, file/content access, universal file URLs, third-party cookies, app-data backup, and untrusted top-level WebView navigation; the APK remains unsigned by policy.

## [v0.3.0] - 2026-08-08

### Added
- Added a purpose-built mobile operations workspace with full-height Map, Aircraft, Watch, and Settings pages, a persistent four-item bottom navigation, compact live telemetry, list search/category/sort controls, per-aircraft watch alerts, session activity, and categorized settings search.
- Added four checked-in ImageGen design studies under `assets/mockups/` as the visual reference for the mobile implementation.

### Changed
- Reworked the phone layout around a midnight-navy aviation console with teal emphasis, clearer hierarchy, touch-sized controls, responsive portrait/landscape behavior, and local VIPTrack branding.
- Bumped the web/PWA cache schema and Android TWA metadata for the 0.3.0 release.

### Security
- Kept Trusted Types enforcement compatible with Leaflet by registering a constrained default policy backed by the pinned DOMPurify sanitizer and same-origin/approved-CDN script URL validation.

## [v0.2.0] - 2026-08-08

### Added
- Added a version-1 local-state JSON backup flow in Settings > Storage for supported display, map, watchlist, named-rule, geofence, trail, alert, and curated-overlay state, with a 1 MiB cap, deterministic migrations, strict validation, and local-only restore.
- Added a source-independent Historical Query Workspace with bounded JSON/CSV ingestion, declared source/license metadata, manual OpenSky trace reuse, time/region/aircraft/flight filters, sorted pagination, missing-signal gaps, local query history, and redacted CSV/JSON exports.
- Added a versioned plugin capability/provenance contract requiring origin, license, data-class, capability, and cleanup metadata; JavaScript modules remain disabled by default, receive only approved capability facades, and record local load/unload outcomes.

### Security
- Removed the embedded OpenSky OAuth client and made historical credentials transient, user-supplied, and cleared after each request.
- Added a centralized PIA-safe aircraft projection across caches, offline snapshots, alerts, reports, shares, webhooks, and track/viewport exports; legacy aircraft-cache records are expired by schema.
- Constrained remote overlays and webhook egress to explicit public HTTPS actions with private-target rejection, bounded/schema-validated GeoJSON, redacted previews, visible status, and opt-in automatic webhook sends.
- Upgraded DOMPurify to 3.4.13 from its reviewed upstream release and added a fail-closed CDN inventory/advisory/SRI gate covering direct and lazy-loaded executable/style dependencies.
- Added a self-host response-header policy with CSP Report-Only/enforcing pairs, HSTS, framing, permissions, MIME, and referrer controls; the main page now has a Trusted Types sanitizer policy while the isolated Cesium frame keeps its compatible eval allowance.

### Changed
- Replaced generated Blob service-worker code and unregister-all startup behavior with the checked-in same-origin `sw.js`; file URLs and unsupported contexts continue with the live map.
- Live aircraft records now retain a bounded, PIA-safe source provenance model with feed/fetch time, position and message age, quality, integrity indicators, fallback chain, response latency, rate budget, and coverage limitations; Settings can copy redacted source-only diagnostics.

## [v0.1.0] - 2026-08-03

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
- Cesium historical playback for selected `globe.airplanes.live` traces, with sampled-position paths, a clamped Cesium clock, accessible play/pause/step/speed controls, and a range scrubber.
- Opt-in MapLibre GL JS 5.24.0 + deck.gl 9.2.1 WebGL renderer via `?renderer=webgl`, with GPU `IconLayer` aircraft and `TripsLayer` history while Leaflet remains the default.
- Official FAA Releasable Aircraft Registry ingest: 315,211 privacy-minimized N-number records in 26 lazy FNV shards, with FAA owner display for non-PIA registrations and no addresses or additional registrants shipped.
- Airframes.io ACARS context link from callsign-bearing aircraft, hidden for PIA aircraft and opened as an external no-referrer pivot.
- Opt-in OpenAIP Class A–G airspace tile overlay with user-supplied local API key storage, OpenAIP attribution, and an on-map class legend.
- Manifest-backed plugin/overlay catalog with four explicit-load military pattern presets and same-origin-only hooks for future JavaScript modules.
- Same-origin i18n catalog loader with 313 shared UI keys, persistent language selection, English fallback, and initial Spanish, French, German, Russian, and Ukrainian catalogs.
- Dedicated-worker OPFS cache for the compact registration index, using synchronous access handles on warm HTTP(S) starts with IndexedDB/CSV fallback.
- Stable same-origin PWA manifest with local icons, Web Share Target routing for ICAO hexes and N-numbers, and an unsigned Bubblewrap TWA Android project targeting GitHub Pages.
- Deterministic, resumable aircraft type-photo enrichment using the local type database, with 522 manifest-backed assets and silhouette fallback coverage.
- Optional Chromium Periodic Background Sync refreshes the public military, VIP, and PIA reference caches every 12 hours without transmitting watchlist identifiers.
- In-memory session statistics dashboard with messages-seen totals, source usage, latency histogram, refresh outcomes, and rolling military/VIP/PIA counts.
- Local track-shape heuristics for unverified orbit/tanker-AWACS, sustained traffic hold, and high-altitude transit candidate hints, with PIA-safe suppression and no persistence.
- Local Squawk 7700 history feed with 24-hour retention, plane-alert-db attribution, PIA-safe display, pinned incident rows, and `?emergency=last24h` filtering.
- Curated aircraft mode for explicit plane-alert-db Interesting / Notable / Historic membership and Badger's Best entries, with a dedicated count and URL-compatible filter.
- Named local map bookmarks for saved camera positions, with a compact bottom-panel list, jump-to controls, and deletion.
- Opt-in MapLibre vector basemaps for CARTO Voyager and Stadia Alidade Smooth Dark, selectable from Settings or with the `?renderer=webgl&basemap=` URL parameters; Leaflet’s ESRI map remains the default.
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

## Roadmap archive — 2026-08-10 — ROADMAP.md

<details>
<summary>Original roadmap snapshot</summary>

```markdown
# Roadmap

**VIPTrack** — single-file Leaflet web app for global military / VIP / government / PIA aircraft tracking. MIT, zero-build, GitHub Pages.

> Version: v0.2.0 → working roadmap **rev. 2026-05-17b** (supersedes the 2026-04-23 draft preserved at the bottom).

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

**Theme: ship the v0.1.0 release on a clean security + legal baseline before adding features.**

---

## Tier — NEXT (1–2 releases out)

Features with clear demand, low-to-medium effort, and direct alignment with the mil/VIP/OSINT focus.

### Alerts, watchlist, intel

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|

### Visualisation & map

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|

### Data sources & enrichment

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|

### Export / interop

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|

### Hardening & polish

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|

---

## Tier — LATER (planned, but deferred)

Bigger lifts. Worth doing; not on the critical path.

| # | Item | Rationale | Effort | Source |
|---|---|---|---|---|

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
```

</details>
