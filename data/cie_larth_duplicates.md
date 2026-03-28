# CIE vs Larth Overlap Report

This report identifies potential duplicates between the new CIE VLM ingestion and the existing Larth (Etruskische Texte) dataset base on text similarity.

## Exact Matches
Documents whose text, after removing spaces and punctuation, is completely identical.

| CIE ID | CIE Text | Larth ID | Larth Text |
|--------|----------|----------|------------|

## Fuzzy Matches
Documents whose normalized text is at least 85.0% similar.

| CIE ID | CIE Text | Larth ID | Larth Text | Similarity |
|--------|----------|----------|------------|------------|
| CIE 58 | L.ATVNI | 2095 | la----tni | 0.91 |
| CIE 141 | XIIX.... | 5834 | xiixx | 0.89 |
| CIE 211 | arnθ:prumaθni:arnθal | 211 | arnθ prumaθni(alisa) arnθ(i)al | 0.86 |
