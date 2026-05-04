"""Rosetta Vector Space — Phase 2: supervised alignment via Procrustes.

The Phase 1 char-init experiment confirmed that the Etruscan embedding
manifold is collapsed at the current ~15k-token corpus size — vanilla
unsupervised MUSE alignment isn't going to find structure adversarially
when there isn't enough structure to find. Supervised alignment using
the ~60 well-attested Etruscan-Latin equivalences from the philological
literature bypasses that problem entirely: we give the algorithm anchor
pairs and ask it to find the rotation that best maps them.

The math is closed-form Procrustes:

    Given matrices X (Etruscan anchor vectors) and Y (Latin anchor vectors),
    find the orthogonal W that minimises ‖XW − Y‖_F.

    Solution: U, S, V = SVD(Xᵀ Y),  W = U Vᵀ.

After alignment, every Etruscan word gets a coordinate in Latin space.
We can then ask: "which Latin words sit at the same coordinate?"

This module ships:

  * ANCHOR_PAIRS — curated list of high-confidence Etruscan-Latin
    equivalences with citations.
  * align_procrustes(...) — the closed-form Procrustes solver.
  * apply_alignment(...) — single-vector projection helper.
  * project_etruscan_to_latin(...) — for one Etruscan word, return the
    top-k Latin neighbours in the aligned space.
  * cross_validate_alignment(...) — k-fold CV on the anchor list to
    measure precision@1 on held-out pairs. This is the honest evaluation
    of whether the alignment generalises beyond the words it was fit on.
"""

from __future__ import annotations

import json
import logging
import random
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("openetruscan.alignment")


# ---------------------------------------------------------------------------
# Anchor pair vocabulary
# ---------------------------------------------------------------------------
#
# Each anchor pair is one well-attested Etruscan→Latin (or Etruscan→Greek-via-
# Latin) equivalence drawn from the Etruscology literature. Citations follow
# Bonfante & Bonfante (2002), "The Etruscan Language: An Introduction" 2nd ed.,
# Wallace (2008), "Zikh Rasna: A Manual of the Etruscan Language and
# Inscriptions", and Pallottino (1968), "Testimonia Linguae Etruscae".
#
# `confidence` flags:
#   * "high" — the equivalence is consensus across the major reference
#     grammars and supported by bilingual inscriptions or strong contextual
#     evidence (e.g. funerary formulas).
#   * "medium" — the equivalence is widely cited but contested in detail
#     (e.g. some numerals are still debated).
#   * "low" — speculative; included for completeness but should be held out
#     of training and used only for evaluation.
#
# We include the `gloss` (the English meaning) as a convenience for human
# readers; it is NOT used by the alignment math.

@dataclass(frozen=True)
class AnchorPair:
    """One Etruscan-Latin equivalence used to seed supervised alignment."""

    etr: str
    lat: str
    gloss: str
    confidence: str  # "high" | "medium" | "low"
    source: str

    def __post_init__(self) -> None:
        # NFC-normalise so the lookup key matches what the FastText models
        # see during inference.
        object.__setattr__(self, "etr", unicodedata.normalize("NFC", self.etr).lower())
        object.__setattr__(self, "lat", unicodedata.normalize("NFC", self.lat).lower())


