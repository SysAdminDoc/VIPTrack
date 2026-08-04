#!/usr/bin/env python3
"""Build compact, privacy-minimized FAA registration shards.

The FAA Releasable Aircraft Database is a large fixed-width-looking CSV
export.  VIPTrack only needs the N-number lookup and a small set of public
registration fields, so this builder deliberately excludes street addresses
and additional registrants.  Shards use the same FNV-1a modulo-26 algorithm
implemented in index.html; a lookup can therefore fetch one small shard.

Example:
    python tools/build_faa_registry.py --archive ReleasableAircraft.zip
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import string
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 1
SOURCE_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
SHARD_LETTERS = string.ascii_uppercase
N_NUMBER_RE = re.compile(r"N[0-9]{1,5}[A-Z]{0,2}$")


def normalise_n_number(value: str) -> str | None:
    """Return a canonical FAA N-number or None for a non-aircraft row."""

    value = str(value or "").strip().upper()
    if not value:
        return None
    if not value.startswith("N"):
        value = "N" + value
    if len(value) > 6 or not N_NUMBER_RE.fullmatch(value):
        return None
    return value


def shard_for_n_number(n_number: str) -> str:
    """Match the JavaScript FNV-1a modulo-26 shard calculation."""

    value = 2166136261
    for char in n_number:
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    return SHARD_LETTERS[value % len(SHARD_LETTERS)]


def clean(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def optional_year(value: str) -> int | None:
    value = clean(value)
    return int(value) if value.isdigit() and len(value) == 4 else None


def optional_date(value: str) -> str | None:
    value = clean(value)
    if not re.fullmatch(r"\d{8}", value):
        return None
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def parse_master(stream: Iterable[str]) -> tuple[dict[str, dict[str, dict]], Counter, int]:
    reader = csv.reader(stream)
    raw_header = next(reader)
    header = [clean(item).replace("ï»¿", "") for item in raw_header]
    columns = {name: index for index, name in enumerate(header)}
    required = {
        "N-NUMBER",
        "SERIAL NUMBER",
        "MFR MDL CODE",
        "YEAR MFR",
        "TYPE REGISTRANT",
        "NAME",
        "STATE",
        "COUNTRY",
        "LAST ACTION DATE",
        "CERT ISSUE DATE",
        "TYPE AIRCRAFT",
        "TYPE ENGINE",
        "STATUS CODE",
        "MODE S CODE",
        "EXPIRATION DATE",
    }
    missing = sorted(required - columns.keys())
    if missing:
        raise ValueError("MASTER.txt is missing columns: " + ", ".join(missing))

    shards = {letter: {} for letter in SHARD_LETTERS}
    counts = Counter()
    total_rows = 0
    for row in reader:
        total_rows += 1
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        n_number = normalise_n_number(row[columns["N-NUMBER"]])
        if not n_number:
            continue
        if n_number in shards[shard_for_n_number(n_number)]:
            raise ValueError(f"Duplicate N-number in MASTER.txt: {n_number}")

        def field(name: str) -> str:
            return clean(row[columns[name]])

        record: dict[str, object] = {}
        values = {
            "owner": field("NAME"),
            "serial": field("SERIAL NUMBER"),
            "modelCode": field("MFR MDL CODE"),
            "registrantType": field("TYPE REGISTRANT"),
            "state": field("STATE"),
            "country": field("COUNTRY"),
            "aircraftType": field("TYPE AIRCRAFT"),
            "engineType": field("TYPE ENGINE"),
            "status": field("STATUS CODE"),
            "modeS": field("MODE S CODE"),
        }
        for key, value in values.items():
            if value:
                record[key] = value
        year = optional_year(row[columns["YEAR MFR"]])
        if year is not None:
            record["year"] = year
        for key, column in (
            ("lastAction", "LAST ACTION DATE"),
            ("certIssue", "CERT ISSUE DATE"),
            ("expiration", "EXPIRATION DATE"),
        ):
            parsed = optional_date(row[columns[column]])
            if parsed:
                record[key] = parsed

        shard = shard_for_n_number(n_number)
        shards[shard][n_number] = record
        counts[shard] += 1
    return shards, counts, total_rows


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def build(archive: Path, output: Path, generated_at: str) -> dict:
    with zipfile.ZipFile(archive) as source:
        try:
            master = source.open("MASTER.txt")
        except KeyError as error:
            raise ValueError("FAA archive does not contain MASTER.txt") from error
        with master:
            import io

            text = io.TextIOWrapper(master, encoding="latin-1", newline="")
            try:
                shards, counts, source_rows = parse_master(text)
            finally:
                text.detach()

    output.mkdir(parents=True, exist_ok=True)
    for letter in SHARD_LETTERS:
        write_json(output / f"master-{letter}.json", shards[letter])

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "source": "FAA Releasable Aircraft Database / MASTER.txt",
        "sourceUrl": SOURCE_URL,
        "generatedAt": generated_at,
        "sourceRows": source_rows,
        "recordCount": sum(counts.values()),
        "ownerCount": sum(1 for records in shards.values() for record in records.values() if record.get("owner")),
        "shardAlgorithm": "fnv1a-mod-26",
        "privacy": "Addresses and additional registrants are intentionally excluded; PIA records are never enriched at runtime.",
        "shards": {
            letter: {"file": f"master-{letter}.json", "records": counts[letter]}
            for letter in SHARD_LETTERS
        },
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="Path to FAA ReleasableAircraft.zip")
    parser.add_argument("--output", type=Path, default=Path("data/faa"), help="Output directory for FAA shards")
    parser.add_argument("--generated-at", default=date.today().isoformat(), help="Manifest generation date (YYYY-MM-DD)")
    args = parser.parse_args()
    manifest = build(args.archive, args.output, args.generated_at)
    print(json.dumps({key: manifest[key] for key in ("generatedAt", "sourceRows", "recordCount", "ownerCount")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
