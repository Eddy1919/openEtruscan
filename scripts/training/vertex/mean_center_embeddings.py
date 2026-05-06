"""Mean-center + renormalize embeddings to fight transformer anisotropy.

The XLM-R-base mean-pooled vectors all live in a tight cone around a shared
direction (Ethayarajh 2019, Mu et al 2018) — hence cosine ≥ 0.9998 between
unrelated words observed in the eval. Subtracting the per-language centroid
and re-L2-normalising recovers the meaningful angular structure that was
hiding underneath the shared offset.

Two-pass over the input JSONL (memory-bounded — vectors stream, only the
running mean accumulator stays resident):

  Pass 1: ∑v per language, count per language → centroids
  Pass 2: write (v - centroid_lang) / ‖v - centroid_lang‖

Optionally: drop the top-K principal components after centering ("all-but-
the-top", Mu et al 2018). Disabled by default; enable with --pca-remove K.

Usage::

    python mean_center_embeddings.py \\
        --input_path /gcs/openetruscan-rosetta/embeddings/lat-grc-xlmr-v3.jsonl \\
        --output_path /gcs/openetruscan-rosetta/embeddings/lat-grc-xlmr-v3-centered.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import math
import subprocess
import sys
from pathlib import Path


def _ensure_numpy() -> None:
    try:
        import numpy  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "numpy"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_path", required=True)
    parser.add_argument("--output_path", required=True)
    parser.add_argument(
        "--pca-remove", type=int, default=0,
        help="If >0, drop the top-K principal components after centering "
             "(per language). 2-3 is the standard 'all-but-the-top' setting.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("mean_center")

    _ensure_numpy()
    import numpy as np

    in_path = Path(args.input_path)
    out_path = Path(args.output_path)

    # ── Pass 1: per-language mean ────────────────────────────────────────
    log.info("Pass 1: computing per-language means from %s", in_path)
    sums: dict[str, np.ndarray] = {}
    counts: collections.Counter[str] = collections.Counter()
    sample_dim = None
    with in_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            lang = row.get("language")
            vec = row.get("vector")
            if not (lang and isinstance(vec, list)):
                continue
            if sample_dim is None:
                sample_dim = len(vec)
            v = np.asarray(vec, dtype=np.float64)
            if lang not in sums:
                sums[lang] = np.zeros(sample_dim, dtype=np.float64)
            sums[lang] += v
            counts[lang] += 1
            if (i + 1) % 50_000 == 0:
                log.info("  pass1 read %d rows", i + 1)
    means = {lang: sums[lang] / counts[lang] for lang in sums}
    for lang, m in means.items():
        log.info("  lang=%s n=%d mean‖m‖=%.4f", lang, counts[lang], np.linalg.norm(m))

    # ── Optional Pass 1.5: per-language top-K PCA components ─────────────
    pca_components: dict[str, np.ndarray] = {}
    if args.pca_remove > 0:
        log.info(
            "Pass 1.5: computing top-%d PCs per language for ABTT removal",
            args.pca_remove,
        )
        # Sample up to 20000 rows per lang for PCA (sklearn-free implementation
        # via numpy SVD on the centered sample matrix).
        per_lang_sample: dict[str, list[np.ndarray]] = collections.defaultdict(list)
        SAMPLE_CAP = 20_000
        with in_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                lang = row.get("language")
                vec = row.get("vector")
                if not (lang and isinstance(vec, list)):
                    continue
                if len(per_lang_sample[lang]) < SAMPLE_CAP:
                    v = np.asarray(vec, dtype=np.float64) - means[lang]
                    per_lang_sample[lang].append(v)
        for lang, vecs in per_lang_sample.items():
            X = np.stack(vecs, axis=0)  # (n, dim)
            # SVD on the data matrix gives PCs in V^T rows.
            _, _, Vt = np.linalg.svd(X, full_matrices=False)
            pca_components[lang] = Vt[: args.pca_remove]  # (K, dim)
            log.info(
                "  lang=%s sampled=%d PCs.shape=%s",
                lang, len(vecs), pca_components[lang].shape,
            )

    # ── Pass 2: rewrite ─────────────────────────────────────────────────
    log.info("Pass 2: rewriting to %s", out_path)
    n_total = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with in_path.open(encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            lang = row.get("language")
            vec = row.get("vector")
            if not (lang and isinstance(vec, list)):
                fout.write(line + "\n")
                continue
            v = np.asarray(vec, dtype=np.float64) - means[lang]
            if pca_components.get(lang) is not None:
                pcs = pca_components[lang]  # (K, dim)
                # Project out the top-K principal components: v -= sum(<v,pc>·pc)
                projection = pcs.T @ (pcs @ v)
                v = v - projection
            n = math.sqrt(float(v @ v))
            if n < 1e-12:
                # Degenerate case (vector exactly on the centroid). Keep the
                # zero vector — the API will return cosine 0 for it, which is
                # correct given there's no signal left.
                v_norm = v
            else:
                v_norm = v / n
            row["vector"] = v_norm.tolist()
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_total += 1
            if n_total % 50_000 == 0:
                log.info("  pass2 wrote %d rows", n_total)
    log.info("DONE: wrote %d rows", n_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
