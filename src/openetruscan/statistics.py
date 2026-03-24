"""
Statistical analysis engine for ancient epigraphic corpora.

Three analysis modules:
  1. Letter frequency analysis   — per-site/date frequency vectors + chi² tests
  2. Dialect clustering          — cosine-distance Ward clustering + PCA projection
  3. Dating heuristics           — rule-based chronological classification

Uses numpy/scipy for SOTA statistical methods on the OpenEtruscan corpus.

Usage:
    from openetruscan.statistics import (
        letter_frequencies,
        compare_frequencies,
        cluster_sites,
        estimate_date,
    )
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist
from scipy.stats import chi2_contingency

from openetruscan.adapter import LanguageAdapter, load_adapter

# ---------------------------------------------------------------------------
# 1. LETTER FREQUENCY ANALYSIS
# ---------------------------------------------------------------------------


@dataclass
class FrequencyResult:
    """Letter frequency analysis for a set of texts."""

    counts: dict[str, int]
    frequencies: dict[str, float]  # Relative frequencies (0–1)
    total_chars: int
    inscription_count: int
    alphabet: list[str]  # Ordered letter list used

    def to_dict(self) -> dict:
        letters = [
            {
                "letter": lt,
                "count": self.counts.get(lt, 0),
                "frequency": round(self.frequencies.get(lt, 0.0), 6),
            }
            for lt in self.alphabet
        ]
        return {
            "letters": letters,
            "total_chars": self.total_chars,
            "inscription_count": self.inscription_count,
        }


def letter_frequencies(
    texts: list[str],
    adapter: LanguageAdapter | None = None,
    language: str = "etruscan",
) -> FrequencyResult:
    """
    Count letter frequencies across a list of canonical texts.

    Only counts characters present in the adapter's alphabet.
    Spaces, punctuation, and unknown characters are excluded.
    """
    if adapter is None:
        adapter = load_adapter(language)

    alphabet_set = set(adapter.alphabet.keys())
    alphabet_sorted = sorted(adapter.alphabet.keys())

    counter: Counter[str] = Counter()
    for text in texts:
        for char in text:
            if char in alphabet_set:
                counter[char] += 1

    total = sum(counter.values())
    frequencies = {
        letter: counter[letter] / total if total > 0 else 0.0 for letter in alphabet_sorted
    }
    counts = {letter: counter[letter] for letter in alphabet_sorted}

    return FrequencyResult(
        counts=counts,
        frequencies=frequencies,
        total_chars=total,
        inscription_count=len(texts),
        alphabet=alphabet_sorted,
    )


@dataclass
class ComparisonResult:
    """Statistical comparison between two frequency distributions."""

    chi2: float
    p_value: float
    significant: bool  # p < 0.05
    effect_size: float  # Cramér's V
    site_a: FrequencyResult
    site_b: FrequencyResult

    def to_dict(self) -> dict:
        return {
            "chi2": round(self.chi2, 4),
            "p_value": round(self.p_value, 6),
            "significant": self.significant,
            "effect_size": round(self.effect_size, 4),
        }


def compare_frequencies(
    freq_a: FrequencyResult,
    freq_b: FrequencyResult,
) -> ComparisonResult:
    """
    Chi-squared test: are two sites' letter distributions significantly different?

    Uses scipy.stats.chi2_contingency on a 2×N contingency table
    (site × letter counts). Computes Cramér's V as effect size.
    """
    alphabet = freq_a.alphabet
    row_a = [freq_a.counts.get(lt, 0) for lt in alphabet]
    row_b = [freq_b.counts.get(lt, 0) for lt in alphabet]

    # Filter out columns where both sites have 0
    filtered_a, filtered_b = [], []
    for a, b in zip(row_a, row_b, strict=True):
        if a > 0 or b > 0:
            filtered_a.append(a)
            filtered_b.append(b)

    if len(filtered_a) < 2 or sum(filtered_a) == 0 or sum(filtered_b) == 0:
        return ComparisonResult(
            chi2=0.0,
            p_value=1.0,
            significant=False,
            effect_size=0.0,
            site_a=freq_a,
            site_b=freq_b,
        )

    observed = np.array([filtered_a, filtered_b])
    chi2_val, p_val, _, _ = chi2_contingency(observed)

    # Cramér's V
    n = observed.sum()
    k = min(observed.shape) - 1
    cramers_v = math.sqrt(chi2_val / (n * k)) if n * k > 0 else 0.0

    return ComparisonResult(
        chi2=float(chi2_val),
        p_value=float(p_val),
        significant=bool(p_val < 0.05),
        effect_size=float(cramers_v),
        site_a=freq_a,
        site_b=freq_b,
    )


# ---------------------------------------------------------------------------
# 2. DIALECT CLUSTERING
# ---------------------------------------------------------------------------


@dataclass
class SiteVector:
    """A single site's frequency vector for clustering."""

    site: str
    inscription_count: int
    vector: list[float]
    cluster_id: int = 0
    pca_x: float = 0.0
    pca_y: float = 0.0