ANCHOR_PAIRS: list[AnchorPair] = [
    # Kinship — among the most secure equivalences in the field.
    AnchorPair("clan", "filius", "son", "high", "Bonfante 2002 §96"),
    AnchorPair("sec", "filia", "daughter", "high", "Bonfante 2002 §97"),
    AnchorPair("ati", "mater", "mother", "high", "Wallace 2008 §3.4"),
    AnchorPair("apa", "pater", "father", "high", "Wallace 2008 §3.4"),
    AnchorPair("puia", "uxor", "wife", "high", "Bonfante 2002 §99"),
    AnchorPair("nefts", "nepos", "nephew/grandson", "high", "Bonfante 2002 §99"),
    AnchorPair("ruva", "frater", "brother", "medium", "Bonfante 2002 §99"),
    AnchorPair("papa", "avus", "grandfather", "medium", "Wallace 2008 §3.4"),
    AnchorPair("lautn", "familia", "family/lineage", "high", "Pallottino 1968 §47"),
    # Civic / magistracies
    AnchorPair("zilaθ", "praetor", "magistrate", "high", "Bonfante 2002 §83"),
    AnchorPair("zilθ", "praetor", "magistrate", "high", "Wallace 2008 §3.5"),
    AnchorPair("maru", "magister", "magistracy title", "medium", "Bonfante 2002 §83"),
    AnchorPair("cepen", "sacerdos", "priest", "medium", "Wallace 2008 §3.5"),
    AnchorPair("spura", "civitas", "city/state", "high", "Bonfante 2002 §85"),
    AnchorPair("methlum", "civitas", "community", "medium", "Pallottino 1968 §50"),
    AnchorPair("tular", "fines", "boundaries", "high", "Bonfante 2002 §86"),
    AnchorPair("rasna", "etruscus", "Etruscan (ethnonym)", "high", "Bonfante 2002 §1"),
    # Funerary / religious — secured by tomb-inscription formulas.
    AnchorPair("suθi", "sepulcrum", "tomb", "high", "Bonfante 2002 §90"),
    AnchorPair("ais", "deus", "god (loanword family)", "medium", "Wallace 2008 §3.6"),
    AnchorPair("aiser", "dei", "gods", "medium", "Wallace 2008 §3.6"),
    AnchorPair("fler", "sacrum", "sacred offering", "medium", "Bonfante 2002 §93"),
    AnchorPair("flerχva", "sacra", "sacred things", "medium", "Bonfante 2002 §93"),
    AnchorPair("fanu", "fanum", "sacred place", "medium", "Wallace 2008 §3.6"),
    # Time / calendar
    AnchorPair("avil", "annus", "year", "high", "Bonfante 2002 §82"),
    AnchorPair("avils", "annorum", "of years (genitive)", "high", "Bonfante 2002 §82"),
    AnchorPair("tiur", "mensis", "month", "high", "Bonfante 2002 §82"),
    AnchorPair("usil", "sol", "sun", "high", "Bonfante 2002 §82"),
    AnchorPair("tiu", "luna", "moon", "medium", "Pallottino 1968 §52"),
    # Cardinal numerals — contested in detail, hence mostly "medium".
    AnchorPair("θu", "unus", "one", "medium", "Wallace 2008 §3.7"),
    AnchorPair("zal", "duo", "two", "high", "Bonfante 2002 §80"),
    AnchorPair("ci", "tres", "three", "high", "Bonfante 2002 §80"),
    AnchorPair("huθ", "sex", "six", "medium", "Wallace 2008 §3.7"),
    AnchorPair("śa", "quattuor", "four", "medium", "Wallace 2008 §3.7"),
    AnchorPair("maχ", "quinque", "five", "medium", "Wallace 2008 §3.7"),
    AnchorPair("semφ", "septem", "seven", "medium", "Wallace 2008 §3.7"),
    AnchorPair("cezp", "octo", "eight", "medium", "Wallace 2008 §3.7"),
    AnchorPair("nurφ", "novem", "nine", "medium", "Wallace 2008 §3.7"),
    AnchorPair("śar", "decem", "ten", "high", "Bonfante 2002 §80"),
    # Verbs (votive / funerary contexts)
    AnchorPair("turce", "dedit", "gave (votive)", "high", "Bonfante 2002 §75"),
    AnchorPair("mulvanice", "dedicavit", "dedicated", "high", "Bonfante 2002 §75"),
    AnchorPair("mulu", "dedit", "dedicated/gave", "medium", "Pallottino 1968 §57"),
    AnchorPair("ace", "fecit", "made", "high", "Bonfante 2002 §75"),
    AnchorPair("lupuce", "mortuus", "died", "high", "Bonfante 2002 §75"),
    AnchorPair("svalce", "vixit", "lived", "high", "Bonfante 2002 §75"),
    AnchorPair("ame", "est", "is/was", "medium", "Wallace 2008 §3.8"),
    AnchorPair("zinace", "scripsit", "wrote/inscribed", "medium", "Wallace 2008 §3.8"),
    AnchorPair("zich", "scribere", "to write", "medium", "Bonfante 2002 §75"),
    AnchorPair("ziχ", "scriptura", "writing/script", "medium", "Bonfante 2002 §75"),
    # Theonyms — Greek/Roman pantheon equivalences are well-secured by
    # iconography on Etruscan mirrors and dedications.
    AnchorPair("tinia", "iuppiter", "Jupiter", "high", "Bonfante 2002 §93"),
    AnchorPair("uni", "iuno", "Juno", "high", "Bonfante 2002 §93"),
    AnchorPair("menrva", "minerva", "Minerva", "high", "Bonfante 2002 §93"),
    AnchorPair("aita", "dis", "Hades/Dis", "high", "Bonfante 2002 §93"),
    AnchorPair("φersipnai", "proserpina", "Persephone", "high", "Bonfante 2002 §93"),
    AnchorPair("turan", "venus", "Venus", "high", "Bonfante 2002 §93"),
    AnchorPair("turms", "mercurius", "Mercury", "high", "Bonfante 2002 §93"),
    AnchorPair("fufluns", "bacchus", "Bacchus/Dionysus", "high", "Bonfante 2002 §93"),
    AnchorPair("hercle", "hercules", "Hercules", "high", "Bonfante 2002 §93"),
    AnchorPair("nethuns", "neptunus", "Neptune", "high", "Bonfante 2002 §93"),
    # Personal-name onomastic anchors — extremely well-attested by bilingual
    # epitaphs naming the same individual.
    AnchorPair("avle", "aulus", "Aulus (praenomen)", "high", "Bonfante 2002 §62"),
    AnchorPair("vel", "velius", "Velius (praenomen)", "medium", "Bonfante 2002 §62"),
    AnchorPair("larθ", "lars", "Lars (praenomen)", "high", "Bonfante 2002 §62"),
]


