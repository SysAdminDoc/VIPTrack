#!/usr/bin/env python3
"""
VIPTrack Type Photo Downloader v1.0.0
Downloads one representative photo per ICAO aircraft type code for self-hosting.

Sources (in priority order):
  1. Planespotters.net API (best quality, real aircraft photos)
  2. airport-data.com API (community-submitted photos)
  3. Wikipedia thumbnails (generic type photos from articles)
  4. Silhouette fallback from airplanes.live

Output: assets/type_photos/{TYPECODE}.jpg
Manifest: assets/type_photos/manifest.json

Usage:
  python download-type-photos.py              # Download all types from live mil feeds
  python download-type-photos.py --resume     # Resume interrupted download (skip existing)
  python download-type-photos.py --types-only # Only use types.json (no live feed needed)
"""

import json, os, sys, time, csv, io, re, hashlib
from pathlib import Path
from urllib.parse import quote

def _bootstrap():
    """Auto-install dependencies."""
    required = ['requests', 'Pillow']
    import importlib, subprocess
    for pkg in required:
        mod = pkg.lower().replace('-', '_')
        if mod == 'pillow': mod = 'PIL'
        try:
            importlib.import_module(mod)
        except ImportError:
            print(f'Installing {pkg}...')
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q',
                                   '--break-system-packages'], stderr=subprocess.DEVNULL)

_bootstrap()

import requests
from PIL import Image

# ============ CONFIG ============
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / 'assets' / 'type_photos'
MANIFEST_PATH = OUTPUT_DIR / 'manifest.json'

TYPES_JSON_URL = 'https://raw.githubusercontent.com/SysAdminDoc/SkyTrack/main/data/aircraft/types.json'
MIL_FEEDS = [
    'https://api.adsb.one/v2/mil',
    'https://api.airplanes.live/v2/mil',
    'https://api.adsb.lol/v2/mil',
]
PIA_FEEDS = [
    'https://api.adsb.one/v2/pia',
    'https://api.adsb.lol/v2/pia',
]

PLANESPOTTERS_API = 'https://api.planespotters.net/pub/photos'
AIRPORT_DATA_API = 'https://airport-data.com/api/ac_thumb.json'
WIKIPEDIA_API = 'https://en.wikipedia.org/api/rest_v1/page/summary'
SILHOUETTE_URLS = [
    'https://raw.githubusercontent.com/SysAdminDoc/SkyTrack/main/assets/silhouettes/',
    'https://globe.airplanes.live/aircraft_sil/',
]

MIN_IMAGE_SIZE = 8192       # Minimum file size in bytes (skip tiny placeholders/silhouettes)
TARGET_WIDTH = 800          # Resize to this width for consistency
JPEG_QUALITY = 85           # JPEG compression quality
REQUEST_DELAY = 0.5         # Seconds between API requests
PLANESPOTTERS_DELAY = 1.0   # Extra delay for planespotters (strict rate limiting)
REQUEST_TIMEOUT = 15

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'VIPTrack-PhotoDownloader/1.0 (github.com/SysAdminDoc/VIPTrack)',
    'Accept': 'image/*, application/json',
})


# ============ HELPERS ============
def log(msg, level='info'):
    icons = {'info': '[*]', 'ok': '[+]', 'warn': '[!]', 'err': '[-]', 'skip': '[~]'}
    print(f"{icons.get(level, '[*]')} {msg}")


def safe_get(url, timeout=REQUEST_TIMEOUT, **kwargs):
    """GET with error handling and rate limit retry."""
    for attempt in range(3):
        try:
            resp = SESSION.get(url, timeout=timeout, **kwargs)
            if resp.status_code == 429:
                wait = (attempt + 1) * 3
                log(f"Rate limited on {url[:60]}... waiting {wait}s", 'warn')
                time.sleep(wait)
                continue
            return resp
        except (requests.RequestException, Exception) as e:
            if attempt == 2:
                return None
            time.sleep(1)
    return None


