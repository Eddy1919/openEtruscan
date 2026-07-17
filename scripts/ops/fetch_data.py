#!/usr/bin/env python3
"""Fetch the OpenEtruscan research corpus from Zenodo and verify checksums.

Why this exists: the corpus CSVs are deliberately not committed to git (see
.gitignore) and the old DVC remote (gs://openetruscan-data-dvc) lived in a
GCP project that no longer exists. The canonical public home of the data is
Zenodo, which gives us a versioned DOI and stable download URLs. This script
is the single supported way to restore the data layer of a fresh clone.

Stdlib only (urllib, hashlib) — it must work before any dependencies are
installed.

Usage:
    python scripts/ops/fetch_data.py            # fetch anything missing
    python scripts/ops/fetch_data.py --force    # re-download everything

Idempotent: a file whose SHA-256 already matches the manifest is skipped; a
downloaded file that fails verification is deleted and the run exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Manifest of Zenodo-hosted data files. Each entry pins the Zenodo record id
# (a *version* DOI: 10.5281/zenodo.<record_id>), the filename inside that
# record, the expected SHA-256, and the repo-relative destination. Add new
# files here — nothing else in this script should need to change.
FILES: list[dict[str, str]] = [
    {
        "record_id": "20075836",
        "filename": "openetruscan_clean.csv",
        "sha256": "4fc09af94005655bfe26affeeb48295c88606ae23c8dbc33ff5436f9083f69f8",
        "dest": "research/data/openetruscan_clean.csv",
    },
]

CHUNK_SIZE = 1 << 20  # 1 MiB

log = logging.getLogger("fetch_data")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    """Stream url to dest via a same-directory temp file (no partial files)."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "openetruscan-fetch-data"})
    try:
        with urllib.request.urlopen(request) as response, tmp.open("wb") as out:
            while chunk := response.read(CHUNK_SIZE):
                out.write(chunk)
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def fetch_one(entry: dict[str, str], *, force: bool) -> bool:
    """Fetch and verify a single manifest entry. Returns True on success."""
    dest = REPO_ROOT / entry["dest"]
    url = (
        f"https://zenodo.org/api/records/{entry['record_id']}" f"/files/{entry['filename']}/content"
    )

    if dest.exists() and not force:
        actual = sha256_of(dest)
        if actual == entry["sha256"]:
            log.info("%s: present, checksum OK — skipping", entry["dest"])
            return True
        log.warning(
            "%s: exists but checksum mismatch (got %s) — re-downloading",
            entry["dest"],
            actual,
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("%s: downloading from %s", entry["dest"], url)
    try:
        download(url, dest)
    except (urllib.error.URLError, OSError) as exc:
        log.error("%s: download failed: %s", entry["dest"], exc)
        return False

    actual = sha256_of(dest)
    if actual != entry["sha256"]:
        dest.unlink(missing_ok=True)
        log.error(
            "%s: SHA-256 mismatch after download (expected %s, got %s) — file deleted",
            entry["dest"],
            entry["sha256"],
            actual,
        )
        return False

    log.info("%s: downloaded, checksum OK", entry["dest"])
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download files even if a verified copy already exists.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")

    failures = [e["dest"] for e in FILES if not fetch_one(e, force=args.force)]
    if failures:
        log.error("FAILED: %s", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
