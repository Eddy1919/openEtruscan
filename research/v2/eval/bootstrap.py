"""Bootstrap-CI and paired-bootstrap utilities for v2 evaluation.

Shared across classification, Rosetta, and lacuna pipelines. Every reported
metric in v2 must come from this module so the CIs are computed identically.

Design notes
------------
- Resampling is *paired*: when comparing model A vs model B on the same test
  set, we resample row indices once and use those same indices to compute both
  metrics on each bootstrap iteration. This controls for test-set variance
  and gives a much tighter CI on the *delta* than unpaired bootstrapping.
- Random seeds are pinned. Reproducibility is mandatory.
- We return both the point estimate and the (lower, upper) bound of the 95% CI
  (percentile method, not BCa — simpler and adequate for our n).
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Sequence


@dataclass(frozen=True)
class BootstrapResult:
    """Point estimate and 95% CI from a bootstrap resample."""

    point: float
    ci_low: float
    ci_high: float
    n_resamples: int
    seed: int

    def fmt(self) -> str:
        half = (self.ci_high - self.ci_low) / 2.0
        return f"{self.point:.4f} ± {half:.4f} (95% CI [{self.ci_low:.4f}, {self.ci_high:.4f}])"

    def to_dict(self) -> dict:
        return {
            "point": self.point,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "n_resamples": self.n_resamples,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class PairedResult:
    """Delta + p-value from a paired-bootstrap test between two models."""

    delta_point: float
    delta_ci_low: float
    delta_ci_high: float
    p_value: float
    n_resamples: int
    seed: int

    def fmt(self) -> str:
        half = (self.delta_ci_high - self.delta_ci_low) / 2.0
        return (
            f"Δ = {self.delta_point:+.4f} ± {half:.4f} "
            f"(95% CI [{self.delta_ci_low:+.4f}, {self.delta_ci_high:+.4f}]), "
            f"p = {self.p_value:.4f}"
        )

    def is_significant(self, alpha: float = 0.05) -> bool:
        return self.p_value < alpha

    def to_dict(self) -> dict:
        return {
            "delta_point": self.delta_point,
            "delta_ci_low": self.delta_ci_low,
            "delta_ci_high": self.delta_ci_high,
            "p_value": self.p_value,
            "n_resamples": self.n_resamples,
            "seed": self.seed,
        }


def bootstrap_ci(
    rows: Sequence,
    metric_fn: Callable[[Sequence], float],
    n_resamples: int = 10_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> BootstrapResult:
    """Return point estimate + (1-alpha) CI for `metric_fn` on `rows`.

    metric_fn is called once with the full `rows` (point estimate) and
    n_resamples times with resampled rows. It must be deterministic.
    """
    if not rows:
        raise ValueError("bootstrap_ci called on empty sequence")
    rng = random.Random(seed)
    n = len(rows)
    point = float(metric_fn(rows))
    resample_metrics: list[float] = []
    for _ in range(n_resamples):
        sample_idx = [rng.randrange(n) for _ in range(n)]
        sample = [rows[i] for i in sample_idx]
        resample_metrics.append(float(metric_fn(sample)))
    resample_metrics.sort()
    alpha = 1.0 - confidence
    lo_idx = int(alpha / 2.0 * n_resamples)
    hi_idx = int((1.0 - alpha / 2.0) * n_resamples) - 1
    return BootstrapResult(
        point=point,
        ci_low=resample_metrics[lo_idx],
        ci_high=resample_metrics[hi_idx],
        n_resamples=n_resamples,
        seed=seed,
    )


def paired_bootstrap(
    rows: Sequence,
    metric_a: Callable[[Sequence], float],
    metric_b: Callable[[Sequence], float],
    n_resamples: int = 10_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> PairedResult:
    """Paired-bootstrap test of (metric_a - metric_b) on the same rows.

    Both metric_a and metric_b are called with the SAME resample of `rows` on
    every iteration. The p-value is the one-sided fraction of resamples where
    delta <= 0 (i.e., A did not beat B). For a two-sided test, double it.
    """
    if not rows:
        raise ValueError("paired_bootstrap called on empty sequence")
    rng = random.Random(seed)
    n = len(rows)
    point_a = float(metric_a(rows))
    point_b = float(metric_b(rows))
    delta_point = point_a - point_b
    deltas: list[float] = []
    n_le_zero = 0
    for _ in range(n_resamples):
        sample_idx = [rng.randrange(n) for _ in range(n)]
        sample = [rows[i] for i in sample_idx]
        delta = float(metric_a(sample)) - float(metric_b(sample))
        deltas.append(delta)
        if delta <= 0:
            n_le_zero += 1
    deltas.sort()
    alpha = 1.0 - confidence
    lo_idx = int(alpha / 2.0 * n_resamples)
    hi_idx = int((1.0 - alpha / 2.0) * n_resamples) - 1
    return PairedResult(
        delta_point=delta_point,
        delta_ci_low=deltas[lo_idx],
        delta_ci_high=deltas[hi_idx],
        p_value=n_le_zero / n_resamples,
        n_resamples=n_resamples,
        seed=seed,
    )


def krippendorff_alpha_nominal(ratings: Sequence[Sequence[str | None]]) -> float:
    """Krippendorff's alpha for nominal data with missing values.

    `ratings[item][rater]` is the label (or None for missing). Returns alpha
    in [-1, 1]; >= 0.80 is the conventional threshold for acceptable
    annotation agreement.

    Implementation follows Krippendorff (2011) "Computing Krippendorff's
    Alpha-Reliability", using coincidence matrices.
    """
    # Coincidence matrix: c[v1][v2] = sum over items of (pair count of v1,v2) / (m_i - 1)
    # where m_i is the number of valid ratings on item i.
    values: set[str] = set()
    for row in ratings:
        for v in row:
            if v is not None:
                values.add(v)
    if not values:
        return float("nan")
    vlist = sorted(values)
    vidx = {v: i for i, v in enumerate(vlist)}
    k = len(vlist)
    coincidences: list[list[float]] = [[0.0] * k for _ in range(k)]
    totals: list[float] = [0.0] * k
    for row in ratings:
        valid = [v for v in row if v is not None]
        m = len(valid)
        if m < 2:
            continue
        # Count ordered pairs; each unordered pair contributes twice to the
        # symmetric coincidence matrix.
        for i, a in enumerate(valid):
            for j, b in enumerate(valid):
                if i == j:
                    continue
                coincidences[vidx[a]][vidx[b]] += 1.0 / (m - 1)
    for i in range(k):
        totals[i] = sum(coincidences[i])
    n_total = sum(totals)
    if n_total == 0:
        return float("nan")
    # Observed disagreement
    obs_disagreement = 0.0
    for i in range(k):
        for j in range(k):
            if i != j:
                obs_disagreement += coincidences[i][j]
    # Expected disagreement under random assignment
    exp_disagreement = 0.0
    for i in range(k):
        for j in range(k):
            if i != j:
                exp_disagreement += totals[i] * totals[j] / (n_total - 1)
    if exp_disagreement == 0:
        return 1.0 if obs_disagreement == 0 else float("nan")
    return 1.0 - obs_disagreement / exp_disagreement


def write_result(path: Path, payload: dict) -> None:
    """Write a JSON result file with a stable schema for downstream tooling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    # Quick self-test: synthetic accuracy comparison
    rng = random.Random(0)
    rows = [(rng.random() < 0.7, rng.random() < 0.6) for _ in range(200)]
    def acc_a(rs):
        return sum(1 for a, _ in rs if a) / len(rs)
    def acc_b(rs):
        return sum(1 for _, b in rs if b) / len(rs)
    a_res = bootstrap_ci(rows, acc_a)
    b_res = bootstrap_ci(rows, acc_b)
    paired = paired_bootstrap(rows, acc_a, acc_b)
    print(f"A: {a_res.fmt()}")
    print(f"B: {b_res.fmt()}")
    print(f"A vs B paired: {paired.fmt()}  significant={paired.is_significant()}")

    # Krippendorff sanity: perfect agreement => 1.0
    perfect = [["a", "a", "a"]] * 30 + [["b", "b", "b"]] * 30
    print(f"krippendorff(perfect agreement) = {krippendorff_alpha_nominal(perfect):.3f}")
    half = [["a", "a", "b"]] * 30 + [["b", "a", "b"]] * 30
    print(f"krippendorff(partial agreement) = {krippendorff_alpha_nominal(half):.3f}")
