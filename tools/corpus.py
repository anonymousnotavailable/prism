"""
Corpus Downloader — fetches every dataset listed in corpus_registry.json
into corpus_cache/ (gitignored — real-world data is never committed, only
the URLs that point to it) so tools/corpus_gauntlet.py has something local
to run Prism's pipeline against.

Deliberately dumb about *what* it downloads: this file's only job is
"reliably get bytes onto disk, or explain clearly why not." Format
sniffing, encoding detection, and actually parsing the result all happen
downstream, in the gauntlet — a download failure here (404, timeout, a
Kaggle key that isn't configured) is not a Prism bug, so it's recorded and
skipped rather than raised.

Run with:  python tools/corpus.py [--only NAME] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests

TOOLS_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = TOOLS_DIR / "corpus_registry.json"
CACHE_DIR = TOOLS_DIR.parent / "corpus_cache"
MANIFEST_PATH = CACHE_DIR / "manifest.json"

TIMEOUT_SECONDS = 45  # government open-data APIs can be genuinely slow, not just broken
MAX_RETRIES = 2
USER_AGENT = "Mozilla/5.0 (compatible; PrismCorpusBenchmark/1.0; +https://github.com/anonymousnotavailable/prism)"

# A plain download that actually landed on an HTML error/login page instead
# of real data is a common silent-failure mode for government portals —
# this catches it instead of caching a useless HTML file as if it were CSV.
_HTML_SNIFF_PREFIXES = (b"<!doctype", b"<!DOCTYPE", b"<html", b"<HTML")


def load_registry() -> list[dict]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["datasets"]


def _safe_filename(name: str, url: str, zip_member: Optional[str] = None, fmt: Optional[str] = None) -> str:
    # A zip_member's own extension (e.g. "bank-full.csv") is what matters for
    # the cached file, not the .zip URL's — the gauntlet reads the extracted
    # file, never the archive. Failing that, trust the registry's declared
    # `format` (e.g. data.gov.in's API URLs carry no extension at all, but
    # the entry says "csv") over a generic ".dat" — a cache file's extension
    # should describe what's actually inside it.
    if zip_member:
        ext = Path(zip_member.split(">")[-1]).suffix
    else:
        ext = Path(url.split("?")[0]).suffix or (f".{fmt}" if fmt else ".dat")
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower())
    return f"{slug}{ext}"


def _fetch_http(entry: dict, force: bool = False) -> dict:
    """Download entry['url'] with retry. If entry['zip_member'] is set, the
    downloaded file is treated as a zip archive and that one member is
    extracted and cached instead of the archive itself — the gauntlet only
    ever sees a plain CSV/XLSX, matching what a real user could upload
    through Prism's own file picker (which doesn't accept .zip). Returns a
    result dict — never raises.
    """
    zip_member = entry.get("zip_member")
    filename = _safe_filename(entry["name"], entry["url"], zip_member, entry.get("format"))
    dest = CACHE_DIR / filename

    if dest.exists() and not force:
        content = dest.read_bytes()
        return {
            "name": entry["name"], "status": "ok", "path": str(dest.relative_to(CACHE_DIR.parent)),
            "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            "attempts": 0, "error": None, "cached": True,
        }

    last_error: Optional[str] = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            resp = requests.get(
                entry["url"], timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, allow_redirects=True
            )
            resp.raise_for_status()
            content = resp.content
            if not content:
                last_error = "empty response body"
                continue
            if entry.get("format") in ("csv", "tsv") and content.lstrip()[:15].lower().startswith(_HTML_SNIFF_PREFIXES):
                last_error = "response looks like an HTML page, not a data file (portal likely changed its URL)"
                continue

            if zip_member:
                # ">"-separated path walks nested zips (e.g. "bank.zip>bank-full.csv"
                # for archives some portals ship as a zip-of-zips).
                try:
                    for part in zip_member.split(">"):
                        with zipfile.ZipFile(BytesIO(content)) as zf:
                            content = zf.read(part)
                except (zipfile.BadZipFile, KeyError) as e:
                    last_error = f"zip extraction failed for member {zip_member!r}: {e}"
                    continue

            dest.write_bytes(content)
            checksum = hashlib.sha256(content).hexdigest()
            return {
                "name": entry["name"], "status": "ok", "path": str(dest.relative_to(CACHE_DIR.parent)),
                "size_bytes": len(content), "sha256": checksum, "attempts": attempt, "error": None,
                "cached": False,
            }
        except requests.exceptions.RequestException as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt <= MAX_RETRIES:
                time.sleep(1.5 * attempt)
    return {
        "name": entry["name"], "status": "failed", "path": None,
        "size_bytes": 0, "sha256": None, "attempts": MAX_RETRIES + 1, "error": last_error,
    }


def _fetch_kaggle(entry: dict) -> dict:
    """Download a Kaggle dataset via kagglehub. Skips gracefully — never
    raises — if kagglehub isn't installed or no API credentials are
    configured (KAGGLE_USERNAME/KAGGLE_KEY env vars or ~/.kaggle/kaggle.json),
    since a missing personal API key is not something this benchmark can or
    should force a user to set up.
    """
    import os

    try:
        import kagglehub
    except ImportError:
        return {
            "name": entry["name"], "status": "skipped", "path": None, "size_bytes": 0, "sha256": None,
            "attempts": 0, "error": "kagglehub not installed (pip install kagglehub) — skipped, not a failure",
        }

    has_env_creds = bool(os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"))
    has_json_creds = (Path.home() / ".kaggle" / "kaggle.json").exists()
    if not (has_env_creds or has_json_creds):
        return {
            "name": entry["name"], "status": "skipped", "path": None, "size_bytes": 0, "sha256": None,
            "attempts": 0,
            "error": (
                "No Kaggle API credentials found (set KAGGLE_USERNAME + KAGGLE_KEY, or place "
                "~/.kaggle/kaggle.json) — skipped, not a failure. Get a key at kaggle.com/settings."
            ),
        }

    try:
        download_path = kagglehub.dataset_download(entry["kaggle_slug"])
        total_size = sum(f.stat().st_size for f in Path(download_path).rglob("*") if f.is_file())
        return {
            "name": entry["name"], "status": "ok", "path": download_path,
            "size_bytes": total_size, "sha256": None, "attempts": 1, "error": None,
        }
    except Exception as e:  # kagglehub's own exceptions aren't a stable public API to catch narrowly
        return {
            "name": entry["name"], "status": "failed", "path": None, "size_bytes": 0, "sha256": None,
            "attempts": 1, "error": f"{type(e).__name__}: {e}",
        }


def fetch_one(entry: dict, force: bool = False) -> dict:
    if entry.get("format") == "kaggle":
        return _fetch_kaggle(entry)
    return _fetch_http(entry, force=force)


def download_corpus(only: Optional[str] = None, force: bool = False) -> list[dict]:
    CACHE_DIR.mkdir(exist_ok=True)
    entries = load_registry()
    if only:
        entries = [e for e in entries if e["name"] == only]
        if not entries:
            print(f"No registry entry named {only!r}.")
            return []

    results = []
    for entry in entries:
        print(f"[{entry['domain']:<12}] {entry['name']} ... ", end="", flush=True)
        result = fetch_one(entry, force=force)
        result["source"] = entry["source"]
        result["domain"] = entry["domain"]
        results.append(result)
        if result["status"] == "ok":
            print(f"OK ({result['size_bytes']:,} bytes)")
        elif result["status"] == "skipped":
            print(f"SKIPPED — {result['error']}")
        else:
            print(f"FAILED — {result['error']}")

    MANIFEST_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_skip = sum(1 for r in results if r["status"] == "skipped")
    n_fail = sum(1 for r in results if r["status"] == "failed")
    print(f"\n{n_ok} downloaded, {n_skip} skipped, {n_fail} failed — manifest: {MANIFEST_PATH}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download the Prism real-world corpus.")
    parser.add_argument("--only", default=None, help="Download a single registry entry by name.")
    parser.add_argument("--force", action="store_true", help="Re-download even if already cached.")
    args = parser.parse_args()
    download_corpus(only=args.only, force=args.force)
    sys.exit(0)