def anchor_pairs(min_confidence: str = "medium") -> list[AnchorPair]:
    """Return anchor pairs filtered by minimum confidence tier."""
    levels = {"low": 0, "medium": 1, "high": 2}
    threshold = levels.get(min_confidence, 1)
    return [p for p in ANCHOR_PAIRS if levels.get(p.confidence, 0) >= threshold]


# ---------------------------------------------------------------------------
# Procrustes alignment
# ---------------------------------------------------------------------------


@dataclass
class AlignmentResult:
    """Output of `align_procrustes`."""

    W: Any  # numpy.ndarray (vector_size × vector_size), orthogonal
    n_pairs_used: int
    n_pairs_dropped: int  # OOV in either model
    dropped: list[tuple[str, str, str]] = field(default_factory=list)
    residual_norm: float = 0.0  # ‖XW − Y‖_F after alignment

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_pairs_used": self.n_pairs_used,
            "n_pairs_dropped": self.n_pairs_dropped,
            "dropped": self.dropped,
            "residual_norm": self.residual_norm,
        }


def _build_anchor_matrices(
    etr_model: Any,
    lat_model: Any,
    pairs: list[AnchorPair],
) -> tuple[Any, Any, list[AnchorPair], list[tuple[str, str, str]]]:
    """Build aligned X / Y matrices, dropping pairs that are OOV in either model.

    Returns ``(X, Y, kept_pairs, dropped)`` where ``dropped`` is a list of
    ``(etr, lat, reason)`` tuples for diagnostic printing.
    """
    import numpy as np

    kept_pairs: list[AnchorPair] = []
    dropped: list[tuple[str, str, str]] = []
    X_rows: list[Any] = []
    Y_rows: list[Any] = []

    # gensim's FastText `__contains__` returns True for ANY string because
    # of its sub-word fallback. We want strict vocab membership for the
    # anchor seeding step — using a sub-word-synthesised vector for an
    # anchor would just inject noise into the rotation. `has_index_for`
    # is the explicit "this token was seen during training" check.
    def _vocab_contains(model: Any, word: str) -> bool:
        wv = model.wv
        if hasattr(wv, "has_index_for"):
            return bool(wv.has_index_for(word))
        return word in getattr(wv, "key_to_index", {})

    for p in pairs:
        etr_in_vocab = _vocab_contains(etr_model, p.etr)
        lat_in_vocab = _vocab_contains(lat_model, p.lat)
        if not etr_in_vocab and not lat_in_vocab:
            dropped.append((p.etr, p.lat, "both OOV"))
            continue
        if not etr_in_vocab:
            dropped.append((p.etr, p.lat, "etr OOV"))
            continue
        if not lat_in_vocab:
            dropped.append((p.etr, p.lat, "lat OOV"))
            continue
        X_rows.append(etr_model.wv[p.etr])
        Y_rows.append(lat_model.wv[p.lat])
        kept_pairs.append(p)

    if not X_rows:
        raise ValueError(
            f"No anchor pairs survived vocabulary filtering "
            f"(dropped {len(dropped)} pairs). "
            f"Are the Etruscan and Latin models trained on relevant corpora?"
        )

    X = np.vstack(X_rows)
    Y = np.vstack(Y_rows)
    return X, Y, kept_pairs, dropped


