#!/usr/bin/env python3
"""Static contract tests for the zero-build VIPTrack document."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CESIUM_FRAME = ROOT / "cesium-frame.html"
FAA_DIR = ROOT / "data" / "faa"
PLUGINS_MANIFEST = ROOT / "plugins" / "manifest.json"
I18N_DIR = ROOT / "data" / "i18n"
OPFS_WORKER = ROOT / "workers" / "registration-opfs-worker.js"
WEB_MANIFEST = ROOT / "manifest.json"
TWA_DIR = ROOT / "android"
TYPE_PHOTO_DOWNLOADER = ROOT / "download-type-photos.py"
TYPE_PHOTO_WORKFLOW = ROOT / "tools" / "run_type_photo_enrichment.ps1"


class VipTrackContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = INDEX.read_text(encoding="utf-8")
        cls.lines = cls.source.splitlines()

    def test_pinned_cdn_resources_have_sri(self) -> None:
        resources = re.findall(
            r"<(?:script|link)\b[^>]*(?:src|href)=\"(https://cdnjs\.cloudflare\.com/[^\"]+)\"[^>]*>",
            self.source,
            flags=re.IGNORECASE,
        )
        self.assertGreaterEqual(len(resources), 6)
        for match in re.finditer(
            r"<(?:script|link)\b[^>]*(?:src|href)=\"https://cdnjs\.cloudflare\.com/[^\"]+\"[^>]*>",
            self.source,
            flags=re.IGNORECASE,
        ):
            self.assertRegex(match.group(0), r'\bintegrity="sha512-[^"]+"')
            self.assertRegex(match.group(0), r'\bcrossorigin="anonymous"')

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
        self.assertEqual(manifest["schemaVersion"], 1)
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
        for marker in (
            "const pluginManifestManager =",
            "plugins/manifest.json",
            "entry.requiresOptIn !== true",
            "url.origin === location.origin",
            "await import(url.href)",
            "id=\"pluginManifestList\"",
            "pluginManifestManager.init();",
        ):
            self.assertIn(marker, self.source)

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

    def test_static_manifest_supports_pwa_twa_and_share_target(self) -> None:
        manifest = json.loads(WEB_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "./")
        self.assertEqual(manifest["scope"], "./")
        self.assertEqual(manifest["start_url"], "./index.html")
        self.assertEqual(manifest["display"], "standalone")
        self.assertIn("standalone", manifest["display_override"])
        self.assertEqual(manifest["share_target"]["method"], "GET")
        self.assertEqual(manifest["share_target"]["params"], {"title": "title", "text": "text", "url": "url"})
        for icon in manifest["icons"]:
            self.assertTrue((ROOT / icon["src"]).is_file(), icon["src"])
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

    def test_twa_project_is_production_scoped_and_unsigned_by_default(self) -> None:
        twa_manifest = json.loads((TWA_DIR / "twa-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(twa_manifest["packageId"], "com.sysadmindoc.viptrack")
        self.assertEqual(twa_manifest["host"], "sysadmindoc.github.io")
        self.assertEqual(twa_manifest["startUrl"], "/VIPTrack/index.html")
        self.assertEqual(twa_manifest["webManifestUrl"], "https://sysadmindoc.github.io/VIPTrack/manifest.json")
        self.assertEqual(twa_manifest["fullScopeUrl"], "https://sysadmindoc.github.io/VIPTrack/")
        self.assertEqual(twa_manifest["signingKey"], {"path": "", "alias": ""})
        self.assertEqual(twa_manifest["shareTarget"]["action"], "https://sysadmindoc.github.io/VIPTrack/index.html")
        self.assertTrue((TWA_DIR / "gradlew.bat").is_file())
        build_gradle = (TWA_DIR / "app" / "build.gradle").read_text(encoding="utf-8")
        for marker in (
            "hostName: 'sysadmindoc.github.io'",
            "launchUrl: '/VIPTrack/index.html'",
            "https://sysadmindoc.github.io/VIPTrack/manifest.json",
            "https://sysadmindoc.github.io/VIPTrack/index.html",
        ):
            self.assertIn(marker, build_gradle)
        self.assertNotIn("127.0.0.1", build_gradle)
        self.assertNotIn("debug.keystore", build_gradle)

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
        for marker in (
            "const openSkyHistoricalManager =",
            "OpenSky Historical Replay (X20)",
            "auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
            "grant_type: 'client_credentials'",
            "opensky-network.org/api/tracks/all",
            "openSkyLoadBtn",
            "No historical track loaded",
            "this._timestamp",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("const openSkyHistoricalManager =")
        end = self.source.index("// ============ X5: LOCAL GEOFENCE EDITOR", start)
        section = self.source[start:end]
        self.assertNotIn("setInterval", section)
        self.assertNotIn("fetchWithProxy", section)
        self.assertIn("clientSecretInput.value = ''", section)
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

    def test_service_worker_hashes_manifest_expires_api_cache_and_evictions_lru_tiles(self) -> None:
        for marker in (
            "const SW_CACHE_SCHEMA = '4.17'",
            "crypto.subtle.digest('SHA-256'",
            "const swManifestHash = await getServiceWorkerManifestHash",
            "'viptrack-' + SW_CACHE_SCHEMA + '-' + swManifestHash.slice(0, 16)",
            "const API_CACHE_TTL_MS = 60000",
            "X-VIPTrack-Cached-At",
            "const TILE_CACHE_LIMIT = 1000",
            "X-VIPTrack-Tile-Last-Used",
            "entries.sort((a, b) => a.lastUsed - b.lastUsed)",
        ):
            self.assertIn(marker, self.source)
        start = self.source.index("// Service Worker Registration")
        end = self.source.index("</script>", start)
        section = self.source[start:end]
        self.assertNotIn("keys.length > 600", section)
        self.assertNotIn("keys.length - 500", section)

    def test_periodic_background_sync_refreshes_public_reference_data_only(self) -> None:
        for marker in (
            "const SW_PERIODIC_SYNC_TAG = 'viptrack-watchlist-refresh'",
            "const SW_PERIODIC_SYNC_MIN_INTERVAL_MS = 12 * 60 * 60 * 1000",
            "const SW_PERIODIC_REFRESH_ASSETS = [",
            "periodicAssets: SW_PERIODIC_REFRESH_ASSETS",
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
            self.assertIn(marker, self.source)
        for filename in (
            "plane-alert-mil.csv",
            "plane-alert-gov.csv",
            "plane-alert-pol.csv",
            "plane-alert-pia.csv",
        ):
            self.assertGreaterEqual(self.source.count(filename), 2)
        start = self.source.index("// Service Worker Registration")
        end = self.source.index("</script>", start)
        section = self.source[start:end]
        self.assertNotIn("fetchWithProxy", section)
        self.assertNotIn("localStorage", section)
        self.assertNotIn("navigator.geolocation", section)

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
