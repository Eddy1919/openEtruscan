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
# 3. DATING HEURISTICS
# ---------------------------------------------------------------------------

# Chronological diagnostic features based on standard Etruscological literature
# (Rix 1963, Bonfante & Bonfante 2002, Wallace 2008)
_ARCHAIC_FEATURES = [
    ("k_before_a", "Uses K before /a/ (archaic tripartition K/C/Q)"),
    ("q_present", "Uses Q before /u/ (archaic tripartition)"),
    ("no_f", "Lacks F (pre-400 BCE script)"),
    ("three_sibilants", "Distinguishes multiple sibilant graphemes"),
]

_CLASSICAL_FEATURES = [
    ("c_dominant", "C used as general velar (K/Q dropped)"),
    ("aspirates_frequent", "Frequent use of θ, φ, χ"),
    ("genitive_al", "Genitive marker -al present"),
]

_LATE_FEATURES = [
    ("f_present", "Uses F (post-400 BCE innovation)"),
    ("simplified_sibilants", "Reduced sibilant inventory"),
    ("latin_influence", "Contains Latin-influenced spellings"),
]


@dataclass
class DatingResult:
    """Estimated date for an inscription based on orthographic features."""

    period: str  # "archaic", "classical", "late", "indeterminate"
    date_range: tuple[int, int]  # (from_bce, to_bce) as positive numbers
    confidence: float  # 0.0–1.0
    features: list[dict]  # [{id, description, present: bool}]

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "date_range": list(self.date_range),
            "date_display": f"{self.date_range[0]}–{self.date_range[1]} BCE",
            "confidence": round(self.confidence, 3),
            "features": self.features,
        }


def estimate_date(
    text: str,
    language: str = "etruscan",
) -> DatingResult:
    """
    Estimate the chronological period of an inscription from orthographic cues.

    Rule-based heuristic using well-established diagnostic features:
      - Archaic (700–500 BCE): K/Q tripartition, no F, three sibilants
      - Classical (500–300 BCE): C dominant, aspirates frequent, -al genitives
      - Late (300–50 BCE): F innovation, simplified sibilants, Latin influence

    Returns an estimated period, date range, confidence score, and the
    list of features that were checked with their presence/absence.
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
        )

    # Extract feature presence
    features_found: dict[str, bool] = {}

    # --- Archaic indicators ---
    # K before a
    has_k_before_a = False
    for i, ch in enumerate(canonical):
        if ch == "k" and i + 1 < len(canonical) and canonical[i + 1] == "a":
            has_k_before_a = True
            break
    features_found["k_before_a"] = has_k_before_a

    # Q present
    features_found["q_present"] = "q" in canonical

    # No F
    features_found["no_f"] = "f" not in canonical

    # Multiple sibilant types
    sibilant_types = sum(1 for s in ["s", "ś", "ξ", "z"] if s in canonical)
    features_found["three_sibilants"] = sibilant_types >= 2

    # --- Classical indicators ---
    # C dominant (uses c, no k or q)
    features_found["c_dominant"] = (
        "c" in canonical and "k" not in canonical and "q" not in canonical
    )

    # Aspirates frequent (θ, φ, χ)
    aspirate_count = sum(1 for ch in canonical if ch in ("θ", "φ", "χ"))
    features_found["aspirates_frequent"] = aspirate_count >= 1

    # Genitive -al
    features_found["genitive_al"] = any(t.endswith("al") for t in tokens)

    # --- Late indicators ---
    # F present
    features_found["f_present"] = "f" in canonical

    # Simplified sibilants (only s, no ś)
    features_found["simplified_sibilants"] = (
        "s" in canonical and "ś" not in canonical and "ξ" not in canonical
    )

    # Latin influence (d, b, g, o — letters Etruscan shouldn't have)
    latin_chars = sum(1 for ch in canonical if ch in ("d", "b", "g", "o"))
    features_found["latin_influence"] = latin_chars >= 1

    # Score each period
    archaic_score = 0.0
    for feat_id, _ in _ARCHAIC_FEATURES:
        if features_found.get(feat_id, False):
            archaic_score += 1.0
    archaic_score /= len(_ARCHAIC_FEATURES)

    classical_score = 0.0
    for feat_id, _ in _CLASSICAL_FEATURES:
        if features_found.get(feat_id, False):
            classical_score += 1.0
    classical_score /= len(_CLASSICAL_FEATURES)

    late_score = 0.0
    for feat_id, _ in _LATE_FEATURES:
        if features_found.get(feat_id, False):
            late_score += 1.0
    late_score /= len(_LATE_FEATURES)

    # Determine winner
    scores = {"archaic": archaic_score, "classical": classical_score, "late": late_score}
    best_period = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best_period]

    # If no clear winner, mark as indeterminate
    sorted_scores = sorted(scores.values(), reverse=True)
    if best_score < 0.25 or (len(sorted_scores) > 1 and sorted_scores[0] - sorted_scores[1] < 0.1):
        best_period = "indeterminate"

    date_ranges = {
        "archaic": (700, 500),
        "classical": (500, 300),
        "late": (300, 50),
        "indeterminate": (700, 50),
    }

    # Build feature report
    all_features = []
    for feat_id, desc in _ARCHAIC_FEATURES + _CLASSICAL_FEATURES + _LATE_FEATURES:
        all_features.append(
            {
                "id": feat_id,
                "description": desc,
                "present": features_found.get(feat_id, False),
            }
        )

    return DatingResult(
        period=best_period,
        date_range=date_ranges[best_period],
        confidence=best_score,
        features=all_features,
    )