def download_image(url):
    """Download an image URL and return bytes, or None on failure."""
    resp = safe_get(url)
    if not resp or resp.status_code != 200:
        return None
    data = resp.content
    if len(data) < MIN_IMAGE_SIZE:
        return None
    # Validate it's actually an image
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        return data
    except Exception:
        return None


def process_image(image_bytes):
    """Resize and optimize image to standard format."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ('RGBA', 'P', 'LA'):
            bg = Image.new('RGB', img.size, (26, 26, 46))  # Dark background
            if img.mode == 'P':
                img = img.convert('RGBA')
            bg.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize if wider than target
        if img.width > TARGET_WIDTH:
            ratio = TARGET_WIDTH / img.width
            new_h = int(img.height * ratio)
            img = img.resize((TARGET_WIDTH, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception as e:
        log(f"Image processing failed: {e}", 'err')
        return None


def save_photo(type_code, image_bytes, source):
    """Process and save a photo for a type code."""
    processed = process_image(image_bytes)
    if not processed:
        return False
    path = OUTPUT_DIR / f"{type_code}.jpg"
    path.write_bytes(processed)
    return True


# ============ PHOTO SOURCES ============
def try_planespotters_by_hex(hex_code):
    """Try Planespotters API by hex code."""
    url = f"{PLANESPOTTERS_API}/hex/{hex_code.upper()}"
    resp = safe_get(url)
    time.sleep(PLANESPOTTERS_DELAY)
    if not resp or resp.status_code != 200:
        return None
    try:
        data = resp.json()
        photos = data.get('photos', [])
        if photos:
            # Prefer thumbnail_large for good quality without being huge
            photo_url = (photos[0].get('thumbnail_large', {}).get('src') or
                         photos[0].get('thumbnail', {}).get('src'))
            if photo_url:
                return download_image(photo_url)
    except Exception:
        pass
    return None


def try_planespotters_by_reg(reg):
    """Try Planespotters API by registration."""
    if not reg:
        return None
    url = f"{PLANESPOTTERS_API}/reg/{quote(reg)}"
    resp = safe_get(url)
    time.sleep(PLANESPOTTERS_DELAY)
    if not resp or resp.status_code != 200:
        return None
    try:
        data = resp.json()
        photos = data.get('photos', [])
        if photos:
            photo_url = (photos[0].get('thumbnail_large', {}).get('src') or
                         photos[0].get('thumbnail', {}).get('src'))
            if photo_url:
                return download_image(photo_url)
    except Exception:
        pass
    return None


def try_airport_data(hex_code, reg=None):
    """Try airport-data.com API."""
    url = f"{AIRPORT_DATA_API}?m={hex_code.upper()}&n=1"
    if reg:
        url += f"&r={quote(reg)}"
    resp = safe_get(url)
    time.sleep(REQUEST_DELAY)
    if not resp or resp.status_code != 200:
        return None
    try:
        data = resp.json()
        if data.get('status') == 200 and data.get('data'):
            img_url = data['data'][0].get('image')
            if img_url:
                return download_image(img_url)
    except Exception:
        pass
    return None


def try_wikipedia(search_name):
    """Try Wikipedia thumbnail by aircraft name."""
    if not search_name:
        return None
    wiki_title = search_name.replace(' ', '_')
    url = f"{WIKIPEDIA_API}/{quote(wiki_title)}"
    resp = safe_get(url)
    time.sleep(REQUEST_DELAY)
    if not resp or resp.status_code != 200:
        return None
    try:
        data = resp.json()
        thumb_url = data.get('thumbnail', {}).get('source')
        if thumb_url:
            # Get higher resolution version
            thumb_url = re.sub(r'/(\d+)px-', '/800px-', thumb_url)
            return download_image(thumb_url)
    except Exception:
        pass
    return None


def try_silhouette(type_code):
    """Try silhouette images as last resort."""
    for base_url in SILHOUETTE_URLS:
        url = f"{base_url}{type_code.upper()}.png"
        img_data = download_image(url)
        if img_data:
            return img_data
        time.sleep(0.2)
    return None


# ============ DATA LOADING ============
def load_types_db():
    """Load the ICAO types database."""
    log("Loading ICAO types database...")
    resp = safe_get(TYPES_JSON_URL)
    if not resp or resp.status_code != 200:
        log("Failed to load types database!", 'err')
        return {}
    data = resp.json()
    types = {}
    for code, info in data.items():
        code = code.upper()
        if isinstance(info, list) and len(info) >= 1:
            types[code] = info[0]  # Full name like "FAIRCHILD A-10 Thunderbolt II"
        elif isinstance(info, str):
            types[code] = info
        else:
            types[code] = code
    log(f"Loaded {len(types)} aircraft type designators", 'ok')
    return types


def load_live_aircraft():
    """Load live military/VIP aircraft from ADSB feeds to get real hex/reg/type samples."""
    log("Loading live aircraft from ADSB feeds...")
    all_aircraft = {}

    for feed_list, label in [(MIL_FEEDS, 'military'), (PIA_FEEDS, 'PIA')]:
        for url in feed_list:
            try:
                resp = safe_get(url, timeout=20)
                if resp and resp.status_code == 200:
                    data = resp.json()
                    ac_list = data.get('ac', [])
                    for ac in ac_list:
                        t = (ac.get('t') or '').strip().upper()
                        if not t or t == 'UNKNOWN':
                            continue
                        hex_code = (ac.get('hex') or '').strip().upper()
                        reg = (ac.get('r') or '').strip()
                        if t not in all_aircraft:
                            all_aircraft[t] = []
                        all_aircraft[t].append({
                            'hex': hex_code,
                            'reg': reg,
                            'flight': (ac.get('flight') or '').strip(),
                            'desc': (ac.get('desc') or '').strip(),
                        })
                    log(f"  {url.split('/')[2]}/{label}: {len(ac_list)} aircraft", 'ok')
            except Exception as e:
                log(f"  {url}: {e}", 'warn')
            time.sleep(0.3)

    log(f"Found {len(all_aircraft)} unique types from live feeds", 'ok')
    return all_aircraft


# ============ MAIN DOWNLOAD LOGIC ============
def download_photo_for_type(type_code, type_name, samples=None):
    """
    Try all photo sources for a given type code.
    Returns (source_name, image_bytes) or (None, None).
    """
    samples = samples or []

    # Strategy 1: Use live aircraft samples to find real photos
    for sample in samples[:3]:  # Try up to 3 samples per type
        hex_code = sample.get('hex', '')
        reg = sample.get('reg', '')

        if hex_code:
            img = try_planespotters_by_hex(hex_code)
            if img:
                return ('planespotters-hex', img)

        if reg:
            img = try_planespotters_by_reg(reg)
            if img:
                return ('planespotters-reg', img)

        if hex_code:
            img = try_airport_data(hex_code, reg)
            if img:
                return ('airport-data', img)

    # Strategy 2: Wikipedia by type name
    if type_name and type_name != type_code:
        img = try_wikipedia(type_name)
        if img:
            return ('wikipedia', img)
        # Try without manufacturer prefix (e.g. "A-10 Thunderbolt II" instead of "FAIRCHILD A-10...")
        parts = type_name.split(' ', 1)
        if len(parts) > 1:
            img = try_wikipedia(parts[1])
            if img:
                return ('wikipedia-short', img)

    # Strategy 3: Wikipedia by type code
    img = try_wikipedia(type_code)
    if img:
        return ('wikipedia-raw', img)

    # Strategy 4: Silhouette fallback
    img = try_silhouette(type_code)
    if img:
        return ('silhouette', img)

    return (None, None)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='VIPTrack Type Photo Downloader')
    parser.add_argument('--resume', action='store_true', help='Skip types that already have photos')
    parser.add_argument('--types-only', action='store_true', help='Only use types.json (no live feed)')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of types to download')
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load manifest if resuming
    manifest = {}
    if args.resume and MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())
        log(f"Resuming: {len(manifest)} types already downloaded", 'info')

    # Load data
    types_db = load_types_db()
    if not types_db:
        log("Cannot proceed without types database", 'err')
        return

    live_samples = {}
    if not args.types_only:
        live_samples = load_live_aircraft()

    # Build work list: merge types from DB + live feeds
    all_types = {}
    for code, name in types_db.items():
        all_types[code] = {'name': name, 'samples': live_samples.get(code, [])}
    for code, samples in live_samples.items():
        if code not in all_types:
            desc = samples[0].get('desc', '') if samples else ''
            all_types[code] = {'name': desc or code, 'samples': samples}

    # Sort: types with live samples first (better chance of finding photos)
    work_list = sorted(all_types.items(),
                       key=lambda x: (-len(x[1]['samples']), x[0]))

    if args.limit:
        work_list = work_list[:args.limit]

    log(f"\n{'='*60}")
    log(f"Total types to process: {len(work_list)}")
    log(f"Types with live samples: {sum(1 for _, v in work_list if v['samples'])}")
    log(f"Output directory: {OUTPUT_DIR}")
    log(f"{'='*60}\n")

    stats = {'downloaded': 0, 'skipped': 0, 'failed': 0, 'sources': {}}

    # Ground/surface codes that are not aircraft types
    NON_AIRCRAFT = {'TWR', 'GND', 'GRND', 'VEH', 'OBST', 'BALL', 'SHIP', 'PARA'}

    for i, (type_code, info) in enumerate(work_list):
        # Skip non-aircraft type codes
        if type_code in NON_AIRCRAFT:
            log(f"[{i+1}/{len(work_list)}] {type_code} - skipping (non-aircraft code)", 'skip')
            stats['skipped'] += 1
            continue

        # Skip if already done
        if args.resume:
            photo_path = OUTPUT_DIR / f"{type_code}.jpg"
            if photo_path.exists() and type_code in manifest:
                stats['skipped'] += 1
                continue

        progress = f"[{i+1}/{len(work_list)}]"
        type_name = info['name']
        samples = info['samples']

        log(f"{progress} {type_code} ({type_name}) - {len(samples)} samples...")

        source, img_data = download_photo_for_type(type_code, type_name, samples)

        if source and img_data:
            if save_photo(type_code, img_data, source):
                stats['downloaded'] += 1
                stats['sources'][source] = stats['sources'].get(source, 0) + 1
                manifest[type_code] = {
                    'name': type_name,
                    'source': source,
                    'file': f"{type_code}.jpg",
                    'ts': int(time.time())
                }
                log(f"  -> Saved from {source}", 'ok')

                # Save manifest periodically
                if stats['downloaded'] % 25 == 0:
                    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
            else:
                stats['failed'] += 1
                log(f"  -> Image processing failed", 'err')
        else:
            stats['failed'] += 1
            log(f"  -> No photo found", 'err')

    # Final manifest save
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    # Summary
    print(f"\n{'='*60}")
    print(f"DOWNLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"  Downloaded: {stats['downloaded']}")
    print(f"  Skipped:    {stats['skipped']}")
    print(f"  Failed:     {stats['failed']}")
    print(f"  Total:      {stats['downloaded'] + stats['skipped'] + stats['failed']}")
    print(f"\n  Sources:")
    for src, count in sorted(stats['sources'].items(), key=lambda x: -x[1]):
        print(f"    {src}: {count}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print(f"  Manifest: {MANIFEST_PATH}")
    print(f"\n  Next steps:")
    print(f"    1. Review photos in {OUTPUT_DIR}")
    print(f"    2. Replace any low-quality images manually")
    print(f"    3. Commit and push to SkyTrack repo")
    print(f"    4. VIPTrack will auto-detect type photos as fallback")


if __name__ == '__main__':
    main()
