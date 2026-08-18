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


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs) -> None:  # noqa: D102 - silence the server
        pass


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