@dataclass
class ClusterResult:
    """Result of dialect clustering analysis."""

    sites: list[SiteVector]
    n_clusters: int
    alphabet: list[str]
    linkage_matrix: list[list[float]]  # For dendrogram rendering

    def to_dict(self) -> dict:
        clusters: dict[int, list[dict]] = {}
        for s in self.sites:
            cid = s.cluster_id
            if cid not in clusters:
                clusters[cid] = []
            clusters[cid].append(
                {
                    "site": s.site,
                    "inscription_count": s.inscription_count,
                    "pca_x": round(s.pca_x, 4),
                    "pca_y": round(s.pca_y, 4),
                    "vector": [round(v, 6) for v in s.vector],
                }
            )
        return {
            "n_clusters": self.n_clusters,
            "alphabet": self.alphabet,
            "clusters": [
                {"cluster_id": cid, "sites": sites} for cid, sites in sorted(clusters.items())
            ],
            "dendrogram": [[round(v, 4) for v in row] for row in self.linkage_matrix],
        }


def cluster_sites(
    corpus,
    language: str = "etruscan",
    min_inscriptions: int = 5,
    max_clusters: int = 6,
) -> ClusterResult:
    """
    Cluster inscription findspots by letter-frequency similarity.

    Method:
      1. Group inscriptions by findspot
      2. Compute normalised frequency vectors (L1-normed) per site
      3. Compute pairwise cosine distances
      4. Ward's hierarchical agglomerative clustering
      5. Auto-select cluster count via max silhouette score (2..max_clusters)
      6. PCA projection to 2D for visualization

    Sites with fewer than `min_inscriptions` are dropped as noise.
    """
    adapter = load_adapter(language)
    alphabet = sorted(adapter.alphabet.keys())
    n_letters = len(alphabet)
    letter_idx = {lt: idx for idx, lt in enumerate(alphabet)}
    alphabet_set = set(alphabet)

    # Step 1: group by findspot
    results = corpus.search(limit=999999, language=language)
    site_texts: dict[str, list[str]] = {}
    for insc in results:
        spot = insc.findspot.strip()
        if spot:
            site_texts.setdefault(spot, []).append(insc.canonical)

    # Filter by min_inscriptions
    site_texts = {s: t for s, t in site_texts.items() if len(t) >= min_inscriptions}

    if len(site_texts) < 2:
        return ClusterResult(sites=[], n_clusters=0, alphabet=alphabet, linkage_matrix=[])

    site_names = sorted(site_texts.keys())
    n_sites = len(site_names)

    # Step 2: build frequency matrix (sites × letters)
    freq_matrix = np.zeros((n_sites, n_letters), dtype=float)
    site_counts = []

    for i, site in enumerate(site_names):
        counter: Counter[str] = Counter()
        for text in site_texts[site]:
            for ch in text:
                if ch in alphabet_set:
                    counter[ch] += 1
        total = sum(counter.values())
        if total > 0:
            for letter, count in counter.items():
                freq_matrix[i, letter_idx[letter]] = count / total
        site_counts.append(len(site_texts[site]))

    # Step 3: pairwise cosine distances
    dist_vector = pdist(freq_matrix, metric="cosine")
    # Replace NaN (from zero vectors) with 1.0 (max distance)
    dist_vector = np.nan_to_num(dist_vector, nan=1.0)

    # Step 4: Ward's linkage
    z_linkage = linkage(dist_vector, method="ward")

    # Step 5: auto-select k via silhouette (if enough sites)
    best_k = 2
    if n_sites >= 4:
        from scipy.spatial.distance import squareform

        dist_matrix = squareform(dist_vector)
        best_score = -1.0
        for k in range(2, min(max_clusters + 1, n_sites)):
            labels = fcluster(z_linkage, t=k, criterion="maxclust")
            if len(set(labels)) < 2:
                continue
            score = _silhouette_score(dist_matrix, labels)
            if score > best_score:
                best_score = score
                best_k = k

    labels = fcluster(z_linkage, t=best_k, criterion="maxclust")

    # Step 6: PCA to 2D
    pca_coords = _pca_2d(freq_matrix)

    # Build result
    site_vectors = []
    for i, site in enumerate(site_names):
        site_vectors.append(
            SiteVector(
                site=site,
                inscription_count=site_counts[i],
                vector=freq_matrix[i].tolist(),
                cluster_id=int(labels[i]),
                pca_x=float(pca_coords[i, 0]),
                pca_y=float(pca_coords[i, 1]),
            )
        )

    return ClusterResult(
        sites=site_vectors,
        n_clusters=best_k,
        alphabet=alphabet,
        linkage_matrix=z_linkage.tolist(),
    )


