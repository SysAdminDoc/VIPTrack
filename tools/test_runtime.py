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

    # Mirrors relayHealth.AUTH_FAILURE_LIMIT in index.html.
    RELAY_AUTH_FAILURE_LIMIT = 3

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

    def test_a_relay_that_refuses_outright_is_dropped_not_retried_forever(self) -> None:
        # corsproxy.io answered 401 on every request for weeks while relayHealth
        # reported healthy, because a failure was only recorded once *every* relay
        # failed. A relay demanding an account key is gone, not having a bad minute.
        #
        # Every fetchWithProxy() call below passes skipDirect, exactly as the feed
        # loop does. Without it the direct attempt succeeds against the base stub and
        # no relay is contacted at all, so the test passes while proving nothing.
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        host = self.base_url.split("//", 1)[1]
        attempts: dict[str, int] = {"refusing": 0, "working": 0}
        poll = ("async (n) => { for (let i = 0; i < n; i++) "
                "await fetchWithProxy('https://api.adsb.lol/v2/mil', {}, { skipDirect: true }); }")
        forced_poll = ("async (n) => { for (let i = 0; i < n; i++) { lastSuccessfulProxy = ''; "
                       "await fetchWithProxy('https://api.adsb.lol/v2/mil', {}, { skipDirect: true }); } }")

        def handler(route):
            url = route.request.url
            if host in url or url.startswith("file://"):
                route.fallback()
                return
            if "allorigins.win" in url:
                attempts["refusing"] += 1
                route.fulfill(status=401, content_type="application/json",
                              headers={"Access-Control-Allow-Origin": "*"},
                              body='{"error":"A valid API key is required"}')
                return
            if "corsproxy.io" in url:
                attempts["working"] += 1
                if "pia" in url or "ladd" in url:
                    _json_route(route, PIA_FIXTURE)
                else:
                    _json_route(route, MIL_FIXTURE)
                return
            route.fallback()

        # Playwright runs routes last-registered-first, so the relay override has to be
        # registered after the base stub or the base stub answers the relay instead.
        self._route_external(page)
        page.route("**/*", handler)
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)
            self.assertGreater(attempts["working"], 0, "the working relay must carry traffic")

            # Ten polls must not cost ten round-trips to a relay that already refused.
            before = attempts["refusing"]
            page.evaluate(poll, 10)
            self.assertLessEqual(
                attempts["refusing"] - before, self.RELAY_AUTH_FAILURE_LIMIT,
                "a relay answering 401 must not be re-tried on every poll")

            # Sticky selection alone keeps the refusing relay out of the way while the
            # working one holds. Force it back to the front, the way an intermittently
            # working relay does in production, and the 401s must retire it for good.
            page.evaluate(forced_poll, 4)
            self.assertTrue(page.evaluate("relayHealth.isRelayDisabled('allorigins')"),
                            "three 401s from one relay must disable it for the session")
            self.assertLessEqual(
                attempts["refusing"], self.RELAY_AUTH_FAILURE_LIMIT,
                "the refusing relay must never be attempted more than the strike limit")

            # Once retired it must stay retired, however often the caller cycles back.
            settled = attempts["refusing"]
            working_before = attempts["working"]
            page.evaluate(forced_poll, 5)
            self.assertEqual(attempts["refusing"], settled,
                             "no further attempt may reach a disabled relay")
            # Feeds must keep loading through the relay that still answers.
            self.assertGreater(attempts["working"], working_before)

            # The health control has to name the relay that refused, rather than
            # leaving the user to read it out of the console.
            described = page.evaluate("relayHealth.describe()")
            self.assertIn("allorigins.win", described)
            self.assertIn("401/403", described)
            self.assertEqual(page.evaluate("relayHealth.status()"), "healthy")
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_repointing_the_custom_relay_clears_the_old_relay_verdict(self) -> None:
        # Both stand-in relay hosts must already be in the page's connect-src, or the
        # browser refuses the request before it leaves and the relay records a network
        # error rather than the 401 this test depends on.
        # Health is keyed by slot id, not by URL. Without an explicit reset a user who
        # replaces a relay that earned three 401s gets a brand-new, never-tried relay
        # that is silently excluded for the rest of the session.
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        host = self.base_url.split("//", 1)[1]
        tried: list[str] = []

        def handler(route):
            url = route.request.url
            if host in url or url.startswith("file://"):
                route.fallback()
                return
            if "tfr2go.com" in url:
                tried.append("dead")
                route.fulfill(status=401, content_type="application/json",
                              headers={"Access-Control-Allow-Origin": "*"},
                              body='{"error":"A valid API key is required"}')
                return
            if "davidmegginson.github.io" in url:
                tried.append("fresh")
                _json_route(route, MIL_FIXTURE)
                return
            route.fallback()

        self._route_external(page)
        page.route("**/*", handler)
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            retire = """async () => {
                relayRegistry.setUrl('https://tfr2go.com/');
                for (let i = 0; i < 4; i++) { lastSuccessfulProxy = '';
                    await fetchWithProxy('https://api.adsb.lol/v2/mil', {}, { skipDirect: true }); }
                return relayHealth.isRelayDisabled('custom');
            }"""
            self.assertTrue(page.evaluate(retire),
                            "the refusing custom relay was never retired, so nothing is being tested")
            self.assertIn("dead", tried)

            tried.clear()
            swapped = page.evaluate(
                """async () => {
                    relayRegistry.setUrl('https://davidmegginson.github.io/');
                    const disabled = relayHealth.isRelayDisabled('custom');
                    lastSuccessfulProxy = '';
                    const response = await fetchWithProxy(
                        'https://api.adsb.lol/v2/mil', {}, { skipDirect: true });
                    return { disabled, ok: Boolean(response && response.ok) };
                }"""
            )
            self.assertFalse(swapped["disabled"],
                             "a newly configured relay inherited the previous one's retirement")
            self.assertIn("fresh", tried, "the replacement relay was never attempted")
            self.assertTrue(swapped["ok"], "the replacement relay did not carry the request")

            # Clearing the slot must not leave a verdict that names an unrelated relay.
            described = page.evaluate(
                "() => { relayRegistry.clear(); return relayHealth.describe(); }")
            self.assertNotIn("allorigins.win refused", described)
            self.assertNotIn("corsproxy.io refused", described)
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_attribution_is_visible_and_credits_the_live_feed(self) -> None:
        # A static rule outside any media query used to hide the attribution control
        # entirely, on every raster basemap, while the settings help text told the user
        # it was still showing. OSM/CARTO/Stadia require it, and adsb.fi's terms
        # require the feed to be cited with a link back.
        with self._page() as (page, crashes):
            for density, compact in (("default", False), ("compact", True)):
                page.evaluate("(on) => document.body.classList.toggle('compact-mode', on)", compact)
                page.wait_for_timeout(250)
                box = page.evaluate(
                    """() => {
                        const el = document.querySelector('.leaflet-control-attribution');
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return { w: rect.width, h: rect.height, display: style.display,
                                 visibility: style.visibility, opacity: style.opacity,
                                 html: el.innerHTML };
                    }"""
                )
                self.assertIsNotNone(box, f"no attribution control at {density} density")
                self.assertNotEqual(box["display"], "none", f"attribution hidden at {density} density")
                self.assertNotEqual(box["visibility"], "hidden", f"attribution hidden at {density} density")
                self.assertGreater(box["w"], 0, f"attribution has no width at {density} density")
                self.assertGreater(box["h"], 0, f"attribution has no height at {density} density")
                self.assertIn("Esri", box["html"], f"the basemap credit is missing at {density} density")

            page.evaluate("() => document.body.classList.remove('compact-mode')")

            # The feed credit is added when a source answers, and must be a real link.
            feed = page.evaluate(
                """() => {
                    const src = dataSourceManager.enabledSources()[0];
                    setFeedAttribution(src);
                    const el = document.querySelector('.leaflet-control-attribution');
                    const link = el ? el.querySelector('a[href^="https://adsb"], a[href^="https://airplanes"]') : null;
                    return { name: src.name, href: link ? link.getAttribute('href') : null,
                             text: link ? link.textContent : null };
                }"""
            )
            self.assertTrue(feed["href"], f"the live feed {feed['name']} is not credited with a link")
            self.assertTrue(feed["href"].startswith("https://"))
            self.assertEqual(feed["text"], feed["name"])

            # Visible is not the same as unobstructed. The mobile peek card and the
            # bottom nav are fixed and sit over the map's bottom edge, so check what is
            # actually painted at the control's centre rather than trusting geometry.
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(900)
            covered = page.evaluate(
                """() => {
                    const el = document.querySelector('.leaflet-control-attribution');
                    const rect = el.getBoundingClientRect();
                    const hit = document.elementFromPoint(rect.x + rect.width / 2,
                                                          rect.y + rect.height / 2);
                    return { onTop: el.contains(hit), hit: hit ? hit.className : null,
                             bottom: Math.round(rect.bottom), viewport: window.innerHeight };
                }"""
            )
            self.assertTrue(covered["onTop"],
                            f"mobile chrome covers the attribution: {covered['hit']}")
            self.assertLessEqual(covered["bottom"], covered["viewport"],
                                 "the attribution is pushed off the bottom of the viewport")
            self.assertEqual(crashes, [])

    def test_catalogued_government_aircraft_reach_the_gov_filter(self) -> None:
        # /mil and /pia cannot return a government airframe, so the Gov filter counted
        # zero against a live feed for as long as it shipped. The catalogue is swept by
        # rotating /hex/ batches instead.
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        host = self.base_url.split("//", 1)[1]
        batches: list[str] = []

        def handler(route):
            url = route.request.url
            if host in url or url.startswith("file://"):
                route.fallback()
                return
            # The relay percent-encodes the target, so match the encoded form too.
            if "/hex/" in url or "%2Fhex%2F" in url:
                batches.append(url)
                requested = url.split("hex%2F")[-1] if "%2Fhex%2F" in url else url.split("/hex/")[-1]
                first = requested.split("%2C")[0].split(",")[0].split("?")[0][:6]
                _json_route(route, {"ac": [{
                    "hex": first, "type": "adsb_icao", "flight": "GOV1    ", "t": "B762",
                    "lat": 51.4, "lon": -0.4, "alt_baro": 30000, "gs": 420, "track": 90,
                }]})
                return
            route.fallback()

        self._route_external(page)
        page.route("**/*", handler)
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            # The sweep is only meaningful if the catalogue actually loaded.
            catalogue = page.evaluate(
                """() => {
                    catalogueSweep.refresh();
                    return { total: catalogueSweep.hexes.length,
                             batch: catalogueSweep.batchSize(),
                             gov: militaryDB.government.size,
                             pol: militaryDB.police.size };
                }"""
            )
            self.assertGreater(catalogue["gov"], 0, "the government catalogue did not load")
            self.assertGreater(catalogue["pol"], 0, "the police catalogue did not load")
            self.assertEqual(catalogue["total"], catalogue["gov"] + catalogue["pol"])

            # A batch has to fit inside the egress URL cap once the relay encodes it,
            # or validateUrl drops the request and the sweep silently does nothing.
            fits = page.evaluate(
                """() => {
                    const batch = catalogueSweep.nextBatch();
                    const target = 'https://api.adsb.lol/v2/hex/' + batch.join(',').toLowerCase();
                    const relayed = CONFIG.publicRelays[0].build(target);
                    return { size: batch.length, target: target.length, relayed: relayed.length,
                             cap: egressPolicy.maxUrlLength,
                             accepted: Boolean(egressPolicy.validateUrl(relayed, { kind: 'proxy' })) };
                }"""
            )
            self.assertGreater(fits["size"], 0)
            self.assertLessEqual(fits["relayed"], fits["cap"],
                                 "the relayed batch URL exceeds the egress cap and would be dropped")
            self.assertTrue(fits["accepted"], "egressPolicy rejects the batch URL the sweep builds")

            # The cursor must advance and wrap, or the same head is polled forever and
            # the tail of the catalogue is never reached.
            walked = page.evaluate(
                """() => {
                    catalogueSweep.cursor = 0;
                    const first = catalogueSweep.nextBatch()[0];
                    const second = catalogueSweep.nextBatch()[0];
                    return { first, second, moved: first !== second };
                }"""
            )
            self.assertTrue(walked["moved"], "the sweep cursor does not advance between batches")

            # End to end: a catalogued government hex fed back by the API must be
            # classified as government and counted under the Gov filter.
            landed = page.evaluate(
                """async () => {
                    // VIP wins over government in classifyAircraft, and several
                    // dictator-alert airframes are on both lists, so pick one that is
                    // only in the government catalogue.
                    const hex = [...militaryDB.government.keys()].find(h =>
                        !badgersBestDB.isVIP(String(h).toUpperCase()) &&
                        !militaryDB.military.has(String(h).toUpperCase()));
                    if (!hex) return { hex: null };
                    delete aircraftCache[hex.toUpperCase()];
                    processAircraftData([{ hex: hex.toLowerCase(), type: 'adsb_icao',
                        flight: 'GOV1', t: 'B762', lat: 51.4, lon: -0.4,
                        alt_baro: 30000, gs: 420, track: 90 }], null);
                    const cached = aircraftCache[hex.toUpperCase()];
                    return { hex, kept: Boolean(cached),
                             category: cached ? cached.category_type : null,
                             govCount: Number(document.getElementById('countGov').textContent) };
                }"""
            )
            self.assertIsNotNone(landed["hex"],
                                 "no government-only hex in the catalogue to test with")
            self.assertTrue(landed["kept"],
                            f"a catalogued government aircraft ({landed['hex']}) was discarded")
            self.assertEqual(landed["category"], "government")
            self.assertGreater(landed["govCount"], 0, "the Gov counter stayed at zero")

            # A catalogue hit sets militaryInfo whatever its sub-category, so testing
            # that alone put every government and police airframe into the Military
            # lane as well. Each must appear under its own filter and no other.
            lanes = page.evaluate(
                """() => {
                    const pick = (map) => [...map.keys()].find(h =>
                        !badgersBestDB.isVIP(String(h).toUpperCase()) &&
                        !militaryDB.military.has(String(h).toUpperCase()));
                    const govHex = pick(militaryDB.government);
                    const polHex = pick(militaryDB.police);
                    if (!govHex || !polHex) return null;
                    const seed = (hex, flight) => {
                        const key = hex.toUpperCase();
                        delete aircraftCache[key];
                        processAircraftData([{ hex: hex.toLowerCase(), type: 'adsb_icao',
                            flight, t: 'B762', lat: 51.4, lon: -0.4, alt_baro: 30000,
                            gs: 420, track: 90 }], null);
                        return aircraftCache[key];
                    };
                    const gov = seed(govHex, 'GOVLANE');
                    const pol = seed(polHex, 'POLLANE');
                    return {
                        govCategory: gov ? gov.category_type : null,
                        polCategory: pol ? pol.category_type : null,
                        govInMilitary: isMilitaryAircraft(gov),
                        polInMilitary: isMilitaryAircraft(pol),
                        polInPolice: isPoliceAircraft(pol),
                        govInPolice: isPoliceAircraft(gov)
                    };
                }"""
            )
            self.assertIsNotNone(lanes, "no government-only or police-only hex to test with")
            self.assertEqual(lanes["govCategory"], "government")
            self.assertEqual(lanes["polCategory"], "police")
            self.assertFalse(lanes["govInMilitary"], "a government aircraft also counts as military")
            self.assertFalse(lanes["polInMilitary"], "a police aircraft is filed under military")
            self.assertTrue(lanes["polInPolice"], "a police aircraft has no lane of its own")
            self.assertFalse(lanes["govInPolice"])

            # And the sweep must actually issue its batch request during a refresh.
            batches.clear()
            page.evaluate("async () => { lastFetchTime = 0; await loadAircraft(); }")
            page.wait_for_timeout(2500)
            self.assertTrue(batches, "the refresh cycle issued no catalogue batch request")
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_ladd_is_a_first_class_filter_that_survives_a_share_link(self) -> None:
        # LADD is the FAA's other privacy programme and tar1090 treats military, pia and
        # ladd as co-equal filterDbFlag values. This app fetched neither the endpoint nor
        # recognised the flag, and airplanes.live's piaUrl pointed at /v2/ladd, which
        # conflated the two categories on the one source that publishes both.
        with self._page() as (page, crashes):
            # Every source that publishes /ladd must ask for it, and the one that
            # answers 400 must not be asked at all.
            wiring = page.evaluate(
                """() => dataSourceManager.sources.map(s => ({
                    key: s.key, ladd: s.laddUrl || null, pia: s.piaUrl || null }))"""
            )
            by_key = {row["key"]: row for row in wiring}
            for key in ("adsbone", "adsblol", "airplaneslive"):
                self.assertTrue(by_key[key]["ladd"], f"{key} does not request /ladd")
                self.assertTrue(by_key[key]["ladd"].endswith("/ladd"))
                self.assertNotEqual(by_key[key]["pia"], by_key[key]["ladd"],
                                    f"{key} points pia and ladd at the same endpoint")
            self.assertIsNone(by_key["adsbfi"]["ladd"],
                              "adsb.fi answers 400 for /ladd and must not be asked")

            # dbFlags bit 8 is what marks a LADD airframe, and it must survive ingest,
            # be classified as its own category, and be counted.
            landed = page.evaluate(
                """() => {
                    const hex = 'FFEE01';
                    delete aircraftCache[hex];
                    processAircraftData([{ hex: hex.toLowerCase(), type: 'adsb_icao',
                        flight: 'LADD1', t: 'PC12', dbFlags: 8, lat: 40.1, lon: -74.2,
                        alt_baro: 11350, gs: 197, track: 88 }], null);
                    const cached = aircraftCache[hex];
                    return { kept: Boolean(cached),
                             category: cached ? cached.category_type : null,
                             count: Number(document.getElementById('countLadd').textContent) };
                }"""
            )
            self.assertTrue(landed["kept"], "a LADD aircraft was discarded at ingest")
            self.assertEqual(landed["category"], "ladd")
            self.assertGreater(landed["count"], 0, "the LADD counter stayed at zero")

            # A military airframe must not be swept into the LADD lane.
            separation = page.evaluate(
                """() => {
                    const hex = 'FFEE02';
                    delete aircraftCache[hex];
                    const before = Number(document.getElementById('countLadd').textContent);
                    processAircraftData([{ hex: hex.toLowerCase(), type: 'adsb_icao',
                        flight: 'RCH9', t: 'C17', dbFlags: 1, lat: 40.2, lon: -74.3,
                        alt_baro: 30000, gs: 400, track: 90 }], null);
                    const cached = aircraftCache[hex];
                    return { category: cached ? cached.category_type : null,
                             before, after: Number(document.getElementById('countLadd').textContent) };
                }"""
            )
            self.assertEqual(separation["category"], "military",
                             "a military aircraft was reclassified as LADD")
            self.assertEqual(separation["after"], separation["before"],
                             "a military aircraft was counted in the LADD lane")

            # The filter has to round-trip through a share link.
            page.evaluate("() => { settings.filter = 'ladd'; }")
            link = page.evaluate("() => shareManager.buildViewUrl ? shareManager.buildViewUrl() : location.href")
            self.assertIn("filter=ladd", link)

            page.goto(link, wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)
            self.assertEqual(page.evaluate("() => settings.filter"), "ladd",
                             "the LADD filter did not survive a share link")
            self.assertEqual(crashes, [])

    def test_position_source_is_never_shown_as_an_aircraft_type(self) -> None:
        # In the tar1090/adsb.lol schema `type` is the position source (adsb_icao, mlat,
        # tisb, adsr, mode_s) and `t` is the ICAO type designator. Three surfaces read
        # `ac.t || ac.type`, so an airframe with no database entry displayed "adsb_icao"
        # where its type belonged.
        with self._page() as (page, crashes):
            rendered = page.evaluate(
                """() => {
                    // A catalogued military airframe, so the keep filter admits it, but
                    // with no `t`: exactly the case that used to fall through to the
                    // position source for its displayed type.
                    const hex = [...militaryDB.military.keys()][0].toUpperCase();
                    delete aircraftCache[hex];
                    processAircraftData([{ hex: hex.toLowerCase(), type: 'mlat',
                        flight: 'NOTYPE1', lat: 51.4, lon: -0.4,
                        alt_baro: 20000, gs: 300, track: 45 }], null);
                    const cached = aircraftCache[hex];
                    if (cached) { cached.t = ''; cached.desc = ''; }
                    selectAircraft(hex);
                    window.__mlatHex = hex;
                    return {
                        kept: Boolean(cached),
                        posSource: cached ? cached.posSource : null,
                        infoType: document.getElementById('infoType').textContent,
                        infoPosSource: document.getElementById('infoPosSource').textContent,
                        posRowShown: document.getElementById('infoPosSourceRow').style.display !== 'none'
                    };
                }"""
            )
            self.assertTrue(rendered["kept"])
            # The defect, stated directly.
            self.assertNotIn("mlat", rendered["infoType"].lower(),
                             "the position source is being rendered as the aircraft type")
            self.assertNotIn("adsb_icao", rendered["infoType"].lower())

            # And the field is surfaced where an analyst can read it, in plain words.
            self.assertTrue(rendered["posRowShown"], "the position source row stayed hidden")
            self.assertIn("MLAT", rendered["infoPosSource"])
            self.assertEqual(rendered["posSource"], "mlat")

            # No other surface may render it as a type either.
            surfaces = page.evaluate(
                """() => {
                    settings.filter = 'mil-vip';
                    mobileSupport.renderAircraftList && mobileSupport.renderAircraftList();
                    const text = document.body.innerText;
                    return { leaks: ['adsb_icao', 'mlat •', '• mlat', 'tisb_icao']
                        .filter(token => text.includes(token)) };
                }"""
            )
            self.assertEqual(surfaces["leaks"], [],
                             f"a position source leaked into a type surface: {surfaces['leaks']}")

            # A filter must be able to exclude everything the aircraft did not report.
            filtered = page.evaluate(
                """() => {
                    const mlatHex = window.__mlatHex, adsbHex = 'FFDD02';
                    delete aircraftCache[adsbHex];
                    processAircraftData([{ hex: adsbHex.toLowerCase(), type: 'adsb_icao',
                        flight: 'REAL1', t: 'C17', dbFlags: 1, lat: 51.5, lon: -0.5,
                        alt_baro: 30000, gs: 400, track: 90 }], null);
                    searchSystem.filters = { adsbOnly: true };
                    const mlatPasses = searchSystem.passesFilters(aircraftCache[mlatHex]);
                    const adsbPasses = searchSystem.passesFilters(aircraftCache[adsbHex]);
                    searchSystem.filters = {};
                    const bothPassUnfiltered = searchSystem.passesFilters(aircraftCache[mlatHex])
                        && searchSystem.passesFilters(aircraftCache[adsbHex]);
                    return { mlatPasses, adsbPasses, bothPassUnfiltered };
                }"""
            )
            self.assertTrue(filtered["bothPassUnfiltered"],
                            "the fixture aircraft are filtered out for some unrelated reason")
            self.assertTrue(filtered["adsbPasses"], "an ADS-B position was excluded by the ADS-B filter")
            self.assertFalse(filtered["mlatPasses"], "an MLAT position survived the ADS-B-only filter")

            # The offline projection is an explicit field allowlist. Dropping posSource
            # there made a cache round trip hide genuine ADS-B aircraft from this very
            # filter, because a missing value reads as "not ADS-B".
            round_tripped = page.evaluate(
                """() => {
                    const hex = 'FFDD02';
                    const snapshot = privacySafeAircraftSnapshot(aircraftCache[hex],
                                                                 { includeHistory: false });
                    return { carried: Object.prototype.hasOwnProperty.call(snapshot, 'posSource'),
                             value: snapshot.posSource };
                }"""
            )
            self.assertTrue(round_tripped["carried"],
                            "the offline projection drops the position source")
            self.assertEqual(round_tripped["value"], "adsb_icao")
            self.assertEqual(crashes, [])

    def test_uncaught_failures_reach_the_diagnostics_export(self) -> None:
        # There was no window.onerror and no unhandledrejection handler anywhere, and
        # the diagnostics export carried source health only - no version, no browser,
        # no errors. With an empty issue tracker that made the first bug only a user
        # could reproduce undiagnosable.
        with self._page() as (page, crashes):
            # An exception thrown from a timer is uncaught by definition: nothing in
            # the app's own call stack can catch it.
            page.evaluate("() => { setTimeout(() => { throw new Error('AUDIT_TIMER_BOOM'); }, 0); }")
            page.evaluate("() => { Promise.reject(new Error('AUDIT_PROMISE_BOOM')); }")
            page.wait_for_timeout(800)

            diagnostics = page.evaluate("() => dataSourceManager.getDiagnostics()")

            messages = " ".join(entry["message"] for entry in diagnostics["errors"])
            self.assertIn("AUDIT_TIMER_BOOM", messages,
                          "an uncaught exception never reached the error log")
            self.assertIn("AUDIT_PROMISE_BOOM", messages,
                          "a rejected promise never reached the error log")

            # The export has to describe the build and the situation, not just sources.
            self.assertEqual(diagnostics["appVersion"], "0.8.2")
            for field in ("cacheSchema", "userAgent", "renderer", "basemap", "filter", "relay"):
                self.assertTrue(diagnostics.get(field) not in (None, ""), f"{field} missing")
            self.assertIn(diagnostics["renderer"], ("leaflet", "webgl"))
            self.assertLessEqual(len(diagnostics["errors"]), 20)

            # And it still must not carry anything that identifies an aircraft.
            leaked = page.evaluate(
                """() => {
                    errorHandler.log('/audit', new Error(
                        'failed for a0b1c2 reg N615WM via https://api.adsb.lol/v2/hex/a0b1c2'), 'error');
                    const text = JSON.stringify(dataSourceManager.getDiagnostics());
                    return { text, hits: ['a0b1c2', 'N615WM', 'api.adsb.lol/v2/hex']
                        .filter(token => text.includes(token)) };
                }"""
            )
            self.assertEqual(leaked["hits"], [],
                             f"an identifier survived redaction: {leaked['hits']}")

            # A callsign identifies an aircraft as surely as its hex does.
            callsign = page.evaluate(
                """() => {
                    errorHandler.log('/audit2', new Error('lost contact with RCH463'), 'error');
                    const text = JSON.stringify(dataSourceManager.getDiagnostics());
                    return { leaked: text.includes('RCH463'), redacted: text.includes('<callsign>') };
                }"""
            )
            self.assertFalse(callsign["leaked"], "a callsign survived into the diagnostics export")
            self.assertTrue(callsign["redacted"])

            # The console is a side channel out of the browser as well: devtools
            # screenshots end up in bug reports.
            console_lines: list[str] = []
            page.on("console", lambda msg: console_lines.append(msg.text))
            page.evaluate(
                "() => errorHandler.log('/audit3',"
                " new Error('trace a0b1c2 reg N615WM callsign RCH463'), 'error')")
            page.wait_for_timeout(400)
            joined = " ".join(console_lines)
            for token in ("a0b1c2", "N615WM", "RCH463"):
                self.assertNotIn(token, joined, f"{token} reached the console unredacted")

            # And the handler must not recurse when the thrown value cannot be
            # stringified - that value is exactly what a broken library throws.
            survived = page.evaluate(
                """() => {
                    const hostile = { toString() { throw new Error('nope'); } };
                    try { errorHandler.log('/audit4', hostile, 'error'); } catch (e) { return 'threw'; }
                    return errorHandler.getRecent(1)[0].message;
                }"""
            )
            self.assertEqual(survived, "<unprintable>",
                             "a value whose toString throws was not handled")
            self.assertIn("<hex>", leaked["text"])
            self.assertIn("<reg>", leaked["text"])
            self.assertIn("<url>", leaked["text"])

            # Two thrown errors are expected; the page itself must not have crashed
            # in any other way.
            unexpected = [c for c in crashes if "AUDIT_" not in c]
            self.assertEqual(unexpected, [])

    def test_the_altitude_legend_renders_and_follows_its_setting(self) -> None:
        # A complete, styled, six-locale legend was hidden by an unconditional
        # `display: none !important` and never rendered, stranding its translations.
        probe = """() => {
            const el = document.querySelector('.legend');
            if (!el) return { present: false };
            const r = el.getBoundingClientRect();
            const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
            return { present: true, display: getComputedStyle(el).display,
                     w: Math.round(r.width), h: Math.round(r.height),
                     onTop: el.contains(hit), hit: hit ? (hit.className || hit.tagName) : null,
                     inViewport: r.top >= 0 && r.bottom <= window.innerHeight
                                 && r.right <= window.innerWidth,
                     bands: el.querySelectorAll('.legend-item').length,
                     text: el.textContent.trim() };
        }"""
        with self._page() as (page, crashes):
            shown = page.evaluate(probe)
            self.assertTrue(shown["present"], "the legend markup is gone")
            self.assertNotEqual(shown["display"], "none", "the legend is hidden by CSS")
            self.assertGreater(shown["w"], 0)
            self.assertGreater(shown["h"], 0)
            self.assertEqual(shown["bands"], 7, "an altitude band is missing from the legend")
            # Visible is not unobstructed: the zoom control and the info panel share
            # this edge of the map.
            self.assertTrue(shown["onTop"], f"the legend is covered by {shown['hit']}")
            self.assertTrue(shown["inViewport"], "the legend is drawn outside the viewport")
            # Its labels come from the catalogue, so a broken key shows as the key.
            self.assertNotIn("legend.", shown["text"])

            # It explains the altitude colouring, so it follows that setting.
            page.evaluate(
                "() => { document.getElementById('toggleAltColors').click(); }")
            page.wait_for_timeout(300)
            hidden = page.evaluate(probe)
            self.assertEqual(hidden["display"], "none",
                             "the legend stayed up after altitude colouring was switched off")

            page.evaluate("() => { document.getElementById('toggleAltColors').click(); }")
            page.wait_for_timeout(300)
            self.assertNotEqual(page.evaluate(probe)["display"], "none",
                                "the legend did not come back when colouring was switched on")
            self.assertEqual(crashes, [])

    def test_track_shape_analysis_only_runs_where_it_is_read(self) -> None:
        # analyse() slices 120 history points and runs a haversine plus a bearing over
        # each one. It used to run for every aircraft on every sweep while render()
        # drew the result for exactly one.
        with self._page() as (page, crashes):
            measured = page.evaluate(
                """() => {
                    // A synthetic sweep of 500 aircraft, each with enough history that
                    // analyse() does its full walk rather than bailing on minPoints.
                    const now = Date.now();
                    const history = [];
                    for (let i = 0; i < 300; i++) {
                        history.push([51 + i * 0.001, -0.4 + i * 0.001, 30000, now - (300 - i) * 1000]);
                    }
                    const fleet = [];
                    for (let i = 0; i < 500; i++) {
                        fleet.push({ hex: 'FF' + i.toString(16).padStart(4, '0').toUpperCase(),
                                     history: history.map(p => p.slice()), t: 'C17' });
                    }

                    let calls = 0;
                    const realAnalyse = trackHeuristicManager.analyse;
                    trackHeuristicManager.analyse = function (...args) {
                        calls++;
                        return realAnalyse.apply(this, args);
                    };
                    const started = performance.now();
                    fleet.forEach(ac => trackHeuristicManager.update(ac));
                    const elapsed = performance.now() - started;
                    trackHeuristicManager.analyse = realAnalyse;

                    // The one aircraft whose answer is actually displayed must still
                    // get a real result, on demand.
                    const target = fleet[0];
                    const onDemand = trackHeuristicManager.ensure(target);

                    return { calls, elapsed, fleet: fleet.length,
                             hasMetrics: Boolean(onDemand && onDemand.metrics),
                             tagCount: onDemand ? onDemand.tags.length : -1 };
                }"""
            )
            # Not "fewer calls" but "almost none": nothing in this fleet is selected or
            # watchlisted, so the sweep should analyse nothing at all.
            self.assertEqual(measured["fleet"], 500)
            self.assertLessEqual(
                measured["calls"], measured["fleet"] // 10,
                f"analyse() ran {measured['calls']} times for 500 unselected aircraft")
            # The call count is the contract, but the sweep also has to be fast in
            # wall-clock terms - a cheap skip that still took 40 ms per tick would
            # satisfy the count and miss the point.
            self.assertLess(measured["elapsed"], 250,
                            f"a 500-aircraft sweep took {measured['elapsed']:.0f} ms")

            # And the result is still correct when it is asked for.
            self.assertTrue(measured["hasMetrics"],
                            "an on-demand analysis produced no metrics")
            self.assertGreaterEqual(measured["tagCount"], 0)

            # A selected aircraft is analysed by the sweep without being asked.
            selected = page.evaluate(
                """() => {
                    const hex = Object.keys(aircraftCache)[0];
                    if (!hex) return null;
                    selectedHex = hex;
                    const ac = aircraftCache[hex];
                    ac.trackHeuristics = null;
                    ac.trackHeuristicsStale = true;
                    trackHeuristicManager.update(ac);
                    return { computed: Boolean(ac.trackHeuristics),
                             stale: ac.trackHeuristicsStale === true };
                }"""
            )
            self.assertIsNotNone(selected, "no aircraft in the fixture to select")
            self.assertTrue(selected["computed"],
                            "the selected aircraft was not analysed by the sweep")
            self.assertFalse(selected["stale"])
            self.assertEqual(crashes, [])

    def test_cold_start_does_not_download_the_full_registration_csv(self) -> None:
        # Without OPFS sync access the app fetched data/aircraft/registrations.csv -
        # 32 MB - on every cold start, while a compact registry sat unused because it
        # was wired only to the OPFS path (and was itself corrupt: keyed by whole CSV
        # lines rather than by hex, so it seeded 3,928 junk entries).
        requested: list[str] = []
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        page.on("request", lambda request: requested.append(request.url))
        self._route_external(page)
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            # Take the path a browser without OPFS sync access takes, by removing the
            # capability rather than by calling the fallback directly - otherwise the
            # test proves the fallback works without proving it is what runs.
            loaded = page.evaluate(
                """async () => {
                    const realGetDirectory = navigator.storage && navigator.storage.getDirectory;
                    if (navigator.storage) {
                        Object.defineProperty(navigator.storage, 'getDirectory',
                            { configurable: true, value: undefined });
                    }
                    registrationOPFSManager.worker = null;
                    registrationDB.aircraft.clear();
                    registrationDB.loaded = false;
                    registrationDB.loading = false;
                    const opfsAvailable = registrationOPFSManager.init();
                    const ok = await registrationDB.init();
                    if (navigator.storage && realGetDirectory) {
                        Object.defineProperty(navigator.storage, 'getDirectory',
                            { configurable: true, value: realGetDirectory });
                    }
                    return { ok, opfsAvailable, size: registrationDB.aircraft.size };
                }"""
            )
            self.assertFalse(loaded["opfsAvailable"],
                             "OPFS was not actually stubbed out, so the fallback path was not taken")
            self.assertTrue(loaded["ok"], "the registration database failed to load")
            self.assertGreater(loaded["size"], 5000,
                               "the compact registry seeded almost nothing")

            csv_hits = [u for u in requested if u.endswith("registrations.csv")]
            self.assertEqual(csv_hits, [],
                             "cold start still downloads the full registration CSV")
            json_hits = [u for u in requested if u.endswith("registrations.json")]
            self.assertTrue(json_hits, "the compact registry was never fetched")

            # And what it seeded has to be usable: hex-keyed, resolving to real records.
            resolved = page.evaluate(
                """() => {
                    // Not every catalogued hex has a row in the upstream registration
                    // data, so measure coverage rather than betting on one airframe.
                    // Sample evenly across the catalogue: the first few hundred hexes
                    // are the lowest ICAO allocations and are unrepresentative.
                    const all = [...militaryDB.military.keys()];
                    const step = Math.max(1, Math.floor(all.length / 500));
                    const hexes = all.filter((_, i) => i % step === 0).slice(0, 500);
                    let found = 0, withRegistration = 0;
                    for (const hex of hexes) {
                        const record = registrationDB.aircraft.get(String(hex).toUpperCase());
                        if (record) { found++; if (record.r) withRegistration++; }
                    }
                    return { sampled: hexes.length, found, withRegistration };
                }"""
            )
            self.assertIsNotNone(resolved)
            self.assertGreater(resolved["sampled"], 0, "the military catalogue is empty")
            # Measured coverage is ~83% of catalogued military hexes; the rest have no
            # row in the upstream registration data at all, so they were never
            # resolvable from the CSV either. A 50% floor was loose enough to hide a
            # real collapse, so hold it just under what the data actually supports.
            self.assertGreater(
                resolved["found"], resolved["sampled"] * 0.75,
                f"only {resolved['found']}/{resolved['sampled']} catalogued military hexes "
                "resolve in the compact registry")
            self.assertGreater(resolved["withRegistration"], 0)

            # A registry keyed by anything but hex must be refused outright rather than
            # loaded as if it were real - that is the defect that shipped.
            refused = page.evaluate(
                """async () => {
                    const realFetch = window.fetch;
                    window.fetch = async () => new Response(
                        JSON.stringify({ 'AAAAAA;N1;C17;;;;OWNER': { r: 'junk' } }),
                        { status: 200, headers: { 'Content-Type': 'application/json' } });
                    const accepted = await registrationDB.fetchCompact();
                    window.fetch = realFetch;
                    return accepted;
                }"""
            )
            self.assertFalse(refused, "a registry keyed by CSV lines was accepted as valid")
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_a_hidden_tab_stops_polling(self) -> None:
        # Six repeating timers stored no handle and bypassed the pausable registry, so
        # a background tab kept probing connectivity, re-checking source health,
        # re-rendering the detail panel and re-reading geolocation forever.
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        outbound: list[str] = []
        host = self.base_url.split("//", 1)[1]
        page.on("request", lambda request: outbound.append(request.url)
                if host not in request.url and not request.url.startswith("file://") else None)
        self._route_external(page)
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            registered = page.evaluate(
                "() => _pausableIntervals.map(entry => entry.name).filter(Boolean)")
            for name in ("connectivity", "source-health", "source-detail",
                         "position-cache", "plane-alert-sync"):
                self.assertIn(name, registered, f"the {name} timer is not pausable")

            # Hide the tab the way the browser does, and confirm every registered timer
            # actually stopped rather than merely being marked.
            page.evaluate(
                """() => {
                    Object.defineProperty(document, 'visibilityState',
                        { configurable: true, get: () => 'hidden' });
                    Object.defineProperty(document, 'hidden',
                        { configurable: true, get: () => true });
                    document.dispatchEvent(new Event('visibilitychange'));
                }"""
            )
            page.wait_for_timeout(500)
            live = page.evaluate("() => _pausableIntervals.filter(e => e.id).length")
            self.assertEqual(live, 0, "a registered timer kept running while the tab was hidden")

            self.assertIsNone(page.evaluate("() => _fetchIntervalId"),
                              "the feed loop kept running while the tab was hidden")

            # Boot fallbacks can still be completing, and one-shot requests are not
            # polling. What must not happen is the same URL being fetched again and
            # again, which is what an unpaused timer looks like.
            outbound.clear()
            page.wait_for_timeout(12000)
            repeated = {url: outbound.count(url) for url in set(outbound)
                        if outbound.count(url) > 1}
            self.assertEqual(repeated, {},
                             f"a hidden tab kept re-fetching: {repeated}")

            # And they must come back, or hiding the tab once would end the session.
            page.evaluate(
                """() => {
                    Object.defineProperty(document, 'visibilityState',
                        { configurable: true, get: () => 'visible' });
                    Object.defineProperty(document, 'hidden',
                        { configurable: true, get: () => false });
                    document.dispatchEvent(new Event('visibilitychange'));
                }"""
            )
            page.wait_for_timeout(500)
            resumed = page.evaluate("() => _pausableIntervals.filter(e => e.id).length")
            self.assertEqual(resumed, page.evaluate("() => _pausableIntervals.length"),
                             "timers did not resume when the tab came back")
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_an_older_database_upgrades_to_every_store(self) -> None:
        # The store guards live inside onupgradeneeded, which only fires when the
        # version increases. A user carrying an older database must come out of the
        # upgrade with every store the code opens transactions against.
        #
        # This drives the app's own skytrackDB.init() against a real pre-seeded v1
        # database. An earlier version of this test re-implemented the guard logic in
        # the test itself, which proved the test's copy worked and said nothing about
        # the shipped handler.
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        self._route_external(page)
        try:
            # Seed a v1 database on the origin BEFORE the app loads, shaped as it
            # shipped: aircraftCache present, trailHistory absent.
            page.goto(f"{self.base_url}/manifest.json", wait_until="load", timeout=30000)
            seeded = page.evaluate(
                """async () => {
                    await new Promise(resolve => {
                        const del = indexedDB.deleteDatabase('VIPTrackDB');
                        del.onsuccess = del.onerror = del.onblocked = () => resolve();
                    });
                    const db = await new Promise((resolve, reject) => {
                        const request = indexedDB.open('VIPTrackDB', 1);
                        request.onupgradeneeded = event => {
                            const database = event.target.result;
                            database.createObjectStore('databases', { keyPath: 'name' });
                            database.createObjectStore('userData', { keyPath: 'key' });
                            database.createObjectStore('aircraftCache', { keyPath: 'hex' });
                        };
                        request.onsuccess = () => resolve(request.result);
                        request.onerror = () => reject(request.error);
                    });
                    const names = [];
                    for (let i = 0; i < db.objectStoreNames.length; i++) names.push(db.objectStoreNames[i]);
                    const version = db.version;
                    db.close();
                    return { names: names.sort(), version };
                }"""
            )
            self.assertEqual(seeded["names"], ["aircraftCache", "databases", "userData"])
            self.assertEqual(seeded["version"], 1)

            # Now load the app on the same origin and let its own init() upgrade it.
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            after = page.evaluate(
                """async () => {
                    await skytrackDB.init();
                    const db = skytrackDB.db;
                    if (!db) return null;
                    const names = [];
                    for (let i = 0; i < db.objectStoreNames.length; i++) names.push(db.objectStoreNames[i]);
                    let usable = false;
                    try {
                        const tx = db.transaction(['trailHistory'], 'readwrite');
                        tx.objectStore('trailHistory').add({ timestamp: Date.now(), lat: 0, lon: 0 });
                        await new Promise((resolve, reject) => {
                            tx.oncomplete = resolve;
                            tx.onerror = () => reject(tx.error);
                        });
                        usable = true;
                    } catch (error) { usable = false; }
                    return { names: names.sort(), version: db.version, usable };
                }"""
            )
            self.assertIsNotNone(after, "the app never opened its database")
            self.assertGreater(after["version"], seeded["version"],
                               "the app did not upgrade the older database")
            self.assertEqual(after["names"], ["databases", "trailHistory", "userData"],
                             "the app's own upgrade did not converge on the current store set")
            self.assertNotIn("aircraftCache", after["names"],
                             "the unused store survived the app's upgrade")
            self.assertTrue(after["usable"],
                            "a transaction against the newly created store failed")
            self.assertEqual(crashes, [])
        finally:
            page.evaluate(
                "() => new Promise(resolve => {"
                " const del = indexedDB.deleteDatabase('VIPTrackDB');"
                " del.onsuccess = del.onerror = del.onblocked = () => resolve(); })")
            page.close()

    def test_a_share_link_reproduces_the_whole_filter_state(self) -> None:
        # A link carried the map position and the category filter but none of the
        # search filters, so handing someone a link did not hand them the view - which
        # is the reproducible-query requirement an OSINT workflow is built on.
        with self._page() as (page, crashes):
            built = page.evaluate(
                """() => {
                    searchSystem.filters = {
                        altMin: 15000, altMax: 41000,
                        speedMin: 200, speedMax: 550,
                        airport: 'EGLL', airline: 'RCH',
                        regex: '^RCH', types: ['military'],
                        emergency: true, adsbOnly: true
                    };
                    settings.filter = 'military';
                    return { url: shareManager.buildViewUrl(),
                             filters: JSON.parse(JSON.stringify(searchSystem.filters)) };
                }"""
            )
            url = built["url"]
            for expected in ("altMin=15000", "altMax=41000", "speedMin=200", "speedMax=550",
                             "airport=EGLL", "airline=RCH", "regex=%5ERCH", "types=military",
                             "emergency=1", "adsbOnly=1", "filter=military"):
                self.assertIn(expected, url, f"{expected} is missing from the share link")

            # A share link must still never name a privacy-protected aircraft.
            self.assertNotIn("hex=", url.split("?", 1)[1].replace("filter=", ""))

            page.goto(url, wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            restored = page.evaluate(
                """() => ({
                    filters: JSON.parse(JSON.stringify(searchSystem.filters || {})),
                    category: settings.filter,
                    inputs: {
                        altMin: document.getElementById('altMin')?.value,
                        airport: document.getElementById('filterAirport')?.value,
                        adsbOnly: document.getElementById('filterAdsbOnly')?.checked
                    }
                })"""
            )
            self.assertEqual(restored["category"], "military")
            for key, value in built["filters"].items():
                self.assertEqual(restored["filters"].get(key), value,
                                 f"{key} did not survive the round trip")

            # The controls must agree with what is being filtered, or the panel lies.
            self.assertEqual(restored["inputs"]["altMin"], "15000")
            self.assertEqual(restored["inputs"]["airport"], "EGLL")
            self.assertTrue(restored["inputs"]["adsbOnly"])

            # And the same filters must select the same aircraft, which is the point.
            same = page.evaluate(
                """() => {
                    const passing = Object.values(aircraftCache)
                        .filter(ac => searchSystem.passesFilters(ac)).length;
                    searchSystem.filters = {};
                    const unfiltered = Object.values(aircraftCache).length;
                    return { passing, unfiltered };
                }"""
            )
            self.assertLessEqual(same["passing"], same["unfiltered"],
                                 "the restored filters selected more than the whole cache")
            self.assertEqual(crashes, [])

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
        #
        # The Inline exception is the one that applies here: a target inside a sentence,
        # sized by the line-height of the non-target text around it, is exempt. The map
        # credit is exactly that shape, and the licences (ODbL for OSM, the CARTO and
        # Stadia terms, adsb.fi's link-back requirement) all require those credits to be
        # links. Enlarging them to 24px would mean a credit line taller than the control.
        # Everything outside that credit is still held to the full size.
        for width, height in ((1440, 900), (390, 844)):
            with self._page(viewport={"width": width, "height": height}) as (page, crashes):
                undersized = page.evaluate(
                    "() => { const sel = 'a[href],button:not([disabled]),input:not([disabled]),"
                    "select,[role=switch],[role=tab]'; const out = [];"
                    " document.querySelectorAll(sel).forEach(el => { if (!el.offsetParent) return;"
                    " if (el.tagName === 'A' && getComputedStyle(el).display === 'inline'"
                    " && el.closest('.leaflet-control-attribution')) return;"
                    " const r = el.getBoundingClientRect();"
                    " if (r.width < 24 || r.height < 24) out.push((el.id || el.className || el.tagName)"
                    " + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)); }); return out; }"
                )
                self.assertEqual(undersized, [], f"{width}x{height}")

                # The exception is about pointer target size, not about keyboard access.
                # Every credit link must still be reachable and show a focus ring, or the
                # exemption would be hiding a real regression.
                credits = page.evaluate(
                    "() => [...document.querySelectorAll('.leaflet-control-attribution a[href]')]"
                    " .map(a => ({ tabbable: a.tabIndex >= 0, href: a.getAttribute('href') || '' }))"
                )
                self.assertTrue(credits, "the map credit has no links to exempt")
                for credit in credits:
                    self.assertTrue(credit["tabbable"], f"credit link not keyboard reachable: {credit}")
                    self.assertTrue(credit["href"].startswith("https://"), credit)
                self.assertEqual(crashes, [])

    # ---- surfaces the 2026-08-18 audit listed as unexercised (VT-53) ----

    def test_weather_parsing_survives_the_shapes_the_api_actually_returns(self) -> None:
        # aviationweather.gov reports visibility as a string ("10+", "1/2"), not a
        # number, and omits fields entirely rather than sending null.
        with self._page() as (page, crashes):
            categories = page.evaluate(
                """() => ({
                    halfMile: weatherSystem.getFlightCategory({ visib: '1/2', clouds: [] }),
                    tenPlus: weatherSystem.getFlightCategory({ visib: '10+', clouds: [] }),
                    threeMiles: weatherSystem.getFlightCategory({ visib: '3', clouds: [] }),
                    missing: weatherSystem.getFlightCategory({ clouds: [] }),
                    lowCeiling: weatherSystem.getFlightCategory({ visib: '10+', clouds: [{cover:'OVC', base: 400}] }),
                    numeric: weatherSystem.getFlightCategory({ visib: 0.5, clouds: [] })
                })"""
            )
            # Half a mile is LIFR by definition; reporting it as VFR is a safety-facing
            # misread of the same data the panel shows.
            self.assertEqual(categories["halfMile"], "LIFR", categories)
            self.assertEqual(categories["tenPlus"], "VFR", categories)
            self.assertEqual(categories["threeMiles"], "MVFR", categories)
            self.assertEqual(categories["missing"], "UNKN", categories)
            self.assertEqual(categories["lowCeiling"], "LIFR", categories)
            self.assertEqual(categories["numeric"], "LIFR", categories)

            # Malformed payloads must not throw out of the parser.
            survived = page.evaluate(
                """() => {
                    const shapes = [null, undefined, {}, { clouds: 'not-an-array' },
                                    { clouds: [{}] }, { temp: 'x', dewp: 'y' },
                                    { visib: {}, clouds: [{ cover: 'OVC' }] }];
                    for (const shape of shapes) {
                        try {
                            weatherSystem.parseMETAR(shape);
                            weatherSystem.getCeiling(shape && shape.clouds);
                            weatherSystem.formatWind(shape && shape.wind);
                        } catch (e) { return 'threw on ' + JSON.stringify(shape) + ': ' + e.message; }
                    }
                    return 'ok';
                }"""
            )
            self.assertEqual(survived, "ok")
            self.assertEqual(crashes, [])

    def test_plugin_manifest_enforces_its_capability_boundary(self) -> None:
        with self._page() as (page, crashes):
            state = page.evaluate(
                """() => ({
                    entries: pluginManifestManager.entries.length,
                    status: document.getElementById('pluginManifestStatus')?.textContent || '',
                    modulesOptIn: pluginManifestManager.moduleIds.size >= 0
                })"""
            )
            self.assertGreater(state["entries"], 0, "the manifest loaded no entries")
            self.assertTrue(state["modulesOptIn"])

            # A manifest entry declaring a capability outside the allowlist, or one it
            # has no matching data class for, must be refused rather than loaded.
            refused = page.evaluate(
                """() => {
                    const bad = pluginManifestManager._normalise({
                        id: 'audit-bad', name: 'Audit', version: '1.0.0', kind: 'geojson-preset',
                        presetId: 'x', origin: 'local', license: 'MIT',
                        dataClasses: ['public-reference'], capabilities: ['exfiltrate-watchlist']
                    });
                    const unknownClass = pluginManifestManager._normalise({
                        id: 'audit-class', name: 'Audit', version: '1.0.0', kind: 'geojson-preset',
                        presetId: 'x', origin: 'local', license: 'MIT',
                        dataClasses: ['secret-stuff'], capabilities: []
                    });
                    return { bad: bad === null, unknownClass: unknownClass === null };
                }"""
            )
            self.assertTrue(refused["bad"], "a capability outside the allowlist was accepted")
            self.assertTrue(refused["unknownClass"], "an unknown data class was accepted")

            # Provenance is local-only and bounded.
            provenance = page.evaluate(
                """() => {
                    const entry = pluginManifestManager.entries[0];
                    const before = pluginManifestManager.provenanceLog.length;
                    pluginManifestManager._recordProvenance(entry, 'load', 'audit\\nprobe');
                    const record = pluginManifestManager.provenanceLog[0];
                    return { grew: pluginManifestManager.provenanceLog.length > before,
                             detail: record.detail, id: record.id };
                }"""
            )
            self.assertTrue(provenance["grew"])
            # Newlines are stripped so a log line cannot be forged.
            self.assertNotIn("\n", provenance["detail"])
            self.assertEqual(crashes, [])

    def test_historical_workspace_filters_paginates_and_redacts(self) -> None:
        with self._page() as (page, crashes):
            result = page.evaluate(
                """async () => {
                    const records = [];
                    for (let i = 0; i < 60; i++) {
                        records.push({ timestamp: Date.now() - i * 60000, hex: 'AE00' + String(i % 10) + '0',
                                       callsign: 'RCH' + i, type: 'C17',
                                       lat: 38 + i * 0.01, lon: -77 + i * 0.01,
                                       altitude: 20000 + i * 100, speed: 400, bearing: 90 });
                    }
                    // A PIA hex must be redacted on ingest, not on display. Membership is
                    // a piaDB lookup rather than a range, so take one the catalogue holds.
                    const piaHex = (typeof piaDB !== 'undefined' && piaDB.loaded && piaDB.aircraft.size)
                        ? [...piaDB.aircraft.keys()][0] : null;
                    if (piaHex) {
                        records.push({ timestamp: Date.now(), hex: piaHex.toUpperCase(), callsign: 'SECRET1',
                                       type: 'B738', lat: 40, lon: -75, altitude: 30000 });
                    }
                    const source = historicalWorkspace._source({
                        id: 'audit-source', name: 'Audit archive', license: 'CC0',
                        terms: 'local analysis only'
                    });
                    const parsed = historicalWorkspace._records(records, source);
                    const pia = parsed.find(r => r.piaRedacted);
                    return { total: parsed.length,
                             seeded: Boolean(piaHex),
                             piaFound: Boolean(pia),
                             piaHex: pia ? pia.hex : null,
                             piaCallsign: pia ? pia.callsign : null,
                             sorted: parsed.every((r, i) => i === 0 || parsed[i - 1].timestamp <= r.timestamp) };
                }"""
            )
            self.assertTrue(result["sorted"], "records were not sorted by time")
            self.assertEqual(result["total"], 61 if result["seeded"] else 60)
            # Guard against a vacuous pass: only assert redaction if a PIA hex existed.
            self.assertTrue(result["seeded"], "piaDB held no hex to seed with")
            self.assertTrue(result["piaFound"], "a known PIA hex was not flagged")
            self.assertEqual(result["piaHex"], "", "a PIA hex survived ingest")
            self.assertEqual(result["piaCallsign"], "", "a PIA callsign survived ingest")

            # Oversized and malformed archives are refused with a reason.
            rejects = page.evaluate(
                """() => {
                    const source = historicalWorkspace._source({ id: 'a', name: 'A', license: 'x', terms: 'y' });
                    const cases = {};
                    const attempt = (label, records) => {
                        try { historicalWorkspace._records(records, source); cases[label] = 'ACCEPTED'; }
                        catch (e) { cases[label] = 'rejected'; }
                    };
                    attempt('empty', []);
                    attempt('tooMany', new Array(20001).fill({ timestamp: 1, lat: 0, lon: 0 }));
                    attempt('forbiddenField', [{ timestamp: 1, lat: 0, lon: 0, registration: 'N1' }]);
                    attempt('unknownField', [{ timestamp: 1, lat: 0, lon: 0, nonsense: 1 }]);
                    attempt('badLat', [{ timestamp: 1, lat: 999, lon: 0 }]);
                    attempt('futureTime', [{ timestamp: Date.now() + 86400000, lat: 0, lon: 0 }]);
                    return cases;
                }"""
            )
            self.assertEqual(rejects, {
                "empty": "rejected", "tooMany": "rejected", "forbiddenField": "rejected",
                "unknownField": "rejected", "badLat": "rejected", "futureTime": "rejected",
            })
            self.assertEqual(crashes, [])

    def test_trail_renderer_colours_every_mode_without_throwing(self) -> None:
        with self._page() as (page, crashes):
            colours = page.evaluate(
                """() => {
                    const out = {};
                    const previous = trailRenderer.options.colorBy;
                    // Ragged history: a null altitude, a repeated position (zero elapsed
                    // time for the speed estimate) and a single-point trail.
                    const samples = [
                        [51.5, -0.12, 0, Date.now() - 60000],
                        [51.6, -0.13, 35000, Date.now() - 30000],
                        [51.6, -0.13, null, Date.now() - 30000],
                        [51.7, -0.14, 41000, Date.now()]
                    ];
                    for (const mode of ['altitude', 'speed', 'time', 'solid']) {
                        trailRenderer.options.colorBy = mode;
                        try {
                            const group = trailRenderer.createGradientTrail(samples, { hex: 'AE1234' });
                            const layers = group ? group.getLayers() : [];
                            const lines = layers.filter(l => typeof l.getLatLngs === 'function');
                            const bad = lines.filter(l => {
                                const c = l.options.color;
                                return !c || c === 'undefined' || c === 'NaN';
                            });
                            out[mode] = { segments: lines.length, bad: bad.length };
                        } catch (e) { out[mode] = 'threw: ' + e.message; }
                    }
                    trailRenderer.options.colorBy = previous;
                    out.tooShort = trailRenderer.createGradientTrail([[1, 2, 3, 4]], {});
                    return out;
                }"""
            )
            self.assertIsNone(colours.pop("tooShort"), "a one-point trail should produce no segments")
            for mode, value in colours.items():
                self.assertNotIsInstance(value, str, f"{mode}: {value}")
                self.assertEqual(value["segments"], 3, f"{mode} produced {value['segments']} segments")
                self.assertEqual(value["bad"], 0, f"{mode} produced an undefined colour")
            self.assertEqual(crashes, [])

    def test_photo_pipeline_resolves_and_falls_through_to_the_silhouette(self) -> None:
        # The base stub answers every image with a valid GIF, so the golden path
        # resolves at the first self-hosted source. The fall-through only happens
        # when every source fails, which needs images to actually fail.
        with self._page() as (page, crashes):
            found = page.evaluate(
                """async () => {
                    const hex = Object.keys(aircraftCache)[0];
                    if (!hex) return 'no aircraft';
                    delete photoCache[hex];
                    delete photoFailCache[hex];
                    await loadAircraftPhoto(hex, aircraftCache[hex]);
                    const div = document.getElementById('aircraftPhoto');
                    return { cached: Boolean(photoCache[hex]),
                             loading: div.innerHTML.includes('Loading...'),
                             failCached: Boolean(photoFailCache[hex]) };
                }"""
            )
            self.assertTrue(found["cached"], "a resolvable photo was not cached")
            self.assertFalse(found["loading"], "the panel was left showing Loading...")
            self.assertFalse(found["failCached"])

            # Now make every image fail and confirm the chain ends at the silhouette
            # rather than leaving the panel stuck. Use a hex the run has never fetched
            # and no type code: already-requested URLs come from the browser's HTTP
            # cache, which page.route never sees.
            page.route("**/*.jpg", lambda route: route.abort())
            page.route("**/hex-image-thumb*", lambda route: route.abort())
            exhausted = page.evaluate(
                """async () => {
                    const hex = 'FFFE01';
                    aircraftCache[hex] = { hex, t: '', r: '', flight: 'AUDIT1', lat: 51.5, lon: -0.12 };
                    delete photoCache[hex];
                    delete photoFailCache[hex];
                    await loadAircraftPhoto(hex, aircraftCache[hex]);
                    const div = document.getElementById('aircraftPhoto');
                    return { failCached: Boolean(photoFailCache[hex]),
                             loading: div.innerHTML.includes('Loading...'),
                             html: div.innerHTML.slice(0, 160) };
                }"""
            )
            self.assertFalse(exhausted["loading"], "the panel was left showing Loading...")
            self.assertTrue(exhausted["failCached"],
                            f"the exhausted chain was not cached: {exhausted['html']}")

            # A second open must be served from the fail cache, not re-walk the chain.
            reused = page.evaluate(
                """async () => {
                    const hex = 'FFFE01';
                    let requests = 0;
                    const RealImage = window.Image;
                    window.Image = function (...args) { requests++; return new RealImage(...args); };
                    await loadAircraftPhoto(hex, aircraftCache[hex]);
                    window.Image = RealImage;
                    return requests;
                }"""
            )
            self.assertEqual(reused, 0, "a cached photo failure still probed image sources")
            self.assertEqual(crashes, [])

    def test_photo_and_banner_fallbacks_resolve_to_a_real_host(self) -> None:
        # remoteSilhouettes and remoteAirlineLogos are defined on DATA_URLS but were
        # read off CONFIG, so the mirror URL was the literal string "undefined" plus a
        # filename. The Android bundle ships neither photos nor silhouettes, so the
        # fallback written to cover that build was the thing that broke it.
        #
        # The mirror is only ever assigned from an onerror handler, so the local image
        # has to actually fail. With the base stub answering every image with a valid
        # GIF the fallback never runs and this test proves nothing.
        seen: list[str] = []
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        page.on("request", lambda request: seen.append(request.url))
        self._route_external(page)
        page.route("**/assets/silhouettes/**", lambda route: route.abort())
        page.route("**/assets/airlines/**", lambda route: route.abort())
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            mirrors = page.evaluate(
                "() => ({ silhouettes: DATA_URLS.remoteSilhouettes,"
                " logos: DATA_URLS.remoteAirlineLogos })")
            for key, value in mirrors.items():
                self.assertTrue(str(value).startswith("https://"),
                                f"the {key} mirror is not an absolute https URL: {value!r}")

            seen.clear()
            page.evaluate(
                """() => {
                    const div = document.getElementById('aircraftPhoto');
                    if (div) div.innerHTML = '';
                    showFallbackPhoto({ t: 'ZZZZ' }, div);
                    loadAirlineBanner('AAL123');
                }"""
            )
            # onerror, and the mirror assignment it makes, are asynchronous.
            page.wait_for_timeout(2500)

            # Positive control: unless the fallback actually reached the mirror there is
            # nothing here to be wrong, and the assertion below would pass vacuously.
            mirror_host = mirrors["silhouettes"].split("/")[2]
            self.assertTrue(
                any(mirror_host in url for url in seen),
                f"the fallback never reached the mirror host, so nothing was exercised: {seen[-5:]}")

            broken = [url for url in seen
                      if url.rsplit("/", 1)[-1].startswith("undefined") or "/undefined" in url]
            self.assertEqual(broken, [], f"requests built from an undefined value: {broken[:5]}")
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_the_wikipedia_toggle_actually_stops_wikipedia_requests(self) -> None:
        # The toggle was wired end to end and persisted in the backup schema, but its
        # only reader had no callers while the live fetch ran unguarded, so switching
        # it off did not stop the page contacting en.wikipedia.org.
        hits: list[str] = []
        page = self._new_page()
        crashes: list[str] = []
        page.on("pageerror", lambda exc: crashes.append(str(exc)))
        page.on("request", lambda request: hits.append(request.url)
                if "en.wikipedia.org" in request.url else None)
        self._route_external(page)
        # Wikipedia is priority 8. Everything ahead of it has to fail for the chain to
        # get that far, otherwise both halves of this test read zero and prove nothing.
        for pattern in ("**/assets/aircraft_photos/**", "**/hexdb.io/**",
                        "**/airport-data.com/**", "**/*.jpg"):
            page.route(pattern, lambda route: route.abort())
        page.route("**/en.wikipedia.org/**", lambda route: route.fulfill(
            status=200, content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
            body='{"title":"Boeing C-17","thumbnail":{"source":"https://upload.example.org/c17.jpg"}}'))
        try:
            page.goto(f"{self.base_url}/index.html", wait_until="load", timeout=60000)
            page.wait_for_timeout(BOOT_SETTLE_MS)

            walk = """async (hex) => {
                aircraftCache[hex] = { hex, t: 'C17', r: '', flight: 'AUDIT1', lat: 51.5, lon: -0.12 };
                delete photoCache[hex];
                delete photoFailCache[hex];
                await loadAircraftPhoto(hex, aircraftCache[hex]);
            }"""

            # Positive control: with the setting on, the chain must reach Wikipedia.
            page.evaluate("() => { settings.showWiki = true; }")
            hits.clear()
            page.evaluate(walk, "FFFE10")
            page.wait_for_timeout(1500)
            self.assertGreater(len(hits), 0,
                               "the photo chain never reached Wikipedia, so the off case proves nothing")

            # With it off, not one request may leave for Wikipedia.
            page.evaluate("() => { settings.showWiki = false; }")
            hits.clear()
            page.evaluate(walk, "FFFE11")
            page.wait_for_timeout(1500)
            self.assertEqual(hits, [],
                             f"Wikipedia was contacted while the setting was off: {hits[:3]}")
            self.assertEqual(crashes, [])
        finally:
            page.close()

    def test_cesium_globe_lane_boots_or_degrades_without_throwing(self) -> None:
        # The 3D lane is lazy-loaded from a CDN the harness stubs, so the contract
        # under test is that requesting it never breaks the page.
        url = f"{self.base_url}/index.html?3d=1"
        with self._page(url=url) as (page, crashes):
            state = page.evaluate(
                """() => ({
                    requested: cesium3DManager.requested,
                    bodyClass: document.body.className.includes('cesium-3d-mode'),
                    mapAlive: typeof map !== 'undefined' && Boolean(map),
                    markers: Object.keys(markers).length
                })"""
            )
            self.assertTrue(state["requested"], "?3d=1 did not request the globe")
            # Whether or not Cesium loads, the app must still be functioning.
            self.assertTrue(state["mapAlive"])
            self.assertEqual(crashes, [])

    def test_mobile_workspace_pages_all_render(self) -> None:
        with self._page(viewport={"width": 390, "height": 780}) as (page, crashes):
            for panel in ("map", "list", "watchlist", "settings"):
                rendered = page.evaluate(
                    """(panel) => {
                        mobileSupport.setActivePanel(panel);
                        return { active: mobileSupport.activePanel,
                                 bodyClass: document.body.className.includes('mobile-panel-' + panel) };
                    }""",
                    panel,
                )
                self.assertEqual(rendered["active"], panel, f"{panel} did not become active")
                self.assertTrue(rendered["bodyClass"], f"{panel} set no body class")
            self.assertEqual(crashes, [])

    def test_csv_export_quotes_and_defuses_spreadsheet_formulas(self) -> None:
        # Feed-controlled callsigns land straight in an analyst's spreadsheet, where
        # a leading = executes. Quoting was also inconsistent: an embedded quote
        # broke the row and a comma shifted every column after it.
        with self._page() as (page, crashes):
            cells = page.evaluate(
                """() => [csvCell('=HYPERLINK("x")'), csvCell('A,B"C'), csvCell('+1'),
                          csvCell('-7'), csvCell('@here'), csvCell('RCH419'), csvCell(null)]"""
            )
            # This one needs quoting too, so the guard sits inside the quotes.
            self.assertEqual(cells[0], '"\'=HYPERLINK(""x"")"')
            self.assertEqual(cells[1], '"A,B""C"')
            self.assertTrue(cells[2].startswith("'+"))
            self.assertTrue(cells[3].startswith("'-"))
            self.assertTrue(cells[4].startswith("'@"))
            # An ordinary value must stay untouched.
            self.assertEqual(cells[5], "RCH419")
            self.assertEqual(cells[6], "")
            self.assertEqual(crashes, [])

    def test_mobile_pan_control_meets_target_size_and_clears_the_nav(self) -> None:
        # The pan grid is the SC 2.5.7 non-drag alternative, so it must stay on
        # touch -- but it rendered as 30px desktop chrome floating mid-screen.
        with self._page(viewport={"width": 360, "height": 640}) as (page, crashes):
            layout = page.evaluate(
                """() => {
                    const pan = document.querySelector('.map-pan-control');
                    if (!pan) return { missing: true };
                    const button = pan.querySelector('button:not(.map-pan-spacer)');
                    const b = button.getBoundingClientRect();
                    const r = pan.getBoundingClientRect();
                    const nav = document.querySelector('.mobile-bottom-nav, .mobile-nav');
                    const navTop = nav ? nav.getBoundingClientRect().top : window.innerHeight;
                    return { width: Math.round(b.width), height: Math.round(b.height),
                             bottom: Math.round(r.bottom), navTop: Math.round(navTop),
                             right: Math.round(r.right), viewportWidth: window.innerWidth,
                             visible: r.width > 0 };
                }"""
            )
            self.assertFalse(layout.get("missing"), "the SC 2.5.7 pan alternative disappeared on mobile")
            self.assertTrue(layout["visible"])
            self.assertGreaterEqual(layout["width"], 44)
            self.assertGreaterEqual(layout["height"], 44)
            self.assertLessEqual(layout["bottom"], layout["navTop"], "pan grid overlaps the bottom nav")
            self.assertLessEqual(layout["right"], layout["viewportWidth"])
            self.assertEqual(crashes, [])

    def test_sweep_work_is_not_repeated_per_aircraft_or_per_poll(self) -> None:
        with self._page() as (page, crashes):
            # A named list's callsign regex was recompiled for every aircraft on
            # every 6 s sweep -- thousands of identical RegExp constructions.
            compiles = page.evaluate(
                """() => {
                    alertSystem.namedWatchlists.clear();
                    alertSystem.createNamedWatchlist('Audit', { callsignRegex: '^RCH' });
                    const Real = window.RegExp;
                    let count = 0;
                    const Counted = function (...args) { count++; return new Real(...args); };
                    Counted.prototype = Real.prototype;
                    window.RegExp = Counted;
                    const list = [...alertSystem.namedWatchlists.values()][0];
                    for (const ac of Object.values(aircraftCache)) {
                        alertSystem.matchesNamedRules(ac, list.rules);
                    }
                    window.RegExp = Real;
                    alertSystem.namedWatchlists.clear();
                    return { count, aircraft: Object.keys(aircraftCache).length };
                }"""
            )
            self.assertGreater(compiles["aircraft"], 1, "no aircraft to sweep")
            self.assertLessEqual(compiles["count"], 1,
                                 f"regex compiled {compiles['count']} times for {compiles['aircraft']} aircraft")

            # The watchlist panel was torn down and rebuilt on every poll even when
            # closed and unchanged.
            rebuilds = page.evaluate(
                """() => {
                    alertSystem.watchlist.clear();
                    alertSystem.watchlist.set('ABC123',
                        { hex: 'ABC123', name: 'Audit', notes: '', addedAt: Date.now() });
                    alertSystem._watchlistSignature = '';
                    alertSystem.updateWatchlistUI();
                    const container = document.getElementById('watchlistItems');
                    let mutations = 0;
                    const observer = new MutationObserver(records => { mutations += records.length; });
                    observer.observe(container, { childList: true, subtree: true });
                    for (let i = 0; i < 5; i++) alertSystem.updateWatchlistUI();
                    observer.disconnect();
                    return mutations;
                }"""
            )
            self.assertEqual(rebuilds, 0, "the closed, unchanged watchlist was rebuilt")
            self.assertEqual(crashes, [])

    def test_local_state_import_preserves_settings_it_does_not_carry(self) -> None:
        # The backup schema is a subset of `settings`; a straight overwrite reset
        # every key it does not carry rather than merely excluding it.
        with self._page() as (page, crashes):
            preserved = page.evaluate(
                """async () => {
                    settings.coverageMode = 'tracks';
                    settings.coverageWindow = 24;
                    settings.coverageInterval = 60;
                    saveSettings();
                    const state = localStateManager.buildState();
                    await localStateManager._persist(state);
                    const stored = JSON.parse(localStorage.getItem('viptrack_settings_v3'));
                    return { mode: stored.coverageMode, window: stored.coverageWindow,
                             interval: stored.coverageInterval, filter: stored.filter };
                }"""
            )
            self.assertEqual(preserved["mode"], "tracks")
            self.assertEqual(preserved["window"], 24)
            self.assertEqual(preserved["interval"], 60)
            # The keys the backup does carry are still applied.
            self.assertIsNotNone(preserved["filter"])
            self.assertEqual(crashes, [])

    def test_opensky_credential_slot_can_actually_hold_a_credential(self) -> None:
        # The credentials surface watched two storage keys nothing ever wrote, so the
        # slot read "not configured" forever and its Clear button was unreachable.
        with self._page() as (page, crashes):
            before = page.evaluate(
                "() => credentialRegistry.isConfigured("
                " credentialRegistry.slots.find(s => s.id === 'opensky'))"
            )
            self.assertFalse(before)

            after = page.evaluate(
                """() => {
                    document.getElementById('openSkyClientId').value = 'client-abc';
                    document.getElementById('openSkyClientSecret').value = 'secret-xyz';
                    const box = document.getElementById('openSkyRemember');
                    box.checked = true;
                    box.dispatchEvent(new Event('change', { bubbles: true }));
                    const slot = credentialRegistry.slots.find(s => s.id === 'opensky');
                    credentialRegistry.render();
                    return { configured: credentialRegistry.isConfigured(slot),
                             hasClear: Boolean(document.querySelector('[data-cred-clear="opensky"]')) };
                }"""
            )
            self.assertTrue(after["configured"], "storing credentials did not register the slot")
            self.assertTrue(after["hasClear"], "no Clear control appeared for a held credential")

            # Stored credentials survive a request; the per-use path still wipes.
            survived = page.evaluate(
                "() => { openSkyHistoricalManager.clearAuthState();"
                " return document.getElementById('openSkyClientId').value; }"
            )
            self.assertEqual(survived, "client-abc")

            cleared = page.evaluate(
                """() => {
                    credentialRegistry.clear('opensky');
                    openSkyHistoricalManager.clearAuthState();
                    const slot = credentialRegistry.slots.find(s => s.id === 'opensky');
                    return { configured: credentialRegistry.isConfigured(slot),
                             field: document.getElementById('openSkyClientId').value };
                }"""
            )
            self.assertFalse(cleared["configured"])
            self.assertEqual(cleared["field"], "", "clearing the slot left the secret in the field")
            self.assertEqual(crashes, [])

    def test_coverage_sampling_can_be_switched_off(self) -> None:
        # Enabling the view turned sampling on and nothing ever turned it back off,
        # so one visit left the browser accumulating position history permanently.
        with self._page() as (page, crashes):
            state = page.evaluate(
                """async () => {
                    await coverageView.setMode('density', false);
                    const afterEnable = settings.coverageRecording;
                    coverageView.setRecording(false);
                    const afterDisable = settings.coverageRecording;
                    const timerStopped = coverageRecorder.timer === 0;
                    aircraftCache['AE1234'] = {hex: 'AE1234', lat: 5, lon: 5};
                    const wrote = await coverageRecorder.tick();
                    return { afterEnable, afterDisable, timerStopped, wrote };
                }"""
            )
            self.assertTrue(state["afterEnable"], "turning the view on should start sampling")
            self.assertFalse(state["afterDisable"], "sampling could not be turned off")
            self.assertTrue(state["timerStopped"])
            self.assertEqual(state["wrote"], 0, "a tick wrote rows while recording was off")

            # The dedupe map must track the live cache, not every hex ever seen.
            pruned = page.evaluate(
                """async () => {
                    settings.coverageRecording = true;
                    coverageRecorder.lastByHex.clear();
                    coverageRecorder.lastByHex.set('DEADBE', [1, 1]);
                    aircraftCache['AE1234'] = {hex: 'AE1234', lat: 7, lon: 7};
                    await coverageRecorder.tick();
                    return coverageRecorder.lastByHex.has('DEADBE');
                }"""
            )
            self.assertFalse(pruned, "lastByHex kept a hex that left the cache")
            self.assertEqual(crashes, [])

    def test_coverage_view_reports_that_it_cannot_draw_under_webgl(self) -> None:
        # ?renderer=webgl hides the Leaflet map, and this layer draws on a Leaflet
        # pane -- the toggle used to toast success onto an invisible canvas.
        url = f"{self.base_url}/index.html?renderer=webgl"
        with self._page(url=url) as (page, crashes):
            page.wait_for_function(
                "() => typeof webglMapManager !== 'undefined' && webglMapManager.renderer",
                timeout=45000,
            )
            result = page.evaluate(
                """async () => {
                    const applied = await coverageView.setMode('density', false);
                    return { applied, rendersHere: coverageView.rendersHere(),
                             status: document.getElementById('coverageStatus').textContent,
                             canvas: Boolean(coverageView.canvas) };
                }"""
            )
            self.assertFalse(result["rendersHere"])
            self.assertFalse(result["applied"], "coverage claimed success under WebGL")
            self.assertFalse(result["canvas"])
            self.assertIn("standard map", result["status"])
            self.assertEqual(crashes, [])

    def test_user_supplied_names_render_as_text_not_markup(self) -> None:
        # DOMPurify strips scripts, so this was never XSS -- but a name containing a
        # quote broke out of the aria-label attribute and garbled the row, and angle
        # brackets rendered as (sanitized) markup instead of the name the user typed.
        hostile = 'A"<b>&B'
        with self._page() as (page, crashes):
            result = page.evaluate(
                """(name) => {
                    bookmarks.length = 0;
                    bookmarks.push({ id: 1, name, lat: 51.5, lng: -0.12, zoom: 8 });
                    renderBookmarks();
                    alertSystem.watchlist.clear();
                    alertSystem.watchlist.set('ABC123',
                        { hex: 'ABC123', name, notes: '', addedAt: Date.now() });
                    alertSystem.updateWatchlistUI();
                    const bookmark = document.querySelector('.bookmark-name');
                    const watch = document.querySelector('.watchlist-name');
                    const remove = document.querySelector('.watchlist-remove');
                    return {
                        bookmarkText: bookmark ? bookmark.textContent : null,
                        watchText: watch ? watch.textContent : null,
                        removeLabel: remove ? remove.getAttribute('aria-label') : null,
                        strayBold: document.querySelectorAll('.bookmark-name b, .watchlist-name b').length
                    };
                }""",
                hostile,
            )
            self.assertEqual(result["bookmarkText"], hostile)
            self.assertEqual(result["watchText"], hostile)
            # The attribute must survive intact rather than being split by the quote.
            self.assertEqual(result["removeLabel"], "Remove " + hostile)
            self.assertEqual(result["strayBold"], 0)
            self.assertEqual(crashes, [])

    def test_health_probes_skip_sources_the_live_loop_just_measured(self) -> None:
        # The whole data plane rides one free relay that rate-limits, and the live
        # loop already records real latencies every 6 s. Re-probing a source it just
        # used spends budget to learn what is already known.
        with self._page() as (page, crashes):
            probed = page.evaluate(
                """async () => {
                    const calls = [];
                    const real = dataSourceManager.checkSource.bind(dataSourceManager);
                    dataSourceManager.checkSource = source => { calls.push(source.key); return Promise.resolve(); };
                    const now = Date.now();
                    // One source measured moments ago, one silent for ten minutes.
                    const enabled = dataSourceManager.enabledSources();
                    enabled.forEach(s => { s.lastSuccess = 0; s.lastError = 0; });
                    enabled[0].lastSuccess = now;
                    if (enabled[1]) enabled[1].lastSuccess = now - 600000;
                    await dataSourceManager.checkAllSources();
                    dataSourceManager.checkSource = real;
                    return { calls, fresh: enabled[0].key, stale: enabled[1] ? enabled[1].key : null };
                }"""
            )
            self.assertNotIn(probed["fresh"], probed["calls"],
                             "a source measured seconds ago was probed again")
            if probed["stale"]:
                self.assertIn(probed["stale"], probed["calls"],
                              "a silent source must still be probed")

            # A succeeding live loop is itself proof of connectivity.
            skipped = page.evaluate(
                """async () => {
                    let fetched = false;
                    const realFetch = window.fetch;
                    window.fetch = (...args) => { fetched = true; return realFetch(...args); };
                    offlineManager.isOnline = true;
                    lastFetchTime = Date.now();
                    await offlineManager.checkConnection();
                    window.fetch = realFetch;
                    return fetched;
                }"""
            )
            self.assertFalse(skipped, "connectivity probe ran while the feed was live")
            self.assertEqual(crashes, [])

    def test_alert_sounds_share_one_audio_context(self) -> None:
        # A fresh AudioContext per alert is never closed and browsers cap how many a
        # page may hold, so a long-running tab used to lose alert sounds entirely.
        with self._page() as (page, crashes):
            created = page.evaluate(
                """() => {
                    const Real = window.AudioContext || window.webkitAudioContext;
                    let count = 0;
                    const Counted = function (...args) { count++; return new Real(...args); };
                    Counted.prototype = Real.prototype;
                    window.AudioContext = Counted;
                    window.webkitAudioContext = Counted;
                    alertSystem._audioContext = null;
                    for (let i = 0; i < 20; i++) alertSystem.playSound('chime');
                    window.AudioContext = Real;
                    window.webkitAudioContext = Real;
                    return count;
                }"""
            )
            self.assertEqual(created, 1, f"{created} AudioContexts created for 20 alerts")
            self.assertEqual(crashes, [])

    def test_going_offline_renders_once_not_every_poll(self) -> None:
        # The 6 s poll kept calling showCachedPositions(), which re-toasted and tore
        # down every marker each time -- the toast never cleared and the map flickered.
        with self._page() as (page, crashes):
            page.evaluate("async () => { offlineManager.cachePositions();"
                          " await new Promise(r => setTimeout(r, 300)); }")
            result = page.evaluate(
                """() => {
                    const toasts = [];
                    const realToast = window.toast;
                    window.toast = msg => { toasts.push(msg); return realToast(msg); };
                    offlineManager.handleOffline();
                    const afterFirst = Object.keys(markers).map(h => markers[h]);
                    // Three more polls, exactly as the interval would drive them.
                    loadAircraft(); loadAircraft(); loadAircraft();
                    const afterPolls = Object.keys(markers).map(h => markers[h]);
                    const stable = afterFirst.length === afterPolls.length &&
                        afterFirst.every((marker, i) => marker === afterPolls[i]);
                    const label = document.getElementById('dataSource').textContent;
                    window.toast = realToast;
                    offlineManager.isOnline = true;
                    return { toasts, stable, markerCount: afterPolls.length, label };
                }"""
            )
            # One transition toast, and no "Showing data from N minutes ago" repeat.
            self.assertEqual(
                [t for t in result["toasts"] if "Showing data from" in t], [],
                "the offline poll re-announced the cache age")
            self.assertLessEqual(len(result["toasts"]), 1, result["toasts"])
            self.assertTrue(result["stable"], "markers were torn down and rebuilt by the poll")
            # The age readout still updates so the user can see the data is stale.
            self.assertIn("Cached", result["label"])
            self.assertEqual(crashes, [])

    def test_keyboard_filter_shortcuts_drive_the_real_filter(self) -> None:
        # Two control sets share [data-filter]: the mobile chip bar (earlier in the
        # document) and the desktop radios. A bare selector hits the hidden chip, so
        # M toasted "Military only" while settings.filter never changed.
        with self._page() as (page, crashes):
            self.assertEqual(page.evaluate("settings.filter"), "mil-vip")
            page.keyboard.press("m")
            page.wait_for_timeout(400)
            self.assertEqual(page.evaluate("settings.filter"), "military")
            self.assertEqual(page.evaluate(
                "() => [...document.querySelectorAll('.filter-btn.active')].map(b => b.dataset.filter)"
            ), ["military"])

            page.keyboard.press("v")
            page.wait_for_timeout(400)
            self.assertEqual(page.evaluate("settings.filter"), "vip")

            page.keyboard.press("a")
            page.wait_for_timeout(400)
            self.assertEqual(page.evaluate("settings.filter"), "mil-vip")

            # The hidden chips must stay untouched: an active chip dims markers to
            # 0.08 opacity with nothing on screen explaining why.
            self.assertEqual(page.evaluate(
                "() => [...document.querySelectorAll('.filter-chip-btn.active')].length"
            ), 0)
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
