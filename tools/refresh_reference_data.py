"""Refresh the vendored aircraft reference database from tar1090-db.

The app serves `data/aircraft/registrations.csv` from this repository, so the file
is part of the release rather than something fetched at runtime. Upstream publishes
a new build most days; without a documented refresh this silently drifts, which is
how the checked-in copy ended up five months behind without anyone noticing.

Usage from the repository root:

    py -3.13 tools/refresh_reference_data.py            # refresh if upstream is newer
    py -3.13 tools/refresh_reference_data.py --check    # report only, non-zero if stale
    py -3.13 tools/refresh_reference_data.py --force    # refresh regardless

`--check` is what the freshness gate in `test_viptrack.py` mirrors offline; this
script is the only thing that talks to the network.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "aircraft"
CSV_PATH = DATA / "registrations.csv"
VERSION_PATH = DATA / "dbversion.txt"
MANIFEST_PATH = DATA / "manifest.json"

UPSTREAM = "https://raw.githubusercontent.com/wiedehopf/tar1090-db/csv"
VERSION_URL = f"{UPSTREAM}/version"
CSV_URL = f"{UPSTREAM}/aircraft.csv.gz"

# Upstream rebuilds most days. Past this the gate complains; it is a prompt to run
# this script, not a correctness failure.
STALE_AFTER_DAYS = 120


def _get(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "VIPTrack-reference-refresh"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def local_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip() if VERSION_PATH.exists() else ""


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def age_days(manifest: dict) -> int | None:
    stamp = manifest.get("refreshedAt")
    if not stamp:
        return None
    try:
        refreshed = datetime.date.fromisoformat(stamp)
    except ValueError:
        return None
    return (datetime.date.today() - refreshed).days


def write_manifest(version: str, rows: int) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "source": "wiedehopf/tar1090-db (csv branch)",
                "sourceUrl": CSV_URL,
                "license": "ODbL-1.0 (upstream aggregates OpenSky and community data)",
                "dbVersion": version,
                "refreshedAt": datetime.date.today().isoformat(),
                "rows": rows,
                "staleAfterDays": STALE_AFTER_DAYS,
                "refreshCommand": "py -3.13 tools/refresh_reference_data.py",
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def refresh(force: bool) -> int:
    upstream_version = _get(VERSION_URL, timeout=30).decode("utf-8").strip()
    current = local_version()
    print(f"local dbversion:    {current or '(none)'}")
    print(f"upstream dbversion: {upstream_version}")

    if current == upstream_version and not force:
        print("Already current; nothing to do.")
        return 0

    print(f"Downloading {CSV_URL} ...")
    payload = gzip.decompress(_get(CSV_URL))
    text = payload.decode("utf-8", errors="replace")
    rows = text.count("\n")
    if rows < 100_000:
        print(f"Refusing to write a suspiciously small database ({rows} rows).", file=sys.stderr)
        return 1

    # Normalise to LF so the single-file diff stays reviewable on Windows.
    io.open(CSV_PATH, "w", encoding="utf-8", newline="\n").write(text)
    VERSION_PATH.write_text(upstream_version + "\n", encoding="utf-8")
    write_manifest(upstream_version, rows)
    print(f"Wrote {CSV_PATH.relative_to(ROOT)} ({rows} rows) at dbversion {upstream_version}.")
    return 0


def check() -> int:
    manifest = load_manifest()
    age = age_days(manifest)
    version = manifest.get("dbVersion") or local_version() or "(unknown)"
    if age is None:
        print(f"Reference database {version}: no refresh date recorded.")
        return 1
    print(f"Reference database {version}: refreshed {age} days ago (limit {STALE_AFTER_DAYS}).")
    if age > STALE_AFTER_DAYS:
        print("Stale. Run: py -3.13 tools/refresh_reference_data.py", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report freshness without downloading")
    parser.add_argument("--force", action="store_true", help="refresh even if versions match")
    args = parser.parse_args()
    return check() if args.check else refresh(args.force)


if __name__ == "__main__":
    raise SystemExit(main())
