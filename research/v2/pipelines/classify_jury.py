"""Multi-model LLM-jury runner for Stream A (Classification).

Reads the frozen test pool from `classify_split.py` and runs N frontier
models in parallel, each independently labeling every row according to the
codebook (`research/v2/codebooks/classification.md`). Outputs one JSONL row
per (model, inscription).

API providers are pluggable via `--providers`. Default jury is a 3-rater
panel chosen for training-data independence — Claude Opus 4.7 (Anthropic
via Vertex), Gemini 2.5 Pro (Google), and DeepSeek V3 (DeepSeek via Vertex
Model Garden MaaS). All three bill to the same GCP project; no separate
vendor billing relationships needed.

Auth
----
- **Claude (AnthropicVertex)**: run `gcloud auth application-default login`
  on your dev machine, or rely on the VM/Cloud-Run service account in prod.
  No `ANTHROPIC_API_KEY` is read.
- **Gemini**: secret `GOOGLE_API_KEY` is fetched from Secret Manager via
  `_secrets.get_secret`. Pre-resolves to `os.environ["GOOGLE_API_KEY"]` if
  set (useful for local override).
- **DeepSeek (Vertex MaaS)**: same ADC pattern as Claude — no key. Region
  override via `MAAS_VERTEX_REGION` (defaults to us-central1 where Model
  Garden publishes its MaaS endpoints).
- **OpenAI** (kept in the registry but not in the default jury): set
  `OPENAI_API_KEY` if you opt in via `--providers ... gpt-5`.

The script is rate-limited and resumable: it appends to the output file,
skips (model, id) pairs already present, and supports --max-rows for smoke
tests.

This file deliberately does NOT call the APIs from this script's tests; an
operator runs it with keys configured. The schema and prompts are fixed so
that re-runs are reproducible across providers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _secrets import get_secret  # noqa: E402

def _resolve_codebook(language: str) -> Path:
    """Resolve `codebooks/{language}/classification.md` from the repo layout."""
    return Path(__file__).resolve().parent.parent / "codebooks" / language / "classification.md"


# Default to Etruscan for backward compatibility. Override via --language.
CODEBOOK_PATH = _resolve_codebook("etr")

# AnthropicVertex defaults — override via env if your Vertex deployment uses
# a different region or project.
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID", "double-runway-465420-h9")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "europe-west1")


SYSTEM_PROMPT = """You are an expert Etruscan epigrapher. You will receive a single
Etruscan inscription and must classify it into exactly one of seven epigraphic
types, following the codebook below. Reply with a JSON object only — no prose
outside the JSON.

You must follow the decision tree in the codebook in the specified order. If
the evidence is insufficient to reach a confident label, return label = "unsure"
and explain why in `rationale`. Forcing a label without evidence is worse than
returning "unsure"; the unsure row will be adjudicated by a human philologist.
"""

USER_TEMPLATE = """## Codebook (verbatim)
{codebook}

---

## Inscription to classify

- Id: {id}
- Raw text: {raw_text!r}
- Canonical transliteration: {canonical!r}
- Translation (English, may be empty): {translation!r}
- Source tag: {source_tag}

