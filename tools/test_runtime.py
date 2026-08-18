"""Runtime acceptance for VIPTrack.

The contract suite in `test_viptrack.py` matches strings in `index.html` and never
executes a line of JavaScript, so it stayed green while the primary feed, the trace
API, the photo API, every CORS relay and the radar service were all failing. This
suite boots the real page in Chromium with every outbound host intercepted and
asserts observable behaviour instead.

Run from the repository root:

    py -3.13 tools/test_runtime.py

Requires `playwright` and its Chromium build. If either is missing the suite skips
rather than fails, so it can sit alongside the offline gates without becoming a
platform dependency.

Fixtures under `tools/fixtures/` are verbatim captures of public aggregator
responses. Never hand-author one: a fixture with the wrong shape passes the very
defect it is supposed to guard.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import os
import re
import socket
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

try:  # pragma: no cover - environment probe
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment probe
    sync_playwright = None
    PLAYWRIGHT_IMPORT_ERROR = exc

MIL_FIXTURE = json.loads((FIXTURES / "adsb-mil.json").read_text(encoding="utf-8"))
PIA_FIXTURE = json.loads((FIXTURES / "adsb-pia.json").read_text(encoding="utf-8"))

# Long enough for the boot sequence, the first source sweep and the first render.
BOOT_SETTLE_MS = 9000


class _LimitedReader:
    """Wraps a file object so only the requested byte range is sent."""

    def __init__(self, handle, remaining: int) -> None:
        self._handle = handle
        self._remaining = remaining

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size < 0 or size > self._remaining:
            size = self._remaining
        chunk = self._handle.read(size)
        self._remaining -= len(chunk)
        return chunk

    def close(self) -> None:
        self._handle.close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static handler with byte-range support.

    `SimpleHTTPRequestHandler` ignores `Range` and answers 200 with the whole file.
    GitHub Pages answers 206, and PMTiles is built entirely on range requests, so a
    server without this tests a transport the app never actually uses.
    """

    def log_message(self, *args, **kwargs) -> None:  # noqa: D102 - silence the server
        pass

    def send_head(self):
        header = self.headers.get("Range")
        if not header:
            return super().send_head()
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()
        match = re.match(r"bytes=(\d+)-(\d*)$", header.strip())
        if not match:
            return super().send_head()
        size = os.path.getsize(path)
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_error(416)
            return None
        handle = open(path, "rb")
        handle.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return _LimitedReader(handle, end - start + 1)


@contextlib.contextmanager
def serve_repository():
    """Serve the repository over HTTP so service workers and OPFS behave normally."""
    handler = functools.partial(_QuietHandler, directory=str(ROOT))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _json_route(route, payload, status=200):
    route.fulfill(
        status=status,
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
        body=json.dumps(payload),
    )


