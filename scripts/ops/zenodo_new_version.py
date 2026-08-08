#!/usr/bin/env python3
"""Create the next version of the OpenEtruscan Zenodo dataset deposit.

What this does, in order, against the Zenodo REST API:

1. Creates a new version draft of the dataset record (concept
   10.5281/zenodo.20075835; current version 10.5281/zenodo.20075836).
2. Keeps the existing ``openetruscan_clean.csv`` (its SHA256 4fc09af9... is
   pinned by ``scripts/ops/fetch_data.py`` and by the frozen-split
   reproduction chain, so it must not change).
3. Uploads ``openetruscan_clean_grouped.csv`` alongside it: the same 6,567
   rows plus two columns, ``dup_group_id`` and ``dup_group_size``, produced
   by ``scripts/data_pipeline/add_dup_group_id.py``. 470 rows repeat a
   ``canonical_transliterated`` value under a different id (626 excess rows
   once Leiden markup is normalized); the group columns let any consumer
   split on text groups instead of rows, which is the leak that contaminated
   the frozen v2 classification split (PRE_REGISTRATION.md Deviation D).
4. Replaces the record description with DESCRIPTION_HTML below.
5. Publishes, and prints the new version DOI.

After it prints the DOI, finish the paper trail in this order:
  - release-manifest.json: identifiers.dataset_version_doi -> the new DOI
    (the manifest first, then the surfaces; never the other way round);
  - research/data/README.md: note the grouped file and the new version DOI;
  - scripts/ops/fetch_data.py: optionally add the grouped file with the
    SHA256 this script prints (the original entry stays byte-identical);
  - CHANGELOG.md.

Requires ``ZENODO_TOKEN`` in the environment (a personal token with
``deposit:write`` and ``deposit:actions``). Dry-run by default; pass
``--publish`` to actually publish, because a published Zenodo version is
permanent and cannot be deleted, only superseded.

Usage:
    export ZENODO_TOKEN=...
    python scripts/ops/zenodo_new_version.py \
        --grouped-csv /path/to/openetruscan_clean_grouped.csv          # dry run
    python scripts/ops/zenodo_new_version.py \
        --grouped-csv /path/to/openetruscan_clean_grouped.csv --publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

API = "https://zenodo.org/api"
CURRENT_RECORD_ID = "20075836"

# Keep this free of em dashes and of any claim the release manifest does not
# back. It restates research/data/README.md; if the two drift, that README
# wins and this constant is the bug.
DESCRIPTION_HTML = """\
<p>The OpenEtruscan ML-Ready Corpus is a normalized, quality-tagged dataset of
6,567 Etruscan inscriptions for machine-learning tasks: word and character
embedding training, lacuna restoration, glyph recognition, and diachronic
analysis.</p>

<p>Version 1.1 ships two files:</p>
<ul>
<li><b>openetruscan_clean.csv</b>: the 10-column corpus, byte-identical to
version 1.0 (SHA256 4fc09af94005655bfe26affeeb48295c88606ae23c8dbc33ff5436f9083f69f8).
Columns: id, raw_text, canonical_transliterated, canonical_italic,
canonical_words_only, translation, year_from, year_to, intact_token_ratio,
data_quality.</li>
<li><b>openetruscan_clean_grouped.csv</b>: the same 6,567 rows plus
<b>dup_group_id</b> (first 12 hex chars of the SHA-256 of the text after
Leiden editorial markup is stripped, whitespace collapsed, and case folded)
and <b>dup_group_size</b> (rows sharing that normalized text).</li>
</ul>

<p>Why the new columns: 470 rows repeat a canonical_transliterated value
under a different id, because short formulaic inscriptions (mi, su&#952;ina,
aplu) genuinely recur across distinct artifacts; 626 excess rows share a
group once Leiden variants such as la(u)tni / lautn(i) / laut(n)i are
normalized together. The repeats are correct data and the corpus is
deliberately not deduplicated, but they mean <b>row-level random train/test
splits leak</b>: the same text lands on both sides under different ids. This
contaminated the corpus maintainers' own frozen classification split (25 of
400 test rows; see PRE_REGISTRATION.md Deviation D in the code repository).
Split on dup_group_id, not on rows.</p>

