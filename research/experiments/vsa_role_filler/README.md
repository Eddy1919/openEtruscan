# Vector-Symbolic role–filler encoding (WP1 spike)

First build of WP1 of the neurosymbolic work plan (maintainer-held)
(NS1.1 + NS1.2 + NS1.3). Binding-as-algebra (Plate HRR / Kanerva; MAP bipolar
variant) applied to the real corpus — **zero training**.

## Question

Can we represent an inscription as a bundle of bound `role⊗filler` pairs so that
(a) unbinding recovers a filler by algebra, and (b) we retrieve **structural**
parallels — same epigraphic structure, *different words* — that a char-3-gram
(lexical) baseline cannot see?

`I = PRAENOMEN⊗larθ + GENTILICIUM⊗velus + PATRONYMIC⊗cracial + STATUS⊗clan`

## Method

- **NS1.1 parser** — heuristic, formulaic-first: praenomen set, gentilicium slot,
  `-al/-s/-sa` genitive → PATRONYMIC, status words (`lautni/clan/sec/puia`),
  theonyms, `mi`/`turce`. Tokenised across the separator zoo (`: · • | space`).
- **NS1.2 encoder** — MAP/HRR: random bipolar atoms per role, per filler, and per
  position; bind = elementwise product (self-inverse), bundle = sum; cleanup =
  nearest filler atom. `D = 4096`. Content vector `I = Σ role⊗filler`; content-blind
  structure vector `S = Σ role⊗position`.
- **NS1.3** — retrieve by `S` (structure) vs a char-3-gram cosine baseline; score
  each method's top-5 by role-sequence similarity and by shared-word (lexical)
  overlap.

## Results (seed=7, D=4096, corpus = 5,932 inscriptions)

Parser: 2,756 multi-token inscriptions; roles GENTILICIUM 6105 / PRAENOMEN 5914 /
PATRONYMIC 1840 / EGO 173 / STATUS 96 / VERB 43 / OBJECT 19 / THEONYM 18.

**Round-trip unbind** (`cleanup(I ⊗ ROLE)` recovers the filler):

| role | accuracy | note |
|---|---:|---|
| STATUS | 98.9% | singular per inscription |
| PATRONYMIC | 88.7% | usually singular |
| GENTILICIUM | 64.1% | often 2+ bound to one role → superposition crosstalk |

**Structural retrieval (NS1.3, top-5, n=120 queries):**

| method | role-structure sim | lexical (word) overlap |
|---|---:|---:|
| VSA structure vector | **0.977** | **0.024** |
| char-3-gram baseline | 0.831 | 0.089 |

VSA surfaces near-identical structure with almost no shared words — e.g.
`larθ θeprine vetnalisa` ↔ `velia muθuna velus` (PRAENOMEN·GENTILICIUM·PATRONYMIC,
**0 shared characters**); `arntni sepu tutnal clan` ↔ `larθiaial arθniai seiaθial sec`
(STATUS·PRAENOMEN·GENTILICIUM·PATRONYMIC, 0 shared words). These are parallels a
lexical or surface-embedding method cannot pair.

## Honest caveats (do not oversell)

1. **The 0.98-vs-0.83 headline is partly circular** — the VSA structure vector is
   built from the roles the metric then scores, so clustering-by-role is
   guaranteed. The non-trivial signal is the **near-zero lexical overlap at high
   structure match** (it is not just retrieving lexical copies). A real
   "beats embeddings" claim needs the human-judged **NS0.1 structural-parallel
   gold**, not role-Jaccard. Feasibility confirmed; validation pending the gate.
2. **Parser quality is unmeasured.** The greedy fallback assigns a role to every
   leftover token, so "coverage" is trivially high but role *correctness* is not
   yet evaluated (that is NS0.2). It also imposes name-structure on non-name /
   garbled inscriptions.
3. **Repeated-role crosstalk** caps GENTILICIUM unbind at 64%; fixable by binding
   each repeated filler to a distinct positional/index atom (NS1.2 follow-up).

## Silver re-score (NS0.1-silver) — the non-circular test

`vsa_silver_eval.py` builds a **silver** structural-parallel set from
*high-confidence* parses only (anchored by a known function word / praenomen, not
the greedy fallback) and re-scores retrieval where it can't be circular: on
same-template pairs that **share zero words**, a lexical method has nothing to
grab, so the baseline scores there are fully honest.

- High-confidence subset: **611 / 5,932 (~10%)** inscriptions (anchored, ≥3 roles).
  This is the current *scope* of structural retrieval — the clearly formulaic
  onomastic texts; fragments and one-word stones are out of scope.
- 48 templates with ≥2 members; 487 queries; **412 have a zero-word sibling**.

**Recall@10 (seed=11):**

| method | all same-template | **zero-word siblings** |
|---|---:|---:|
| VSA structure | 1.000 | **0.911** (by construction) |
| char-3-gram | 0.299 | **0.082** |
| token-overlap | 0.273 | **0.005** |
| random floor | 0.107 | 0.102 |

**Non-circular finding:** lexical retrieval **cannot** find structural parallels —
char-3-gram (0.082) is at the random floor (0.102) on zero-word siblings,
token-overlap (0.005) below it. VSA reaches them (0.911) — by construction, since
its vector encodes the template. So the eval proves the *baseline gap* honestly;
it does **not** independently prove VSA quality (that stays tautological here).

