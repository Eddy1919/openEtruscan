#!/usr/bin/env python3
"""
Reasoning-based labeler for the cleaned Etruscan corpus.

Encodes the rubric I'd apply if labeling each row by hand, in a
priority-ordered cascade. Every label carries:
  - a category (one of the 7 scholarly classes)
  - a confidence (high / medium / low / skip)
  - the signal that triggered it (so the user can audit)

Priority order (first match wins):
  1. Hand-labeled gold (the 184 rows already in inscription_labels.csv)
  2. Strong canonical-Etruscan keywords (suθi → funerary, deity name → dedicatory, …)
  3. Strong English-translation phrases (lived for / dedicated to / I am the X of …)
  4. Structural patterns in MT-junk translations (mr-X mrs-Y son/daughter → funerary kinship list)
  5. Mid-confidence defaults (name-only short canonical → funerary; mi+name formula → ownership)
  6. SKIP for rows with no signal at all

Output: openetruscan_labels.csv with columns:
   id, label, confidence, signal_source
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

CLEAN_CSV = Path("/home/edoardo/Documents/openEtruscan/openetruscan_clean.csv")
GOLD_CSV = Path("/home/edoardo/Documents/openEtruscan/inscription_labels.csv")
OUT_CSV = Path("/home/edoardo/Documents/openEtruscan/openetruscan_labels.csv")


# -----------------------------------------------------------------------
# Strong canonical-Etruscan keyword groups (whole-token match for safety)
# -----------------------------------------------------------------------

# Tomb / death / kinship-on-tomb terms
FUNERARY_ETR = {
    "suθi", "suθina", "suθiθ", "σuθi", "σuθiθ", "σuθic",
    "lupu", "lupuce", "svalce", "svalθas", "avils", "avil",
    "murce", "ceriχunce", "tamera", "ceχa", "hinthial",
    "lautni", "lavtni", "puia", "clan", "sec", "ati", "papacs",
    "nefts", "huσur", "θapna", "zivas", "clenaraśi", "atiu", "atial",
}

# Dedication verbs + Etruscan pantheon
DEDICATORY_ETR = {
    "turce", "mulvanice", "muluvanice", "mulu",
    "alpan", "fleres", "flerχva", "cver",
    "aisera", "ais", "eiser", "aisna", "tuθina", "tmia",
    # deities
    "tinia", "tinśi", "uni", "unial", "menerva", "menrvas",
    "θesan", "θeśan", "turan", "fuflunś", "fufluns",
    "hercle", "selva", "selvans", "caθa", "leθn", "vetsl",
    "śuri", "śuris", "saucne", "aritimi", "aplu", "sethlans",
    "turms", "heramaśva", "θemiasa", "śacni", "śacnicla",
    "thufltha", "θuflθa", "θuflθicla", "rath",
}

VOTIVE_ETR = {
    # Strong votive markers — "thank offering" semantics
    "mlaχ",  # also dedicatory; treat as votive when paired with deity
}

LEGAL_ETR = {
    "zilχ", "zilχnu", "zilc", "zilaθ", "zilaχnθas", "zilacal", "zilci",
    "eprθnev", "purθ", "marunuχ", "lucair", "cepen", "tenu", "camθi",
    "amce", "eslz", "parχis", "tenθas", "naper",
}

BOUNDARY_ETR = {
    "tular", "tularias", "rasna", "raśnas", "raśneś",
    "spura", "spural", "spurana", "meθlum", "meθlumθ", "methlumθ",
    "vaχr",
}

COMMERCIAL_ETR = {
    "presnts", "pruχ", "aska", "culiχna", "θafna", "qutum",
}

# Vessel-mark indicators (when paired with "mi" → ownership)
VESSEL_ETR = {
    "aska", "culiχna", "θafna", "qutum", "pruχ",
    "lekythos", "skyphos", "kylix", "olla", "aryballos",
}


def tokenize(s: str) -> list[str]:
    return re.findall(r"[\wθχσφξςśŚšńṛṭḥṿṣṇẹ𐌀-𐌟']+", s, flags=re.UNICODE)


def has_any(tokens: set[str], vocab: set[str]) -> bool:
    return bool(tokens & vocab)


# -----------------------------------------------------------------------
# Translation-side regexes
# -----------------------------------------------------------------------

# Real English translation signals
RE_FUNERARY_EN = re.compile(
    r"\b(lived for|dead at|died at|tomb|sarcophagus|buried|funerary|"
    r"freedman|freedwoman|son of|daughter of|wife of|husband of|"
    r"years of age|years\b|interred|cippus of the tomb|stele|"
    r"having held|having produced|having lived)",
    re.I,
)
RE_DEDICATORY_EN = re.compile(
    r"\b(dedicated|sacred|votive offering|thank offering|"
    r"for the divinity|to the divinity|to the gods|"
    r"i \(was dedicated\)|i \(am\) of|sanctuary|"
    r"in honor of|on behalf of)",
    re.I,
)
RE_OWNERSHIP_EN = re.compile(
    r"\b(i \(am\) the|i \(am the|i \(belong to\)|i \(was\) given|"
    r"gave me|made me|painted by|don't take me|don't steal me|"
    r"vessel of|cup of|bowl of|jug of|plate of|flask of|olla of|"
    r"pyxis of|chalice of|aryballos of|skyphos of|kylix of|"
    r"the work of|workshop of|the \(palette\) of|the \(ceramic\) of|"
    r"\(was\) given to|\(was\) donated|presented by|"
    r"property of|the \(stele\) of)",
    re.I,
)
RE_VOTIVE_EN = re.compile(
    r"\b(votive offering|thank offering|as a votive|as a thank)",
    re.I,
)
RE_BOUNDARY_EN = re.compile(
    r"\b(boundary|of the community|sacred area)",
    re.I,
)
RE_LEGAL_EN = re.compile(
    r"\b(magistrate|praetor|governor|haruspex|voting tribe|"
    r"this \(contract\)|written above|served as governor|"
    r"the general|of the office)",
    re.I,
)
RE_COMMERCIAL_EN = re.compile(
    r"\b(weighed|coins?|talents?|drachma)",
    re.I,
)

# Larth MT-junk: kinship-list pattern (very high precision for funerary)
RE_KINSHIP_JUNK = re.compile(
    r"(mr-|mrs-|ms-).{2,}?(son|daughter|wife|husband|freedman|slave|"
    r"sons|daughters|spit|s-daughter|s-son|of-age|years|years-old)",
    re.I,
)
# Larth MT-junk: deity reference
RE_DEITY_JUNK = re.compile(
    r"\b(turan|tinia|uni|menerva|minerva|fufluns|bacchus|hercle|"
    r"hercules|aplu|apollo|turms|hermes|sethlans|hephaestus|selvans|"
    r"silvanus|catha|thufltha|thusu|vesna|aritimi|artemis|saturn|"
    r"the-god|goddess|divinit)",
    re.I,
)


# -----------------------------------------------------------------------
# Reasoning hierarchy
# -----------------------------------------------------------------------

def label_row(canonical: str, translation: str, words_only: str
              ) -> tuple[str | None, str, str]:
    """Return (label, confidence, signal_source). label=None means SKIP."""
    canon_tokens = set(tokenize(canonical.lower()))
    words_tokens = set(tokenize(words_only.lower()))
    tokens = canon_tokens | words_tokens

    # === Tier 1: strong canonical Etruscan keywords ====================
    # Funerary keywords are very high precision (suθi etc are unambiguous)
    if has_any(tokens, FUNERARY_ETR):
        return ("funerary", "high", "etr_keyword:funerary")

    # Deity name + dedication verb → dedicatory
    has_deity = has_any(tokens, DEDICATORY_ETR)
    if has_deity:
        # If a thank-offering / votive verb co-occurs with deity, prefer votive
        if "alpan" in tokens or "cver" in tokens or "fleres" in tokens:
            return ("votive", "high", "etr_keyword:votive_deity")
        return ("dedicatory", "high", "etr_keyword:dedicatory_deity")

    # Magistrate / office keywords → legal
    if has_any(tokens, LEGAL_ETR):
        return ("legal", "high", "etr_keyword:legal")

    # Boundary / civic keywords → boundary
    if has_any(tokens, BOUNDARY_ETR):
        return ("boundary", "high", "etr_keyword:boundary")

    # Commercial keywords (rare)
    if has_any(tokens, COMMERCIAL_ETR):
        return ("commercial", "medium", "etr_keyword:commercial")

    # === Tier 2: real English translation phrases ======================
    if translation and len(translation) > 12 and " " in translation.strip():
        if RE_VOTIVE_EN.search(translation):
            return ("votive", "high", "en_phrase:votive")
        if RE_DEDICATORY_EN.search(translation):
            return ("dedicatory", "high", "en_phrase:dedicatory")
        if RE_FUNERARY_EN.search(translation):
            return ("funerary", "high", "en_phrase:funerary")
        if RE_OWNERSHIP_EN.search(translation):
            return ("ownership", "high", "en_phrase:ownership")
        if RE_BOUNDARY_EN.search(translation):
            return ("boundary", "high", "en_phrase:boundary")
        if RE_LEGAL_EN.search(translation):
            return ("legal", "high", "en_phrase:legal")
        if RE_COMMERCIAL_EN.search(translation):
            return ("commercial", "high", "en_phrase:commercial")

    # === Tier 3: structural patterns in MT-junk translations ===========
    if translation:
        if RE_DEITY_JUNK.search(translation):
            return ("dedicatory", "medium", "junk_translation:deity_ref")
        if RE_KINSHIP_JUNK.search(translation):
            return ("funerary", "medium", "junk_translation:kinship_list")

    # === Tier 4: ownership formula in canonical (mi + person/vessel) ===
    # "mi" alone or "mi" followed by a name typically marks self-identifying
    # objects (vessels, mirrors, weights). Very common in the corpus.
    if "mi" in canon_tokens:
        # If a vessel word appears, lock in ownership
        if has_any(tokens, VESSEL_ETR):
            return ("ownership", "high", "etr_formula:mi+vessel")
        # mi alone with a short canonical and no keywords → ownership
        if len(canon_tokens) <= 6:
            return ("ownership", "medium", "etr_formula:mi+name")
        return ("ownership", "low", "etr_formula:mi_present")

    # === Abstain on everything else ====================================
    # Critical: do NOT default name-only short fragments to "funerary" even
    # though that's the corpus prior. Including ~5,000 prior-based labels
    # would (a) imbalance training 30:1 toward funerary and (b) teach the
    # neural to predict the prior rather than learn features. Better to
    # abstain than to launder the prior as a label.
    return (None, "skip", "no_signal")


# -----------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------

def main() -> None:
    # Load gold labels (these always win)
    gold: dict[str, tuple[str, str]] = {}
    if GOLD_CSV.exists():
        with GOLD_CSV.open() as f:
            for r in csv.DictReader(f):
                gold[r["id"]] = (r["label"], r.get("confidence", "high"))

    rows_in = list(csv.DictReader(CLEAN_CSV.open()))

    # Per-quality split — only label clean rows
    out_rows = []
    for r in rows_in:
        if r["data_quality"] != "clean":
            continue
        rid = r["id"]
        if rid in gold:
            label, conf = gold[rid]
            out_rows.append({
                "id": rid, "label": label, "confidence": conf,
                "signal_source": "gold:claude_hand_label",
            })
            continue
        label, conf, source = label_row(
            canonical=r["canonical_transliterated"],
            translation=r["translation"],
            words_only=r["canonical_words_only"],
        )
        if label is None:
            continue
        out_rows.append({
            "id": rid, "label": label, "confidence": conf,
            "signal_source": source,
        })

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "label", "confidence", "signal_source"])
        w.writeheader()
        w.writerows(out_rows)

    print(f"wrote {len(out_rows):,} labels to {OUT_CSV}")


if __name__ == "__main__":
    main()
