#!/bin/bash
# Download CIE fascicle PDFs from studietruschi.org
BASE="https://www.studietruschi.org/wp-content/uploads"

FILES=(
  # Volume I
  "2025/01/CIE-I_Introduzione.pdf"
  "2025/01/CIE-I_tit.1_474.pdf"
  "2025/01/CIE-I_Clusium-cum-agro-Clusino-tit.-475-1742.pdf"
  "2025/01/CIE-I_Clusium-cum-agro-Clusino-tit.-1743-3306.pdf"
  "2025/01/CIE-I_Perusia-tit.-3307-4612.pdf"
  "2025/01/CIE-I_Additamentum.pdf"
  # Volume II
  "2025/01/CIE-II-1-1_nn.-4918-5152.pdf"
  "2025/01/CIE-II-1_1_nn.-5153-5210.pdf"
  "2025/01/CIE-II-2-1_tit.-8001-8448.pdf"
  "2024/12/CIE-II.2.2_Indices-et-Tabulae.pdf"
  # Volume III
  "2024/12/CIE-III_1-Tarquinii.pdf"
  "2024/12/CIE-III_1-Indices.pdf"
  # Supplementum
  "2024/12/CIE-Suppl_Zagrabia.pdf"
)

echo "Downloading ${#FILES[@]} CIE fascicle PDFs..."
for f in "${FILES[@]}"; do
  filename=$(basename "$f")
  if [ -f "$filename" ]; then
    echo "  ⏭  $filename (already exists)"
  else
    echo "  ⬇  $filename"
    curl -sLo "$filename" "$BASE/$f" && echo "  ✅  $filename" || echo "  ❌  $filename FAILED"
  fi
done
echo ""
echo "Done. Files:"
ls -lh *.pdf 2>/dev/null
