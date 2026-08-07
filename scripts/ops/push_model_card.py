#!/usr/bin/env python3
"""Push a version-controlled model card to the Hugging Face Hub.

Model cards are the surface a citing scholar reaches first and the one this
project has been worst at maintaining: the classifier card advertised a
retracted "99% Macro F1" for months after the repository had corrected it.
The fix is to keep every card in git under `models/<id>/README.md`, let
`scripts/ops/check_release_truth.py` gate it against `release-manifest.json`,
and push from that checked copy rather than editing on the Hub.

This deliberately does NOT reuse `hf_sync.py --upload`. That helper calls
`upload_folder` on the git-ignored `data/models/` tree, which would push
whatever happens to be on the maintainer's disk — the opposite of a
reviewable, reproducible correction. This script uploads exactly one file.

Requires `HF_TOKEN` in the environment or `.env`. Dry-run by default: the
upload only happens with `--push`, because it publishes to a public model
repository and is not silently reversible.

Usage:
    python scripts/ops/push_model_card.py openetruscan-classifier
    python scripts/ops/push_model_card.py openetruscan-classifier --push
    python scripts/ops/push_model_card.py --all --push
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "release-manifest.json"


def _load_models() -> list[dict[str, Any]]:
    with MANIFEST.open(encoding="utf-8") as fh:
        manifest: dict[str, Any] = json.load(fh)
    models: list[dict[str, Any]] = manifest["models"]
    return models


def _resolve(models: list[dict[str, Any]], model_id: str) -> dict[str, Any]:
    for model in models:
        if model["id"] == model_id:
            return model
    known = ", ".join(m["id"] for m in models)
    raise SystemExit(f"unknown model {model_id!r}; manifest knows: {known}")


def _token() -> str:
    token = os.getenv("HF_TOKEN")
    if not token:
        # Match hf_sync.py's behaviour so both scripts read the same place.
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv(ROOT / ".env")
            load_dotenv(ROOT / ".env.local")
            token = os.getenv("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN not set. Export it or put it in .env — it is never committed.")
    return token


def push(model: dict[str, Any], *, dry_run: bool) -> int:
    card_path_rel = model.get("card")
    if not card_path_rel:
        print(f"{model['id']}: no card declared in the manifest, skipping")
        return 0

    card = ROOT / card_path_rel
    if not card.exists():
        print(f"{model['id']}: {card_path_rel} missing on disk", file=sys.stderr)
        return 1

    repo_id = model["hub"]
    size = card.stat().st_size
    print(f"{model['id']}: {card_path_rel} ({size:,} bytes) -> {repo_id}/README.md")

    if dry_run:
        print("  dry run — pass --push to upload. This publishes to a public repo.")
        return 0

    from huggingface_hub import HfApi

    HfApi().upload_file(
        path_or_fileobj=str(card),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="model",
        token=_token(),
        commit_message=(
            "docs: correct model card against release-manifest.json "
            "(retracts the 99% macro F1 claim)"
        ),
    )
    print(f"  pushed. Verify: https://huggingface.co/{repo_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_id", nargs="?", help="model id as listed in the manifest")
    parser.add_argument("--all", action="store_true", help="push every card in the manifest")
    parser.add_argument(
        "--push",
        action="store_true",
        help="actually upload (default is a dry run — this publishes publicly)",
    )
    args = parser.parse_args()

    models = _load_models()
    if args.all:
        targets = models
    elif args.model_id:
        targets = [_resolve(models, args.model_id)]
    else:
        parser.error("give a model id or --all")

    if args.push:
        _token()  # fail fast before touching the network

    return max(push(m, dry_run=not args.push) for m in targets)


if __name__ == "__main__":
    sys.exit(main())
