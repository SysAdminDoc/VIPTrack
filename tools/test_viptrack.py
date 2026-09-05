#!/usr/bin/env python3
"""Static contract tests for the zero-build VIPTrack document."""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from check_cdn_dependencies import run_gate
from check_security_headers import run_gate as run_security_header_gate


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CESIUM_FRAME = ROOT / "cesium-frame.html"
FAA_DIR = ROOT / "data" / "faa"
PLUGINS_MANIFEST = ROOT / "plugins" / "manifest.json"
I18N_DIR = ROOT / "data" / "i18n"
OPFS_WORKER = ROOT / "workers" / "registration-opfs-worker.js"
CORS_RELAY_WORKER = ROOT / "workers" / "cors-relay.js"
WEB_MANIFEST = ROOT / "manifest.json"
SERVICE_WORKER = ROOT / "sw.js"
ANDROID_DIR = ROOT / "android"
TYPE_PHOTO_DOWNLOADER = ROOT / "download-type-photos.py"
TYPE_PHOTO_WORKFLOW = ROOT / "tools" / "run_type_photo_enrichment.ps1"
UI_STYLES = ROOT / "assets" / "viptrack-ui.css"
UI_MOCKUPS = ROOT / "assets" / "mockups"
CRLF = b"\r\n"


class VipTrackContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = INDEX.read_text(encoding="utf-8")
        cls.lines = cls.source.splitlines()

    def test_pinned_cdn_resources_have_sri(self) -> None:
        resources = re.findall(
            r"<(?:script|link)\b[^>]*(?:src|href)=\"(https://(?:cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)/[^\"]+)\"[^>]*>",
            self.source,
            flags=re.IGNORECASE,
        )
        self.assertGreaterEqual(len(resources), 6)
        for match in re.finditer(
            r"<(?:script|link)\b[^>]*(?:src|href)=\"https://(?:cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)/[^\"]+\"[^>]*>",
            self.source,
            flags=re.IGNORECASE,
        ):
            self.assertRegex(match.group(0), r'\bintegrity="sha512-[^"]+"')
            self.assertRegex(match.group(0), r'\bcrossorigin="anonymous"')

    def test_cdn_dependency_inventory_and_sanitizer_gate(self) -> None:
        summary = run_gate()
        self.assertEqual(summary["schemaVersion"], 1)
        self.assertEqual(summary["dependencies"], 10)
        for marker in (
            "cdn_dependencies.json",
            "reviewPolicyDays",
            "advisoryStatus",
            "FORBID_TAGS",
            "FORBID_ATTR",
            "srcdoc",
            "escapeHTML(markup)",
        ):
            self.assertIn(marker, self.source + (ROOT / "tools" / "check_cdn_dependencies.py").read_text(encoding="utf-8") + (ROOT / "tools" / "cdn_dependencies.json").read_text(encoding="utf-8"))
        self.assertNotIn("dompurify/3.2.6", self.source)

        # Assert the pins agree with the inventory rather than pinning a version in
        # the test, which failed on the very upgrade the advisory review exists to
        # produce. The sanitizer is the app's single XSS boundary, so its advisory
        # status must name the version actually loaded.
        inventory = json.loads((ROOT / "tools" / "cdn_dependencies.json").read_text(encoding="utf-8"))
        by_id = {dep["id"]: dep for dep in inventory["dependencies"]}
        sanitizer = by_id["dompurify-js"]
        self.assertIn(sanitizer["url"], self.source,
                      "index.html does not load the sanitizer the inventory pins")
        self.assertEqual(sanitizer["advisoryStatus"], f"clear-through-{sanitizer['version']}")
        self.assertIn(sanitizer["integrity"], self.source)
        for dep in inventory["dependencies"]:
            self.assertIn(dep["version"], dep["url"],
                          f"{dep['id']} url does not carry its pinned version")

    def test_html_sinks_use_pinned_sanitizer(self) -> None:
        self.assertIn("purify.min.js", self.source)
        self.assertIn("function safeHTML", self.source)
        self.assertIn("window.DOMPurify.sanitize", self.source)
        for line in self.lines:
            if ".bindPopup(" in line or ".bindTooltip(" in line or ".setContent(" in line:
                self.assertIn("safeHTML", line, msg=line.strip())

    def test_settings_toggles_are_keyboard_operable_switches(self) -> None:
        toggles = re.findall(r'<button\b[^>]*class="toggle(?: on)?"[^>]*></button>', self.source)
        self.assertEqual(len(toggles), 15)
        self.assertNotIn('<div class="toggle', self.source)
        for toggle in toggles:
            self.assertIn('type="button"', toggle)
            self.assertIn('role="switch"', toggle)
            self.assertRegex(toggle, r'aria-checked="(?:true|false)"')
            self.assertRegex(toggle, r'aria-labelledby="toggle[A-Za-z]+Label"')
        for label_id in re.findall(r'aria-labelledby="([^"]+)"', '\n'.join(toggles)):
            self.assertIn(f'id="{label_id}"', self.source)
        for marker in (
            "function syncToggleAria(toggle)",
            "function initAccessibleToggles()",
            "new MutationObserver",
            "attributeFilter: ['class']",
            "toggle.setAttribute('aria-checked'",
            ".toggle:focus-visible",
        ):
            self.assertIn(marker, self.source)

    def test_dialogs_expose_state_and_keyboard_focus_contract(self) -> None:
        for marker in (
            'id="infoPanel" role="dialog" aria-modal="true"',
            'id="settingsPanel" role="dialog" aria-modal="true"',
            'id="bookmarkModal" role="dialog" aria-modal="true"',
            'id="onboardOverlay" role="dialog" aria-modal="true"',
            'id="helpOverlay" role="dialog" aria-modal="true"',
            'aria-hidden="true"',
            'aria-labelledby="settingsTitle"',
            'aria-labelledby="bookmarkModalTitle"',
            'aria-describedby="onboardDescription"',
            'const dialogAccessibility =',
            'const focusableSelector =',
            "event.key === 'Escape'",
            "event.key !== 'Tab'",
            'previousFocus',
            'dialogAccessibility.open',
            'dialogAccessibility.close',
            "attributeFilter: ['class', 'hidden']",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn('onclick="document.getElementById(\'helpOverlay\')', self.source)

    def test_tabs_and_filters_expose_selection_state(self) -> None:
        for marker in (
            'role="tablist" aria-label="Search views"',
            'id="searchTabResults" type="button" role="tab" aria-selected="true" aria-controls="tabResults"',
            'role="tabpanel" aria-labelledby="searchTabFilters"',
            'role="tablist" aria-label="Aircraft detail sections"',
            'id="infoTabOverview" type="button" role="tab" aria-selected="true" aria-controls="tabOverview"',
            'role="tabpanel" aria-labelledby="infoTabRoute"',
            'role="radiogroup" aria-label="Aircraft category filter"',
            'type="button" role="radio" aria-checked="true" data-filter="mil-vip"',
            'role="radiogroup" aria-label="Aircraft list categories"',
            'function syncFilterButtonAria()',
            'function activateInfoTab(tabName)',
            'function handleTabKeydown(event, selector, activate)',
            "t.setAttribute('aria-selected'",
            "p.setAttribute('aria-hidden'",
            "button.setAttribute('aria-pressed'",
            "searchFilterBtn')?.setAttribute('aria-expanded'",
        ):
            self.assertIn(marker, self.source)

    def test_action_buttons_have_explicit_types_and_toggle_names(self) -> None:
        for marker in (
            'id="watchBtn" type="button" title="Add to Watchlist" aria-pressed="false"',
            'id="infoClose" type="button"',
            'id="addBookmarkBtn" type="button" title="Save current view" aria-label="Save current view"',
            'id="installDismiss" type="button" aria-label="Dismiss install prompt"',
            'class="alert-close" type="button" aria-label="Dismiss alert"',
            # Assert the contract (the button carries a type and a data-hex), not the
            # exact interpolation -- pinning the expression blocked escapeHTML here.
            'class="watchlist-remove" data-hex="',
            'class="history-remove" type="button"',
            'class="bookmark-delete" type="button"',
            'class="overlay-remove" aria-label="Remove overlay"',
            "watchBtn.setAttribute('aria-pressed'",
            "this.setAttribute('aria-pressed', 'false')",
            "this.setAttribute('aria-pressed', 'true')",
        ):
            self.assertIn(marker, self.source)

    def test_toolbar_dropdowns_expose_keyboard_state(self) -> None:
        for marker in (
            'id="mapMenuBtn" type="button" aria-label="Map and layers menu" aria-controls="mapMenuPanel" aria-expanded="false"',
            'id="mapMenuPanel" role="region" aria-label="Map and layers" hidden',
            'id="toolsMenuBtn" type="button" aria-label="Tools menu" aria-controls="toolsMenuPanel" aria-expanded="false"',
            'id="toolsMenuPanel" role="region" aria-label="Tools" hidden',
            'const closeDropdowns = restoreTrigger =>',
            "panel.hidden = true",
            "trigger.setAttribute('aria-expanded', 'true')",
            "event.key === 'ArrowDown'",
            "closeDropdowns(trigger)",
        ):
            self.assertIn(marker, self.source)

    def test_privacy_data_precedes_registration_enrichment(self) -> None:
        privacy_marker = self.source.index("Resolve privacy protection before registration enrichment")
        registration_marker = self.source.index("// Registration DB", privacy_marker)
        self.assertLess(privacy_marker, registration_marker)
        self.assertIn("registrationDB.loaded && !cached.piaInfo", self.source)
        self.assertIn("PIA — operator anonymised", self.source)
        self.assertIn("cacheKey: 'viptrack_pia_v1'", self.source)

    def test_pia_safe_projection_covers_durable_and_outbound_boundaries(self) -> None:
        projection_start = self.source.index("function privacySafeAircraftSnapshot")
        projection_end = self.source.index("snapshot.r =", projection_start)
        protected_projection = self.source[self.source.index("if (protectedAircraft)", projection_start):projection_end]
        for forbidden in ("snapshot.r", "snapshot.desc", "snapshot.ownOp", "snapshot.from", "snapshot.to", "snapshot.history", "faaOwner", "faaRegistry"):
            self.assertNotIn(forbidden, protected_projection)
        for marker in (
            "function scrubAircraftCacheForPrivacy",
            "schemaVersion: AIRCRAFT_CACHE_SCHEMA",
            "data?.schemaVersion !== AIRCRAFT_CACHE_SCHEMA",
            "localStorage.removeItem('viptrack_aircraft')",
            "const OFFLINE_CACHE_SCHEMA = 2",
            "schemaVersion: OFFLINE_CACHE_SCHEMA",
            "cached?.schemaVersion === OFFLINE_CACHE_SCHEMA ? cached : null",
            "this._normaliseInfo(info)",
            "const safe = privacySafeAircraftSnapshot(ac, { includeHistory: false })",
            "const safeAc = privacySafeAircraftSnapshot(ac, { includeHistory: false }) || {}",
            "const safeAircraft = privacySafeAircraftSnapshot(ac, { includeHistory: false }) || {}",
            "const privacyProtected = isPrivacyProtectedAircraft(ac)",
            "if (!privacyProtected && points.length < 2",
            "const trackExport =",
            "_safe(ac)",
            "if (!privacyProtected && ac.ownOp)",
            "const isPIA = item?.isPIA === true",
        ):
            self.assertIn(marker, self.source)
        snapshot_start = self.source.index("function privacySafeAircraftSnapshot(ac")
        snapshot = self.source[snapshot_start:self.source.index("Object.assign(snapshot", snapshot_start)]
        self.assertIn("posSource:", snapshot,
                      "the projection drops posSource, which hides ADS-B aircraft from the ADS-B filter")
        webhook_start = self.source.index("const alertWebhook =")
        webhook_end = self.source.index("// Hook into existing alertSystem", webhook_start)
        self.assertNotIn("ac.r", self.source[webhook_start:webhook_end])
        export_start = self.source.index("const trackExport =")
        export_end = self.source.index("// ============ X8:", export_start)
        export_section = self.source[export_start:export_end]
        self.assertIn("privacySafeAircraftSnapshot", export_section)
        self.assertIn("registration: safe.r || null", export_section)

    def test_user_egress_policy_bounds_overlays_proxies_and_webhooks(self) -> None:
        policy_start = self.source.index("const egressPolicy =")
        proxy_start = self.source.index("async function fetchWithProxy", policy_start)
        policy = self.source[policy_start:proxy_start]
        for marker in (
            "maxUrlLength: 2048",
            "maxOverlayBytes: 2 * 1024 * 1024",
            "url.protocol !== 'https:'",
            "url.username || url.password",
            "this._isPrivateHost(url.hostname)",
            "validateWebhookUrl(value, kind = 'generic')",
            "discord.com",
        ):
            self.assertIn(marker, policy)
        proxy_section = self.source[proxy_start:self.source.index("function saveMapPosition", proxy_start)]
        self.assertIn("const target = egressPolicy.validateUrl(url)", proxy_section)
        self.assertIn("const proxyUrl = egressPolicy.validateUrl", proxy_section)
        overlay_start = self.source.index("const geojsonLoader =")
        overlay_end = self.source.index("const curatedOverlayManager =", overlay_start)
        overlay = self.source[overlay_start:overlay_end]
        for marker in (
            "readBoundedResponseText(resp)",
            "egressPolicy.validateUrl(url, { kind: 'overlay' })",
            "credentials: 'omit'",
            "_parse(text)",
            "_valid(data)",
            "featureCount",
        ):
            if marker == "featureCount":
                continue
            self.assertIn(marker, overlay)
        self.assertNotIn("fetchWithProxy", overlay)
        self.assertNotIn("geojsonLoader.addFromUrl(overlayUrl)", self.source)
        webhook_start = self.source.index("const alertWebhook =")
        webhook_end = self.source.index("// Hook into existing alertSystem", webhook_start)
        webhook = self.source[webhook_start:webhook_end]
        for marker in (
            "validateWebhookUrl",
            "explicit = false",
            "mode: 'cors'",
            "credentials: 'omit'",
            "Payload preview (redacted)",
            "webhookClearBtn",
            "setEnabled",
        ):
            self.assertIn(marker, webhook + self.source)
        self.assertNotIn("mode: 'no-cors'", webhook)
        self.assertNotIn("ac.r", webhook)

    def test_faa_registry_shards_are_lazy_compact_and_pia_safe(self) -> None:
        for marker in (
            "const faaRegistryManager =",
            "data/faa/master-' + letter + '.json",
            "shardFor(nNumber)",
            "if (CONFIG.isLocalFile) return null",
            "if (!ac || isPrivacyProtectedAircraft(ac)) return null",
            "id=\"infoFaaOwnerRow\"",
            "faaRegistryManager.enrich(ac).then",
        ):
            self.assertIn(marker, self.source)
        manifest = json.loads((FAA_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["shardAlgorithm"], "fnv1a-mod-26")
        self.assertGreaterEqual(manifest["recordCount"], 300_000)
        total = 0
        owners = 0
        forbidden = {"street", "street2", "zip", "address", "otherNames"}
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            shard_meta = manifest["shards"][letter]
            self.assertEqual(shard_meta["file"], f"master-{letter}.json")
            shard = json.loads((FAA_DIR / shard_meta["file"]).read_text(encoding="utf-8"))
            self.assertEqual(len(shard), shard_meta["records"])
            for n_number, record in shard.items():
                self.assertRegex(n_number, r"^N[0-9]{1,5}[A-Z]{0,2}$")
                self.assertTrue(forbidden.isdisjoint(record))
                owners += bool(record.get("owner"))
            total += len(shard)
        self.assertEqual(total, manifest["recordCount"])
        self.assertEqual(owners, manifest["ownerCount"])

    def test_csp_covers_tfr_mirror(self) -> None:
        self.assertIn("https://tfr2go.com", self.source)

    def test_deployment_headers_and_trusted_types_cover_modes_and_sinks(self) -> None:
        summary = run_security_header_gate()
        self.assertEqual(summary["headerBlocks"], 3)
        headers = (ROOT / "_headers").read_text(encoding="utf-8")
        for marker in (
            "Content-Security-Policy-Report-Only",
            "Content-Security-Policy:",
            "Strict-Transport-Security",
            "Permissions-Policy",
            "X-Frame-Options: SAMEORIGIN",
            "trusted-types viptrack",
            "require-trusted-types-for 'script'",
            "trustedTypes.createPolicy('viptrack'",
            "const SAFE_HTML_OPTIONS",
            "document.body.insertAdjacentHTML('beforeend', safeHTML(html))",
        ):
            self.assertIn(marker, self.source + headers)
        self.assertNotIn("'unsafe-eval'", headers.split("/index.html", 1)[1].split("/cesium-frame.html", 1)[0])

    def test_local_state_backup_is_versioned_bounded_and_privacy_safe(self) -> None:
        manager_start = self.source.index("const localStateManager =")
        manager_end = self.source.index("function setLoadingProgress(", manager_start)
        manager = self.source[manager_start:manager_end]
        for marker in (
            "const LOCAL_STATE_FORMAT = 'viptrack-local-state'",
            "const LOCAL_STATE_SCHEMA = 1",
            "const LOCAL_STATE_MAX_BYTES = 1024 * 1024",
            "LOCAL_STATE_FORBIDDEN_KEY_RE",
            "_localStateFindForbiddenKey",
            "schemaVersion > LOCAL_STATE_SCHEMA",
            "migrate(payload)",
            "_localStateCanonicalState",
            "aircraft cache and trail observations",
            "raw PIA and enrichment fields",
            "viptrack_settings_v3",
            "viptrack_alert_settings",
            "saveUserData('watchlist'",
            "saveUserData('named_watchlists'",
            "saveUserData('geofences'",
            "id=\"localStateExportBtn\"",
            "id=\"localStateImportBtn\"",
            "localStateManager.importFile(file)",
        ):
            self.assertIn(marker, manager + self.source)
        self.assertNotIn("openSkyClientSecret", manager)
        self.assertNotIn("openAipApiKey", manager)
        for catalog in I18N_DIR.glob("*.json"):
            messages = json.loads(catalog.read_text(encoding="utf-8"))["messages"]
            for key in ("settings.exportLocalState", "settings.importLocalState", "settings.localStateHelp", "settings.localStateReady"):
                self.assertIn(key, messages, msg=f"{catalog.name}: {key}")

    def test_historical_workspace_is_bounded_source_attributed_and_pia_safe(self) -> None:
        start = self.source.index("const historicalWorkspace =")
        end = self.source.index("// ============ X23:", start)
        workspace = self.source[start:end]
        for marker in (
            "const HISTORICAL_WORKSPACE_SCHEMA = 1",
            "const HISTORICAL_WORKSPACE_MAX_BYTES = 8 * 1024 * 1024",
            "const HISTORICAL_WORKSPACE_MAX_RECORDS = 20000",
            "HISTORICAL_RECORD_FORBIDDEN_KEY_RE",
            "adapters:",
            "_source(source)",
            "_records(rawRecords, source)",
            "Source license / permission",
            "Source terms / retention note",
            "isPrivacyProtectedHex(hex)",
            "piaRedacted",
            "historical_workspace",
            "_saveQueryHistory(query)",
            "_queryMatches(query)",
            "missing-signal gap(s) over 5 minutes",
            "exportCsv()",
            "exportJson()",
            "historicalImportFileBtn",
            "historicalUseOpenSkyBtn",
            "historicalRunBtn",
            "historicalPrevBtn",
            "historicalNextBtn",
        ):
            self.assertIn(marker, workspace + self.source)
        self.assertNotIn("clientSecret", workspace)
        self.assertNotIn("access_token", workspace)
        for catalog in I18N_DIR.glob("*.json"):
            messages = json.loads(catalog.read_text(encoding="utf-8"))["messages"]
            for key in ("settings.historicalWorkspace", "settings.historicalWorkspaceHelp", "settings.importHistoricalFile", "settings.useOpenSkyTrace", "settings.runHistoricalQuery", "settings.clearHistoricalData", "settings.exportHistoricalCsv", "settings.exportHistoricalJson", "settings.historicalNoData"):
                self.assertIn(key, messages, msg=f"{catalog.name}: {key}")

    def test_airframes_acars_link_is_callsign_based_and_pia_safe(self) -> None:
        for marker in (
            'id="linkAirframes"',
            "https://app.airframes.io/flights/${encodeURIComponent(flight)}",
            "const available = Boolean(flight) && !isPrivacyProtectedAircraft(ac)",
            "linkAirframes.style.display = available ? 'inline-flex' : 'none'",
            "rel=\"noopener noreferrer\"",
        ):
            self.assertIn(marker, self.source)

    def test_openaip_overlay_is_opt_in_key_gated_and_class_legended(self) -> None:
        for marker in (
            "const openAipAirspaceOverlay =",
            "api.tiles.openaip.net/api/data/airspaces/{z}/{x}/{y}.png",
            "viptrack_openaip_api_key_v1",
            "if (!this._isValidKey(this.apiKey))",
            "id=\"toggleOpenAIP\"",
            "id=\"openAipSaveKeyBtn\"",
            "id=\"openAipClearKeyBtn\"",
            "for (const letter of 'ABCDEFG')",
            "L.DomUtil.create('div', 'openaip-legend')",
            "attribution: '&copy; OpenAIP'",
        ):
            self.assertIn(marker, self.source)
        manager = re.search(r"const openAipAirspaceOverlay =([\s\S]*?)// ============ X5", self.source)
        self.assertIsNotNone(manager)
        self.assertIsNone(re.search(r"apiKey\s*=\s*['\"][A-Za-z0-9]{8,}", manager.group(1)))

    def test_plugin_manifest_is_explicit_opt_in_and_same_origin_only(self) -> None:
        manifest = json.loads(PLUGINS_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemaVersion"], 2)
        self.assertEqual(len(manifest["plugins"]), 4)
        self.assertEqual(manifest["modules"], [])
        preset_manifest = json.loads((ROOT / "data" / "overlays" / "manifest.json").read_text(encoding="utf-8"))
        preset_ids = {preset["id"] for preset in preset_manifest["presets"]}
        self.assertEqual({entry["presetId"] for entry in manifest["plugins"]}, preset_ids)
        for entry in manifest["plugins"]:
            self.assertEqual(entry["kind"], "geojson-preset")
            self.assertTrue(entry["requiresOptIn"])
            self.assertFalse(entry["verified"])
            self.assertEqual(entry["geojson"], "../data/overlays/mil-patterns.geojson")
            self.assertEqual(entry["version"], "1.0.0")
            self.assertEqual(entry["origin"], "same-origin")
            self.assertEqual(entry["license"], "MIT")
            self.assertEqual(entry["dataClasses"], ["public-geometry"])
            self.assertEqual(entry["capabilities"], ["overlay.geojson"])
            self.assertEqual(entry["approvedCapabilities"], ["overlay.geojson"])
            self.assertEqual(entry["cleanupHook"], "deactivate")
        for marker in (
            "const pluginManifestManager =",
            "plugins/manifest.json",
            "entry.requiresOptIn !== true",
            "url.origin === location.origin",
            "await import(url.href)",
            "PLUGIN_CAPABILITY_ALLOWLIST",
            "_grantedCapabilities",
            "_deniedCapabilities",
            "_capabilityContext",
            "_recordProvenance",
            "pluginOverlays",
            "cleanupHook",
            "modules disabled by default",
            "moduleIds",
            "module.activate(this._capabilityContext(entry))",
            "id=\"pluginManifestList\"",
            "pluginManifestManager.init();",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("module.activate({ map, L, toast, geojsonLoader })", self.source)

    def test_cors_relay_worker_only_fetches_hosts_the_app_itself_declares(self) -> None:
        # The relay is a fetch primitive pointed at the open internet. If its allowlist
        # drifts wider than the page's own connect-src it becomes an open proxy that
        # happens to be hosted by whoever deployed VIPTrack.
        self.assertTrue(CORS_RELAY_WORKER.is_file(), "workers/cors-relay.js is missing")
        source = CORS_RELAY_WORKER.read_text(encoding="utf-8")

        listed = re.search(r"export const ALLOWED_TARGET_HOSTS = \[(.*?)\]", source, re.S)
        self.assertIsNotNone(listed, "ALLOWED_TARGET_HOSTS must be an exported array literal")
        hosts = re.findall(r"'([^']+)'", listed.group(1))
        self.assertTrue(hosts, "the relay allowlist must not be empty")

        # Every feed the app actually polls has to be reachable through the relay,
        # otherwise the relay cannot replace the public pool it exists to retire.
        for required in ("api.adsb.one", "api.adsb.lol", "opendata.adsb.fi"):
            self.assertIn(required, hosts)

        connect_src = re.search(r"connect-src 'self'([^;]*);", self.source)
        self.assertIsNotNone(connect_src)
        declared = connect_src.group(1)
        for host in hosts:
            self.assertIn(
                "https://" + host,
                declared,
                f"relay allowlists {host}, which the page's own connect-src does not permit",
            )

        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required to exercise the relay decision function")

        # Assert on the decision itself rather than on the presence of a guard: a
        # source-text assertion cannot tell a working allowlist from a commented one.
        probe = (
            "import { isAllowedTarget } from %s;\n"
            "const cases = ["
            "['https://api.adsb.lol/v2/mil', true],"
            "['https://api.adsb.one/v2/ladd', true],"
            "['https://evil.example.org/steal', false],"
            "['https://api.adsb.lol.evil.org/v2/mil', false],"
            "['http://api.adsb.lol/v2/mil', false],"
            "['https://127.0.0.1/v2/mil', false],"
            "['https://169.254.169.254/latest/meta-data/', false],"
            "['https://user:pass@api.adsb.lol/v2/mil', false],"
            "['https://api.adsb.lol:8080/v2/mil', false],"
            "['not-a-url', false]"
            "];\n"
            "const bad = cases.filter(([url, want]) => isAllowedTarget(url) !== want).map(([url]) => url);\n"
            "console.log(JSON.stringify(bad));\n"
        ) % json.dumps(CORS_RELAY_WORKER.as_uri())

        with tempfile.TemporaryDirectory() as work:
            probe_path = Path(work) / "probe.mjs"
            probe_path.write_bytes(probe.encode("utf-8"))
            result = subprocess.run(
                [node, str(probe_path)], capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip()), [], "relay allow/deny decisions are wrong")

    def test_relay_list_is_configurable_and_prefers_the_operator_relay(self) -> None:
        # The public relay pool closed once already (corsproxy.io went key-only on
        # 2026-09-04). A hardcoded list means the next closure is another outage.
        self.assertIn("const relayRegistry = {", self.source)
        self.assertIn("STORAGE_KEY: 'viptrack_relay_url'", self.source)
        self.assertNotIn("CONFIG.corsProxies", self.source)

        registry = self.source[self.source.index("const relayRegistry = {"):self.source.index("const relayHealth = {")]
        self.assertIn("relays.unshift(", registry, "the operator's own relay must be tried first")
        self.assertIn("egressPolicy.validateUrl", registry, "a stored relay URL must be validated")

        # fetchWithProxy must iterate the registry, not a frozen array.
        fetcher = self.source[self.source.index("async function fetchWithProxy("):]
        fetcher = fetcher[:fetcher.index("async function fetchWithTimeout(")]
        self.assertIn("relayRegistry.list()", fetcher)

    def test_map_attribution_is_not_suppressed(self) -> None:
        # OSM tiles are ODbL and the CARTO and Stadia terms both require visible
        # attribution. This rule used to sit outside any media query, hiding the credit
        # on every raster basemap while the settings help text said it was showing.
        for rule in re.findall(r"\.leaflet-control-attribution[^{]*\{([^}]*)\}", self.source):
            self.assertNotIn(
                "display: none", rule.replace("display:none", "display: none"),
                "attribution must not be hidden by CSS",
            )
        self.assertNotIn("body.embed .leaflet-control-attribution", self.source)

        # The raster lane must actually carry a credit for the tiles it draws.
        tile_layer = re.search(r"baseMaps\['esri-gray'\] = L\.tileLayer\((.*)\);", self.source)
        self.assertIsNotNone(tile_layer)
        self.assertIn("attribution:", tile_layer.group(1))
        self.assertIn("Esri", tile_layer.group(1))

        # adsb.fi's terms require citing the feed with a link back; the others are
        # community projects credited the same way.
        self.assertIn("function setFeedAttribution(src)", self.source)
        for key in ("adsbone", "adsblol", "airplaneslive"):
            block = self.source[self.source.index("{ key: '" + key + "'"):]
            self.assertIn("projectUrl:", block[:block.index("},")],
                          f"source {key} has no project URL to credit")

    def test_the_altitude_legend_is_not_killed_by_css(self) -> None:
        # The legend is a complete, styled, six-locale feature that was hidden by an
        # unconditional `display: none !important` inside a block named for a status
        # dock that was never built. That stranded 48 translated strings.
        for rule in re.findall(r"(?<!-)\.legend\s*\{([^}]*)\}", self.source):
            self.assertNotIn("display: none !important", rule)
            self.assertNotIn("display:none !important", rule)

        # It follows the setting that governs the colouring it explains.
        self.assertIn("body.no-alt-colors .legend", self.source)
        self.assertIn("classList.toggle('no-alt-colors', !settings.altitudeColors)", self.source)

        # And every band it draws must still have a translation in every catalogue.
        legend_keys = set(re.findall(r'data-i18n="(legend\.[^"]+)"', self.source))
        self.assertGreaterEqual(len(legend_keys), 8)
        for catalog in sorted(I18N_DIR.glob("*.json")):
            messages = json.loads(catalog.read_text(encoding="utf-8"))["messages"]
            missing = sorted(legend_keys - set(messages))
            self.assertEqual(missing, [], f"{catalog.name} is missing {missing}")

    def test_readme_data_source_table_matches_the_code(self) -> None:
        # The table claimed ADSB One sent CORS headers, omitted adsb.fi entirely, and
        # listed an endpoint the code did not poll. This repo's failure mode is green
        # checks over a dead data plane, so a README that misdescribes the data plane
        # is a hazard rather than a cosmetic problem.
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        table_start = readme.index("### Data Sources")
        table = readme[table_start:readme.index("## Settings", table_start)]

        sources = re.search(r"sources: \[(.*?)\n        \],", self.source, re.S)
        self.assertIsNotNone(sources, "could not find the source list in index.html")
        block = sources.group(1)
        names = re.findall(r"name: '([^']+)'", block)
        self.assertGreaterEqual(len(names), 4)
        for name in names:
            self.assertIn(name, table, f"{name} is missing from the README data-source table")

        # Every source is relayed. A "Yes" in the CORS column would be a lie.
        self.assertEqual(block.count("cors: false"), len(names),
                         "a source claims to send CORS headers")
        self.assertNotIn("| Yes |", table, "the table claims a source sends CORS headers")

        # And the relay must be described as the live-data path, not a file:// aid.
        self.assertNotIn("CORS proxy failover for file:// protocol", readme)
        self.assertIn("Deploy your own data relay", readme)

    def test_compact_registration_registry_is_hex_keyed(self) -> None:
        # The OPFS worker seeds the whole registration database from this file. It
        # accepted any object, and the shipped file is keyed by entire CSV lines
        # rather than by hex - so every browser with OPFS loaded 3,928 junk entries
        # instead of the real registry and never fell back to the CSV.
        worker = OPFS_WORKER.read_text(encoding="utf-8")
        self.assertIn("HEX_KEY", worker, "the worker does not check the registry shape")
        self.assertIn("isRecordMap", worker)

        compact = ROOT / "data" / "aircraft" / "registrations.json"
        if not compact.is_file():
            self.skipTest("no compact registry is shipped")
        records = json.loads(compact.read_text(encoding="utf-8"))
        self.assertIsInstance(records, dict)
        keys = list(records)[:200]
        self.assertTrue(keys, "the compact registry is empty")
        hex_keyed = [k for k in keys if re.fullmatch(r"[0-9A-F]{4,6}", k)]
        self.assertGreaterEqual(
            len(hex_keyed), int(len(keys) * 0.9),
            "the compact registry is not keyed by ICAO hex, so it cannot seed the registry",
        )

    def test_no_runtime_url_points_at_a_sibling_repository(self) -> None:
        # v0.6.0 moved every runtime fetch off the sibling SysAdminDoc/SkyTrack repo,
        # but five asset mirrors were left behind - and one of them, the type-photo
        # mirror, already answers 404 there while VIPTrack's own path serves it. A
        # fallback pointing at another repository can rot without anything here
        # noticing.
        for name, source in (("index.html", self.source),
                             ("sw.js", SERVICE_WORKER.read_text(encoding="utf-8")),
                             ("cesium-frame.html", CESIUM_FRAME.read_text(encoding="utf-8"))):
            self.assertNotIn("SysAdminDoc/SkyTrack", source,
                             f"{name} fetches from the sibling SkyTrack repository")

        # Every raw.githubusercontent mirror this app builds must name this repo.
        mirrors = re.findall(r"https://raw\.githubusercontent\.com/SysAdminDoc/([A-Za-z0-9_.-]+)/",
                             self.source)
        self.assertTrue(mirrors, "no first-party mirrors found to check")
        for repo in set(mirrors):
            self.assertEqual(repo, "VIPTrack", f"a mirror points at {repo}")

    def test_repeating_timers_go_through_the_pausable_registry(self) -> None:
        # Six timers stored no handle, were never cleared, and bypassed the registry
        # that exists so a background tab stops polling. They kept running while the
        # tab was hidden.
        bare = []
        for match in re.finditer(r"(?<![.\w])setInterval\(", self.source):
            start = self.source.rfind("\n", 0, match.start()) + 1
            line = self.source[start:self.source.find("\n", match.start())]
            # The registry itself, and the object method named setInterval on the
            # coverage view, are the legitimate uses.
            if "_pausableIntervals" in line or "entry.fn" in line:
                continue
            if re.search(r"\bsetInterval\(fn, ms\)", line):
                continue
            if re.search(r"^\s*setInterval\(seconds\)", line):
                continue
            # A timer that stores its handle and is cleared elsewhere manages its own
            # lifetime; the feed loop, the coverage recorder and the one-shot readiness
            # poll are all of that shape. What must never exist again is a repeating
            # timer with no handle at all, which can be neither paused nor stopped.
            assigned = re.match(r"\s*(?:const |let |var )?([\w.$]+)\s*=\s*setInterval\(", line)
            if assigned and f"clearInterval({assigned.group(1)})" in self.source:
                continue
            bare.append(line.strip()[:110])
        self.assertEqual(
            bare, [],
            "these repeating timers are neither registered as pausable nor ever cleared, "
            "so they keep running in a background tab: " + "; ".join(bare),
        )
        self.assertIn("_pauseAllIntervals", self.source)
        self.assertIn("_resumeAllIntervals", self.source)

    def test_indexeddb_stores_are_pinned_to_the_declared_version(self) -> None:
        # The store-creation guards only run inside onupgradeneeded, which only fires
        # when the version increases. Adding a store without bumping dbVersion is
        # silent: existing users never get it, and every transaction against it throws
        # NotFoundError. dbVersion has never moved off 1, so nothing has forced the
        # question yet.
        version = re.search(r"dbVersion:\s*(\d+)", self.source)
        self.assertIsNotNone(version, "skytrackDB declares no dbVersion")
        declared = int(version.group(1))
        self.assertGreaterEqual(declared, 1)

        stores = sorted(set(re.findall(r"createObjectStore\('([^']+)'", self.source)))
        self.assertTrue(stores, "no object stores found")

        # The pinned pair. Changing the store set without moving the version fails
        # here, which is the whole point: the failure message says what to do.
        EXPECTED_STORES = ["aircraftCache", "databases", "trailHistory", "userData"]
        EXPECTED_VERSION = 1
        self.assertEqual(
            stores, EXPECTED_STORES,
            f"the object-store set changed to {stores}. Bump skytrackDB.dbVersion above "
            f"{declared} so onupgradeneeded runs for existing users, then update "
            "EXPECTED_STORES and EXPECTED_VERSION in this test together.",
        )
        self.assertEqual(
            declared, EXPECTED_VERSION,
            f"skytrackDB.dbVersion moved to {declared}. Confirm every store in "
            f"{stores} is created under the new version, then update EXPECTED_VERSION.",
        )

        # Every store the code opens a transaction against must be one it creates,
        # or that transaction throws NotFoundError on a database that predates it.
        opened = set(re.findall(r"transaction\(\['([^']+)'\]", self.source))
        opened |= set(re.findall(r"objectStore\('([^']+)'\)", self.source))
        for name in sorted(opened):
            self.assertIn(name, stores,
                          f"a transaction opens '{name}', which no upgrade path creates")

    def test_i18n_catalogs_share_schema_keys_and_same_origin_loader(self) -> None:
        for marker in (
            "const i18nManager =",
            "data/i18n/",
            "data-i18n",
            "languageSelect",
            "viptrack_language_v1",
            "credentials: 'same-origin'",
            "location.protocol === 'file:'",
            "this.messages.en",
        ):
            self.assertIn(marker, self.source)
        source_keys = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', self.source))
        self.assertGreaterEqual(len(source_keys), 120)
        catalogs = {}
        for language in ("en", "es", "fr", "de", "ru", "uk"):
            path = I18N_DIR / f"{language}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(payload["language"], language)
            self.assertIsInstance(payload["messages"], dict)
            catalogs[language] = set(payload["messages"])
            self.assertEqual(source_keys, catalogs[language])
            self.assertGreaterEqual(len(catalogs[language]), 120)
        self.assertEqual(catalogs["en"], catalogs["es"])

    def test_opfs_registration_worker_uses_sync_handles_with_fallback_contract(self) -> None:
        worker = OPFS_WORKER.read_text(encoding="utf-8")
        for marker in (
            "const OPFS_SCHEMA_VERSION = 1",
            "const OPFS_FILE_NAME = 'viptrack-registrations-v1.json'",
            "navigator.storage.getDirectory",
            "createSyncAccessHandle()",
            "accessHandle.read(bytes, { at: 0 })",
            "accessHandle.write(bytes, { at: 0 })",
            "accessHandle.flush()",
            "self.onmessage = async event",
            "type: 'loaded'",
            "code: error?.message === 'OPFS unavailable' ? 'unsupported' : 'load-failed'",
        ):
            self.assertIn(marker, worker)
        for marker in (
            "const registrationOPFSManager =",
            "workers/registration-opfs-worker.js",
            "new Worker(workerUrl.href",
            "DATA_URLS.registrations.compact",
            "Loaded', this.aircraft.size, 'registrations from OPFS",
            "navigator.storage?.getDirectory",
            "this.worker?.terminate()",
            "'data/aircraft/registrations.json'",
            "'workers/registration-opfs-worker.js'",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("createSyncAccessHandle()", self.source)

    def test_static_manifest_supports_pwa_and_share_target(self) -> None:
        manifest = json.loads(WEB_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "./")
        self.assertEqual(manifest["scope"], "./")
        self.assertEqual(manifest["start_url"], "./index.html")
        self.assertEqual(manifest["display"], "standalone")
        self.assertIn("standalone", manifest["display_override"])
        self.assertEqual(manifest["share_target"]["method"], "GET")
        self.assertEqual(manifest["share_target"]["params"], {"title": "title", "text": "text", "url": "url"})
        for icon in manifest["icons"]:
            icon_path = ROOT / icon["src"]
            self.assertTrue(icon_path.is_file(), icon["src"])
            png = icon_path.read_bytes()
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            expected_size = int(icon["sizes"].split("x", 1)[0])
            self.assertEqual(struct.unpack(">II", png[16:24]), (expected_size, expected_size))
        self.assertEqual({icon["sizes"] for icon in manifest["icons"]}, {"192x192", "512x512"})
        self.assertTrue(all("maskable" in icon["purpose"] for icon in manifest["icons"]))
        self.assertFalse((ROOT / "assets" / "logo" / "VIPTrack_Mark.svg").exists())
        self.assertNotIn("SkyTrack_Logo", self.source + SERVICE_WORKER.read_text(encoding="utf-8") + WEB_MANIFEST.read_text(encoding="utf-8"))
        for marker in (
            '<link rel="manifest" href="manifest.json">',
            '<link rel="icon" type="image/png" sizes="16x16" href="assets/logo/VIPTrack_Mark-16x16.png">',
            '<link rel="icon" type="image/png" sizes="32x32" href="assets/logo/VIPTrack_Mark-32x32.png">',
            '<link rel="icon" type="image/png" sizes="48x48" href="assets/logo/VIPTrack_Mark-48x48.png">',
            '<link rel="apple-touch-icon" sizes="192x192" href="assets/logo/VIPTrack_Mark-192x192.png">',
            "location.protocol === 'file:'",
            "display_override: ['window-controls-overlay', 'standalone']",
            "share_target:",
            "_extractSharedValue(params)",
            "sharedRegistration",
            "searchSystem?.executeSearch",
        ):
            self.assertIn(marker, self.source)

    def test_native_android_app_bundles_the_mobile_shell_and_stays_unsigned(self) -> None:
        self.assertTrue((ANDROID_DIR / "gradlew.bat").is_file())
        self.assertFalse((ANDROID_DIR / "twa-manifest.json").exists())
        build_gradle = (ANDROID_DIR / "app" / "build.gradle").read_text(encoding="utf-8")
        manifest = (ANDROID_DIR / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
        activity = (ANDROID_DIR / "app" / "src" / "main" / "java" / "com" / "sysadmindoc" / "viptrack" / "LauncherActivity.java").read_text(encoding="utf-8")
        navigation = (ANDROID_DIR / "app" / "src" / "main" / "java" / "com" / "sysadmindoc" / "viptrack" / "VipTrackNavigation.java").read_text(encoding="utf-8")
        navigation_test = ANDROID_DIR / "app" / "src" / "test" / "java" / "com" / "sysadmindoc" / "viptrack" / "VipTrackNavigationTest.java"
        resources = ANDROID_DIR / "app" / "src" / "main" / "res"
        for marker in (
            "androidx.webkit:webkit:1.16.0",
            "syncVipTrackWebAssets",
            "verifyVipTrackWebAssets",
            "include 'type_photos/**'",
            "Bulk aircraft photos must not be packaged",
            "FAA shards must remain an on-demand HTTPS dataset",
            "minSdk 24",
            "targetSdk 36",
        ):
            self.assertIn(marker, build_gradle)
        for marker in (
            'android.permission.INTERNET',
            'android.permission.ACCESS_NETWORK_STATE',
            'android:usesCleartextTraffic="false"',
            'android:allowBackup="false"',
            'android:roundIcon="@mipmap/ic_launcher_round"',
            'android:pathPrefix="/VIPTrack"',
            'android:scheme="https"',
        ):
            self.assertIn(marker, manifest)
        for marker in (
            "WebViewAssetLoader",
            "MIXED_CONTENT_NEVER_ALLOW",
            "setAllowFileAccess(false)",
            "setAcceptThirdPartyCookies(webView, false)",
            'addJavascriptInterface(new AndroidBridge(this), "VIPTrackAndroid")',
            "ServiceWorkerController",
            "buildAssetShareUrl",
            "return BuildConfig.DEBUG",
        ):
            self.assertIn(marker, activity)
        for marker in (
            "sysadmindoc.github.io",
            'APP_SCOPE_PATH = "/VIPTrack/"',
            "isSafeExternalUrl",
            "MAX_QUERY_LENGTH",
        ):
            self.assertIn(marker, navigation)
        self.assertTrue(navigation_test.is_file())
        self.assertNotIn("androidbrowserhelper", build_gradle + manifest + activity)
        self.assertNotIn("signingConfig", build_gradle)
        self.assertNotIn("debug.keystore", build_gradle)
        for launcher_name in ("ic_launcher.xml", "ic_launcher_round.xml"):
            adaptive_icon = (resources / "mipmap-anydpi-v26" / launcher_name).read_text(encoding="utf-8")
            self.assertIn("<adaptive-icon", adaptive_icon)
            self.assertIn('@color/ic_launcher_background', adaptive_icon)
            self.assertIn('@mipmap/ic_launcher_foreground', adaptive_icon)
            self.assertIn('@mipmap/ic_launcher_monochrome', adaptive_icon)
        self.assertIn(
            '#050B18',
            (resources / "values" / "ic_launcher_background.xml").read_text(encoding="utf-8"),
        )
        density_sizes = {
            "mdpi": (108, 48),
            "hdpi": (162, 72),
            "xhdpi": (216, 96),
            "xxhdpi": (324, 144),
            "xxxhdpi": (432, 192),
        }
        for density, (layer_size, legacy_size) in density_sizes.items():
            density_dir = resources / f"mipmap-{density}"
            for name, expected_size in (
                ("ic_launcher_foreground.png", layer_size),
                ("ic_launcher_monochrome.png", layer_size),
                ("ic_launcher.png", legacy_size),
                ("ic_launcher_round.png", legacy_size),
            ):
                png = (density_dir / name).read_bytes()
                self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", png[16:24]), (expected_size, expected_size))
        for obsolete in (
            resources / "drawable-anydpi" / "ic_launcher_foreground.xml",
            resources / "drawable-anydpi" / "ic_launcher_monochrome.xml",
            resources / "drawable-anydpi" / "ic_launcher_legacy_background.xml",
            resources / "mipmap-anydpi" / "ic_launcher.xml",
            resources / "mipmap-anydpi" / "ic_launcher_round.xml",
            resources / "mipmap-anydpi-v33" / "ic_launcher.xml",
            resources / "mipmap-anydpi-v33" / "ic_launcher_round.xml",
        ):
            self.assertFalse(obsolete.exists(), str(obsolete))
        store_icon = (ANDROID_DIR / "store_icon.png").read_bytes()
        self.assertEqual(store_icon[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", store_icon[16:24]), (512, 512))
        # The Android build no longer pins airplanes.live: that endpoint requires
        # approved API access and answers 403, so every platform follows measured health.
        self.assertNotIn("CONFIG.isAndroidApp && source.key !== 'airplaneslive'", self.source)
        self.assertNotIn("androidSourceOrder", self.source)
        self.assertIn("const VIPTRACK_ANDROID_QA_MODE = IS_VIPTRACK_ANDROID_APP", self.source)

    def test_live_feed_relay_contract_survives_cors_removal(self) -> None:
        # Verified 2026-08-18 from a browser on the live origin: no public ADS-B
        # aggregator sends Access-Control-Allow-Origin, so every feed must be marked
        # `cors: false` and relayed, and the health check must not skip relayed sources.
        for key in ("adsbone", "adsblol", "airplaneslive", "adsbfi"):
            descriptor = re.search(r"\{ key: '" + key + r"'.*?limitations:", self.source, re.S)
            self.assertIsNotNone(descriptor, key)
            self.assertIn("cors: false", descriptor.group(0), key)
        self.assertNotIn("source.cors === false && location.hostname.includes('github.io')", self.source)
        # api.codetabs.com stopped answering; corsproxy.io is the verified-fastest relay.
        self.assertNotIn("api.codetabs.com", self.source)
        self.assertIn("https://corsproxy.io/?url=", self.source)
        self.assertIn("https://api.allorigins.win/raw?url=", self.source)
        # adsb.fi uses /lat/../lon/../dist/..; the /point/ shape returns HTTP 400.
        self.assertIn("'https://opendata.adsb.fi/api/v2/lat/'", self.source)
        self.assertNotIn("'https://opendata.adsb.fi/api/v2/point/'", self.source)
        # airplanes.live is opt-out until an operator holds approved API access.
        self.assertIn("disabled: true", self.source)
        self.assertIn("disabledReason:", self.source)
        self.assertIn("if (source.disabled)", self.source)
        self.assertIn("enabledSources()", self.source)

    def test_connectivity_probe_follows_the_healthiest_source(self) -> None:
        # Both former probe hosts now answer 403, which reported "offline" on a healthy
        # connection. The probe must derive its target from the source manager instead.
        self.assertIn("getProbeSource()", self.source)
        self.assertNotIn("'https://api.adsb.one/v2/point/0/0/1'", self.source)
        self.assertNotIn("'https://api.airplanes.live/v2/point/0/0/1'", self.source)
        self.assertIn("skipDirect", self.source)

    def test_connect_src_is_a_real_allowlist(self) -> None:
        meta = re.search(r'http-equiv="Content-Security-Policy" content="(.*?)"', self.source, re.S)
        self.assertIsNotNone(meta)
        policy = meta.group(1)
        # CSP has no comment syntax: an HTML comment inside content=" silently invalidates
        # the directives around it and the page falls back to default-src 'self'.
        self.assertNotIn("<!--", policy)
        self.assertNotIn("-->", policy)
        headers = (ROOT / "_headers").read_text(encoding="utf-8")
        for name, text in (("meta", policy), ("_headers", headers)):
            connect = re.search(r"connect-src ([^;]+);", text)
            self.assertIsNotNone(connect, name)
            tokens = connect.group(1).split()
            # Bare scheme sources match every origin and make the allowlist decorative.
            self.assertNotIn("http:", tokens, name)
            self.assertNotIn("https:", tokens, name)
            self.assertIn("'self'", tokens, name)
            for required in ("https://api.adsb.lol", "https://opendata.adsb.fi", "https://corsproxy.io",
                             "https://nowcoast.noaa.gov", "https://api.rainviewer.com"):
                self.assertIn(required, tokens, f"{name}: {required}")
        self.assertIn("object-src 'none'", policy)

    def test_feed_health_is_visible_and_inspectable(self) -> None:
        # The reliability indicator was switched off with a global `display: none`, so a
        # feed outage was indistinguishable from normal operation.
        self.assertNotIn(".data-source-indicator { display: none !important; }", self.source)
        self.assertIn('id="dataSourceDetail"', self.source)
        self.assertIn('aria-controls="dataSourceDetail"', self.source)
        self.assertIn("healthSummary()", self.source)
        self.assertIn("renderDetail()", self.source)
        self.assertIn("toggleDetail(", self.source)
        # Counts must be against enabled sources, not the raw list including disabled ones.
        self.assertIn("const enabled = this.enabledSources();", self.source)
        for state in ("is-healthy", "is-degraded", "is-unhealthy"):
            self.assertIn(state, self.source)
        # Escape closes the panel and focus returns to the control that opened it.
        self.assertIn("this.toggleDetail(false);", self.source)

    def test_accessibility_preferences_and_skip_link(self) -> None:
        # user-scalable=no / maximum-scale block pinch zoom (WCAG 2.1 SC 1.4.4), and the
        # mobile flight deck is now a first-class surface.
        viewport = re.search(r'<meta name="viewport" content="([^"]+)"', self.source)
        self.assertIsNotNone(viewport)
        self.assertNotIn("user-scalable=no", viewport.group(1))
        self.assertNotIn("maximum-scale", viewport.group(1))
        # Skip link is the first element in the body and targets the main content.
        body = self.source.split("<body>", 1)[1].lstrip()
        self.assertTrue(body.startswith('<a class="skip-link" href="#map"'), body[:80])
        # OS preferences, in the inline styles and in the sheet that owns the mobile deck.
        ui_css = (ROOT / "assets" / "viptrack-ui.css").read_text(encoding="utf-8")
        for sheet, text in (("index.html", self.source), ("viptrack-ui.css", ui_css)):
            self.assertIn("prefers-reduced-motion: reduce", text, sheet)
            self.assertIn("forced-colors: active", text, sheet)
        self.assertIn("prefers-contrast: more", self.source)
        # Marker interpolation has to honour the setting too, not just CSS transitions.
        self.assertIn("_prefersReducedMotion()", self.source)

    def test_faa_snapshot_ages_out_of_owner_identity(self) -> None:
        # FAA section 803 withholding is continuous, so a frozen snapshot drifts toward
        # holding records an owner has since asked to be withheld.
        manifest = json.loads((ROOT / "data" / "faa" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("generatedAt", manifest)
        self.assertRegex(manifest["generatedAt"], r"^\d{4}-\d{2}-\d{2}")
        self.assertIn("OWNER_STALE_DAYS", self.source)
        self.assertIn("OWNER_EXPIRY_DAYS", self.source)
        self.assertIn("ownerWithheld: true", self.source)
        self.assertIn("faaRegistryManager.provenance()", self.source)
        # Past the limit the aircraft facts survive and only identity is dropped.
        self.assertIn("const { name, owner, ownerName, city, state, ...rest } = record;", self.source)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("tools/build_faa_registry.py", readme)

    def test_vendored_reference_database_declares_its_vintage(self) -> None:
        # registrations.csv ships with the release, so it drifts silently unless the
        # refresh is documented and gated. It had sat five months behind upstream.
        manifest = json.loads((ROOT / "data" / "aircraft" / "manifest.json").read_text(encoding="utf-8"))
        for key in ("source", "sourceUrl", "license", "dbVersion", "refreshedAt", "rows", "refreshCommand"):
            self.assertIn(key, manifest)
        version_file = (ROOT / "data" / "aircraft" / "dbversion.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(manifest["dbVersion"], version_file)
        self.assertGreater(manifest["rows"], 100_000)
        refreshed = datetime.date.fromisoformat(manifest["refreshedAt"])
        age = (datetime.date.today() - refreshed).days
        self.assertLessEqual(age, manifest.get("staleAfterDays", 120),
                             "run: py -3.13 tools/refresh_reference_data.py")
        self.assertTrue((ROOT / "tools" / "refresh_reference_data.py").is_file())

    def test_release_version_is_synchronized_across_shell_docs_and_android(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        build_gradle = (ANDROID_DIR / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("<title>VIPTrack v0.8.2:", self.source)
        self.assertIn('class="version">v0.8.2', self.source)
        self.assertIn("version-0.8.2-blue", readme)
        self.assertIn("## [v0.8.2] - 2026-08-29", changelog)
        self.assertIn("versionName '0.8.2'", build_gradle)
        self.assertIn("versionCode 13", build_gradle)

        # The service worker serves index.html cache-first with no revalidation, so a
        # cache key that does not move means returning users stay on the old build.
        # The key carries the app version and a fingerprint of the precached bytes.
        service_worker = SERVICE_WORKER.read_text(encoding="utf-8")
        self.assertIn("const APP_VERSION = '0.8.2';", service_worker)
        self.assertIn("const VIPTRACK_APP_VERSION = '0.8.2';", self.source)
        self.assertIn("appVersion: APP_VERSION", service_worker)
        self.assertIn("assetFingerprint: STATIC_ASSET_FINGERPRINT", service_worker)

        listed = re.search(r"const STATIC_ASSETS = \[(.*?)\];", service_worker, re.S)
        self.assertIsNotNone(listed)
        assets = [a for a in re.findall(r"'([^']+)'", listed.group(1))
                  if not a.startswith("http") and a != "sw.js"]
        self.assertTrue(assets)
        digest = hashlib.sha256()
        for asset in assets:
            digest.update(asset.encode("utf-8"))
            digest.update((ROOT / asset).read_bytes())
        expected = digest.hexdigest()[:12]
        recorded = re.search(r"const STATIC_ASSET_FINGERPRINT = '([0-9a-f]+)';", service_worker)
        self.assertIsNotNone(recorded, "sw.js carries no STATIC_ASSET_FINGERPRINT")
        self.assertEqual(
            recorded.group(1), expected,
            "a precached asset changed without the service-worker cache key moving. "
            f"Set STATIC_ASSET_FINGERPRINT = '{expected}' in sw.js.",
        )

    def test_type_photo_catalog_and_resumable_workflow_are_wired(self) -> None:
        downloader = TYPE_PHOTO_DOWNLOADER.read_text(encoding="utf-8")
        workflow = TYPE_PHOTO_WORKFLOW.read_text(encoding="utf-8")
        manifest_path = ROOT / "assets" / "type_photos" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest), 500)
        for type_code, entry in manifest.items():
            self.assertRegex(type_code, r"^[A-Z0-9]{2,8}$")
            self.assertEqual(entry["file"], f"{type_code}.jpg")
            self.assertTrue((manifest_path.parent / entry["file"]).is_file(), type_code)
            self.assertIn(entry["source"], {"planespotters-hex", "planespotters-reg", "airport-data", "wikipedia", "wikipedia-short", "wikipedia-raw", "silhouette", "existing"})
        for marker in (
            "LOCAL_TYPES_JSON",
            "REQUEST_RETRIES = 2",
            "--limit",
            "default=500",
            "--all-types",
            "--dry-run",
            "load_manifest()",
            "write_manifest(manifest)",
            "preserved for --resume",
        ):
            self.assertIn(marker, downloader)
        for marker in ("--types-only", "--resume", "--limit", "--all-types", "--dry-run"):
            self.assertIn(marker, workflow)
        for marker in (
            "typePhotos: 'assets/type_photos/'",
            "typePhotosFallback:",
            "const typePhotoUrls =",
        ):
            self.assertIn(marker, self.source)

    def test_session_stats_dashboard_tracks_privacy_safe_feed_health(self) -> None:
        for marker in (
            "const statsDashboard =",
            "maxSamples: 24",
            "messagesSeen = 0",
            "latencySamples = []",
            "sourceUse = new Map()",
            "statsDashboard.recordSuccess(src, allAc.length, Date.now() - statsStartedAt, provenance)",
            "statsDashboard.recordFailure()",
            "id=\"statsLatencyHistogram\"",
            "id=\"statsRollingCounts\"",
            "id=\"statsSourceUsage\"",
            "id=\"statsResetBtn\"",
            "No aircraft identifiers,",
            "tracks, or source payloads are persisted",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const statsDashboard =")
        end = self.source.index("// ============ INDEXEDDB STORAGE", start)
        section = self.source[start:end]
        self.assertNotIn("localStorage", section)
        self.assertIn("this.rolling.slice(-12)", section)
        self.assertIn("this.latencySamples", section)

    def test_source_provenance_is_freshness_bounded_and_pia_safe(self) -> None:
        for marker in (
            "rateBudget: { capacity: 1, refillPerSec: 1",
            "coverage:",
            "limitations:",
            "describe(url)",
            "lastFetchLatency",
            "lastFallbackChain",
            "getDiagnostics()",
            "function _normaliseAircraftProvenance",
            "ac.seen_pos",
            "ac.seen",
            "ac.nac_p",
            "sourceFetchedAt",
            "sourceFallbackChain",
            "sourceRateBudget",
            "sourceIntegrity",
            "quality = 'fresh'",
            "quality = 'stale'",
            "processAircraftData(allAc, provenance)",
            "renderAircraftProvenance(ac)",
            "id=\"sourceEvidenceSection\"",
            "id=\"copySourceDiagnosticsBtn\"",
            "navigator.clipboard.writeText(JSON.stringify(dataSourceManager.getDiagnostics()",
        ):
            self.assertIn(marker, self.source)
        source_start = self.source.index("const dataSourceManager =")
        source_end = self.source.index("// ============ L14:", source_start)
        source_section = self.source[source_start:source_end]
        self.assertNotIn("aircraftCache", source_section)
        self.assertNotIn("ac.r", source_section)
        provenance_start = self.source.index("function _normaliseAircraftProvenance")
        provenance_end = self.source.index("function privacySafeAircraftSnapshot", provenance_start)
        self.assertNotIn("ac.r", self.source[provenance_start:provenance_end])
        # The cache schema is meant to advance when the projection changes; pinning
        # its value blocked exactly that. Assert it exists, is an integer, and only
        # ever moves forward from the version this contract was written against.
        schema = re.search(r"const AIRCRAFT_CACHE_SCHEMA = (\d+);", self.source)
        self.assertIsNotNone(schema, "the aircraft cache projection carries no schema version")
        self.assertGreaterEqual(int(schema.group(1)), 3)

    def test_track_shape_heuristics_are_local_unverified_and_pia_safe(self) -> None:
        for marker in (
            "const trackHeuristicManager =",
            "minPoints: 8",
            "minDurationMs: 45 * 1000",
            "_haversineNm",
            "_bearing",
            "directRatio",
            "averageAltitude >= 40000",
            "info.heuristicOrbit",
            "info.heuristicTransit",
            "info.heuristicHold",
            "trackHeuristicManager.update(existing)",
            "trackHeuristicManager.update(cached)",
            "trackHeuristicManager.render(ac)",
            "id=\"trackHeuristicsSection\"",
            "Unverified pattern hints",
            "isPrivacyProtectedAircraft(ac)",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const trackHeuristicManager =")
        end = self.source.index("// L17: retain a privacy-safe", start)
        section = self.source[start:end]
        self.assertNotIn("fetch(", section)
        self.assertNotIn("localStorage", section)
        self.assertNotIn("ac.r", section)
        self.assertNotIn("ac.ownOp", section)
        self.assertIn("trackHeuristics = { tags: [], metrics: null", section)
        self.assertNotIn("trackHeuristics: a.trackHeuristics", self.source)

    def test_squawk_7700_history_is_persisted_attributed_and_url_filterable(self) -> None:
        for marker in (
            "const emergencyHistoryManager =",
            "emergency_squawk_history_v1",
            "mergeWindowMs: 15 * 60 * 1000",
            "windowMs: 24 * 60 * 60 * 1000",
            "militaryDB.getByHex(ac?.hex)",
            "emergencyHistoryManager.observe(existing, now)",
            "emergencyHistoryManager.observe(cached, now)",
            "params.set('emergency', emergency)",
            "emergencyHistoryManager.applyUrlMode(emergency)",
            'id="emergencyFeed"',
            'id="emergencyFeedModeBtn"',
            'id="emergencyFeedList"',
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const emergencyHistoryManager =")
        end = self.source.index("// ============ AIRPORT FREQUENCIES DATABASE", start)
        section = self.source[start:end]
        self.assertIn("isPrivacyProtectedAircraft(ac)", section)
        self.assertIn("Operator anonymised", section)
        self.assertNotIn("ac.r", section)
        self.assertNotIn("ac.ownOp", section)
        self.assertIn("skytrackDB.saveUserData(this.storageKey, data)", section)

    def test_curated_aircraft_mode_uses_catalog_membership_and_excludes_heuristics(self) -> None:
        for marker in (
            "function isCuratedAircraft(ac)",
            "interestingDB.isInteresting(hex)",
            "civilianDB.isCivilianInteresting(hex)",
            "data-filter=\"curated\"",
            "countCurated",
            "settings.filter === 'curated'",
        ):
            self.assertIn(marker, self.source)
        # Assert the contract - curated is one of the values the filter allowlist
        # accepts - rather than the exact line. The previous marker pinned
        # "'curated'].includes(settings.filter)", which broke the moment another
        # category was appended to the same list.
        allowlists = re.findall(r"\[([^\]]*)\]\.includes\(settings\.filter\)", self.source)
        self.assertTrue(allowlists, "no filter allowlist guards settings.filter")
        for allowlist in allowlists:
            self.assertIn("'curated'", allowlist)
        start = self.source.index("function isCuratedAircraft(ac)")
        end = self.source.index("function getAirlineCode", start)
        section = self.source[start:end]
        self.assertIn("badgersBestDB.isVIP(hex)", section)
        self.assertNotIn("category_type === 'military'", section)

    def test_named_watchlists_cover_rule_dimensions_and_persistence(self) -> None:
        for marker in (
            "namedWatchlists: new Map()",
            "normalizeNamedRules",
            "matchesNamedRules",
            "named_watchlists",
            "namedWatchlistGeofences",
            "this.triggerAlert(ac, 'WATCHLIST', list.name + ' matched', 'named_' + list.id)",
        ):
            self.assertIn(marker, self.source)
        self.assertRegex(self.source, r"rules\.hexes\.length")
        self.assertRegex(self.source, r"rules\.callsignRegex")
        self.assertRegex(self.source, r"rules\.types\.length")
        self.assertRegex(self.source, r"rules\.countries\.length")
        self.assertRegex(self.source, r"rules\.altMin")
        self.assertRegex(self.source, r"rules\.geofences\.length")

    def test_named_watchlist_dynamic_markup_uses_safe_html(self) -> None:
        marker = "updateNamedWatchlistUI()"
        start = self.source.index(marker)
        end = self.source.index("// ============ WEATHER SYSTEM", start)
        section = self.source[start:end]
        self.assertIn("container.innerHTML = safeHTML(items)", section)

    def test_geofence_editor_persists_geometry_and_alerts_transitions(self) -> None:
        for marker in (
            "const geofenceManager =",
            "geofences: new Map()",
            "start('circle')",
            "start('polygon')",
            "pointInPolygon",
            "checkAircraft(ac)",
            "geofence.name + (inside ? ' entry' : ' exit')",
            "saveUserData('geofences'",
        ):
            self.assertIn(marker, self.source)
        geofence_start = self.source.index("const geofenceManager =")
        geofence_end = self.source.index("// ============ X6: COINCIDENCE DETECTOR", geofence_start)
        geofence_section = self.source[geofence_start:geofence_end]
        self.assertIn("layer.bindTooltip(safeHTML(geofence.name)", geofence_section)
        self.assertIn("container.innerHTML = safeHTML(items)", geofence_section)

    def test_pia_rotation_timeline_is_local_and_privacy_safe(self) -> None:
        for marker in (
            "const piaRotationTimeline =",
            "windowMs: 20 * 86400000",
            "profileKey(ac)",
            "pia_rotation_timeline",
            "PIA rotation timeline",
            "public PIA addresses observed within the 20-day rotation window",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const piaRotationTimeline =")
        end = self.source.index("// ============ AIRPORT FREQUENCIES DATABASE", start)
        section = self.source[start:end]
        self.assertIn("flight", section)
        self.assertIn("ac?.t", section)
        self.assertNotIn("ac.r", section)
        self.assertNotIn("ac.ownOp", section)
        self.assertIn("list.innerHTML = safeHTML", section)

    def test_curated_overlay_manifest_and_loader_contract(self) -> None:
        manifest_path = ROOT / "data" / "overlays" / "manifest.json"
        geojson_path = ROOT / "data" / "overlays" / "mil-patterns.geojson"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(len(manifest["presets"]), 4)
        self.assertEqual(len({preset["id"] for preset in manifest["presets"]}), 4)
        self.assertEqual(len(geojson["features"]), 4)
        self.assertTrue(all(feature["properties"]["template"] for feature in geojson["features"]))
        self.assertTrue(all(not feature["properties"]["verified"] for feature in geojson["features"]))
        for marker in ("const curatedOverlayManager =", "data/overlays/manifest.json", "setPreset(id", "filter: feature => feature?.properties?.presetId === preset.id"):
            self.assertIn(marker, self.source)
        self.assertIn("curatedOverlayList", self.source)

    def test_receiver_coverage_uses_direct_tar1090_json_and_directional_bins(self) -> None:
        for marker in (
            "const receiverCoverageManager =",
            "receiverCoverageUrl",
            "receiver.json",
            "aircraft.json",
            "stats.json",
            "sectorCount: 36",
            "max_distance",
            "metres / 1000",
            "No feeder data is sent to a proxy",
            "receiverCoverageLoadBtn",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const receiverCoverageManager =")
        end = self.source.index("// ============ X5: LOCAL GEOFENCE EDITOR", start)
        section = self.source[start:end]
        self.assertNotIn("fetchWithProxy", section)
        self.assertIn("Math.floor(bearing / (360 / this.sectorCount))", section)
        self.assertIn("L.polygon(points", section)

    def test_opensky_replay_is_manual_oauth_historical_only(self) -> None:
        self.assertNotIn("defaultCredentials", self.source)
        self.assertNotIn("mparker-api-client", self.source)
        self.assertNotRegex(self.source, r"clientSecret\s*:\s*['\"]")
        for marker in (
            "const openSkyHistoricalManager =",
            "OpenSky Historical Replay (X20)",
            "auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
            "grant_type: 'client_credentials'",
            "opensky-network.org/api/tracks/all",
            "openSkyLoadBtn",
            "No historical track loaded",
            "this._timestamp",
            "clearAuthState",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const openSkyHistoricalManager =")
        end = self.source.index("// ============ X5: LOCAL GEOFENCE EDITOR", start)
        section = self.source[start:end]
        self.assertNotIn("setInterval", section)
        self.assertNotIn("fetchWithProxy", section)
        self.assertIn("clientSecretInput.value = ''", section)
        self.assertIn("finally", section)
        self.assertIn("this.clearAuthState()", section)
        self.assertIn("age <= 30 * 86400", section)

    def test_faa_sua_overlay_is_filtered_cached_and_stale_safe(self) -> None:
        for marker in (
            "const faaSuaOverlay =",
            "Special_Use_Airspace/FeatureServer/0/query",
            "TYPE_CODE IN ('R','P','MOA','W')",
            "returnGeometry: 'true'",
            "cacheMaxAge: 28 * 86400000",
            "skytrackDB.saveDatabase(this.cacheName, payload, this.cacheMaxAge)",
            "expired or incomplete data was not shown",
            "toggleFAASUA",
            "FAA SUA polygons",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const faaSuaOverlay =")
        end = self.source.index("// ============ X5: LOCAL GEOFENCE EDITOR", start)
        section = self.source[start:end]
        self.assertIn("new Set(['R', 'P', 'MOA', 'W'])", section)
        self.assertIn("['Polygon', 'MultiPolygon'].includes", section)
        self.assertIn("featureLayer.bindTooltip(safeHTML(this._tooltip(feature))", section)
        self.assertNotIn("fetchWithProxy", section)
        self.assertNotIn("setInterval", section)

    def test_share_exports_current_trail_png_with_link_fallback(self) -> None:
        for marker in (
            "title=\"Share aircraft trail PNG (copy link if unsupported)\"",
            "_collectTrailPoints(hex)",
            "new OffscreenCanvas(1200, 675)",
            "convertToBlob({ type: 'image/png' })",
            "navigator.canShare({ files: [file] })",
            "files: [file]",
            "sharing link instead",
            "await this.copyToClipboard(link)",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const shareManager =")
        end = self.source.index("// ============ MIDNIGHT THEME", start)
        section = self.source[start:end]
        self.assertIn("trailLine._group?.getLayers?.()", section)
        self.assertNotIn("navigator.share({ title, text: 'Follow this flight:'", section)

    def test_trail_retention_and_map_bookmarks_are_local_and_persistent(self) -> None:
        for marker in (
            "clearOldData(maxAgeDays = 7)",
            "id=\"trailRetention\"",
            "value=\"1\"",
            "value=\"7\"",
            "value=\"14\"",
            "value=\"30\"",
            "viptrack_trail_retention_days",
            "trailRetentionApply",
            "let bookmarks = []",
            "viptrack_bookmarks",
            "addBookmark(name)",
            "goToBookmark(id)",
            "Saved Locations",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("await skytrackDB.clearOldData(retention)", self.source)
        self.assertIn("localStorage.setItem('viptrack_bookmarks'", self.source)
        self.assertIn("map.setView([b.lat, b.lng], b.zoom)", self.source)

    def test_service_worker_hashes_manifest_expires_api_cache_and_evictions_lru_tiles(self) -> None:
        worker = SERVICE_WORKER.read_text(encoding="utf-8")
        for marker in (
            "const MANIFEST_HASH = fnv1a(JSON.stringify",
            "const API_CACHE_TTL_MS = 60000",
            "X-VIPTrack-Cached-At",
            "const TILE_CACHE_LIMIT = 1000",
            "X-VIPTrack-Tile-Last-Used",
            "entries.sort((a, b) => a.lastUsed - b.lastUsed)",
            # The API cache is capped and swept the same way tiles are: relay URLs
            # carry the target in the query string, so every pan mints a new key.
            "const API_CACHE_LIMIT = 50",
            "async function evictApiEntries(cache)",
            "live.sort((a, b) => a.cachedAt - b.cachedAt)",
            "await evictApiEntries(cache);",
            "self.addEventListener('install'",
            "self.addEventListener('activate'",
            "self.addEventListener('fetch'",
            "self.skipWaiting()",
            "self.clients.claim()",
        ):
            self.assertIn(marker, worker)
        # A stale cache from a previous run must be reclaimed on activate, not only
        # when the same URL happens to be requested again.
        activate = worker[worker.index("self.addEventListener('activate'"):worker.index("self.addEventListener('periodicsync'")]
        self.assertIn("evictApiEntries", activate)
        # Assert the contract - the shell and the worker agree on the schema version -
        # rather than a literal value, which pinned the constant the version exists to
        # let move and failed the moment it was bumped.
        # The cache name has to be derived from the prefix, the app version and the
        # manifest hash. Pinning its exact expression blocked adding the app version,
        # which is the whole point of the key moving between releases.
        cache_name = re.search(r"const CACHE_NAME = (.+);", worker)
        self.assertIsNotNone(cache_name)
        for part in ("CACHE_PREFIX", "APP_VERSION", "MANIFEST_HASH"):
            self.assertIn(part, cache_name.group(1))
        worker_schema = re.search(r"const CACHE_SCHEMA_VERSION = '([0-9.]+)';", worker)
        shell_schema = re.search(r"const SW_CACHE_SCHEMA = '([0-9.]+)'", self.source)
        self.assertIsNotNone(worker_schema)
        self.assertIsNotNone(shell_schema)
        self.assertEqual(worker_schema.group(1), shell_schema.group(1),
                         "index.html and sw.js disagree on the cache schema version")
        self.assertIn("new URL('sw.js', document.baseURI)", self.source)
        self.assertIn("updateViaCache: 'none'", self.source)
        self.assertIn("location.protocol !== 'file:'", self.source)
        self.assertNotIn("getRegistrations()", self.source)
        self.assertNotIn("unregister()", self.source)
        self.assertNotIn("new Blob([swCode]", self.source)
        self.assertNotIn("Blob([swCode]", worker)
        self.assertNotIn("keys.length > 600", worker)
        self.assertNotIn("keys.length - 500", worker)

    def test_mobile_operations_ui_has_mockup_parity_contracts(self) -> None:
        styles = UI_STYLES.read_text(encoding="utf-8")
        worker = SERVICE_WORKER.read_text(encoding="utf-8")
        for marker in (
            'href="assets/viptrack-ui.css"',
            "createAppBar()",
            "createMapChrome()",
            "mobile-map-peek",
            "mobile-page-panel",
            "mobileListSearch",
            'data-list-category="government"',
            "<span>Aircraft</span>",
            "watch-overview",
            "toggleWatchAlerts(hex)",
            "mobileSettingsSearch",
            "data-settings-group",
            "Local-first • credentials stay on this device",
            "Configure your flight deck",
            "function seedAndroidQaWorkspace()",
            "Loading QA flight deck...",
            "trustedTypes.createPolicy('default'",
            "RETURN_TRUSTED_TYPE: false",
        ):
            self.assertIn(marker, self.source)
        for marker in (
            "--accent: #21d4b4",
            ".mobile-app-bar",
            ".mobile-bottom-nav",
            ".mobile-map-peek",
            ".list-aircraft-item",
            ".watch-card",
            ".mobile-settings-categories",
            "IMAGEGEN FLIGHT DECK V2",
            "--deck-cyan: #28dfc1",
            "@media (max-width: 767.98px), (pointer: coarse) and (max-height: 767.98px)",
            "--mobile-safe-bottom: max(var(--mobile-nav-gap), env(safe-area-inset-bottom, 0px))",
            "--mobile-nav-clearance: calc(var(--mobile-nav-height) + var(--mobile-safe-bottom) + var(--mobile-nav-gap))",
        ):
            self.assertIn(marker, styles)
        for marker in (
            "const isPhoneViewport = window.matchMedia(",
            "(max-width: 767.98px), (pointer: coarse) and (max-height: 767.98px)",
            "this.isMobile = false",
            "this.isTablet = false",
            'assets/logo/VIPTrack_Mark-128x128.png',
        ):
            self.assertIn(marker, self.source)
        self.assertIn("'assets/viptrack-ui.css'", worker)
        sanitizer_url = next(d["url"] for d in json.loads(
            (ROOT / "tools" / "cdn_dependencies.json").read_text(encoding="utf-8"))["dependencies"]
            if d["id"] == "dompurify-js")
        self.assertLess(self.source.index(sanitizer_url),
                        self.source.index('leaflet/1.9.4/leaflet.js', self.source.index('<body>')))
        for page in ("map", "list", "watch", "settings"):
            mockup = UI_MOCKUPS / f"viptrack-{page}.png"
            self.assertTrue(mockup.is_file(), mockup)
            self.assertGreater(mockup.stat().st_size, 100_000)
        imagegen_board = UI_MOCKUPS / "viptrack-flightdeck-v2-board.png"
        self.assertTrue(imagegen_board.is_file(), imagegen_board)
        self.assertGreater(imagegen_board.stat().st_size, 1_000_000)

    def test_periodic_background_sync_refreshes_public_reference_data_only(self) -> None:
        worker = SERVICE_WORKER.read_text(encoding="utf-8")
        for marker in (
            "const SW_PERIODIC_SYNC_TAG = 'viptrack-watchlist-refresh'",
            "const SW_PERIODIC_SYNC_MIN_INTERVAL_MS = 12 * 60 * 60 * 1000",
            "registration.periodicSync",
            "periodicSync.register",
            "const PERIODIC_SYNC_TAG =",
            "const PERIODIC_REFRESH_ASSETS =",
            "async function refreshPeriodicAssets()",
            "self.addEventListener('periodicsync'",
            "event.tag !== PERIODIC_SYNC_TAG",
            "credentials: 'omit'",
            "cache.put(request, response.clone())",
        ):
            self.assertIn(marker, self.source + worker)
        for filename in (
            "plane-alert-mil.csv",
            "plane-alert-gov.csv",
            "plane-alert-pol.csv",
            "plane-alert-pia.csv",
        ):
            self.assertGreaterEqual(worker.count(filename), 2)
        self.assertNotIn("fetchWithProxy", worker)
        self.assertNotIn("localStorage", worker)
        self.assertNotIn("navigator.geolocation", worker)

    def test_cesium_globe_is_opt_in_lazy_loaded_and_synced(self) -> None:
        # The frame has to load exactly the build the inventory pins, whatever that
        # version is; restating the URL here pinned the test to one release.
        inventory = json.loads((ROOT / "tools" / "cdn_dependencies.json").read_text(encoding="utf-8"))
        frame_source = CESIUM_FRAME.read_text(encoding="utf-8")
        for dep_id in ("cesium-js", "cesium-css"):
            dep = next(d for d in inventory["dependencies"] if d["id"] == dep_id)
            self.assertIn(dep["url"], frame_source)
            self.assertIn(dep["integrity"], frame_source)
        frame_source = CESIUM_FRAME.read_text(encoding="utf-8")
        for marker in (
            "?3d=1",
            "urlParams.get('3d') === '1'",
            "const cesium3DManager =",
            "CESIUM_VERSION = '1.143'",
            "CESIUM_JS_INTEGRITY",
            "CESIUM_CSS_INTEGRITY",
            "frame.setAttribute('sandbox', 'allow-scripts allow-same-origin')",
            "new URL('cesium-frame.html', document.baseURI).href",
            "new Cesium.Viewer(frameDocument",
            "new Cesium.OpenStreetMapImageryProvider",
            "Cesium.Cartesian3.fromDegrees",
            "entityByHex: new Map()",
            "this.viewer.entities.suspendEvents()",
            "cesium3DManager.sync();",
            "body.cesium-3d-mode",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("Cesium.Ion.defaultAccessToken", self.source)
        parent_csp = re.search(
            r'<meta http-equiv="Content-Security-Policy" content="([\s\S]*?)">',
            self.source,
            flags=re.IGNORECASE,
        )
        self.assertIsNotNone(parent_csp)
        self.assertNotIn("'unsafe-eval'", parent_csp.group(1))
        self.assertNotRegex(self.source, r'<script[^>]+src="[^"]*Cesium\.js"')
        for marker in (
            "script-src 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",
            "window.CESIUM_BASE_URL",
            'crossorigin="anonymous"',
        ):
            self.assertIn(marker, frame_source)
        frame_csp = re.search(
            r'<meta http-equiv="Content-Security-Policy" content="([\s\S]*?)">',
            frame_source,
            flags=re.IGNORECASE,
        )
        self.assertIsNotNone(frame_csp)
        self.assertIn("'unsafe-eval'", frame_csp.group(1))

    def test_webgl_renderer_is_opt_in_and_uses_gpu_layers(self) -> None:
        for marker in (
            "?renderer=webgl",
            "urlParams.get('renderer') === 'webgl'",
            "const webglMapManager =",
            "MAPLIBRE_VERSION = '5.24.0'",
            "DECKGL_VERSION = '9.2.1'",
            "WEBGL_MAP_STYLE",
            "new maplibregl.Map",
            "new deck.MapboxOverlay",
            "new IconLayer",
            "new TripsLayer",
            "getPath: trip => trip.path",
            "getTimestamps: trip => trip.timestamps",
            "webglMapManager.sync();",
            "body.webgl-mode",
            "script.integrity = integrity",
            "link.integrity = MAPLIBRE_CSS_INTEGRITY",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("maplibregl.Map({ container: _el('map')", self.source)
        self.assertIn("MAPLIBRE_JS_INTEGRITY = 'sha512-", self.source)
        self.assertIn("MAPLIBRE_CSS_INTEGRITY = 'sha512-", self.source)
        self.assertIn("DECKGL_JS_INTEGRITY = 'sha512-", self.source)
        self.assertNotIn("'unsafe-eval'", re.search(
            r'<meta http-equiv="Content-Security-Policy" content="([\s\S]*?)">',
            self.source,
            flags=re.IGNORECASE,
        ).group(1))

    def test_maplibre_vector_basemap_option_is_opt_in_and_attributed(self) -> None:
        for marker in (
            "const MAPLIBRE_VECTOR_STYLES =",
            "'carto-voyager'",
            "'stadia-alidade-smooth-dark'",
            "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
            "https://tiles.stadiamaps.com/styles/alidade_smooth_dark.json",
            "supportsBasemap(key)",
            "styleFor(key = settings.mapStyle)",
            "async setBasemap(key, announce = true)",
            "renderer.once('style.load'",
            "id=\"basemapStyle\"",
            "?renderer=webgl&basemap=",
            "attribution remains visible",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const MAPLIBRE_VECTOR_STYLES =")
        end = self.source.index("async function fetchWithProxy", start)
        section = self.source[start:end]
        self.assertNotIn("api_key", section)
        self.assertIn("this.renderer.setStyle(style)", section)
        self.assertIn("saveSettings()", section)

    def test_hand_maintained_sources_stay_on_lf_endings(self) -> None:
        """Guard against Windows tooling silently rewriting a whole file.

        `pathlib.Path.write_text` translates LF to CRLF on Windows, and with
        `core.autocrlf=false` git stores that literally -- a one-key edit to a JSON
        catalog or a one-entry CHANGELOG addition turns into a whole-file diff that
        buries the real change. The vendored trees under `data/` (upstream CSVs, FAA
        shards) are CRLF as shipped and deliberately not covered here.
        """
        tracked = [
            ROOT / "index.html", ROOT / "sw.js", ROOT / "cesium-frame.html",
            ROOT / "manifest.json", ROOT / "_headers",
            ROOT / "README.md", ROOT / "CHANGELOG.md",
            UI_STYLES, PLUGINS_MANIFEST, OPFS_WORKER,
            ROOT / "tools" / "cdn_dependencies.json",
        ]
        tracked += sorted(I18N_DIR.glob("*.json"))
        tracked += [
            ROOT / "tools" / name for name in (
                "test_viptrack.py", "test_runtime.py", "check_cdn_dependencies.py",
                "check_security_headers.py", "build_basemap_pmtiles.py",
                "build_faa_registry.py", "refresh_reference_data.py",
            )
        ]
        offenders = [
            path.relative_to(ROOT).as_posix()
            for path in tracked
            if path.is_file() and CRLF in path.read_bytes()
        ]
        self.assertEqual(offenders, [], "CRLF crept into hand-maintained sources")

    def test_csp_blocked_egress_is_explained_not_swallowed(self) -> None:
        # connect-src is a strict allowlist, so webhook / overlay / receiver targets
        # are refused by policy and fetch() reports a bare "Failed to fetch".
        for marker in (
            "const cspWatch = {",
            "securitypolicyviolation",
            "async describeFailure(url, fallback)",
            "mixedContentNote(url)",
            "await cspWatch.describeFailure(",
        ):
            self.assertIn(marker, self.source)

        start = self.source.index("const cspWatch = {")
        section = self.source[start:self.source.index("async function readBoundedResponseText", start)]
        # Only connect-src refusals may be reported this way; other directives would
        # produce a misleading "add this host" instruction.
        self.assertIn("effectiveDirective !== 'connect-src'", section)
        # The violation arrives after the fetch rejects, so a synchronous read races it.
        self.assertIn("await new Promise(resolve => setTimeout(resolve, 10))", section)
        # An unblocked host must keep the caller's own wording.
        self.assertIn("return this.explain(url) || fallback;", section)

        # Every user-configured egress feature explains itself.
        self.assertEqual(self.source.count("await cspWatch.describeFailure("), 3)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Allowlisting your own hosts", readme)
        self.assertIn("mixed content", readme.lower())

    def test_no_url_builder_names_a_privacy_protected_aircraft(self) -> None:
        # buildViewUrl was guarded; buildUrl (address bar) and generateLink (Share
        # Flight) were not, so two of three builders leaked the identity they exist
        # to protect.
        start = self.source.index("const shareManager = {")
        section = self.source[start:self.source.index("async createTrailPng(hex)", start)]
        self.assertIn("if (hex && !isPrivacyProtectedAircraft(aircraftCache[hex])) params.set('hex', hex);", section)
        self.assertIn("const privacyProtected = isPrivacyProtectedAircraft(ac);", section)
        # generateLink must withhold the position too - a PIA position plus a map
        # link is the same disclosure by another route.
        link_start = section.index("generateLink(hex) {")
        link_section = section[link_start:section.index("_collectTrailPoints(hex)", link_start)]
        self.assertIn("if (!privacyProtected) {", link_section)
        # Both the identity and the position must sit inside the guard, and the guard
        # must come first -- an unguarded set before it would leak regardless.
        guard = link_section.index("if (!privacyProtected) {")
        self.assertLess(guard, link_section.index("params.set('hex', hex)"))
        self.assertLess(guard, link_section.index("params.set('lat'"))
        self.assertLess(guard, link_section.index("params.set('lon'"))

    def test_visibility_is_parsed_from_the_text_the_api_sends(self) -> None:
        # aviationweather.gov sends visibility as text ("10+", "1/2", "1 1/2"), not a
        # number. Comparing those strings numerically is always false, so the flight
        # category silently fell through to VFR -- including for half-mile, which is
        # LIFR. Runtime coverage lives in test_runtime.py; this pins the helper.
        for marker in (
            "visibilityMiles(value) {",
            "const vis = this.visibilityMiles(data?.visib);",
            "const ceil = this.getCeiling(data?.clouds);",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("visibilityMiles(value) {")
        section = self.source[start:self.source.index("getFlightCategory(data) {", start)]
        # Mixed numbers and bare fractions both appear in real payloads.
        self.assertIn("\s+", section)
        self.assertIn("denominator", section)
        self.assertIn("Number.isFinite(number) ? number : null", section)

    def test_coverage_view_is_local_aggregated_and_pia_redacted(self) -> None:
        for marker in (
            "const COVERAGE_MODES = ['off', 'density', 'tracks']",
            "const COVERAGE_WINDOW_HOURS = [1, 6, 24, 168]",
            "const COVERAGE_INTERVAL_SECONDS = [15, 30, 60, 300]",
            "const coverageRecorder = {",
            "const coverageView = {",
            "async saveTrailPoints(points)",
            "async streamTrailHistory(since, onRecord",
            "async clearTrailHistory()",
            "id=\"coverageMode\"",
            "id=\"coverageWindow\"",
            "id=\"coverageInterval\"",
            "id=\"coverageClearBtn\"",
            "coverageView.applyUrlState(params)",
            "coverageView.writeUrlState(params)",
        ):
            self.assertIn(marker, self.source)

        recorder = self.source[self.source.index("const coverageRecorder = {"):self.source.index("const coverageView = {")]
        # Redaction at write time: the store must never hold a PIA position at all.
        self.assertIn("if (!ac || isPrivacyProtectedAircraft(ac)) continue;", recorder)
        # Sampling, not mirroring - an unchanged position writes nothing.
        self.assertIn("if (previous && previous[0] === lat && previous[1] === lon) continue;", recorder)

        view = self.source[self.source.index("const coverageView = {"):self.source.index("// ============ X3: PLANE-ALERT-DB")]
        # Redaction again at read time, because the store may predate a hex being PIA.
        self.assertIn("isPrivacyProtectedHex(hex) || isPrivacyProtectedAircraft(aircraftCache[hex])", view)
        # Aggregate during the walk; never materialise the raw window.
        self.assertIn("streamTrailHistory(since", view)
        self.assertIn("COVERAGE_POINT_LIMIT", view)
        self.assertIn("cells.set(key,", view)
        self.assertNotIn("getAll(", view)
        # Local only: nothing about this view may reach the network.
        for forbidden in ("fetch(", "XMLHttpRequest", "http://", "https://"):
            self.assertNotIn(forbidden, view)

    def test_self_hosted_pmtiles_basemap_is_same_origin_and_uncommitted(self) -> None:
        for marker in (
            "const PMTILES_JS_URL =",
            "const PMTILES_BASEMAP_KEY = 'pmtiles-dark'",
            "const PMTILES_DEFAULT_PATH = 'data/basemap/basemap.pmtiles'",
            "maplibregl.addProtocol('pmtiles'",
            "'pmtiles://' + this.archiveUrl()",
            "id=\"basemapPmtilesOption\"",
            "id=\"pmtilesPath\"",
            "'pmtiles-dark'",
        ):
            self.assertIn(marker, self.source)

        start = self.source.index("const pmtilesBasemap = {")
        section = self.source[start:self.source.index("const webglMapManager = {", start)]
        # Any scheme, protocol-relative URL, or traversal must be refused: connect-src
        # is a real allowlist, so a cross-origin archive would be blocked anyway, and
        # accepting one would put an arbitrary host into the style at runtime.
        self.assertIn("if (/^[a-z][a-z0-9+.-]*:/i.test(value)) return false;", section)
        self.assertIn("if (value.startsWith('//') || value.startsWith('/')) return false;", section)
        self.assertIn("if (value.split('/').includes('..')) return false;", section)
        self.assertIn("'PMTiles'", section)  # magic-byte probe, not a bare response.ok

        # The archive is a rebuildable binary; committing it would grow git history by
        # its full size on every refresh.
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/basemap/", gitignore)
        self.assertFalse((ROOT / "data" / "basemap" / "basemap.pmtiles").exists() and
                         not any(line.strip() == "data/basemap/" for line in gitignore.splitlines()))

        builder = (ROOT / "tools" / "build_basemap_pmtiles.py").read_text(encoding="utf-8")
        for marker in ("DEFAULT_MAXZOOM = 6", "SIZE_BUDGET_MB", "--allow-large", "Refusing maxzoom"):
            self.assertIn(marker, builder)

        # The point of the lane is removing third-party basemap hosts, so it must not
        # smuggle one back in via glyphs or sprites.
        for smuggled in ("glyphs", "sprite", "protomaps.github.io", "https://"):
            self.assertNotIn(smuggled, section[section.index("style() {"):])

    def test_cesium_playback_uses_trace_samples_and_scrubber(self) -> None:
        for marker in (
            "id=\"cesiumPlayback\"",
            "id=\"cesiumPlaybackSlider\"",
            "id=\"cesiumPlaybackPlay\"",
            "loadHistoricalTrace(hex, { ...data, trace: filtered })",
            "_normaliseTrace(data)",
            "new Cesium.SampledPositionProperty()",
            "new Cesium.VelocityOrientationProperty(position)",
            "new Cesium.TimeIntervalCollection",
            "this.viewer.clock.currentTime",
            "Cesium.ClockRange.CLAMPED",
            "setPlaybackTime(seconds)",
            "togglePlayback()",
            "stepPlayback(seconds)",
            "cesiumPlaybackSlider')?.addEventListener('input'",
            "if (cesium3DManager.requested) cesium3DManager.clearPlayback(false)",
        ):
            self.assertIn(marker, self.source)
        # globe.airplanes.live answers 403 through every relay, so remote traces are
        # disabled and playback falls back to the locally recorded trail. traceUrl
        # stays as the switch that re-enables them if a reachable host appears.
        self.assertIn("traceUrl: null", self.source)
        self.assertIn("const endpoints = CONFIG.traceUrl ?", self.source)
        self.assertNotIn("globe.airplanes.live/data/traces", self.source)
        self.assertNotIn("globe.airplanes.live/aircraft_sil", self.source)
        self.assertNotIn("globe.airplanes.live/airline_banners", self.source)
        self.assertIn("trace_full_' + hexLower + '.json", self.source)
        self.assertIn("trace_recent_' + hexLower + '.json", self.source)


if __name__ == "__main__":
    unittest.main()
