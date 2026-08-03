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


if __name__ == "__main__":
    unittest.main()