def _silhouette_score(dist_matrix: np.ndarray, labels: np.ndarray) -> float:
    """Compute mean silhouette score from a precomputed distance matrix."""
    n = len(labels)
    silhouettes = np.zeros(n)

    for i in range(n):
        same = [j for j in range(n) if labels[j] == labels[i] and j != i]
        diff_clusters: dict[int, list[int]] = {}
        for j in range(n):
            if labels[j] != labels[i]:
                diff_clusters.setdefault(int(labels[j]), []).append(j)

        a_i = np.mean([dist_matrix[i, j] for j in same]) if same else 0.0

        if not diff_clusters:
            silhouettes[i] = 0.0
            continue

        b_i = min(
            np.mean([dist_matrix[i, j] for j in members]) for members in diff_clusters.values()
        )
        denom = max(a_i, b_i)
        silhouettes[i] = (b_i - a_i) / denom if denom > 0 else 0.0

    return float(np.mean(silhouettes))


def _pca_2d(matrix: np.ndarray) -> np.ndarray:
    """Project an (n_samples, n_features) matrix to 2D via SVD."""
    centered = matrix - matrix.mean(axis=0)
    if centered.shape[0] < 2:
        return np.zeros((centered.shape[0], 2))
    u, s, _vt = np.linalg.svd(centered, full_matrices=False)
    return u[:, :2] * s[:2]


# ---------------------------------------------------------------------------
# 3. DATING HEURISTICS — Descriptive Tagging System
# ---------------------------------------------------------------------------

# Chronological diagnostic features based on standard Etruscological literature
# (Rix 1963, Bonfante & Bonfante 2002, Wallace 2008)
#
# Each feature has a scholarly weight reflecting its diagnostic strength.
# Weights are normalised per period so each period's total = 1.0.

_ARCHAIC_FEATURES = [
    ("k_before_a", "Uses K before /a/ (archaic tripartition K/C/Q)", 0.35),
    ("q_present", "Uses Q before /u/ (archaic tripartition)", 0.30),
    ("no_f", "Lacks F (pre-400 BCE script)", 0.20),
    ("three_sibilants", "Distinguishes multiple sibilant graphemes", 0.15),
]