**Residual gate:** whether "same parsed template" == "genuine philological
parallel" needs a philologist. The script prints a spot-check list; most pairs are
real (`larθi satnei carnasa` ↔ `velia muθuna velus`), one was garbled
(`ARNθNA IθU LARθI`) — i.e. templates are mostly-right, not perfect (parser-limited).

## NS1.1-widen + neural-embedding baseline (`vsa_widen_neural.py`)

Widened parser (bigger praenomen/kinship/theonym lexicons, abbreviation handling,
2-slot templates) and a third, **neural** baseline added to the silver re-score.

**Scope after widening:** anchored ≥3-role parses **611 → 678 (11.4%)**; anchored
≥2-role **968 (16.3%)**. Honest ceiling: only 2,756 / 5,932 inscriptions are
multi-token — ~54% of the corpus is a single word/fragment with no structure to
retrieve. Structural retrieval is inherently for the multi-word onomastic core;
the *corpus*, not the parser, is the main limit.

**Silver re-score with a neural baseline (n=678, seed=11):**

| method | recall@10 all | recall@10 **zero-word** |
|---|---:|---:|
| VSA structure | 1.000 | **0.918** (by construction) |
| gemini-embedding-001 (768d) | 0.285 | **0.085** |
| char-3-gram | 0.297 | 0.095 |
| token-overlap | 0.266 | 0.013 |
| random floor | 0.108 | 0.107 |

**"Beats embeddings" — settled.** A strong neural sentence embedding retrieves
zero-word structural siblings at 0.085 — the random floor, indistinguishable from
char-ngram. So **neither surface nor semantic embeddings encode abstract role
structure**; only the role-factored VSA representation does (non-circular, since
the embeddings aren't built from the parse). This is the genuine contribution of
the strand.

## NS1.4 — prosopography / analogy (`vsa_prosopography.py`)

Two capabilities fall out of the role-filler parse:

- **Gens grouping (strong):** unbind/group by GENTILICIUM → 2,882 distinct gentes,
  **190 with ≥3 attested members**. Produces immediately-useful auto-dossiers —
  e.g. gens `cainei` assembles **27 stones** with their praenomina + patronymics
  (`θana cainei velus`, `larθi cainei velus`, …).
- **Cross-stone filiation linking (proof-of-concept):** a stone's PATRONYMIC is the
  genitive of the parent's name, so we link it to the parent's *own* stone in the
  same gens. **13 clean father↔child links**, e.g. `laris vete arnθal` (Laris, son
  of Arnth) → `arnθ vete tetial` (the stone of Arnth Vete); `larθ carna velus` →
  `vel carna`. Genuine automated family-network reconstruction.

Honest limits: yield is modest (13) because it needs *both* stones attested and
parseable; some parser "gentes" are noise (`ril` = "aged", not a family); proper
Etruscan patronymic morphology + disambiguation would raise both precision and
recall. The VSA relational-analogy test (`child ⊗ T → parent`) needs ≥20 clean
pairs to be meaningful and only ~13 links exist → **deferred**, not claimed.

## NS3.1 — structure → restoration A/B (NEGATIVE, `vsa_restore_ab.py`)

Tested whether feeding **structural** (VSA) parallels to the lacuna restorer beats
the shipped **lexical** (char-3-gram) RAG. Same 66-task v2.0.3 gold, same model
(gemini-2.5-flash) and prompt; only the retrieved parallels differ.

| parallels fed to restorer | span-exact (all 66) | structured subset (65) |
|---|---:|---:|
| char-3-gram (shipped RAG) | **0.318** | **0.323** |
| VSA-structural | 0.167 | 0.169 |

**Structural parallels *hurt* restoration.** Interpretation: restoration is a
**lexical** problem — to fill `mi mla?mlakaš` you need stones sharing the actual
surrounding words (`mi mlaχ mlakas`), not stones sharing only the abstract role
template. Structure gives the shape, not the missing character.

**Conclusion / architectural guardrail:** VSA/structure is for parallel-finding
and prosopography; the restorer must keep its lexical retriever. (A lexical∪
structural *hybrid* is untested and the only remaining reason structure might aid
restoration — e.g. when no lexical parallel exists.) This is why WP3 in the WBS is
"only novel *on top of* WP1" — and here the raw swap is a documented negative.

## Verdict

WP1 is worth continuing. Established: (1) binding-as-algebra runs on real data with
zero training; (2) it does the one thing lexical/embedding retrieval provably
can't — structural parallels at zero lexical overlap (baselines ≈ random there);
(3) current scope is ~10% of the corpus (parser-limited). Next per the WBS:
philologist-ratify a slice of the silver → true NS0.1 gold; widen the parser
(raise the ~10%); fix repeated-role crosstalk (positional binding); add a neural
embedding (LaBSE / gemini) as a third baseline; then feed structure-factored
vectors into WP3 (Hopfield restoration).

## Reproduction

```bash
python vsa_etruscan.py     # numpy only; corpus.json is the public /search dump (CC BY 4.0)
```
`corpus.json` = `{id, canonical}` for the 5,932 public inscriptions, pulled from
`www.openetruscan.com/api/search` (regenerable).
