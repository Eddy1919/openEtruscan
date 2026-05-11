#!/usr/bin/env bash
# rosetta-eval-v1 — frozen reference benchmark for the Rosetta vector space.
#
# Runs the three eval columns the methodology demands:
#   1. random       — analytical chance under uniform random retrieval
#   2. levenshtein  — edit-distance baseline against the Latin vocab
#   3. model        — whatever model the API under test is currently serving
#
# Each column uses the *same* held-out test split (T1.3), the *same*
# min_confidence=medium filter, and the *same* metric definitions
# (strict@k, semantic-field@k, coverage@threshold). The model column is
# parameterised by --api-url so the benchmark grades a protocol, not a
# specific checkpoint — point at a staging API to evaluate a new model.
#
# Output: a single JSON document with top-level keys
#   {benchmark, generated_at_utc, api_url, random, levenshtein, model}
# Pipe to a file (or --output), or send to stdout for piping into jq.
#
# Usage:
#   bash evals/rosetta_eval_v1.sh --api-url https://api.openetruscan.com
#   bash evals/rosetta_eval_v1.sh --api-url http://localhost:8000 --output eval/v1.json
#
# Reproducibility notes: research/notes/reproduce-rosetta-eval-v1.md

set -euo pipefail

# ── Argument parsing ───────────────────────────────────────────────────
API_URL=""
OUTPUT=""
NO_PACE=""

usage() {
    cat >&2 <<EOF
Usage: $0 --api-url <URL> [--output <file>] [--no-pace]

Required:
  --api-url URL       Base URL of the API under test (e.g. https://api.openetruscan.com).

Optional:
  --output FILE       Write the JSON to FILE; default is stdout.
                      If FILE is "auto" the script writes
                      eval/rosetta-eval-v1-<UTC-timestamp>.json
                      (creates the eval/ directory if needed).
  --no-pace           Skip the 2.05 s between-request delay (local APIs only).
  -h, --help          Show this message and exit.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-url)
            API_URL="$2"; shift 2 ;;
        --api-url=*)
            API_URL="${1#*=}"; shift ;;
        --output)
            OUTPUT="$2"; shift 2 ;;
        --output=*)
            OUTPUT="${1#*=}"; shift ;;
        --no-pace)
            NO_PACE="--no-pace"; shift ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "Unknown argument: $1" >&2
            usage; exit 2 ;;
    esac
done

if [[ -z "$API_URL" ]]; then
    echo "ERROR: --api-url is required" >&2
    usage
    exit 2
fi

# ── Locate the eval harness regardless of cwd ──────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS="$SCRIPT_DIR/run_rosetta_eval.py"

if [[ ! -f "$HARNESS" ]]; then
    echo "ERROR: cannot find $HARNESS" >&2
    exit 2
fi

# ── Workspace for intermediate JSON ────────────────────────────────────
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

RANDOM_JSON="$WORKDIR/random.json"
LEV_JSON="$WORKDIR/levenshtein.json"
LABSE_JSON="$WORKDIR/labse.json"
V4_JSON="$WORKDIR/v4.json"

run_column() {
    # $1 = display label
    # $2 = --baseline arg (one of random / levenshtein / none)
    # $3 = output JSON path
    # $4 = optional --embedder alias (default: omitted → LaBSE)
    local label="$1"
    local baseline="$2"
    local out="$3"
    local embedder="${4-}"
    echo "▶ ${label}  (baseline=${baseline}${embedder:+, embedder=${embedder}})" >&2
    python "$HARNESS" \
        --api-url "$API_URL" \
        --benchmark rosetta-eval-v1 \
        --baseline "$baseline" \
        ${embedder:+--embedder "$embedder"} \
        --json \
        $NO_PACE \
        > "$out"
}

# random is purely analytical — no API traffic, runs in <1s
run_column "random      " random       "$RANDOM_JSON"
# levenshtein pulls /neural/rosetta/vocab once, then computes locally
run_column "levenshtein " levenshtein  "$LEV_JSON"
# model under test (default partition — LaBSE/v1) — full /neural/rosetta traffic, paced
run_column "labse       " none         "$LABSE_JSON"
# T2.3 head-to-head column: same harness against the xlmr-lora-v4 partition.
# If the v4 partition is incomplete on the target language (e.g. T2.3 only
# ingested ett but not lat), this column may show empty neighbours — that
# is itself a publishable finding, not an error.
run_column "v4          " none         "$V4_JSON"  "xlmr-lora-v4"

GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Combine the four reports into one. python -c (not jq) so we don't add
# a dependency the rest of the repo doesn't already need. Both `model` and
# `labse` carry the LaBSE numbers — `model` is preserved as the historical
# key from the pre-T2.4 schema so older consumers keep working.
python <<PY > "$WORKDIR/combined.json"
import json
labse = json.load(open("$LABSE_JSON"))
out = {
    "benchmark": "rosetta-eval-v1",
    "generated_at_utc": "$GENERATED_AT",
    "api_url": "$API_URL",
    "random": json.load(open("$RANDOM_JSON")),
    "levenshtein": json.load(open("$LEV_JSON")),
    "labse": labse,
    "model": labse,
    "v4": json.load(open("$V4_JSON")),
}
json.dump(out, __import__("sys").stdout, indent=2, ensure_ascii=False, default=str)
PY

if [[ -z "$OUTPUT" ]]; then
    cat "$WORKDIR/combined.json"
elif [[ "$OUTPUT" == "auto" ]]; then
    mkdir -p "$REPO_ROOT/eval"
    TS="$(date -u +%Y%m%dT%H%M%SZ)"
    DEST="$REPO_ROOT/eval/rosetta-eval-v1-${TS}.json"
    cp "$WORKDIR/combined.json" "$DEST"
    echo "Wrote $DEST" >&2
else
    cp "$WORKDIR/combined.json" "$OUTPUT"
    echo "Wrote $OUTPUT" >&2
fi
