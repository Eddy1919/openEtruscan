#!/usr/bin/env python3
"""Regenerate docs/openapi.json from the FastAPI app.

The committed spec is a build artifact of `openetruscan.api.server:app`;
whenever the API surface or the package version changes, re-run:

    python scripts/ops/generate_openapi.py

CI diffs the committed file against a fresh regeneration and fails on
drift. Output is deterministic (sorted keys, 2-space indent, trailing
newline), so running the script twice yields byte-identical files.

Importing the app needs no live database: the lifespan (DB pool, model
loading) only runs on server startup, never on import or `app.openapi()`.
"""

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Same pattern as tests/conftest.py: settings() captures os.environ at first
# openetruscan import, so the environment must be pinned before importing
# the app module.
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("ENABLE_DOCS", "1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs" / "openapi.json",
        help="output path (default: docs/openapi.json)",
    )
    args = parser.parse_args()

    from openetruscan.api.server import app

    schema = app.openapi()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out} (API version {schema['info']['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
