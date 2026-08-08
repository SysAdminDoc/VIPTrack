#!/usr/bin/env python3
"""Static deployment-header and Trusted Types contract checks."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADERS = ROOT / "_headers"
INDEX = ROOT / "index.html"


class SecurityHeaderGateError(RuntimeError):
    """Raised when deployment security contracts are missing or unsafe."""


def _header_blocks() -> dict[str, dict[str, str]]:
    blocks: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw_line in HEADERS.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(" "):
            current = line
            blocks[current] = {}
            continue
        if current and ":" in line:
            name, value = line.strip().split(":", 1)
            blocks[current][name] = value.strip()
    return blocks


def run_gate() -> dict[str, int]:
    errors: list[str] = []
    if not HEADERS.is_file():
        raise SecurityHeaderGateError("_headers policy file is missing")
    blocks = _header_blocks()
    common = blocks.get("/*", {})
    for header in ("Strict-Transport-Security", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy", "X-Frame-Options"):
        if not common.get(header):
            errors.append(f"common response header is missing: {header}")
    index_headers = blocks.get("/index.html", {})
    frame_headers = blocks.get("/cesium-frame.html", {})
    for path, headers in (("/index.html", index_headers), ("/cesium-frame.html", frame_headers)):
        if "Content-Security-Policy-Report-Only" not in headers:
            errors.append(f"{path}: Report-Only CSP is missing")
        if "Content-Security-Policy" not in headers:
            errors.append(f"{path}: enforcing CSP is missing")
        csp = headers.get("Content-Security-Policy", "")
        for directive in ("object-src 'none'", "base-uri", "frame-ancestors 'self'"):
            if directive not in csp:
                errors.append(f"{path}: CSP is missing {directive}")
    index_csp = index_headers.get("Content-Security-Policy", "")
    for directive in ("trusted-types viptrack", "require-trusted-types-for 'script'"):
        if directive not in index_csp:
            errors.append(f"/index.html: CSP is missing {directive}")
    if "'unsafe-eval'" in index_csp:
        errors.append("/index.html: enforcing CSP must not allow unsafe-eval")
    frame_csp = frame_headers.get("Content-Security-Policy", "")
    if "'unsafe-eval'" not in frame_csp:
        errors.append("/cesium-frame.html: Cesium-compatible unsafe-eval allowance is missing")

    source = INDEX.read_text(encoding="utf-8")
    for marker in (
        "trustedTypes.createPolicy('viptrack'",
        "const SAFE_HTML_OPTIONS",
        "window.DOMPurify.sanitize",
        "escapeHTML(markup)",
        "require-trusted-types-for 'script'",
        "location.protocol === 'file:'",
        "urlParams.get('3d') === '1'",
        "urlParams.get('renderer') === 'webgl'",
        "navigator.share",
        "document.body.insertAdjacentHTML('beforeend', safeHTML(html))",
    ):
        if marker not in source:
            errors.append(f"index.html is missing security/mode marker: {marker}")
    for line_number, line in enumerate(source.splitlines(), 1):
        if re.search(r"\b(?:innerHTML|outerHTML)\s*=|insertAdjacentHTML\(", line) and "safeHTML(" not in line:
            errors.append(f"index.html:{line_number}: dynamic HTML sink bypasses safeHTML")
        if any(sink in line for sink in (".bindPopup(", ".bindTooltip(", ".setContent(")) and "safeHTML(" not in line:
            errors.append(f"index.html:{line_number}: Leaflet/HTML sink bypasses safeHTML")
    if errors:
        raise SecurityHeaderGateError("\n".join(errors))
    return {"headerBlocks": len(blocks), "checkedSinks": len(source.splitlines())}


if __name__ == "__main__":
    try:
        summary = run_gate()
    except SecurityHeaderGateError as exc:
        print(f"Security-header gate failed:\n{exc}")
        raise SystemExit(1)
    print(f"Security-header gate passed: {summary['headerBlocks']} header blocks, {summary['checkedSinks']} source lines")