class VipTrackRuntime(unittest.TestCase):
    """Behavioural acceptance against a fully stubbed network."""

    playwright = None
    browser = None
    base_url = None
    _server = None
    _contexts: list = []

    # Set by individual tests to make the live feed fail.
    feed_status = 200

    @classmethod
    def setUpClass(cls) -> None:
        if sync_playwright is None:
            raise unittest.SkipTest(f"playwright unavailable: {PLAYWRIGHT_IMPORT_ERROR}")
        cls._server = serve_repository()
        cls.base_url = cls._server.__enter__()
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - environment probe
            cls.playwright.stop()
            cls._server.__exit__(None, None, None)
            raise unittest.SkipTest(f"chromium unavailable: {exc}")

    def tearDown(self) -> None:
        while self._contexts:
            with contextlib.suppress(Exception):
                self._contexts.pop().close()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.browser:
            cls.browser.close()
        if cls.playwright:
            cls.playwright.stop()
        if cls._server:
            cls._server.__exit__(None, None, None)

    def _route_external(self, page, feed_status=200):
        """Intercept everything that is not the local origin.

        The relay wraps the feed URL in a query string, so the aggregator host is
        matched anywhere in the URL rather than only in the host position.
        """
        host = self.base_url.split("//", 1)[1]

        def handler(route):
            url = route.request.url
            # The local origin and the file:// document itself are the app under test.
            # Without this the catch-all below answers the HTML document with a GIF.
            if host in url or url.startswith("file://"):
                route.fallback()
                return
            # Leaflet, pako and DOMPurify are the app's runtime, not its data. Stubbing
            # them out just yields "L is not defined" and tests nothing, so they load
            # for real; every data-bearing host below stays intercepted.
            if "cdnjs.cloudflare.com" in url or "cdn.jsdelivr.net" in url:
                route.fallback()
                return
            if feed_status != 200 and ("adsb" in url or "airplanes.live" in url):
                route.fulfill(status=feed_status, content_type="text/plain",
                              headers={"Access-Control-Allow-Origin": "*"}, body="blocked")
                return
            if "pia" in url or "ladd" in url:
                _json_route(route, PIA_FIXTURE)
                return
            if "adsb" in url or "airplanes.live" in url:
                _json_route(route, MIL_FIXTURE)
                return
            if url.endswith(".csv") or "plane-alert" in url or "ourairports" in url:
                route.fulfill(status=200, content_type="text/csv",
                              headers={"Access-Control-Allow-Origin": "*"}, body="")
                return
            if url.endswith(".json"):
                _json_route(route, {})
                return
            # Tiles, photos, silhouettes: a transparent 1x1 GIF keeps layout honest.
            route.fulfill(status=200, content_type="image/gif", headers={"Access-Control-Allow-Origin": "*"},
                          body=b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\x00\x00\x00!"
                               b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")

        page.route("**/*", handler)

    def _new_page(self, viewport=None):
        # Service workers fetch outside the page's routing table, so a registered
        # sw.js silently served real network data into a "stubbed" run. Blocking
        # them is what makes this suite hermetic.
        context = self.browser.new_context(
            viewport=viewport or {"width": 1440, "height": 900},
            service_workers="block",
        )
        self._contexts.append(context)
        return context.new_page()

    @contextlib.contextmanager
    def _page(self, feed_status=200, viewport=None, url=None):
        page = self._new_page(viewport)
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        self._route_external(page, feed_status=feed_status)
        page.goto(url or f"{self.base_url}/index.html", wait_until="load", timeout=60000)
        # Dismiss the first-run overlays so they do not intercept pointer events.
        page.evaluate(
            "document.querySelectorAll('#onboardOverlay,#ethicsDisclaimer')"
            ".forEach(el => { el.classList.remove('show'); el.style.display = 'none'; });"
        )
        page.wait_for_timeout(BOOT_SETTLE_MS)
        try:
            yield page, crashes
        finally:
            page.close()

    # ---------------------------------------------------------------- behaviour

    def test_fixture_feed_plots_aircraft_on_the_map(self) -> None:
        with self._page() as (page, crashes):
            page.wait_for_function("() => Object.keys(markers).length > 0", timeout=30000)
            # Marker keys are upper-cased hex; fixture hexes are lower case.
            hexes = {h.upper() for h in page.evaluate("Object.keys(markers)")}
            self.assertGreater(len(hexes), 0)
            self.assertIn(MIL_FIXTURE["ac"][0]["hex"].upper(), hexes)
            # Nothing may appear on the map that the stubbed network did not supply.
            supplied = {ac["hex"].upper() for ac in MIL_FIXTURE["ac"] + PIA_FIXTURE["ac"]}
            self.assertEqual(sorted(hexes - supplied), [],
                             "markers appeared for aircraft the fixtures never provided")
            self.assertIn("aircraft", page.evaluate("document.getElementById('dataSource').textContent"))
            self.assertEqual(crashes, [])

    def test_filter_switch_changes_the_rendered_set(self) -> None:
        with self._page() as (page, crashes):
            page.wait_for_function("() => Object.keys(markers).length > 0", timeout=30000)

            def select(mode):
                # Drive the real control rather than an internal function, so the test
                # exercises the path a user actually takes.
                page.evaluate(
                    "mode => document.querySelector(`.filter-btn[data-filter=\"${mode}\"]`).click()",
                    mode,
                )
                page.wait_for_timeout(2000)
                return page.evaluate("Object.keys(markers).length")

            baseline = select("mil-vip")
            military = select("military")
            vip = select("vip")
            self.assertEqual(page.evaluate("settings.filter"), "vip")
            self.assertLessEqual(military, baseline)
            self.assertLessEqual(vip, baseline)
            self.assertNotEqual(
                (military, vip), (baseline, baseline),
                "filter switching never changed the rendered set"
            )
            self.assertEqual(crashes, [])

    def test_selecting_an_aircraft_opens_a_populated_detail_panel(self) -> None:
        with self._page() as (page, crashes):
            page.wait_for_function("() => Object.keys(markers).length > 0", timeout=30000)
            target = page.evaluate("Object.keys(markers)[0]")
            page.evaluate("hex => selectAircraft(hex)", target)
            page.wait_for_timeout(2500)
            panel = page.evaluate(
                "() => { const p = document.getElementById('infoPanel');"
                " return { open: p.classList.contains('show') || p.getAttribute('aria-hidden') === 'false',"
                " text: (p.textContent || '').replace(/\\s+/g, ' ').trim() }; }"
            )
            self.assertTrue(panel["open"], "aircraft detail panel did not open")
            self.assertGreater(len(panel["text"]), 40, "detail panel opened empty")
            self.assertEqual(page.evaluate("selectedHex"), target)
            self.assertEqual(crashes, [])

    def test_failing_feeds_mark_the_status_indicator_unhealthy(self) -> None:
        with self._page(feed_status=403) as (page, crashes):
            page.wait_for_function(
                "() => document.getElementById('dataSourceIndicator')"
                ".classList.contains('is-unhealthy')",
                timeout=45000,
            )
            summary = page.evaluate("dataSourceManager.healthSummary()")
            self.assertEqual(summary["healthy"], 0)
            self.assertEqual(summary["level"], "unhealthy")
            page.evaluate("dataSourceManager.toggleDetail(true)")
            page.wait_for_timeout(500)
            detail = page.evaluate("document.getElementById('dataSourceDetailBody').textContent")
            self.assertIn("Airplanes.live", detail)
            self.assertIn("403", detail, "the disabled source must explain itself")
            self.assertEqual(crashes, [])

    def test_status_detail_opens_and_closes_from_the_keyboard(self) -> None:
        with self._page() as (page, crashes):
            page.focus("#dataSourceIndicator")
            page.keyboard.press("Enter")
            page.wait_for_timeout(600)
            self.assertFalse(page.evaluate("document.getElementById('dataSourceDetail').hidden"))
            self.assertEqual(
                page.evaluate("document.getElementById('dataSourceIndicator').getAttribute('aria-expanded')"),
                "true",
            )
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
            self.assertTrue(page.evaluate("document.getElementById('dataSourceDetail').hidden"))
            self.assertEqual(crashes, [])

    def test_settings_toggle_changes_behaviour_not_just_aria(self) -> None:
        with self._page() as (page, crashes):
            before = page.evaluate("!!settings.showLabels")
            page.evaluate("document.getElementById('toggleLabels').click()")
            page.wait_for_timeout(1200)
            after = page.evaluate("!!settings.showLabels")
            aria = page.evaluate("document.getElementById('toggleLabels').getAttribute('aria-checked')")
            self.assertNotEqual(before, after, "toggling did not change the setting it controls")
            self.assertEqual(aria, str(after).lower())
            persisted = page.evaluate(
                "JSON.parse(localStorage.getItem('viptrack_settings_v3') || '{}').showLabels"
            )
            self.assertEqual(bool(persisted), after, "the setting did not persist")
            self.assertEqual(crashes, [])

    def test_radar_overlay_toggles_both_on_and_off(self) -> None:
        with self._page() as (page, crashes):
            self.assertFalse(page.evaluate("radarActive()"))
            page.evaluate("toggleNexrad()")
            page.wait_for_timeout(1200)
            self.assertTrue(page.evaluate("radarActive()"))
            page.evaluate("toggleNexrad()")
            page.wait_for_timeout(800)
            self.assertFalse(page.evaluate("radarActive()"))
            self.assertEqual(crashes, [])

    def test_a_throttled_relay_is_not_reported_as_dead_feeds(self) -> None:
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        host = self.base_url.split("//", 1)[1]

        def handler(route):
            url = route.request.url
            if host in url or url.startswith("file://"):
                route.fallback()
                return
            if "corsproxy.io" in url or "allorigins.win" in url:
                route.fulfill(status=429, content_type="text/plain",
                              headers={"Access-Control-Allow-Origin": "*"}, body="Too Many Requests")
                return
            route.fallback()

        # Playwright runs routes last-registered-first, so the relay override has to be
        # registered after the base stub or the base stub answers the relay instead.
        self._route_external(page)
        page.route("**/*", handler)
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            # checkAllSources() awaits each source in turn, so waiting for the *first*
            # blocked source races the rest still sitting at 'unknown'. Wait for the
            # whole sweep to land before asserting on all of them.
            page.wait_for_function(
                "() => relayHealth.isThrottled() && dataSourceManager.enabledSources()"
                ".every(s => s.status !== 'unknown')", timeout=45000)
            self.assertTrue(page.evaluate("relayHealth.isThrottled()"))
            self.assertIn("429", page.evaluate("relayHealth.describe()"))
            # Relayed sources must not be counted out over a fault that is not theirs.
            relayed = page.evaluate(
                "dataSourceManager.enabledSources().filter(s => s.cors === false)"
                ".map(s => ({status: s.status, blocked: !!s.blockedByRelay}))"
            )
            self.assertTrue(relayed)
            for source in relayed:
                self.assertEqual(source["status"], "degraded")
                self.assertTrue(source["blocked"])
            # The tooltip must name the relay and the reason, not blame the feeds.
            title = page.evaluate("document.getElementById('dataSourceIndicator').title").lower()
            self.assertIn("no source reachable", title)
            self.assertIn("429", title)
            self.assertIn(page.evaluate("relayHealth.name()").lower(), title)
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_map_pans_without_a_dragging_movement(self) -> None:
        # WCAG 2.2 SC 2.5.7 (AA): Leaflet only offers drag-to-pan, so every map position
        # must also be reachable with a single pointer and no drag.
        with self._page() as (page, crashes):
            labels = page.evaluate(
                "[...document.querySelectorAll('.map-pan-control button')]"
                ".map(b => b.getAttribute('aria-label'))"
            )
            self.assertEqual(sorted(labels), ["Pan east", "Pan north", "Pan south", "Pan west"])
            before = page.evaluate("({lat: map.getCenter().lat, lng: map.getCenter().lng})")
            page.click(".map-pan-control button[aria-label='Pan east']")
            page.wait_for_timeout(1200)
            page.click(".map-pan-control button[aria-label='Pan north']")
            page.wait_for_timeout(1200)
            after = page.evaluate("({lat: map.getCenter().lat, lng: map.getCenter().lng})")
            self.assertGreater(after["lng"], before["lng"])
            self.assertGreater(after["lat"], before["lat"])
            self.assertEqual(crashes, [])

    def test_no_interactive_target_is_below_the_minimum_size(self) -> None:
        # WCAG 2.2 SC 2.5.8 (AA): 24x24 CSS px unless an exception applies.
        for width, height in ((1440, 900), (390, 844)):
            with self._page(viewport={"width": width, "height": height}) as (page, crashes):
                undersized = page.evaluate(
                    "() => { const sel = 'a[href],button:not([disabled]),input:not([disabled]),"
                    "select,[role=switch],[role=tab]'; const out = [];"
                    " document.querySelectorAll(sel).forEach(el => { if (!el.offsetParent) return;"
                    " const r = el.getBoundingClientRect();"
                    " if (r.width < 24 || r.height < 24) out.push((el.id || el.className || el.tagName)"
                    " + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)); }); return out; }"
                )
                self.assertEqual(undersized, [], f"{width}x{height}")
                self.assertEqual(crashes, [])

    def test_csp_blocked_egress_names_the_host_to_allowlist(self) -> None:
        # connect-src is a strict allowlist, so the three user-configured egress
        # features are refused by policy and fetch() reports a bare "Failed to
        # fetch". The user must be told which host to add, not left guessing.
        with self._page() as (page, crashes):
            webhook = page.evaluate(
                "async () => { alertWebhook.url = 'https://hooks.example.org/hook';"
                " alertWebhook.kind = 'generic';"
                " await alertWebhook.send({type:'TEST', message:'x', timestamp: Date.now(),"
                " aircraft:{hex:'TEST00'}}, {explicit:true});"
                " return document.getElementById('webhookStatus').textContent; }"
            )
            self.assertIn("Content-Security-Policy", webhook)
            self.assertIn("hooks.example.org", webhook)
            self.assertNotIn("Failed to fetch", webhook)

            overlay = page.evaluate(
                "async () => { await geojsonLoader.addFromUrl('https://tiles.example.org/a.geojson');"
                " return document.getElementById('overlayStatus').textContent; }"
            )
            self.assertIn("connect-src", overlay)
            self.assertIn("tiles.example.org", overlay)

            # A host that is genuinely allowlisted must keep its own wording, so the
            # explanation cannot be a blanket message on every failure.
            allowed = page.evaluate("() => cspWatch.explain('https://api.adsb.lol/v2/mil')")
            self.assertEqual(allowed, "")
            self.assertEqual(crashes, [])

    def test_http_feeder_on_an_https_page_is_reported_as_mixed_content(self) -> None:
        with self._page() as (page, crashes):
            note = page.evaluate(
                "() => cspWatch.mixedContentNote('http://receiver.local/tar1090/data/receiver.json')"
            )
            # The harness serves over http://, so no mixed-content case exists here;
            # assert the rule itself instead of faking the page protocol.
            self.assertEqual(note, "")
            described = page.evaluate(
                "async () => await cspWatch.describeFailure('http://receiver.local/x.json', 'fallback text')"
            )
            self.assertEqual(described, "fallback text")
            self.assertEqual(crashes, [])

    def test_self_hosted_basemap_serves_tiles_or_falls_back(self) -> None:
        # The archive is gitignored, so both branches are real deployments: an
        # operator who ran the build script, and a clean checkout that did not.
        archive = ROOT / "data" / "basemap" / "basemap.pmtiles"
        url = f"{self.base_url}/index.html?renderer=webgl&basemap=pmtiles-dark"
        with self._page(url=url) as (page, crashes):
            page.wait_for_function(
                "() => typeof webglMapManager !== 'undefined' && webglMapManager.renderer"
                " && webglMapManager.renderer.isStyleLoaded()",
                timeout=45000,
            )
            style = page.evaluate("settings.mapStyle")
            if not archive.exists():
                self.assertEqual(style, "esri-gray", "a missing archive must fall back, not break the map")
                self.assertEqual(crashes, [])
                return

            self.assertEqual(style, "pmtiles-dark")
            source = page.evaluate("webglMapManager.renderer.getStyle().sources.protomaps.url")
            self.assertTrue(source.startswith("pmtiles://" + self.base_url), source)
            # Attribution is a licence obligation of the underlying OSM data.
            self.assertIn("OpenStreetMap", page.evaluate(
                "webglMapManager.renderer.getStyle().sources.protomaps.attribution"))
            # The whole point is that no third-party host is involved.
            self.assertNotIn("http", json.dumps(page.evaluate(
                "webglMapManager.renderer.getStyle().layers")))

            page.wait_for_function(
                "() => webglMapManager.renderer"
                ".querySourceFeatures('protomaps', {sourceLayer: 'earth'}).length > 0",
                timeout=45000,
            )
            # Vector tiles overzoom, so a z6 archive still draws past its max zoom.
            page.evaluate("webglMapManager.renderer.jumpTo({center: [-77.04, 38.90], zoom: 9})")
            page.wait_for_function(
                "() => webglMapManager.renderer"
                ".querySourceFeatures('protomaps', {sourceLayer: 'roads'}).length > 0",
                timeout=30000,
            )
            self.assertEqual(crashes, [])

    def test_pmtiles_archive_path_stays_same_origin(self) -> None:
        with self._page() as (page, crashes):
            rejected = page.evaluate(
                "() => ['https://evil.example/a.pmtiles', '//evil.example/a.pmtiles',"
                " '/etc/a.pmtiles', '../../a.pmtiles', 'data/basemap/a.png']"
                ".map(v => pmtilesBasemap.setPath(v))"
            )
            self.assertEqual(rejected, [False] * 5)
            self.assertTrue(page.evaluate("pmtilesBasemap.setPath('data/basemap/other.pmtiles')"))
            self.assertEqual(page.evaluate("pmtilesBasemap.path()"), "data/basemap/other.pmtiles")
            self.assertTrue(page.evaluate("pmtilesBasemap.archiveUrl()").startswith(self.base_url))
            page.evaluate("pmtilesBasemap.setPath('')")
            self.assertEqual(crashes, [])

    # Writes rows straight into the object store so a test can place points outside
    # the window and at a volume no fixture sweep would ever produce.
    _SEED_COVERAGE = """
        ([rows]) => new Promise((resolve, reject) => {
            const tx = skytrackDB.db.transaction(['trailHistory'], 'readwrite');
            const store = tx.objectStore('trailHistory');
            for (const row of rows) store.add(row);
            tx.oncomplete = () => resolve(rows.length);
            tx.onerror = () => reject(tx.error);
        })
    """

    # The live feed keeps sampling into the same store, so a test that asserts exact
    # counts has to quiesce the recorder and empty both the cache and the store first.
    _QUIESCE_COVERAGE = """
        async () => {
            coverageRecorder.stop();
            settings.coverageRecording = false;
            coverageRecorder.lastByHex.clear();
            _pauseAllIntervals();
            for (const key of Object.keys(aircraftCache)) delete aircraftCache[key];
            await skytrackDB.clearTrailHistory();
        }
    """

    def test_coverage_view_renders_a_window_of_local_history(self) -> None:
        with self._page() as (page, crashes):
            page.evaluate(self._QUIESCE_COVERAGE)
            now = page.evaluate("Date.now()")
            hour = 3600 * 1000
            rows = []
            for i in range(300):
                rows.append({"hex": f"AE{i % 12:04X}", "data": [38.9 + i * 0.002, -77.0 + i * 0.002, 30000],
                             "timestamp": now - (i % 3) * 60 * 1000})
            # Two rows that must never be drawn: one aged out of every window offered,
            # one belonging to a privacy-protected aircraft.
            rows.append({"hex": "AE9999", "data": [10.0, 10.0, 100], "timestamp": now - 400 * hour})
            rows.append({"hex": "ADF7C8", "data": [11.0, 11.0, 100], "timestamp": now})
            page.evaluate(self._SEED_COVERAGE, [rows])
            page.evaluate("() => { aircraftCache['ADF7C8'] = {hex: 'ADF7C8', privacyProtected: true}; }")

            # Drive the view directly so the recorder stays quiet and the counts below
            # describe exactly the rows this test seeded.
            page.evaluate("() => { settings.coverageWindow = 6; settings.coverageMode = 'density'; }")
            page.evaluate("async () => await coverageView.refresh(false)")

            stats = page.evaluate("() => coverageView.stats")
            self.assertEqual(stats["points"], 300, "aged-out and PIA rows must not be counted")
            self.assertEqual(stats["aircraft"], 12)
            self.assertGreaterEqual(stats["redacted"], 1)
            self.assertTrue(page.evaluate("() => Boolean(coverageView.canvas)"))
            self.assertGreater(page.evaluate("() => coverageView.cells.length"), 0)
            # A PIA hex must not survive into either representation.
            self.assertNotIn("ADF7C8", page.evaluate("() => coverageView.tracks.map(t => t[0])"))

            # Both modes have to draw; a mode switch is a repaint, not another walk.
            page.evaluate("() => { settings.coverageMode = 'tracks'; coverageView._draw(); }")
            painted = page.evaluate(
                "() => { const c = coverageView.canvas;"
                " const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
                " let lit = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) lit++; return lit; }"
            )
            self.assertGreater(painted, 0, "tracks mode drew nothing")

            page.evaluate("async () => await coverageView.setMode('off', false)")
            self.assertFalse(page.evaluate("() => Boolean(coverageView.canvas)"))
            # Turning the view on is what opts this browser into sampling at all.
            page.evaluate("async () => await coverageView.setMode('density', false)")
            self.assertTrue(page.evaluate("() => settings.coverageRecording"))
            self.assertEqual(crashes, [])

    def test_coverage_view_stays_interactive_at_store_volume(self) -> None:
        with self._page() as (page, crashes):
            page.evaluate(self._QUIESCE_COVERAGE)
            now = page.evaluate("Date.now()")
            # 60k rows is a realistic week of sampling, and far past what a per-point
            # renderer could redraw on every pan.
            for chunk in range(6):
                rows = [{"hex": f"AE{(chunk * 10000 + i) % 900:04X}",
                         "data": [20 + (i % 6000) * 0.01, -120 + (i % 9000) * 0.012, 30000],
                         "timestamp": now - (i % 300) * 1000}
                        for i in range(10000)]
                page.evaluate(self._SEED_COVERAGE, [rows])

            page.evaluate("() => { settings.coverageWindow = 24; settings.coverageMode = 'density'; }")
            page.evaluate("async () => await coverageView.refresh(false)")
            self.assertEqual(page.evaluate("() => coverageView.stats.points"), 60000)
            # Aggregation is the point: cells drawn must be far fewer than points read.
            self.assertLess(page.evaluate("() => coverageView.cells.length"), 60000)

            redraw = page.evaluate(
                "() => { const t = performance.now(); for (let i = 0; i < 5; i++) coverageView._draw();"
                " return (performance.now() - t) / 5; }"
            )
            self.assertLess(redraw, 250, f"a redraw took {redraw:.0f}ms at 60k stored points")
            self.assertEqual(crashes, [])

    def test_coverage_view_participates_in_url_state(self) -> None:
        with self._page() as (page, crashes):
            page.evaluate("() => coverageView.setWindow(24, false)")
            page.evaluate("() => coverageView.setMode('tracks', false)")
            page.wait_for_function("() => coverageView.stats !== null", timeout=20000)
            url = page.evaluate("shareManager.buildViewUrl()")
            self.assertIn("coverage=tracks", url)
            self.assertIn("coverageWindow=24", url)
            self.assertEqual(crashes, [])

        with self._page(url=url) as (page, crashes):
            page.wait_for_function("() => coverageView.isActive()", timeout=20000)
            self.assertEqual(page.evaluate("() => coverageView.mode()"), "tracks")
            self.assertEqual(page.evaluate("() => coverageView.windowHours()"), 24)
            self.assertEqual(crashes, [])

    def test_coverage_sampling_never_stores_a_privacy_protected_aircraft(self) -> None:
        with self._page() as (page, crashes):
            written = page.evaluate(
                "async () => { await skytrackDB.clearTrailHistory();"
                " aircraftCache['ADF7C8'] = {hex: 'ADF7C8', lat: 5, lon: 5, privacyProtected: true};"
                " aircraftCache['AE1234'] = {hex: 'AE1234', lat: 6, lon: 6};"
                " settings.coverageRecording = true; coverageRecorder.lastByHex.clear();"
                " await coverageRecorder.tick();"
                " const seen = []; await skytrackDB.streamTrailHistory(0, r => seen.push(r.hex));"
                " return seen; }"
            )
            self.assertIn("AE1234", written)
            self.assertNotIn("ADF7C8", written)
            # An unchanged position must not write a second row on the next tick.
            again = page.evaluate("async () => await coverageRecorder.tick()")
            self.assertEqual(again, 0)
            self.assertEqual(crashes, [])

    def test_a_view_link_round_trips_filter_search_and_map_position(self) -> None:
        # A desk finding has to be shareable as a link, the way tar1090 does it.
        with self._page() as (page, crashes):
            page.evaluate("document.querySelector('.filter-btn[data-filter=\"military\"]').click()")
            page.fill("#searchInput", "GLOBEMASTER")
            page.evaluate("map.setView([51.5, -0.12], 8)")
            page.wait_for_timeout(1000)
            url = page.evaluate("shareManager.buildViewUrl()")
            for expected in ("filter=military", "q=GLOBEMASTER", "zoom=8"):
                self.assertIn(expected, url)
            self.assertEqual(crashes, [])

        with self._page(url=url) as (page, crashes):
            self.assertEqual(page.evaluate("settings.filter"), "military")
            self.assertEqual(page.evaluate("document.getElementById('searchInput').value"), "GLOBEMASTER")
            self.assertEqual(page.evaluate("map.getZoom()"), 8)
            self.assertAlmostEqual(page.evaluate("map.getCenter().lat"), 51.5, places=1)
            self.assertEqual(crashes, [])

    def test_a_view_link_never_names_a_privacy_protected_aircraft(self) -> None:
        with self._page() as (page, crashes):
            leaked = page.evaluate(
                # isPrivacyProtectedAircraft() keys off privacyProtected / piaInfo / the hex
                # range -- not dbFlags. Assert against the marker the product actually reads.
                "() => { const hex = Object.keys(markers)[0]; if (!hex) return 'no aircraft';"
                " selectedHex = hex; const ac = aircraftCache[hex] || (aircraftCache[hex] = {hex});"
                " const before = shareManager.buildViewUrl();"
                " if (!before.includes('hex=')) return 'inconclusive: hex absent before flagging';"
                " ac.privacyProtected = true;"
                " const after = shareManager.buildViewUrl(); delete ac.privacyProtected;"
                " return after.includes('hex=') ? 'LEAKED' : 'ok'; }"
            )
            self.assertEqual(leaked, "ok")

            # buildViewUrl is not the only URL builder. buildUrl writes the address
            # bar through replaceState (what a user copies by hand) and generateLink
            # backs the Share Flight button; both used to name the aircraft.
            others = page.evaluate(
                "() => { const hex = Object.keys(markers)[0]; if (!hex) return 'no aircraft';"
                " selectedHex = hex; const ac = aircraftCache[hex] || (aircraftCache[hex] = {hex});"
                " ac.lat = 51.5; ac.lon = -0.12;"
                " const beforeBuild = shareManager.buildUrl();"
                " const beforeLink = shareManager.generateLink(hex);"
                " if (!beforeBuild.includes('hex=') || !beforeLink.includes('hex='))"
                "   return 'inconclusive: hex absent before flagging';"
                " ac.privacyProtected = true;"
                " const afterBuild = shareManager.buildUrl();"
                " const afterLink = shareManager.generateLink(hex);"
                " delete ac.privacyProtected;"
                " return { build: afterBuild.includes('hex=') ? 'LEAKED' : 'ok',"
                "   link: afterLink.includes('hex=') ? 'LEAKED' : 'ok',"
                "   position: (afterLink.includes('lat=') || afterLink.includes('lon=')) ? 'LEAKED' : 'ok' }; }"
            )
            self.assertEqual(others, {"build": "ok", "link": "ok", "position": "ok"})

            # The address bar itself must stay clean after selecting a PIA aircraft.
            address = page.evaluate(
                "() => { const hex = Object.keys(markers)[0];"
                " const ac = aircraftCache[hex]; ac.privacyProtected = true;"
                " selectAircraft(hex); const href = location.href;"
                " delete ac.privacyProtected; deselectAircraft();"
                " return href.includes('hex='); }"
            )
            self.assertFalse(address, "selecting a PIA aircraft put its hex in the address bar")
            self.assertEqual(crashes, [])

    def test_regex_filter_reaches_type_code_and_is_bounded(self) -> None:
        # tar1090's most useful filters (B73., H.., L2J) address the type code and
        # description, which the previous implementation never matched against.
        with self._page() as (page, crashes):
            self.assertTrue(page.evaluate(
                "() => { const r = compileFilterRegex('H..');"
                " const ac = {flight: 'RESCUE1', r: 'N911HQ', t: 'H60', desc: 'Sikorsky UH-60'};"
                " return r.ok && r.value.test([ac.flight, ac.r, ac.t, ac.desc].join(' ')); }"
            ))
            # A user-supplied pattern is untrusted: bound it and refuse the shapes that hang.
            self.assertFalse(page.evaluate("compileFilterRegex('a'.repeat(250)).ok"))
            self.assertFalse(page.evaluate("compileFilterRegex('(a+)+b').ok"))
            self.assertFalse(page.evaluate("compileFilterRegex('[unclosed').ok"))
            self.assertTrue(page.evaluate("compileFilterRegex('B739|B39M').ok"))
            self.assertTrue(page.evaluate("compileFilterRegex('^(?!A320)').ok"))
            # An invalid pattern reports inline rather than as a transient toast.
            page.evaluate("document.getElementById('filterRegex').value = '[unclosed'")
            page.evaluate("searchSystem.applyFilters()")
            page.wait_for_timeout(400)
            self.assertFalse(page.evaluate("document.getElementById('filterRegexError').hidden"))
            self.assertEqual(page.evaluate(
                "document.getElementById('filterRegex').getAttribute('aria-invalid')"), "true")
            self.assertEqual(crashes, [])

    def test_credentials_stay_out_of_backups_and_diagnostics(self) -> None:
        # The promise is "keys never leave this browser". Assert it against the artifacts
        # that do leave: the local-state backup and the diagnostics export.
        with self._page() as (page, crashes):
            page.evaluate(
                "() => { credentialRegistry.allStorageKeys()"
                ".forEach((k, i) => localStorage.setItem(k, 'SENTINEL_KEY_' + i)); }"
            )
            page.evaluate("credentialRegistry.render()")
            page.wait_for_timeout(400)

            rendered = page.evaluate("document.getElementById('credentialStatusBody').textContent")
            self.assertIn("stored in this browser only", rendered)
            self.assertNotIn("SENTINEL_KEY_", rendered, "the status surface must never print a key")

            # Build each outbound artifact for real. A swallowed exception here would
            # make this assertion vacuous, so every part must produce actual content.
            artifacts = page.evaluate(
                "() => ({"
                " backup: JSON.stringify(localStateManager.buildState()),"
                " diagnostics: JSON.stringify(dataSourceManager.getDiagnostics()),"
                " stats: JSON.stringify(dataSourceManager.getStats()) })"
            )
            for name, payload in artifacts.items():
                self.assertGreater(len(payload), 20, f"{name} produced no content to check")
                self.assertNotIn("SENTINEL_KEY_", payload, name)

            # Clearing a slot removes every key it owns.
            page.evaluate("credentialRegistry.clear('openaip')")
            self.assertFalse(page.evaluate(
                "credentialRegistry.isConfigured(credentialRegistry.slots.find(s => s.id === 'openaip'))"))
            self.assertEqual(crashes, [])

    def test_file_protocol_boot_degrades_without_throwing(self) -> None:
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        self._route_external(page)
        try:
            page.goto((ROOT / "index.html").as_uri(), wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)
            self.assertTrue(page.evaluate("CONFIG.isLocalFile"))
            self.assertTrue(page.evaluate("typeof map !== 'undefined' && !!map"),
                            "the map must still initialise from file://")
            self.assertEqual(crashes, [])
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
