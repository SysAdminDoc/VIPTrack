#!/usr/bin/env python3
"""Static contract tests for the zero-build VIPTrack document."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"


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

    def test_csp_covers_tfr_mirror(self) -> None:
        self.assertIn("https://tfr2go.com", self.source)

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
            "const SW_CACHE_SCHEMA = '4.16'",
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


if __name__ == "__main__":
    unittest.main()
