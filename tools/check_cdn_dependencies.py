#!/usr/bin/env python3
"""Fail-closed inventory, SRI, license, and advisory checks for CDN assets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CESIUM_FRAME = ROOT / "cesium-frame.html"
INVENTORY = ROOT / "tools" / "cdn_dependencies.json"
MAX_SRI_BYTES = 128 * 1024 * 1024
EXTERNAL_ASSET_RE = re.compile(r"<(script|link)\b([^>]*)>", re.IGNORECASE | re.DOTALL)
ATTRIBUTE_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*([\"'])(.*?)\2", re.DOTALL)
SRI_RE = re.compile(r"^sha512-[A-Za-z0-9+/]{86}==$")
SEVERITY_BLOCKERS = ("unknown", "vulnerable", "stale", "pending", "unreviewed")


class DependencyGateError(RuntimeError):
    """Raised when the release dependency contract is not satisfied."""


def _attrs(raw: str) -> dict[str, str]:
    return {match.group(1).lower(): match.group(3) for match in ATTRIBUTE_RE.finditer(raw)}


def _load_inventory() -> dict:
    try:
        payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyGateError(f"cannot read dependency inventory: {exc}") from exc
    if payload.get("schemaVersion") != 1:
        raise DependencyGateError("dependency inventory schemaVersion must be 1")
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise DependencyGateError("dependency inventory has no dependencies")
    return payload


def _validate_inventory(payload: dict, today: date) -> list[str]:
    errors: list[str] = []
    dependencies = payload["dependencies"]
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    try:
        review_policy_days = int(payload["reviewPolicyDays"])
    except (KeyError, TypeError, ValueError):
        review_policy_days = 0
    if review_policy_days <= 0:
        errors.append("reviewPolicyDays must be positive")

    for entry in dependencies:
        identifier = entry.get("id", "<missing id>")
        if identifier in seen_ids:
            errors.append(f"{identifier}: duplicate id")
        seen_ids.add(identifier)
        required = ("id", "kind", "name", "version", "url", "integrity", "license", "source", "advisorySource", "advisoryStatus", "reviewedAt")
        for field in required:
            if not entry.get(field):
                errors.append(f"{identifier}: missing {field}")
        url = entry.get("url", "")
        if url in seen_urls:
            errors.append(f"{identifier}: duplicate URL")
        seen_urls.add(url)
        if not url.startswith("https://"):
            errors.append(f"{identifier}: dependency URL must use HTTPS")
        if not entry.get("source", "").startswith("https://"):
            errors.append(f"{identifier}: source must use HTTPS")
        if not entry.get("advisorySource", "").startswith("https://"):
            errors.append(f"{identifier}: advisorySource must use HTTPS")
        if not SRI_RE.fullmatch(entry.get("integrity", "")):
            errors.append(f"{identifier}: invalid SHA-512 SRI value")
        status = str(entry.get("advisoryStatus", "")).lower()
        if any(blocker in status for blocker in SEVERITY_BLOCKERS):
            errors.append(f"{identifier}: advisory status is not release-safe ({entry.get('advisoryStatus')})")
        try:
            reviewed = date.fromisoformat(str(entry["reviewedAt"]))
        except (KeyError, TypeError, ValueError):
            reviewed = None
        if reviewed is None:
            errors.append(f"{identifier}: reviewedAt must be an ISO date")
        else:
            if reviewed > today:
                errors.append(f"{identifier}: reviewedAt is in the future")
            elif review_policy_days and (today - reviewed).days > review_policy_days:
                errors.append(f"{identifier}: advisory review is stale")
    return errors


def _direct_asset_references() -> list[tuple[Path, str, str, str]]:
    references: list[tuple[Path, str, str, str]] = []
    for path in (INDEX, CESIUM_FRAME):
        source = path.read_text(encoding="utf-8")
        for match in EXTERNAL_ASSET_RE.finditer(source):
            tag_name, raw_attrs = match.groups()
            attrs = _attrs(raw_attrs)
            url = attrs.get("src") or attrs.get("href")
            if not url or not url.startswith("https://"):
                continue
            rel = attrs.get("rel", "").lower().split()
            is_asset = tag_name.lower() == "script" or "stylesheet" in rel or attrs.get("as", "").lower() in {"script", "style"}
            if is_asset:
                references.append((path, tag_name.lower(), url, attrs.get("integrity", "")))
    return references


def _validate_references(payload: dict) -> list[str]:
    by_url = {entry["url"]: entry for entry in payload["dependencies"]}
    errors: list[str] = []
    for path, tag_name, url, integrity in _direct_asset_references():
        entry = by_url.get(url)
        if entry is None:
            errors.append(f"{path.name}: external {tag_name} asset is missing from inventory: {url}")
            continue
        if not integrity:
            errors.append(f"{path.name}: external asset has no SRI: {url}")
        elif integrity != entry["integrity"]:
            errors.append(f"{path.name}: SRI does not match inventory: {url}")
        expected_kind = "script" if tag_name == "script" or url.lower().split("?", 1)[0].endswith(".js") else "style"
        if entry["kind"] != expected_kind:
            errors.append(f"{entry['id']}: inventory kind {entry['kind']} does not match {tag_name}")
    combined = INDEX.read_text(encoding="utf-8") + CESIUM_FRAME.read_text(encoding="utf-8")
    for entry in payload["dependencies"]:
        marker = entry.get("sourceMarker")
        if marker and marker not in combined:
            errors.append(f"{entry['id']}: dynamic source marker is missing: {marker}")
        if entry["url"] not in combined and not marker:
            errors.append(f"{entry['id']}: URL is not referenced by the app")
    return errors


def _validate_sanitizer_contract() -> list[str]:
    source = INDEX.read_text(encoding="utf-8")
    try:
        start = source.index("const SAFE_HTML_OPTIONS")
        end = source.index("const DATA_URLS", start)
    except ValueError:
        return ["safeHTML sanitizer boundary is missing"]
    section = source[start:end]
    errors: list[str] = []
    for marker in ("window.DOMPurify.sanitize", "escapeHTML(markup)", "FORBID_TAGS", "FORBID_ATTR", "srcdoc"):
        if marker not in section:
            errors.append(f"safeHTML sanitizer contract is missing {marker}")
    for hostile_tag in ("script", "style", "template", "iframe", "object", "embed"):
        if f"'{hostile_tag}'" not in section:
            errors.append(f"safeHTML does not forbid hostile tag {hostile_tag}")
    if "'IN_PLACE'" in section or "IN_PLACE:" in section:
        errors.append("safeHTML must not enable DOMPurify IN_PLACE mode")
    return errors


def _validate_online_hashes(payload: dict) -> list[str]:
    errors: list[str] = []
    for entry in payload["dependencies"]:
        request = Request(entry["url"], headers={"User-Agent": "VIPTrack-CDN-gate/1"})
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read(MAX_SRI_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            errors.append(f"{entry['id']}: unable to fetch pinned asset ({exc})")
            continue
        if len(body) > MAX_SRI_BYTES:
            errors.append(f"{entry['id']}: asset exceeds online verification cap")
            continue
        digest = "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode("ascii")
        if digest != entry["integrity"]:
            errors.append(f"{entry['id']}: remote bytes do not match SRI inventory")
    return errors


def run_gate(*, online: bool = False, today: date | None = None) -> dict:
    """Run all checks and return the validated inventory summary."""
    payload = _load_inventory()
    check_date = today or date.today()
    errors = _validate_inventory(payload, check_date)
    errors.extend(_validate_references(payload))
    errors.extend(_validate_sanitizer_contract())
    if online:
        errors.extend(_validate_online_hashes(payload))
    if errors:
        raise DependencyGateError("\n".join(errors))
    return {"schemaVersion": payload["schemaVersion"], "dependencies": len(payload["dependencies"]), "online": online}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="fetch each pinned asset and verify its SHA-512 bytes")
    args = parser.parse_args(argv)
    try:
        summary = run_gate(online=args.online)
    except DependencyGateError as exc:
        print(f"CDN dependency gate failed:\n{exc}", file=sys.stderr)
        return 1
    print(f"CDN dependency gate passed: {summary['dependencies']} assets ({'online' if args.online else 'offline'} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
