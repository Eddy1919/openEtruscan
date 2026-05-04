#!/usr/bin/env bash
# Download a fasttext.cc pretrained word-vector binary.
#
# fasttext.cc publishes 157-language Common-Crawl + Wikipedia FastText
# models at https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/.
# Each model is named cc.<iso>.300.bin.gz and decompresses to a
# ~7 GB native-format binary that gensim reads via load_facebook_vectors.
#
# Usage:
#   ./scripts/ops/download_fasttext_model.sh <iso-code> [output-dir]
#
# Examples:
#   ./scripts/ops/download_fasttext_model.sh la            # Latin
#   ./scripts/ops/download_fasttext_model.sh eu            # Modern Basque
#   ./scripts/ops/download_fasttext_model.sh el models/    # Modern Greek (NOT Ancient)
#
# Note: Ancient Greek (grc) is NOT in fasttext.cc's 157-language set —
# fasttext.cc only covers languages with substantial Common Crawl
# representation, which means modern Greek (`el`) only. For Ancient
# Greek embeddings, use CLTK's pretrained Greek vectors instead:
#   pip install cltk && cltk import-corpus greek_models_cltk

set -euo pipefail

ISO="${1:?'Usage: download_fasttext_model.sh <iso-code> [output-dir]'}"
OUT_DIR="${2:-models}"

URL="https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.${ISO}.300.bin.gz"
OUT_GZ="${OUT_DIR}/cc.${ISO}.300.bin.gz"
OUT_BIN="${OUT_DIR}/cc.${ISO}.300.bin"

mkdir -p "${OUT_DIR}"

if [[ -f "${OUT_BIN}" ]]; then
  echo "==> Already have ${OUT_BIN}, skipping download."
  echo "    Delete it and re-run if you want a fresh copy."
  exit 0
fi

echo "==> Downloading ${URL}"
echo "    (~4-7 GB compressed; takes a few minutes on a good link)"
curl -fL --progress-bar -o "${OUT_GZ}" "${URL}"

echo "==> Decompressing"
gunzip -k "${OUT_GZ}"  # -k keeps the .gz around so re-runs don't redownload

echo
echo "Done."
echo "  Compressed:   ${OUT_GZ}  ($(du -h "${OUT_GZ}" | cut -f1))"
echo "  Decompressed: ${OUT_BIN}  ($(du -h "${OUT_BIN}" | cut -f1))"
echo
echo "Next:"
echo "  python scripts/ops/populate_language.py \\"
echo "    --language ${ISO} --source-model ${OUT_BIN} \\"
echo "    --align-to ett --anchor-model models/etruscan.bin"