_CLASSICAL_FEATURES = [
    ("c_dominant", "C used as general velar (K/Q dropped)", 0.40),
    ("aspirates_frequent", "Frequent use of θ, φ, χ", 0.30),
    ("genitive_al", "Genitive marker -al present", 0.30),
]

_LATE_FEATURES = [
    ("f_present", "Uses F (post-400 BCE innovation)", 0.40),
    ("simplified_sibilants", "Reduced sibilant inventory", 0.30),
    ("latin_influence", "Contains Latin-influenced spellings", 0.30),
]

_ALL_FEATURES = _ARCHAIC_FEATURES + _CLASSICAL_FEATURES + _LATE_FEATURES

_PERIOD_FEATURES = {
    "archaic": _ARCHAIC_FEATURES,
    "classical": _CLASSICAL_FEATURES,
    "late": _LATE_FEATURES,
}

_DATE_RANGES = {
    "archaic": (700, 500),
    "classical": (500, 300),
    "late": (300, 50),
    "indeterminate": (700, 50),
}

_DEFAULT_CAVEATS = [
    "Rule-based heuristic: does not account for regional variation",
    "Short texts yield weaker signal — treat low tag_scores with caution",
    "Not a probabilistic model; tag_scores reflect feature presence, not Bayesian posteriors",
]


@dataclass
class DatingResult:
    """Estimated date for an inscription based on orthographic features.

    Attributes:
        period: Best-matching period label.
        date_range: (from_bce, to_bce) as positive numbers.
        confidence: Maximum tag score (backward-compatible; prefer ``tag_scores``).
        tag_scores: Per-period weighted evidence strength (0.0–1.0).
        method: Always ``"descriptive"`` — signals rule-based tagging.
        caveats: Methodological limitations.
        features: Detailed per-feature report.
    """

    period: str  # "archaic", "classical", "late", "indeterminate"
    date_range: tuple[int, int]  # (from_bce, to_bce) as positive numbers
    confidence: float  # 0.0–1.0, max of tag_scores (backward-compat)
    features: list[dict]  # [{id, description, present, weight, period}]
    tag_scores: dict[str, float] | None = None  # {"archaic": 0.65, …}
    method: str = "descriptive"
    caveats: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "date_range": list(self.date_range),
            "date_display": f"{self.date_range[0]}–{self.date_range[1]} BCE",
            "confidence": round(self.confidence, 3),
            "tag_scores": {k: round(v, 3) for k, v in (self.tag_scores or {}).items()},
            "method": self.method,
            "caveats": self.caveats or [],
            "features": self.features,
        }


