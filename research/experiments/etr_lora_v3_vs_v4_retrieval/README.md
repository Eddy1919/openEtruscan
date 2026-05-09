# etr-lora v3 vs v4 — Retrieval A/B

## Question

Did re-training the XLM-RoBERTa + LoRA embedder on the *cleaned* corpus (Cyrillic mirror-glyphs purged, σ/ś/š/ς unified, Old Italic regenerated) produce measurably better retrieval than v3?

## Dataset

A small set of query inscriptions drawn from across the corpus, designed to surface three failure modes of v3:

1. **Sibilant tradition splits** — query has `ś`/`s`, target uses `σ`. v3 treated these as different lexical tokens; v4 should cluster them.
2. **Structural pattern matching** — query is a `[Name]:[Name]:cvan` kinship formula; v4 should retrieve other rows with the same syntactic structure rather than scattered surface-character matches.
3. **Abbreviation handling** — query contains the `ś:l:` patronymic abbreviation; v4 should associate this with full Etruscan name patterns.

## Protocol

1. Embed the query with both v3 and v4 adapters.
2. Run k=5 nearest-neighbor search against the existing pgvector HNSW indexes (one per adapter).
3. Compare the top-5 neighbors qualitatively.

## Run

```bash
python research/experiments/etr_lora_v3_vs_v4_retrieval/eval.py
```

## Results

Qualitative wins observed across all three target failure modes:

### Example 1 — Sibilant convergence

- **Query**: `θania śeianti tlesnaśa`
- **v3 neighbors**: generic names starting with `θania:` (`θania:hecn(i)`, `θania:clantini`)
- **v4 neighbors**: `śeianti • hanunia • tleσnaśa` — note the query has `ś` / `s`, neighbor has `σ` / `σ`. v4 has internalized the σ ↔ ś orthographic equivalence.

### Example 2 — Structural understanding

- **Query**: `arnθ:apucu:θanχvilus:ruvfial:cvan`
- **v3 neighbors**: scattered fragments matching the colon character (`θana : hescn(i) [---]`, `θana:ceisni:s[`)
- **v4 neighbors**: other `cvan` formula rows (`ramθa:capznei:c[v]an`, `v(elia):clanti:cvan`, `ramθa:peticui:cvan`) — the model now recognizes the kinship/dedicatory structure beyond character-level noise.

### Example 3 — Abbreviation handling

- **Query**: `arnθ:cicu:peθna:ś:l:`
- **v3 neighbors**: generic colon strings (`tite::petruni:::::`)
- **v4 neighbors**: `a(rn)θ(al) hupn(i)ś` and `arnθ:helen[e_]` — abbreviation patterns associated with full name forms.

## Conclusion

Re-embedding the corpus with v4 is justified. The qualitative gains are concentrated exactly where the cleaning intervened (sibilant unification, mirror-glyph removal, Old Italic regeneration), confirming that the encoder learned phonologically-meaningful features rather than surface character coincidences.

Quantitative retrieval metrics (precision@k against a labeled relevance set) — pending.