Return JSON with this exact schema:
{{
  "id": {id_json},
  "label": "<one of: funerary, ownership, dedicatory, votive, legal, boundary, commercial, unsure>",
  "confidence": "<high|medium|low>",
  "rationale": "<2-3 sentences citing the codebook decision-tree branch and the textual features that triggered it>",
  "features": ["<feature_1>", "<feature_2>"],
  "alternates_considered": ["<other label seriously considered, if any>"],
  "codebook_version": "v2.0"
}}
"""


@dataclass
class Provider:
    name: str  # e.g. "claude-opus-4-7"
    invoke: Callable[[str, str], str]
    # invoke(system_prompt, user_prompt) -> raw model text


# --- Provider adapters -----------------------------------------------------
# Each adapter is lazy-imported so the script runs even when only one
# provider's SDK is installed.

def _make_anthropic_vertex(model: str) -> Provider:
    """Claude via Vertex AI. Uses Application Default Credentials — no API key."""
    def invoke(system: str, user: str) -> str:
        from anthropic import AnthropicVertex  # type: ignore

        client = AnthropicVertex(region=VERTEX_REGION, project_id=VERTEX_PROJECT_ID)
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts).strip()

    return Provider(name=model, invoke=invoke)


def _make_openai(model: str) -> Provider:
    def invoke(system: str, user: str) -> str:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        resp = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    return Provider(name=model, invoke=invoke)


def _make_gemini(model: str) -> Provider:
    def invoke(system: str, user: str) -> str:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=get_secret("GOOGLE_API_KEY"))
        m = genai.GenerativeModel(model_name=model, system_instruction=system)
        resp = m.generate_content(user)
        return (resp.text or "").strip()

    return Provider(name=model, invoke=invoke)


def _make_vertex_maas(model: str) -> Provider:
    """Open-weights models served via Vertex Model Garden's OpenAI-compatible
    Model-as-a-Service endpoint. Uses Application Default Credentials —
    no separate API key. The same adapter shape works for Llama, Mistral,
    Qwen, etc. — only the `model` id changes.

    Region override: env var `MAAS_VERTEX_REGION` (default us-east5, which
    is where Meta publishes the Llama 4 MaaS endpoint as of 2026-05).

    Path uses /v1/ — the /v1beta1/ form is NOT current and returns 404 even
    for enabled models. Verified by the Console "Use this model" snippet.
    """
    def invoke(system: str, user: str) -> str:
        from google.auth import default  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        from openai import OpenAI  # type: ignore

        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(Request())
        region = os.environ.get("MAAS_VERTEX_REGION", "us-east5")
        base = (
            f"https://{region}-aiplatform.googleapis.com/v1/projects/"
            f"{VERTEX_PROJECT_ID}/locations/{region}/endpoints/openapi"
        )
        client = OpenAI(base_url=base, api_key=credentials.token)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Force JSON-object output. Llama 4 reverts to prose without
            # this flag and burns the max_tokens budget on essays. Mistral
            # / Qwen also benefit. Has no effect on models that already
            # respect the schema (e.g. Claude on Vertex).
            response_format={"type": "json_object"},
        )
        return (resp.choices[0].message.content or "").strip()

    return Provider(name=model, invoke=invoke)


# Default jury: Claude (Vertex/ADC) + Gemini (Secret Manager) + DeepSeek (Vertex MaaS).
# All three bill to the same GCP project (double-runway-465420-h9); no separate
# vendor billing relationships needed. OpenAI is registered but opt-in only.
#
# Vertex model ids: keep these in sync with what's published in Model Garden
# for the billing project. If a generate call returns 404, the id is wrong —
# update here, do not re-invent the timestamp.
PROVIDER_REGISTRY: dict[str, Callable[[], Provider]] = {
    "claude-opus-4-7": lambda: _make_anthropic_vertex("claude-opus-4-7"),
    "claude-sonnet-4-6": lambda: _make_anthropic_vertex("claude-sonnet-4-6"),
    "claude-haiku-4-5": lambda: _make_anthropic_vertex("claude-haiku-4-5@20251001"),
    "gemini-2.5-pro": lambda: _make_gemini("gemini-2.5-pro"),
    "llama-4-scout": lambda: _make_vertex_maas("meta/llama-4-scout-17b-16e-instruct-maas"),
    "llama-4-maverick": lambda: _make_vertex_maas("meta/llama-4-maverick-17b-128e-instruct-maas"),
    "mistral-large-2411": lambda: _make_vertex_maas("mistralai/mistral-large-2411"),
    "gpt-5": lambda: _make_openai("gpt-5"),
    "gpt-4o": lambda: _make_openai("gpt-4o"),
}


# --- Output parsing --------------------------------------------------------

VALID_LABELS = {
    "funerary",
    "ownership",
    "dedicatory",
    "votive",
    "legal",
    "boundary",
    "commercial",
    "unsure",
}
VALID_CONFIDENCES = {"high", "medium", "low"}


def parse_response(insc_id: str, raw: str) -> dict[str, Any]:
    """Parse model output as JSON; on any error mark as 'unsure'."""
    err: str | None = None
    payload: dict[str, Any] = {}
    # Tolerate fenced JSON
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        err = f"json_decode_error: {e}"
    if err is None and (not isinstance(payload, dict)):
        err = "not_a_dict"
        payload = {}
    label = str(payload.get("label", "")).strip().lower()
    if label not in VALID_LABELS:
        err = err or f"invalid_label: {label!r}"
        label = "unsure"
    confidence = str(payload.get("confidence", "")).strip().lower()
    if confidence not in VALID_CONFIDENCES:
        confidence = "low"
    return {
        "id": insc_id,
        "label": label,
        "confidence": confidence,
        "rationale": str(payload.get("rationale", "")).strip(),
        "features": list(payload.get("features") or []),
        "alternates_considered": list(payload.get("alternates_considered") or []),
        "codebook_version": str(payload.get("codebook_version", "v2.0")),
        "parse_error": err,
    }


def iter_test_pool(path: Path) -> Iterator[dict[str, Any]]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_completed_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    done: set[tuple[str, str]] = set()
    with path.open() as f:
        for line in f:
            try:
                row = json.loads(line)
                done.add((row["model"], row["id"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--test-pool", type=Path, required=True,
                    help="Frozen test JSONL produced by classify_split.py")
    ap.add_argument("--out", type=Path, required=True,
                    help="Append-mode JSONL of (model, id, label, …) rows.")
    ap.add_argument("--providers", nargs="+",
                    default=["claude-haiku-4-5", "gemini-2.5-pro", "llama-4-maverick"],
                    help="Provider names from PROVIDER_REGISTRY. "
                         "Default 3-model jury: Claude (Vertex), Gemini, DeepSeek (Vertex MaaS). "
                         "All bill to the same GCP project; no separate API keys needed.")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="Smoke test: cap rows per provider. 0 = no cap.")
    ap.add_argument("--sleep", type=float, default=0.5,
                    help="Seconds to sleep between API calls (politeness).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the prompts that WOULD be sent, do not call any API.")
    ap.add_argument("--language", default="etr",
                    help="ISO-639-3 code selecting which codebook to use. "
                         "Currently supported: etr. Others (osc, fal, rae) are "
                         "scaffolded but the codebooks are still TODOs.")
    args = ap.parse_args(argv)

    codebook_path = _resolve_codebook(args.language)
    if not codebook_path.exists():
        print(f"ERROR: codebook not found at {codebook_path}", file=sys.stderr)
        return 1
    codebook_text = codebook_path.read_text()

    test_rows = list(iter_test_pool(args.test_pool))
    if args.max_rows:
        test_rows = test_rows[: args.max_rows]
    if not test_rows:
        print(f"ERROR: empty test pool at {args.test_pool}", file=sys.stderr)
        return 1

    done = load_completed_keys(args.out)

    # Build a dict keyed by the registry name (e.g. "claude-opus-4-7"), NOT
    # by Provider.name (which the factories set to the versioned underlying
    # model id like "claude-opus-4-7@20251015"). The registry key is what
    # appears in --providers and in the output JSONL's `model` field.
    provider_by_key: dict[str, Provider] = {}
    if not args.dry_run:
        for name in args.providers:
            factory = PROVIDER_REGISTRY.get(name)
            if factory is None:
                print(f"ERROR: unknown provider {name!r}", file=sys.stderr)
                return 1
            try:
                provider_by_key[name] = factory()
            except ImportError as e:
                print(f"ERROR: provider {name!r} needs an SDK: {e}", file=sys.stderr)
                return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sink = args.out.open("a")

    total = len(test_rows) * len(args.providers)
    completed = 0
    skipped = 0
    errors = 0

    try:
        for row in test_rows:
            user_prompt = USER_TEMPLATE.format(
                codebook=codebook_text,
                id=row["id"],
                id_json=json.dumps(row["id"]),
                raw_text=row.get("raw_text", ""),
                canonical=row.get("canonical_transliterated", ""),
                translation=row.get("translation", ""),
                source_tag=row.get("source_tag", ""),
            )

            for provider_name in args.providers:
                key = (provider_name, row["id"])
                if key in done:
                    skipped += 1
                    continue
                if args.dry_run:
                    print(f"--- {provider_name} :: {row['id']} ---")
                    print(user_prompt[:400] + "..." if len(user_prompt) > 400 else user_prompt)
                    continue
                provider = provider_by_key[provider_name]
                try:
                    raw = provider.invoke(SYSTEM_PROMPT, user_prompt)
                except Exception as e:  # noqa: BLE001 — log and skip
                    errors += 1
                    print(f"  [{provider_name} {row['id']}] api_error: {e}", file=sys.stderr)
                    sink.write(json.dumps({
                        "model": provider_name,
                        "id": row["id"],
                        "label": "unsure",
                        "confidence": "low",
                        "rationale": "",
                        "features": [],
                        "alternates_considered": [],
                        "codebook_version": "v2.0",
                        "parse_error": f"api_error: {e}",
                    }, ensure_ascii=False) + "\n")
                    sink.flush()
                    time.sleep(args.sleep)
                    continue
                parsed = parse_response(row["id"], raw)
                parsed["model"] = provider_name
                sink.write(json.dumps(parsed, ensure_ascii=False) + "\n")
                sink.flush()
                completed += 1
                if completed % 25 == 0:
                    print(f"  progress: {completed}/{total - skipped} (errors={errors})",
                          file=sys.stderr)
                time.sleep(args.sleep)
    finally:
        sink.close()

    print(f"Done. completed={completed} skipped={skipped} errors={errors}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