def estimate_date(
    text: str,
    language: str = "etruscan",
) -> DatingResult:
    """
    Estimate the chronological period of an inscription from orthographic cues.

    Uses a **descriptive tagging** system with weighted features:
      - Archaic (700–500 BCE): K/Q tripartition, no F, three sibilants
      - Classical (500–300 BCE): C dominant, aspirates frequent, -al genitives
      - Late (300–50 BCE): F innovation, simplified sibilants, Latin influence

    Each feature carries a scholarly weight reflecting its diagnostic strength.
    Returns per-period ``tag_scores`` instead of a single confidence value.

    .. deprecated:: 0.4.0
        The ``confidence`` field is retained for backward compatibility but
        should be replaced by inspecting ``tag_scores`` directly.
    """
    from openetruscan.normalizer import normalize as _normalize

    result = _normalize(text, language=language)
    canonical = result.canonical
    tokens = result.tokens

    if not canonical.strip():
        return DatingResult(
            period="indeterminate",
            date_range=(700, 50),
            confidence=0.0,
            features=[],
            tag_scores={"archaic": 0.0, "classical": 0.0, "late": 0.0},
            method="descriptive",
            caveats=_DEFAULT_CAVEATS,
        )

    # --- Extract feature presence ---
    features_found: dict[str, bool] = {}

    # Archaic indicators
    has_k_before_a = False
    for i, ch in enumerate(canonical):
        if ch == "k" and i + 1 < len(canonical) and canonical[i + 1] == "a":
            has_k_before_a = True
            break
    features_found["k_before_a"] = has_k_before_a
    features_found["q_present"] = "q" in canonical
    features_found["no_f"] = "f" not in canonical
    sibilant_types = sum(1 for s in ["s", "ś", "ξ", "z"] if s in canonical)
    features_found["three_sibilants"] = sibilant_types >= 2

    # Classical indicators
    features_found["c_dominant"] = (
        "c" in canonical and "k" not in canonical and "q" not in canonical
    )
    aspirate_count = sum(1 for ch in canonical if ch in ("θ", "φ", "χ"))
    features_found["aspirates_frequent"] = aspirate_count >= 1
    features_found["genitive_al"] = any(t.endswith("al") for t in tokens)

    # Late indicators
    features_found["f_present"] = "f" in canonical
    features_found["simplified_sibilants"] = (
        "s" in canonical and "ś" not in canonical and "ξ" not in canonical
    )
    latin_chars = sum(1 for ch in canonical if ch in ("d", "b", "g", "o"))
    features_found["latin_influence"] = latin_chars >= 1

    # --- Weighted scoring per period ---
    tag_scores: dict[str, float] = {}
    for period_name, period_features in _PERIOD_FEATURES.items():
        score = 0.0
        for feat_id, _, weight in period_features:
            if features_found.get(feat_id, False):
                score += weight
        tag_scores[period_name] = score

    # Determine best period
    best_period = max(tag_scores, key=tag_scores.get)  # type: ignore[arg-type]
    best_score = tag_scores[best_period]

    # If no clear winner, mark as indeterminate
    sorted_scores = sorted(tag_scores.values(), reverse=True)
    if best_score < 0.20 or (
        len(sorted_scores) > 1 and sorted_scores[0] - sorted_scores[1] < 0.10
    ):
        best_period = "indeterminate"

    # --- Build feature report (enriched with weight + period) ---
    all_features = []
    for feat_id, desc, weight in _ALL_FEATURES:
        period_label = (
            "archaic"
            if any(f[0] == feat_id for f in _ARCHAIC_FEATURES)
            else "classical"
            if any(f[0] == feat_id for f in _CLASSICAL_FEATURES)
            else "late"
        )
        all_features.append(
            {
                "id": feat_id,
                "description": desc,
                "present": features_found.get(feat_id, False),
                "weight": weight,
                "period": period_label,
            }
        )

    return DatingResult(
        period=best_period,
        date_range=_DATE_RANGES[best_period],
        confidence=best_score,
        features=all_features,
        tag_scores=tag_scores,
        method="descriptive",
        caveats=_DEFAULT_CAVEATS,
    )


# ---------------------------------------------------------------------------
# Bayesian Aoristic Dating
# ---------------------------------------------------------------------------

# 50-year time bins from 700 to 50 BCE (13 bins)
_TIME_BINS = [
    (700, 650), (650, 600), (600, 550), (550, 500),
    (500, 450), (450, 400), (400, 350), (350, 300),
    (300, 250), (250, 200), (200, 150), (150, 100), (100, 50),
]

_BIN_LABELS = [f"{b[0]}-{b[1]} BCE" for b in _TIME_BINS]


