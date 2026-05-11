#!/usr/bin/env python3
"""Push the etr-lora-v4 adapter + model card to HuggingFace Hub.

Skeleton script — the user owns the HuggingFace account and runs this
manually after the v4 adapter has been pulled down from GCS.

PREREQUISITES
-------------

1. `HF_TOKEN` env var set, with write access to the `openetruscan`
   organisation on HuggingFace Hub. Either export it or put it in the
   repo-root `.env` (loaded automatically below, matching the existing
   `scripts/ops/hf_sync.py` convention).

2. The adapter files pulled down from GCS to a local checkout. The
   default location this script reads from is
   `./adapters/etr-lora-v4/` relative to the repo root. To populate it:

   ```bash
   gsutil -m cp -r \
     gs://openetruscan-rosetta/adapters/etr-lora-v4 \
     ./adapters/etr-lora-v4
   ```

   Expected contents (matching `models/etr-lora-v3/`):
     adapter_config.json
     adapter_model.safetensors
     special_tokens_map.json
     tokenizer.json
     tokenizer_config.json
     training_metadata.json

3. The model card README at `models/etr-lora-v4/README.md` lives in
   THIS repo (committed alongside this script). It gets uploaded
   as the Hub repo's `README.md`.

USAGE
-----

```bash
# Dry-run (default) — shows what would be pushed, doesn't touch the Hub.
python scripts/hub/push_etr_lora_v4.py

# Actual push (idempotent — create_repo + upload_folder with exist_ok).
python scripts/hub/push_etr_lora_v4.py --push

# Override the local adapter dir or the target repo id:
python scripts/hub/push_etr_lora_v4.py --push \
  --adapter-dir ./adapters/etr-lora-v4 \
  --repo-id openetruscan/etr-lora-v4
```

WHAT THIS SCRIPT DELIBERATELY DOES NOT DO
------------------------------------------

- It does not pull from GCS. That is a user-driven `gsutil` step
  (this repo's workflow style — surgical building blocks, not
  orchestration scripts).
- It does not auto-create the `openetruscan` org. The user must have
  org-write access on the configured HF account.
- It does not re-run the eval or regenerate the README. Both are
  source-of-truth in this repo; treat the README here as canonical.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REPO_ID = "openetruscan/etr-lora-v4"
DEFAULT_ADAPTER_DIR = REPO_ROOT / "adapters" / "etr-lora-v4"
MODEL_CARD_PATH = REPO_ROOT / "models" / "etr-lora-v4" / "README.md"

# Files we expect in the adapter dir. Used for the pre-flight check;
# the upload itself is folder-based (anything not listed here is also
# uploaded, intentionally — we don't want a typo here to silently
# drop a file from the Hub deposit).
EXPECTED_ADAPTER_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "training_metadata.json",
)


def _load_env() -> None:
    """Load .env at repo root if python-dotenv is available.

    Matches the convention in scripts/ops/hf_sync.py — keep both
    in lockstep if you change it here.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")


def _check_adapter_dir(adapter_dir: Path) -> list[str]:
    missing = []
    for name in EXPECTED_ADAPTER_FILES:
        if not (adapter_dir / name).is_file():
            missing.append(name)
    return missing


def _list_upload_payload(adapter_dir: Path) -> list[Path]:
    return sorted(p for p in adapter_dir.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--adapter-dir",
        type=Path,
        default=DEFAULT_ADAPTER_DIR,
        help=f"Local adapter checkout (default: {DEFAULT_ADAPTER_DIR})",
    )
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO_ID,
        help=f"HuggingFace Hub repo id (default: {DEFAULT_REPO_ID})",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Actually upload. Without this flag, dry-runs (prints intended actions).",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Create the repo as private (default: public).",
    )
    args = parser.parse_args()

    _load_env()
    token = os.getenv("HF_TOKEN")

    print(f"Repo:        {args.repo_id}")
    print(f"Adapter dir: {args.adapter_dir}")
    print(f"Model card:  {MODEL_CARD_PATH}")
    print(f"Visibility:  {'private' if args.private else 'public'}")
    print(f"Mode:        {'PUSH' if args.push else 'DRY-RUN (pass --push to upload)'}")
    print()

    if not MODEL_CARD_PATH.is_file():
        print(f"FATAL: model card not found at {MODEL_CARD_PATH}", file=sys.stderr)
        return 2

    if not args.adapter_dir.is_dir():
        print(
            f"FATAL: adapter directory not found at {args.adapter_dir}. "
            f"Run:\n  gsutil -m cp -r gs://openetruscan-rosetta/adapters/etr-lora-v4 "
            f"{args.adapter_dir}",
            file=sys.stderr,
        )
        return 2

    missing = _check_adapter_dir(args.adapter_dir)
    if missing:
        print(
            f"FATAL: missing expected adapter files in {args.adapter_dir}: {missing}",
            file=sys.stderr,
        )
        return 2

    payload = _list_upload_payload(args.adapter_dir)
    print(f"Adapter files to upload ({len(payload)}):")
    for p in payload:
        print(f"  - {p.relative_to(args.adapter_dir)}")
    print(f"+ README.md (from {MODEL_CARD_PATH.relative_to(REPO_ROOT)})")
    print()

    if not args.push:
        print("Dry-run complete. Re-run with --push to upload.")
        return 0

    if not token:
        print("FATAL: HF_TOKEN not set in env or .env", file=sys.stderr)
        return 2

    # Lazy import so dry-run works without huggingface_hub installed.
    from huggingface_hub import HfApi

    api = HfApi()

    print(f"Ensuring repo {args.repo_id} exists ...")
    api.create_repo(
        repo_id=args.repo_id,
        repo_type="model",
        token=token,
        exist_ok=True,
        private=args.private,
    )

    print(f"Uploading adapter folder from {args.adapter_dir} ...")
    api.upload_folder(
        folder_path=str(args.adapter_dir),
        repo_id=args.repo_id,
        repo_type="model",
        token=token,
        commit_message="Upload etr-lora-v4 adapter weights",
    )

    print(f"Uploading model card README from {MODEL_CARD_PATH} ...")
    api.upload_file(
        path_or_fileobj=str(MODEL_CARD_PATH),
        path_in_repo="README.md",
        repo_id=args.repo_id,
        repo_type="model",
        token=token,
        commit_message="Sync model card from openEtruscan repo",
    )

    print()
    print(f"Done. Verify at: https://huggingface.co/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