def align_procrustes(
    etr_model: Any,
    lat_model: Any,
    pairs: list[AnchorPair] | None = None,
    *,
    min_confidence: str = "medium",
) -> AlignmentResult:
    """Solve orthogonal Procrustes between Etruscan and Latin embeddings.

    Closed-form via SVD: given X (kept-anchor Etruscan vectors) and Y
    (corresponding Latin vectors), find the orthogonal W minimising
    ‖XW − Y‖_F. Solution is W = U Vᵀ where U S V = SVD(Xᵀ Y).

    The orthogonality constraint is what makes this a *rotation+reflection*
    rather than an arbitrary linear map — it preserves cosine geometry
    (cosine similarities computed in W-rotated space match those in the
    original space), which is exactly what we want for nearest-neighbour
    retrieval.
    """
    import numpy as np

    if pairs is None:
        pairs = anchor_pairs(min_confidence=min_confidence)

    X, Y, kept_pairs, dropped = _build_anchor_matrices(etr_model, lat_model, pairs)
    M = X.T @ Y
    U, _S, Vt = np.linalg.svd(M, full_matrices=False)
    W = U @ Vt  # vector_size × vector_size, orthogonal

    residual = float(np.linalg.norm(X @ W - Y, ord="fro"))
    return AlignmentResult(
        W=W,
        n_pairs_used=len(kept_pairs),
        n_pairs_dropped=len(dropped),
        dropped=dropped,
        residual_norm=residual,
    )


def apply_alignment(W: Any, vector: Any) -> Any:
    """Project a single Etruscan vector into Latin space via the alignment."""
    return vector @ W


def project_etruscan_to_latin(
    word: str,
    etr_model: Any,
    lat_model: Any,
    W: Any,
    k: int = 10,
) -> list[tuple[str, float]]:
    """For an Etruscan word, return the top-k Latin neighbours in the
    aligned space.

    Sub-word fallback applies: if the Etruscan word is OOV at the
    word-level, FastText synthesises a vector from its character n-grams,
    so even unseen morphological variants get a sensible projection.
    """
    import numpy as np

    word = unicodedata.normalize("NFC", word).lower()
    etr_vec = etr_model.wv[word]  # FastText handles OOV via subword
    projected = apply_alignment(W, etr_vec)

    # Brute-force cosine over the Latin vocabulary. Acceptable for vocab
    # sizes <100k; switch to ANN if this ever ships at scale.
    lat_vectors = lat_model.wv.vectors
    lat_keys = lat_model.wv.index_to_key

    proj_norm = projected / (np.linalg.norm(projected) + 1e-12)
    lat_norms = lat_vectors / (np.linalg.norm(lat_vectors, axis=1, keepdims=True) + 1e-12)
    sims = lat_norms @ proj_norm

    top_idx = np.argsort(-sims)[:k]
    return [(lat_keys[i], float(sims[i])) for i in top_idx]


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------