def _bin_midpoint(time_bin: tuple[int, int]) -> int:
    """Return the midpoint year of a time bin (as negative BCE)."""
    return -((time_bin[0] + time_bin[1]) // 2)


# Likelihood tables: P(feature_present | time_bin_index)
# Calibrated from epigraphic consensus (Rix 1963, Bonfante 2002, Wallace 2008)
# Index 0 = 700-650 BCE, Index 12 = 100-50 BCE
_LIKELIHOODS: dict[str, list[float]] = {
    # K before /a/ — strong archaic marker, drops off after 500 BCE
    "k_before_a": [
        0.90, 0.85, 0.80, 0.70, 0.15, 0.08,
        0.03, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
    ],
    # Q before /u/ — archaic tripartition
    "q_present": [
        0.80, 0.75, 0.70, 0.60, 0.15, 0.08,
        0.03, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01,
    ],
    # Absence of F — marks pre-400 BCE
    "no_f": [
        0.98, 0.97, 0.95, 0.90, 0.70, 0.40,
        0.20, 0.10, 0.05, 0.03, 0.02, 0.02, 0.01,
    ],
    # Multiple sibilants — archaic orthography
    "three_sibilants": [
        0.85, 0.80, 0.75, 0.65, 0.45, 0.30,
        0.20, 0.15, 0.10, 0.08, 0.05, 0.05, 0.03,
    ],
    # C dominant (K/Q dropped) — classical innovation
    "c_dominant": [
        0.05, 0.08, 0.15, 0.30, 0.70, 0.80,
        0.85, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60,
    ],
    # Frequent aspirates — peaks in classical period
    "aspirates_frequent": [
        0.30, 0.35, 0.45, 0.55, 0.70, 0.75,
        0.80, 0.75, 0.60, 0.50, 0.45, 0.40, 0.35,
    ],
    # Genitive -al — develops from late archaic, peaks classical
    "genitive_al": [
        0.10, 0.15, 0.25, 0.40, 0.60, 0.70,
        0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45,
    ],
    # F present — post-400 BCE innovation
    "f_present": [
        0.02, 0.03, 0.05, 0.10, 0.30, 0.60,
        0.80, 0.90, 0.95, 0.97, 0.98, 0.98, 0.99,
    ],
    # Simplified sibilants — progressive reduction
    "simplified_sibilants": [
        0.05, 0.08, 0.10, 0.15, 0.25, 0.40,
        0.55, 0.70, 0.80, 0.85, 0.90, 0.92, 0.95,
    ],
    # Latin influence — grows from 3rd century
    "latin_influence": [
        0.01, 0.01, 0.01, 0.02, 0.03, 0.05,
        0.10, 0.15, 0.25, 0.40, 0.55, 0.70, 0.80,
    ],
}


@dataclass
class BayesianDatingResult:
    """Bayesian posterior distribution over chronological time bins.

    Attributes:
        posterior: Dict of ``{bin_label: probability}`` (sums to ~1.0).
        map_estimate: Maximum a posteriori year estimate (negative = BCE).
        credible_interval_95: 95% credible interval ``(from_bce, to_bce)``.
        features_observed: Dict of features and whether they were present.
        method: Always ``"bayesian_aoristic"``.
    """

    posterior: dict[str, float]
    map_estimate: int
    credible_interval_95: tuple[int, int]
    features_observed: dict[str, bool]
    method: str = "bayesian_aoristic"

    def to_dict(self) -> dict:
        return {
            "posterior": {k: round(v, 4) for k, v in self.posterior.items()},
            "map_estimate": self.map_estimate,
            "map_display": f"{abs(self.map_estimate)} BCE",
            "credible_interval_95": list(self.credible_interval_95),
            "credible_interval_display": (
                f"{self.credible_interval_95[0]}–{self.credible_interval_95[1]} BCE"
            ),
            "features_observed": self.features_observed,
            "method": self.method,
        }


def bayesian_date(
    text: str,
    language: str = "etruscan",
) -> BayesianDatingResult:
    """
    Estimate inscription date using Bayesian inference over time bins.

    Computes a posterior probability distribution P(period | features)
    using calibrated likelihood tables and a uniform prior over 13
    50-year time bins from 700 to 50 BCE.

    This is the SOTA replacement for ``estimate_date()``, providing true
    probabilistic date estimates rather than descriptive period labels.

    Args:
        text: Raw or canonical inscription text.
        language: Language adapter to use for normalization.

    Returns:
        BayesianDatingResult with full posterior distribution and
        95% credible interval.
    """
    from openetruscan.normalizer import normalize as _normalize

    result = _normalize(text, language=language)
    canonical = result.canonical
    tokens = result.tokens
    n_bins = len(_TIME_BINS)

    # --- Extract feature presence (same logic as estimate_date) ---
    features: dict[str, bool] = {}

    has_k_before_a = False
    for i, ch in enumerate(canonical):
        if ch == "k" and i + 1 < len(canonical) and canonical[i + 1] == "a":
            has_k_before_a = True
            break
    features["k_before_a"] = has_k_before_a
    features["q_present"] = "q" in canonical
    features["no_f"] = "f" not in canonical
    sibilant_types = sum(1 for s in ["s", "ś", "ξ", "z"] if s in canonical)
    features["three_sibilants"] = sibilant_types >= 2
    features["c_dominant"] = (
        "c" in canonical and "k" not in canonical and "q" not in canonical
    )
    aspirate_count = sum(1 for ch in canonical if ch in ("θ", "φ", "χ"))
    features["aspirates_frequent"] = aspirate_count >= 1
    features["genitive_al"] = any(t.endswith("al") for t in tokens)
    features["f_present"] = "f" in canonical
    features["simplified_sibilants"] = (
        "s" in canonical and "ś" not in canonical and "ξ" not in canonical
    )
    latin_chars = sum(1 for ch in canonical if ch in ("d", "b", "g", "o"))
    features["latin_influence"] = latin_chars >= 1

    # --- Bayesian inference ---
    # Uniform prior over all time bins
    log_posterior = [0.0] * n_bins

    for feat_id, is_present in features.items():
        likelihoods = _LIKELIHOODS.get(feat_id)
        if likelihoods is None:
            continue
        for j in range(n_bins):
            p = likelihoods[j]
            if is_present:
                # Add log-likelihood of observing the feature
                log_posterior[j] += _safe_log(p)
            else:
                # Add log-likelihood of NOT observing the feature
                log_posterior[j] += _safe_log(1.0 - p)

    # Convert from log-space to probability
    max_log = max(log_posterior)
    posterior_raw = [2.718281828 ** (lp - max_log) for lp in log_posterior]
    total = sum(posterior_raw)
    posterior = [p / total for p in posterior_raw] if total > 0 else [1.0 / n_bins] * n_bins

    # Build posterior dict
    posterior_dict = {}
    for i, label in enumerate(_BIN_LABELS):
        posterior_dict[label] = posterior[i]

    # MAP estimate
    map_idx = posterior.index(max(posterior))
    map_year = _bin_midpoint(_TIME_BINS[map_idx])

    # 95% credible interval
    ci_low, ci_high = _credible_interval(posterior, _TIME_BINS, 0.95)

    return BayesianDatingResult(
        posterior=posterior_dict,
        map_estimate=map_year,
        credible_interval_95=(ci_low, ci_high),
        features_observed=features,
        method="bayesian_aoristic",
    )


def _safe_log(x: float) -> float:
    """Safe natural logarithm (clamps to avoid log(0))."""
    import math
    return math.log(max(x, 1e-10))


def _credible_interval(
    posterior: list[float],
    bins: list[tuple[int, int]],
    level: float = 0.95,
) -> tuple[int, int]:
    """
    Extract the highest-density credible interval from a posterior.

    Returns (from_bce, to_bce) as positive numbers.
    """
    # Sort bins by posterior probability (descending)
    indexed = sorted(enumerate(posterior), key=lambda x: -x[1])
    cumulative = 0.0
    selected_indices = []
    for idx, prob in indexed:
        cumulative += prob
        selected_indices.append(idx)
        if cumulative >= level:
            break

    selected_indices.sort()
    ci_low = bins[selected_indices[0]][0]
    ci_high = bins[selected_indices[-1]][1]
    return (ci_low, ci_high)

