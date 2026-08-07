#!/usr/bin/env python3
"""Fail when a public surface drifts from `release-manifest.json`.

The manifest is the single source of truth for versions, corpus counts,
licences, and DOIs. Every file listed under `surfaces.checked` restates some
of those values in its own format; this script re-reads each one and asserts
agreement.

An external audit in 2026-08 found four different version numbers across four
public surfaces (repo 1.2.0, PyPI 0.3.0, website footer 2.0.0, citation page
0.5.0) and three corpus totals with no machine-readable reconciliation. Each
drift was individually harmless and collectively meant the project had no
single public truth. This gate is the mechanism that keeps that from
recurring — the surfaces cannot silently disagree again, because CI reads
them all against one file.

Surfaces outside this repository (PyPI, Hugging Face, the frontend repo) are
listed under `surfaces.manual` in the manifest with their observed state, and
are the maintainer's release-checklist responsibility. This script reports
them but cannot enforce them; `--strict-manual` turns any manual surface not
marked resolved into a failure, for use at release time.

Usage:
    python scripts/ops/check_release_truth.py
    python scripts/ops/check_release_truth.py --strict-manual   # release gate
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "release-manifest.json"

# Manual surfaces in these states are known-bad and deliberately recorded as
# such; they fail only under --strict-manual. Any other status is either
# resolved or unrecognised, and an unrecognised status should be loud.
_KNOWN_MANUAL_STATES = {"stale", "carries_retracted_claim"}
_RESOLVED_PREFIXES = ("fixed", "resolved", "ok")


class Failures:
    """Collects every mismatch so one run reports all of them, not just the first."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def check(self, ok: bool, surface: str, message: str) -> None:
        if not ok:
            self.items.append(f"{surface}: {message}")

    def equal(self, surface: str, field: str, observed: Any, expected: Any) -> None:
        self.check(
            observed == expected,
            surface,
            f"{field} is {observed!r}, manifest says {expected!r}",
        )

    def contains(self, surface: str, haystack: str, needle: str, what: str) -> None:
        self.check(needle in haystack, surface, f"does not state {what} ({needle!r})")


def _load_manifest() -> dict[str, Any]:
    with MANIFEST.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


def check_pyproject(m: dict[str, Any], f: Failures) -> None:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    project = pyproject["project"]
    f.equal("pyproject.toml", "project.version", project["version"], m["version"])
    f.equal(
        "pyproject.toml",
        "project.license",
        project.get("license", {}).get("text"),
        m["licences"]["code"]["spdx"],
    )


def check_citation(m: dict[str, Any], f: Failures) -> None:
    path = ROOT / "CITATION.cff"
    cff = yaml.safe_load(path.read_text(encoding="utf-8"))
    ids = m["identifiers"]

    f.equal("CITATION.cff", "version", cff["version"], m["version"])
    f.equal("CITATION.cff", "date-released", cff["date-released"], m["date_released"])
    f.equal("CITATION.cff", "license", cff["license"], m["licences"]["code"]["spdx"])
    # The top-level DOI must be the concept DOI: it is what "cite the project"
    # means, and a version DOI here silently pins every citation to one snapshot.
    f.equal("CITATION.cff", "doi", cff["doi"], ids["concept_doi"])

    preferred = cff.get("preferred-citation", {})
    f.equal(
        "CITATION.cff",
        "preferred-citation.doi",
        preferred.get("doi"),
        ids["dataset_version_doi"],
    )
    _check_url_is_canonical(m, f, "CITATION.cff", preferred.get("url"))

    published = m["corpus_counts"]["published"]["count"]
    archival = m["corpus_counts"]["archival"]["count"]
    notes = preferred.get("notes", "")
    f.contains("CITATION.cff", notes, f"{published:,}", "the published corpus count")
    f.contains("CITATION.cff", notes, f"{archival:,}", "the archival corpus count")


def check_codemeta(m: dict[str, Any], f: Failures) -> None:
    codemeta = json.loads((ROOT / "codemeta.json").read_text(encoding="utf-8"))
    f.equal("codemeta.json", "version", codemeta["version"], m["version"])
    for ref in codemeta.get("referencePublication", []):
        if ref.get("@type") == "Dataset" and "OpenEtruscan" in ref.get("name", ""):
            _check_url_is_canonical(m, f, "codemeta.json", ref.get("url"))


def check_security(m: dict[str, Any], f: Failures) -> None:
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    supported = m["supported_versions"]
    for series in supported["supported"] + supported["security_only"]:
        f.contains("SECURITY.md", text, series, f"the {series} series")
    # A released major that the policy never mentions is the actual failure
    # mode here: SECURITY.md sat on 0.3.x for two majors after 0.3 shipped.
    current_series = ".".join(m["version"].split(".")[:2]) + ".x"
    f.check(
        current_series in supported["supported"],
        "release-manifest.json",
        f"shipped version {m['version']} is not in supported_versions.supported",
    )


def check_readme(m: dict[str, Any], f: Failures) -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for key, spec in m["corpus_counts"].items():
        if key.startswith("$"):
            continue
        f.contains("README.md", text, f"{spec['count']:,}", f"the {key} count")
    # Every count README states must be one the manifest knows about. A stray
    # four-digit total next to the word "inscriptions" is how 5,932 entered
    # the prose in the first place.
    known = {
        f"{spec['count']:,}" for key, spec in m["corpus_counts"].items() if not key.startswith("$")
    }
    for match in re.finditer(r"\*\*([\d,]{5,})\s+(?:unified\s+)?inscriptions?\*\*", text):
        f.check(
            match.group(1) in known,
            "README.md",
            f"states {match.group(1)} inscriptions, which is not a manifest corpus count",
        )


