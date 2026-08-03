#!/usr/bin/env python3
"""Static contract tests for the zero-build VIPTrack document."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