def cross_validate_alignment(
    etr_model: Any,
    lat_model: Any,
    pairs: list[AnchorPair] | None = None,
    *,
    k_folds: int = 5,
    seed: int = 42,
    min_confidence: str = "medium",
    top_k: int = 1,
) -> dict[str, Any]:
    """K-fold CV to measure how well the alignment generalises.

    For each fold we hold out 1/k of the anchor pairs, fit Procrustes on
    the remaining (k-1)/k, and ask: does projecting the held-out
    Etruscan word land its known Latin equivalent in the top-k Latin
    neighbours? The mean of fold-wise precision@k is the reported metric.

    Honest about what this measures: precision@k on *held-out anchor
    pairs*. It tells us whether the rotation generalises to anchor words
    the rotation didn't see — not whether the rotation is meaningful for
    the much larger set of corpus words that have NO known equivalent.
    The latter is what Phase 3 (the discovery tool) is for; it's
    qualitative until we hand-rate the predictions.
    """
    if pairs is None:
        pairs = anchor_pairs(min_confidence=min_confidence)

    # Drop pairs that are OOV in either model up front so each fold sees
    # the same effective denominator.
    _, _, usable, dropped_oov = _build_anchor_matrices(etr_model, lat_model, pairs)
    if k_folds < 2 or len(usable) < k_folds:
        raise ValueError(
            f"Need at least k_folds={k_folds} usable pairs; got {len(usable)} "
            f"({len(dropped_oov)} dropped as OOV)."
        )

    rng = random.Random(seed)
    shuffled = usable[:]
    rng.shuffle(shuffled)

    fold_size = len(shuffled) // k_folds
    fold_results: list[dict[str, Any]] = []
    hits_total = 0
    n_held_out_total = 0

    for fold in range(k_folds):
        start = fold * fold_size
        # Last fold takes the remainder so every pair is held out once.
        end = (fold + 1) * fold_size if fold < k_folds - 1 else len(shuffled)
        held_out = shuffled[start:end]
        train = shuffled[:start] + shuffled[end:]

        result = align_procrustes(etr_model, lat_model, train)
        hits = 0
        per_query: list[dict[str, Any]] = []
        for p in held_out:
            top = project_etruscan_to_latin(p.etr, etr_model, lat_model, result.W, k=top_k)
            top_words = {w for w, _ in top}
            hit = p.lat in top_words
            hits += int(hit)
            per_query.append(
                {
                    "etr": p.etr,
                    "expected_lat": p.lat,
                    "top_predictions": top,
                    "hit": hit,
                }
            )

        precision = hits / len(held_out) if held_out else 0.0
        fold_results.append(
            {
                "fold": fold,
                "n_train": len(train),
                "n_held_out": len(held_out),
                "hits": hits,
                "precision_at_k": precision,
                "queries": per_query,
            }
        )
        hits_total += hits
        n_held_out_total += len(held_out)

    return {
        "k_folds": k_folds,
        "top_k": top_k,
        "n_pairs_total": len(usable),
        "n_pairs_oov_dropped": len(dropped_oov),
        "oov_dropped": dropped_oov,
        "mean_precision_at_k": (
            hits_total / n_held_out_total if n_held_out_total else 0.0
        ),
        "folds": fold_results,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_alignment(
    result: AlignmentResult,
    out_path: Path,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Persist the rotation matrix + metadata to disk.

    The matrix is stored as a numpy ``.npy`` (binary, fast to load); the
    sidecar ``.meta.json`` carries the reproducibility-relevant info
    (anchor count, residual, optional CV results).
    """
    import numpy as np

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, result.W)

    meta = {**result.to_dict(), **(extra_metadata or {})}
    out_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False)
    )


def load_alignment(path: Path) -> Any:
    """Load a saved rotation matrix. Returns the W array."""
    import numpy as np

    p = Path(path)
    # Allow either `foo.npy` or `foo` (we'll add the extension).
    if p.suffix != ".npy":
        p = p.with_suffix(p.suffix + ".npy") if p.suffix else p.with_suffix(".npy")
    return np.load(p)


# ---------------------------------------------------------------------------
# Synthetic Latin corpus (for self-contained demos and tests)
# ---------------------------------------------------------------------------
#
# The proof-of-concept needs Latin word vectors to align against. Real
# production work would download fasttext.cc's pretrained Latin model
# (`cc.la.300.bin`, ~7 GB) or train on a curated dump of EDR / Perseus
# / PHI Latin texts. Both are tracked in ROADMAP.md Phase 1b.
#
# For the demo + tests we use a hand-written Latin "mini-corpus" that
# (a) contains every Latin word in ANCHOR_PAIRS, (b) places those words
# in plausible co-occurrence contexts (genitives with possessor nouns,
# verbs with subjects, etc.), so the resulting embeddings have at least
# the structure necessary for Procrustes to find a meaningful rotation.
# This is NOT a substitute for a real Latin corpus — alignment quality
# against this mini-corpus tells you the math works, not that the math
# generalises.

SYNTHETIC_LATIN_SENTENCES: list[str] = [
    # Family / kinship
    "filius patris est",
    "filia matris est",
    "mater filium amat",
    "pater filiam amat",
    "uxor mariti est",
    "frater sororem habet",
    "nepos avi memoriam servat",
    "avus nepotem docet",
    "familia patris filium habet",
    "familia matris filiam habet",
    "filius patrem honorat",
    "filia matrem honorat",
    "uxor familiam regit",
    # Civic / magistracies
    "praetor civitatis legem dicit",
    "magister scholam regit",
    "sacerdos deum venerat",
    "civitas fines suos defendit",
    "praetor in civitate iudicat",
    "fines civitatis lapide notantur",
    "etruscus praetor in civitate sedet",
    # Time / calendar
    "annus duodecim mensibus constat",
    "annus solis cursu finitur",
    "mensis lunae cursu finitur",
    "sol per caelum movetur",
    "luna noctem illuminat",
    "sol mensem dividit",
    "annorum multorum memoria",
    # Numerals
    "unus duo tres quattuor quinque sex septem octo novem decem",
    "unus deus est",
    "duo fratres sunt",
    "tres filiae matris",
    "decem anni vitae",
    "septem dies in septimana",
    "octo menses transierunt",
    # Verbs
    "dedit donum templo",
    "dedicavit aram deo",
    "fecit opus magnum",
    "mortuus est in proelio",
    "vixit annos septuaginta",
    "scripsit legem civitatis",
    "scriptura litterarum manet",
    "scribere legem opus est",
    "magister scribere docet",
    "puer scribere discit",
    "scriptura sacra deo dicta",
    "filius scribere cum patre",
    "donum dedit deae uxor",
    "opus fecit magister",
    # Theonyms — placed alongside the equivalent's typical contexts.
    "iuppiter pater deorum",
    "iuno uxor iovis",
    "minerva sapientiam donat",
    "venus amorem regit",
    "mercurius nuntius deorum",
    "bacchus vinum donat",
    "hercules opera magna fecit",
    "neptunus mare regit",
    "dis inferos regit",
    "proserpina regina inferorum",
    # Funerary / religious
    "sepulcrum patris in agro",
    "sacrum templo dedit",
    "sacra in fano celebrantur",
    "fanum deae sacrum est",
    "deus in fano honoratur",
    "dei familiam protegunt",
    # Onomastic
    "aulus filius patris est",
    "lars praetor civitatis fuit",
    "velius mater filiam habet",
]


def build_synthetic_latin_corpus(repeat: int = 8) -> list[list[str]]:
    """Return a tokenised, repeated synthetic Latin corpus.

    `repeat` controls how many times the base sentence list is duplicated
    so FastText's `min_count` filter doesn't drop everything. With the
    default 8x and ~60 base sentences we get ~500 sentences and enough
    co-occurrence passes for the manifold to settle.
    """
    tokenised: list[list[str]] = []
    for s in SYNTHETIC_LATIN_SENTENCES:
        tokens = unicodedata.normalize("NFC", s).lower().split()
        tokenised.append(tokens)
    return tokenised * repeat


def train_synthetic_latin_model(
    vector_size: int = 100,
    epochs: int = 30,
) -> Any:
    """Convenience: train a FastText on the synthetic Latin corpus.

    Used by the tests + the CLI smoke test. NOT for production —
    download the real Latin model when one is needed.
    """
    try:
        from gensim.models import FastText
    except ImportError as e:
        raise ImportError("Latin model training requires the [rosetta] extra.") from e

    sentences = build_synthetic_latin_corpus()
    return FastText(
        sentences=sentences,
        vector_size=vector_size,
        window=5,
        min_count=2,
        min_n=3,
        max_n=6,
        epochs=epochs,
        sg=1,
        workers=2,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_evaluate(args: Any) -> int:
    """Run k-fold CV against the prod Etruscan model + a Latin model.

    Two ways to provide the Latin model:
      --lat-model <path>    Load a pretrained gensim model from disk.
      --synthetic-latin     Train the bundled synthetic Latin corpus
                            in-process (fast, self-contained, but not
                            representative of real Latin geometry).
    """
    from openetruscan.ml.rosetta import load_model as _load_rosetta_model

    etr_model = _load_rosetta_model(args.etr_model)
    if args.synthetic_latin:
        logger.info("Training synthetic Latin model in-process …")
        lat_model = train_synthetic_latin_model()
    else:
        lat_model = _load_rosetta_model(args.lat_model)

    cv = cross_validate_alignment(
        etr_model,
        lat_model,
        k_folds=args.k_folds,
        top_k=args.top_k,
        min_confidence=args.min_confidence,
    )
    print(json.dumps(cv, indent=2, ensure_ascii=False, default=str))
    return 0


def _cli_align(args: Any) -> int:
    from openetruscan.ml.rosetta import load_model as _load_rosetta_model

    etr_model = _load_rosetta_model(args.etr_model)
    if args.synthetic_latin:
        lat_model = train_synthetic_latin_model()
    else:
        lat_model = _load_rosetta_model(args.lat_model)

    result = align_procrustes(etr_model, lat_model, min_confidence=args.min_confidence)
    save_alignment(result, Path(args.output))
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_eval = sub.add_parser("evaluate", help="K-fold CV of the supervised alignment")
    p_eval.add_argument("--etr-model", required=True)
    p_eval.add_argument("--lat-model", help="Path to pretrained Latin gensim model")
    p_eval.add_argument("--synthetic-latin", action="store_true",
                        help="Train the bundled synthetic Latin corpus instead")
    p_eval.add_argument("--k-folds", type=int, default=5)
    p_eval.add_argument("--top-k", type=int, default=1)
    p_eval.add_argument("--min-confidence", default="medium",
                        choices=["low", "medium", "high"])
    p_eval.set_defaults(fn=_cli_evaluate)

    p_align = sub.add_parser("align", help="Fit a Procrustes rotation and save it")
    p_align.add_argument("--etr-model", required=True)
    p_align.add_argument("--lat-model")
    p_align.add_argument("--synthetic-latin", action="store_true")
    p_align.add_argument("--output", required=True, help="Path for the saved .npy + meta.json")
    p_align.add_argument("--min-confidence", default="medium",
                        choices=["low", "medium", "high"])
    p_align.set_defaults(fn=_cli_align)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.fn(args)


if __name__ == "__main__":
    import sys
    sys.exit(main())