def check_changelog(m: dict[str, Any], f: Failures) -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # release.yml extracts release notes by this exact heading; no section
    # means the tag push fails after the tag already exists.
    f.contains("CHANGELOG.md", text, f"## [{m['version']}]", "a section for the current version")


def check_model_cards(m: dict[str, Any], f: Failures) -> None:
    for model in m["models"]:
        card_path = model.get("card")
        if not card_path:
            continue
        path = ROOT / card_path
        if not path.exists():
            f.check(False, card_path, "declared in the manifest but missing on disk")
            continue
        text = path.read_text(encoding="utf-8")
        # Model cards carry their own BibTeX; it drifts because nothing reads it.
        for match in re.finditer(r"version\s*=\s*\{([\d.]+)\}", text):
            f.check(
                match.group(1) == m["version"],
                card_path,
                f"BibTeX version = {{{match.group(1)}}}, manifest says {m['version']}",
            )
        # Accept either prose form ("Apache-2.0" / "Apache 2.0"); the card is
        # written for humans and the punctuation is not the claim.
        spdx = m["licences"]["model_weights"]["spdx"]
        f.check(
            spdx in text or spdx.replace("-", " ") in text,
            card_path,
            f"does not state the model-weights licence ({spdx})",
        )
        _check_retraction(model, card_path, text, f)


def _check_retraction(model: dict[str, Any], card_path: str, text: str, f: Failures) -> None:
    """A card must not still carry a claim the project has retracted.

    This is the assertion the whole gate exists for. The classifier card
    advertised "99% Macro F1" for months after the repository, the website,
    and the changelog had all retracted it — every in-repo surface was correct
    and the one surface a citing scholar actually reaches was not. A card that
    reprints its own retracted number is worse than no card.
    """
    retraction = model.get("retracted_claim")
    if not retraction:
        return

    # The bare figure, however it is punctuated ("99%", "99 %", "0.99 macro").
    figure = re.search(r"[\d.]+\s*%?", retraction["value"])
    if figure:
        stale = re.escape(figure.group(0).strip().rstrip("%"))
        pattern = rf"(?<![\d.]){stale}\s*%"
        for match in re.finditer(pattern, text):
            line = text.count("\n", 0, match.start()) + 1
            # A retraction notice necessarily quotes the number it retracts.
            window = text[max(0, match.start() - 300) : match.end() + 300].lower()
            if "retract" in window:
                continue
            f.check(
                False,
                f"{card_path}:{line}",
                f"restates the retracted claim {match.group(0)!r} outside a "
                f"retraction notice — corrected value is "
                f"{retraction['corrected_range']}",
            )

    f.contains(card_path, text.lower(), "retract", "that the earlier claim was retracted")


def check_manual_surfaces(m: dict[str, Any], f: Failures, strict: bool) -> list[str]:
    notes: list[str] = []
    for surface in m["surfaces"]["manual"]:
        status = surface["status"]
        resolved = status.startswith(_RESOLVED_PREFIXES)
        if resolved:
            continue
        line = (
            f"{surface['surface']}: expected {surface['expected']!r}, "
            f"observed {surface['observed']!r} — {surface['action']}"
        )
        if status not in _KNOWN_MANUAL_STATES:
            f.check(False, "release-manifest.json", f"unrecognised manual status {status!r}")
        if strict:
            f.check(False, "manual surface", line)
        else:
            notes.append(line)
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict-manual",
        action="store_true",
        help="treat unresolved out-of-repo surfaces as failures (release gate)",
    )
    args = parser.parse_args()

    manifest = _load_manifest()
    failures = Failures()

    check_pyproject(manifest, failures)
    check_citation(manifest, failures)
    check_codemeta(manifest, failures)
    check_security(manifest, failures)
    check_readme(manifest, failures)
    check_changelog(manifest, failures)
    check_model_cards(manifest, failures)
    notes = check_manual_surfaces(manifest, failures, args.strict_manual)

    for note in notes:
        print(f"note: {note}", file=sys.stderr)

    if failures.items:
        print(
            f"\nrelease truth check FAILED ({len(failures.items)} "
            f"mismatch{'es' if len(failures.items) > 1 else ''}):",
            file=sys.stderr,
        )
        for item in failures.items:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nEdit release-manifest.json first, then the surface. "
            "The manifest is the source of truth, not the file you were editing.",
            file=sys.stderr,
        )
        return 1

    print(f"release truth check passed — {manifest['version']} consistent across surfaces")
    return 0


def _check_url_is_canonical(m: dict[str, Any], f: Failures, surface: str, url: str | None) -> None:
    """Citation URLs must resolve. `/data` was cited for months and 404s."""
    if url is None:
        return
    canonical = {v for k, v in m["canonical_urls"].items() if not k.startswith("$")}
    f.check(
        url in canonical,
        surface,
        f"cites {url!r}, which is not in manifest.canonical_urls (does it resolve?)",
    )


if __name__ == "__main__":
    sys.exit(main())
