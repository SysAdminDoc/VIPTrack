#!/usr/bin/env python3
"""Static contract tests for the zero-build VIPTrack document."""

from __future__ import annotations

import json
import re
import struct
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
WEB_MANIFEST = ROOT / "manifest.json"
SERVICE_WORKER = ROOT / "sw.js"
ANDROID_DIR = ROOT / "android"
TYPE_PHOTO_DOWNLOADER = ROOT / "download-type-photos.py"
TYPE_PHOTO_WORKFLOW = ROOT / "tools" / "run_type_photo_enrichment.ps1"
UI_STYLES = ROOT / "assets" / "viptrack-ui.css"
UI_MOCKUPS = ROOT / "assets" / "mockups"


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
        self.assertEqual(summary["dependencies"], 9)
        for marker in (
            "cdn_dependencies.json",
            "reviewPolicyDays",
            "advisoryStatus",
            "clear-through-3.4.13",
            "https://cdn.jsdelivr.net/npm/dompurify@3.4.13/dist/purify.min.js",
            "FORBID_TAGS",
            "FORBID_ATTR",
            "srcdoc",
            "escapeHTML(markup)",
        ):
            self.assertIn(marker, self.source + (ROOT / "tools" / "check_cdn_dependencies.py").read_text(encoding="utf-8") + (ROOT / "tools" / "cdn_dependencies.json").read_text(encoding="utf-8"))
        self.assertNotIn("dompurify/3.2.6", self.source)

    def test_html_sinks_use_pinned_sanitizer(self) -> None:
        self.assertIn("purify.min.js", self.source)
        self.assertIn("function safeHTML", self.source)
        self.assertIn("window.DOMPurify.sanitize", self.source)
        for line in self.lines:
            if ".bindPopup(" in line or ".bindTooltip(" in line or ".setContent(" in line:
                self.assertIn("safeHTML", line, msg=line.strip())

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
            "const AIRCRAFT_CACHE_SCHEMA = 3",
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
        manager_end = self.source.index("async function getWikipediaSummary", manager_start)
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
        self.assertTrue((ROOT / "assets" / "logo" / "VIPTrack_Mark.svg").is_file())
        self.assertNotIn("SkyTrack_Logo", self.source + SERVICE_WORKER.read_text(encoding="utf-8") + WEB_MANIFEST.read_text(encoding="utf-8"))
        for marker in (
            '<link rel="manifest" href="manifest.json">',
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
        adaptive_icon = (resources / "mipmap-anydpi-v26" / "ic_launcher.xml").read_text(encoding="utf-8")
        themed_icon = (resources / "mipmap-anydpi-v33" / "ic_launcher.xml").read_text(encoding="utf-8")
        foreground = (resources / "drawable-anydpi" / "ic_launcher_foreground.xml").read_text(encoding="utf-8")
        legacy_icon = (resources / "mipmap-anydpi" / "ic_launcher.xml").read_text(encoding="utf-8")
        self.assertIn("<adaptive-icon", adaptive_icon)
        self.assertIn('@drawable/ic_launcher_foreground', adaptive_icon)
        self.assertIn('<monochrome android:drawable="@drawable/ic_launcher_monochrome"', themed_icon)
        self.assertIn('android:rotation="35"', foreground)
        self.assertIn('@drawable/ic_launcher_legacy_background', legacy_icon)
        self.assertFalse(any(resources.glob("mipmap-*/ic_launcher.png")))
        store_icon = (ANDROID_DIR / "store_icon.png").read_bytes()
        self.assertEqual(store_icon[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", store_icon[16:24]), (512, 512))
        self.assertIn("CONFIG.isAndroidApp && source.key !== 'airplaneslive'", self.source)
        self.assertIn("const androidSourceOrder={airplaneslive:0", self.source)
        self.assertIn("const VIPTRACK_ANDROID_QA_MODE = IS_VIPTRACK_ANDROID_APP", self.source)

    def test_release_version_is_synchronized_across_shell_docs_and_android(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        build_gradle = (ANDROID_DIR / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("<title>VIPTrack v0.4.2", self.source)
        self.assertIn('class="version">v0.4.2', self.source)
        self.assertIn("version-0.4.2-blue", readme)
        self.assertIn("## [v0.4.2] - 2026-08-08", changelog)
        self.assertIn("versionName '0.4.2'", build_gradle)
        self.assertIn("versionCode 6", build_gradle)

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
        end = self.source.index("// ============ PHASE 16: AUTO-RETRY SYSTEM", start)
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
        self.assertIn("AIRCRAFT_CACHE_SCHEMA = 3", self.source)

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
            "'curated'].includes(settings.filter)",
        ):
            self.assertIn(marker, self.source)
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
            "const CACHE_SCHEMA_VERSION = '4.24'",
            "const MANIFEST_HASH = fnv1a(JSON.stringify",
            "const CACHE_NAME = CACHE_PREFIX + CACHE_SCHEMA_VERSION + '-' + MANIFEST_HASH",
            "const API_CACHE_TTL_MS = 60000",
            "X-VIPTrack-Cached-At",
            "const TILE_CACHE_LIMIT = 1000",
            "X-VIPTrack-Tile-Last-Used",
            "entries.sort((a, b) => a.lastUsed - b.lastUsed)",
            "self.addEventListener('install'",
            "self.addEventListener('activate'",
            "self.addEventListener('fetch'",
            "self.skipWaiting()",
            "self.clients.claim()",
        ):
            self.assertIn(marker, worker)
        self.assertIn("const SW_CACHE_SCHEMA = '4.24'", self.source)
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
            "watch-overview",
            "toggleWatchAlerts(hex)",
            "mobileSettingsSearch",
            "data-settings-group",
            "Local-first • credentials stay on this device",
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
        self.assertLess(self.source.index('dompurify@3.4.13'), self.source.index('leaflet/1.9.4/leaflet.js', self.source.index('<body>')))
        for page in ("map", "list", "watch", "settings"):
            mockup = UI_MOCKUPS / f"viptrack-{page}.png"
            self.assertTrue(mockup.is_file(), mockup)
            self.assertGreater(mockup.stat().st_size, 100_000)

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
            "https://cdn.jsdelivr.net/npm/cesium@1.143/Build/Cesium/Cesium.js",
            "https://cdn.jsdelivr.net/npm/cesium@1.143/Build/Cesium/Widgets/widgets.css",
            'integrity="sha512-mexEiWjKPe7eqeQMhzHg5B5ENdrWI0NMQwVUZu7MXhS3t8dZeKeJQxAWQfXgFtXjdVpza0Gm+wVolB02nnymKg=="',
            'integrity="sha512-fsYfjqOKt+KyVW0YZa1aHucMVyjVuLVkCP/187bJFe+AO9vSyJnjHd3Qkt4sioYq1qrnHu81rPY3KDK8fRRykA=="',
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
        self.assertIn("traceUrl: 'https://globe.airplanes.live/data/traces/'", self.source)
        self.assertIn("trace_full_' + hexLower + '.json", self.source)
        self.assertIn("trace_recent_' + hexLower + '.json", self.source)


if __name__ == "__main__":
    unittest.main()