<p>Provenance: roughly 71% of rows derive from the Larth Dataset (Vico and
Spanakis, 2023, CC-BY-4.0) and 29% from Corpus Inscriptionum Etruscarum
Vol. I extractions (public domain). The cleaning pipeline, normalized
columns, quality tags, and group columns are released under CC-BY-4.0.
Schema documentation, editorial conventions, quality tiers, and known
limitations (including what the quality tiers do not filter) are maintained
in research/data/README.md of the code repository:
https://github.com/Eddy1919/openEtruscan</p>
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _req(
    method: str,
    url: str,
    token: str,
    payload: dict | list | None = None,
    data: bytes | None = None,
    ctype: str | None = None,
) -> dict:
    body = json.dumps(payload).encode() if payload is not None else data
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    elif ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--grouped-csv",
        type=Path,
        required=True,
        help="openetruscan_clean_grouped.csv produced by add_dup_group_id.py",
    )
    ap.add_argument("--record-id", default=CURRENT_RECORD_ID)
    ap.add_argument(
        "--publish",
        action="store_true",
        help="Actually publish. Without it: create and inspect the draft only.",
    )
    args = ap.parse_args(argv)

    token = os.environ.get("ZENODO_TOKEN", "")
    if not token:
        print("ERROR: ZENODO_TOKEN is not set.", file=sys.stderr)
        return 1
    if not args.grouped_csv.exists():
        print(f"ERROR: {args.grouped_csv} does not exist.", file=sys.stderr)
        return 1

    grouped_sha = _sha256(args.grouped_csv)
    print(f"grouped csv: {args.grouped_csv} sha256={grouped_sha}", file=sys.stderr)

    # 1. New version draft from the latest published version.
    draft = _req("POST", f"{API}/records/{args.record_id}/versions", token)
    draft_id = draft["id"]
    print(f"draft record id: {draft_id}", file=sys.stderr)

    # 2. Import the previous version's files (keeps openetruscan_clean.csv
    #    byte-identical without re-uploading).
    _req("POST", f"{API}/records/{draft_id}/draft/actions/files-import", token)

    # 3. Upload the grouped file.
    fname = "openetruscan_clean_grouped.csv"
    _req("POST", f"{API}/records/{draft_id}/draft/files", token, payload=[{"key": fname}])
    _req(
        "PUT",
        f"{API}/records/{draft_id}/draft/files/{fname}/content",
        token,
        data=args.grouped_csv.read_bytes(),
        ctype="application/octet-stream",
    )
    _req("POST", f"{API}/records/{draft_id}/draft/files/{fname}/commit", token)

    # 4. Metadata: bump version, replace description.
    meta = _req("GET", f"{API}/records/{draft_id}/draft", token)["metadata"]
    meta["version"] = "1.1.0"
    meta["description"] = DESCRIPTION_HTML
    meta["publication_date"] = meta.get("publication_date") or "2026-08-08"
    _req("PUT", f"{API}/records/{draft_id}/draft", token, payload={"metadata": meta})

    if not args.publish:
        print(f"DRY RUN: draft ready at https://zenodo.org/uploads/{draft_id}", file=sys.stderr)
        print("Inspect it, then re-run with --publish.", file=sys.stderr)
        return 0

    # 5. Publish.
    published = _req("POST", f"{API}/records/{draft_id}/draft/actions/publish", token)
    doi = published.get("doi") or published.get("pids", {}).get("doi", {}).get("identifier", "")
    print(f"published: DOI {doi}")
    print(f"grouped-file sha256 for fetch_data.py: {grouped_sha}")
    print(
        "Now update, in this order: release-manifest.json "
        "(identifiers.dataset_version_doi), research/data/README.md, "
        "scripts/ops/fetch_data.py, CHANGELOG.md."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
