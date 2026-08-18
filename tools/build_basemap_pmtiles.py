"""Build the optional self-hosted PMTiles basemap for VIPTrack.

The app's raster basemaps come from third parties (Esri for the Leaflet default,
OpenStreetMap for the Cesium globe, CARTO/Stadia for the MapLibre vector styles).
Each of those reserves the right to block a busy third-party site. A PMTiles
archive removes that dependency: one file, served from the same origin over HTTP
range requests, no tile server and no API key.

The archive is *not* checked in. It is a large binary that has to be rebuilt as
upstream data ages, and every rebuild would add its full size to git history
permanently. Run this script to produce it locally, then deploy `data/basemap/`
with the site. `.gitignore` keeps it out of the repository.

Measured against the Protomaps daily planet build on 2026-08-18 (127.9 GB):

    world  z0-6   42.7 MB    <- default; overzooms acceptably to ~z10
    world  z0-7  178.4 MB
    CONUS  z0-10 361.1 MB    <- US only, and a third of the Pages budget

The published tree is ~466 MB against the GitHub Pages 1 GB soft limit, so z0-6
is the only build that leaves meaningful headroom. Higher zooms are refused by
default; pass --allow-large if you host somewhere without that ceiling.

Requires the go-pmtiles CLI: https://github.com/protomaps/go-pmtiles/releases

Usage from the repository root:

    py -3.13 tools/build_basemap_pmtiles.py             # world z0-6
    py -3.13 tools/build_basemap_pmtiles.py --check     # report what is installed
    py -3.13 tools/build_basemap_pmtiles.py --maxzoom 7 --bbox -125,24.4,-66.9,49.4
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASEMAP_DIR = ROOT / "data" / "basemap"
ARCHIVE_PATH = BASEMAP_DIR / "basemap.pmtiles"
MANIFEST_PATH = BASEMAP_DIR / "manifest.json"

BUILD_HOST = "https://build.protomaps.com"

# Past this the archive stops being a rounding error against the GitHub Pages
# budget. --allow-large lifts it for operators hosting elsewhere.
DEFAULT_MAXZOOM = 6
LARGE_MAXZOOM = 7
SIZE_BUDGET_MB = 96

# Upstream rebuilds the planet weekly; the basemap ages slowly, so this is a
# nudge rather than a correctness boundary.
STALE_AFTER_DAYS = 180


def _pmtiles_cli() -> str:
    found = shutil.which("pmtiles")
    if found:
        return found
    fallback = Path.home() / "tools" / "pmtiles" / "pmtiles.exe"
    if fallback.exists():
        return str(fallback)
    raise SystemExit(
        "go-pmtiles CLI not found. Install it from "
        "https://github.com/protomaps/go-pmtiles/releases and put it on PATH."
    )


def _head_ok(url: str) -> bool:
    # The build host answers 403 to urllib's default User-Agent, so a probe that
    # omits this reports every candidate build as missing.
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "VIPTrack-basemap-build"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def latest_planet_build(today: datetime.date | None = None) -> str:
    """Return the newest published daily planet build URL.

    Protomaps keeps a rolling window rather than every day, so walk backwards
    until one answers instead of guessing a cadence.
    """
    day = today or datetime.date.today()
    for back in range(0, 45):
        candidate = day - datetime.timedelta(days=back)
        url = f"{BUILD_HOST}/{candidate.strftime('%Y%m%d')}.pmtiles"
        if _head_ok(url):
            return url
    raise SystemExit(f"no Protomaps planet build answered under {BUILD_HOST}")


def write_manifest(source_url: str, maxzoom: int, bbox: str | None, size_bytes: int) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "source": "protomaps/basemaps daily planet build",
                "sourceUrl": source_url,
                "license": "ODbL-1.0 (OpenStreetMap contributors); Protomaps basemap schema",
                "attribution": "© OpenStreetMap contributors · Protomaps",
                "maxzoom": maxzoom,
                "bbox": bbox or "-180,-85.05,180,85.05",
                "bytes": size_bytes,
                "builtAt": datetime.date.today().isoformat(),
                "staleAfterDays": STALE_AFTER_DAYS,
                "buildCommand": "py -3.13 tools/build_basemap_pmtiles.py",
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def build(maxzoom: int, bbox: str | None, allow_large: bool) -> int:
    ceiling = LARGE_MAXZOOM if allow_large else DEFAULT_MAXZOOM
    if maxzoom > ceiling:
        print(
            f"Refusing maxzoom {maxzoom}: the world build grows roughly 4x per level "
            f"({DEFAULT_MAXZOOM} -> 42.7 MB, {LARGE_MAXZOOM} -> 178.4 MB) and this "
            "repository publishes ~466 MB of a 1 GB budget. Pass --allow-large if you "
            "host somewhere without that ceiling.",
            file=sys.stderr,
        )
        return 1

    cli = _pmtiles_cli()
    source_url = latest_planet_build()
    BASEMAP_DIR.mkdir(parents=True, exist_ok=True)
    command = [cli, "extract", source_url, str(ARCHIVE_PATH), f"--maxzoom={maxzoom}"]
    if bbox:
        command.append(f"--bbox={bbox}")
    print(f"Source:  {source_url}")
    print(f"Command: {' '.join(command)}")
    result = subprocess.run(command)
    if result.returncode != 0:
        return result.returncode

    size = ARCHIVE_PATH.stat().st_size
    megabytes = size / (1024 * 1024)
    if not allow_large and megabytes > SIZE_BUDGET_MB:
        ARCHIVE_PATH.unlink()
        print(
            f"Built archive is {megabytes:.1f} MB, over the {SIZE_BUDGET_MB} MB budget; "
            "removed. Narrow the bbox, lower the zoom, or pass --allow-large.",
            file=sys.stderr,
        )
        return 1

    write_manifest(source_url, maxzoom, bbox, size)
    print(f"Wrote {ARCHIVE_PATH.relative_to(ROOT)} ({megabytes:.1f} MB) at maxzoom {maxzoom}.")
    print("Enable it in Settings > Appearance > Basemap, or open ?renderer=webgl&basemap=pmtiles-dark.")
    return 0


def check() -> int:
    if not ARCHIVE_PATH.exists():
        print("No self-hosted basemap installed (data/basemap/basemap.pmtiles is absent).")
        print("Build one with: py -3.13 tools/build_basemap_pmtiles.py")
        return 0
    megabytes = ARCHIVE_PATH.stat().st_size / (1024 * 1024)
    manifest = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("manifest.json is unreadable; rebuild the archive.", file=sys.stderr)
            return 1
    built = manifest.get("builtAt", "(unknown)")
    print(f"Basemap archive: {megabytes:.1f} MB, maxzoom {manifest.get('maxzoom', '?')}, built {built}.")
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(built)).days
    except ValueError:
        return 0
    print(f"Age: {age} days (stale after {manifest.get('staleAfterDays', STALE_AFTER_DAYS)}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report the installed archive without building")
    parser.add_argument("--maxzoom", type=int, default=DEFAULT_MAXZOOM, help=f"maximum zoom (default {DEFAULT_MAXZOOM})")
    parser.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat to build a regional archive")
    parser.add_argument("--allow-large", action="store_true", help="lift the zoom and size ceilings")
    args = parser.parse_args()
    if args.check:
        return check()
    return build(args.maxzoom, args.bbox, args.allow_large)


if __name__ == "__main__":
    raise SystemExit(main())
