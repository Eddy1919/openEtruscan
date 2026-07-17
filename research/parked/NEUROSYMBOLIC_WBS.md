# Neuro-symbolic methods for low-resource epigraphy — WBS

Work-breakdown for a new research strand: reuse a small set of **computational
principles** (not biological detail) that are unusually well-suited to Etruscan.
One PR per task, same discipline as [`SOTA_ROADMAP.md`](SOTA_ROADMAP.md): pick
the lowest-numbered task whose dependencies are met, open one PR titled
`[<NS-ID>] <title>`.

---

## Thesis

Dead languages are the **anti-LLM regime**: ~6,500 short, formulaic inscriptions,
zero parallel text, no fluent judge. Scaling is the wrong tool. What the problem
needs is **compositional generalization from tiny, highly-structured data** — and
that is exactly what four brain-inspired *principles* provide. We reuse the
principle, never the implementation (spikes/phase/ring geometry are theater for
text):

1. **Factorize** structure from content (cognitive maps / grid codes) → WP2.
2. **Bind** role–filler compositionally in vector algebra (VSA/HRR) → WP1.
3. **Complete** patterns from partial cues (attractors) → WP3.
4. **Ground** meaning in the non-text world (grounded cognitive map) → WP4.

**Standing gate (WP0):** nothing is "better" without an eval. Every WP reports
against a frozen gold set + a named baseline, with the same honesty as
[`v2/PRE_REGISTRATION.md`](v2/PRE_REGISTRATION.md). "Novel-and-right" must be
distinguished from "novel-and-wrong" *before* any claim.

Prior art in this repo to build on / beat: the char-3-gram retriever and RAG
restorer ([`experiments/lacuna_restoration_rag/`](experiments/lacuna_restoration_rag/)),
the LaBSE / etr-lora embeddings ([`FINDINGS.md`](FINDINGS.md)), and the v2.0.3
lacuna gold (66 tasks).

---

## WP0 — Evaluation gate (cross-cutting, do the minimum first)

| ID | Task | Acceptance | Deps | Effort |
|---|---|---|---|---|
| NS0.1 | **Structural-parallel gold** — 150–300 pairs judged "same epigraphic structure? yes/no" (e.g. `larθ velus clan` ↔ `arnθ spurina clan` = yes despite zero shared words). | JSONL of judged pairs, seed-frozen, held-out split. | — | 1–2 d (needs a philologist for a subset) |
| NS0.2 | **Role-query gold** — N inscriptions hand-parsed into `{role: filler}` (gold for unbind accuracy). | ≥200 rows with roles from the WP1 codebook. | — | 1 d |
| NS0.3 | **Restoration gold** — reuse v2.0.3 66-task set; tag each with its structural template. | tagged JSONL. | — | 0.5 d |

Bootstrap trick: draw NS0.1/NS0.2 from the *clean, formulaic* inscriptions (rule-parsable with high confidence), so the eval doesn't itself depend on the model under test.

---

## WP1 — Vector-Symbolic role–filler encoding (HRR/VSA) — **START HERE**

Binding as algebra (Plate HRR / Kanerva; MAP for the bipolar variant). ~Zero
training, kilobytes of parameters, interpretable, robust to missing terms.

Encode an inscription as a bundle of bound role⊗filler pairs:
`I = PRAENOMEN⊗larθ + GENTILICIUM⊗velus + PATRONYMIC⊗cracial + STATUS⊗clan`.

| ID | Task | Acceptance | Deps | Effort |
|---|---|---|---|---|
| NS1.1 | **Role–filler parser** — bootstrap from Etruscan onomastic formulae (praenomen set, gentilicium slot, `-al/-s` genitive patronymics, status words `lautni/clan/sec/puia`, theonyms, `mi`/`turce`/`muluvanice`). Tokenise across the separator zoo (`: · • \| space`). | ≥60% of multi-token inscriptions parsed into ≥2 roles; coverage + confusion reported honestly. | — | 1–2 d |
| NS1.2 | **HRR codebook + encoder** — random atoms for roles + fillers; bind (circular-conv or MAP product), bundle (sum), cleanup memory (nearest atom). | round-trip: `unbind(I, ROLE)` recovers the true filler via cleanup at ≥90% on clean rows. | NS1.1 | 1 d |
| NS1.3 | **Structural retrieval + eval** — content-blind structure vectors; retrieve same-structure/different-filler parallels. | beats char-3-gram + LaBSE on NS0.1 structural-parallel gold (report P@k). | NS1.2, NS0.1 | 1 d |
| NS1.4 | **Analogy / prosopography** — `larθ:velus :: arnθ:?`; kinship reconstruction via unbind + cleanup. | recovers held-out `(gens, patronymic)` links at > random baseline on NS0.2. | NS1.2, NS0.2 | 1 d |
| NS1.5 | **Graceful degradation** — measure retrieval/unbind accuracy vs fraction of roles removed (simulate fragmentary stones). | monotone, gentle degradation curve; documented. | NS1.2 | 0.5 d |

**Decision gate:** if NS1.3 beats baselines on structural parallels → VSA is a real
tool; feed it into WP3 and the restorer. If not → document as a negative result
(structure-blind retrieval doesn't help Etruscan) and stop WP1.

---

## WP2 — Factorized structure↔content model (cognitive-maps / TEM, applied)

Small model with a **bottleneck separating a discrete template latent from
content fillers**, so templates transfer across names → zero-shot slot restoration.

| ID | Task | Acceptance | Deps | Effort |
|---|---|---|---|---|
| NS2.1 | **Template induction** — cluster inscriptions into templates (from WP1 role-sequences or an unsupervised latent). | interpretable template inventory covering the head classes. | WP1 | 1–2 d |
| NS2.2 | **Factorized model** — train with structure/content split (VQ or discrete bottleneck for structure; free fillers). | reconstructs held-out inscriptions; latent demonstrably encodes template not content (swap test). | NS2.1 | 3–5 d |
| NS2.3 | **Zero-shot slot restoration** — fill a lacuna with a name never seen in that slot. | beats the RAG restorer on the subset where the true filler is absent from all retrieved parallels (NS0.3). | NS2.2, NS0.3 | 1 d |

Risk: data-hungry and eval-hard. Gate on WP1 succeeding first.

---

## WP3 — Modern Hopfield restoration over structure-factored patterns

Store patterns as attractors; a damaged inscription relaxes to the completion,
with **basin depth = confidence**. Only novel *on top of* WP1/WP2 (raw-text
Hopfield ≈ the RAG retriever we already have — say so).

| ID | Task | Acceptance | Deps | Effort |
|---|---|---|---|---|
| NS3.1 | **Structure-factored Hopfield** — store WP1 hypervectors; single-step completion of a masked inscription. | completes held-out masked rows; documented equivalence/difference vs RAG. | WP1 | 1 d |
| NS3.2 | **Basin-depth confidence** — calibrate settle-sharpness against correctness. | confidence monotone with accuracy on NS0.3 (like the RAG calibration table). | NS3.1, NS0.3 | 0.5 d |

---

## WP4 — Grounded cognitive map (the deep bet: "interpret", not just "retrieve")

Place each inscription by **text × findspot(geo) × date × object-type × image**.
Meaning triangulated by co-occurring world-context. Geography/time are genuine
continuous manifolds → the manifold/map machinery finally applies literally.

| ID | Task | Acceptance | Deps | Effort |
|---|---|---|---|---|
| NS4.1 | **Assemble grounded features** — join text with provenance (findspot lat/lon), date_approx, object/medium, and images where present. | a grounded feature table over the corpus; coverage reported per modality. | — | 1–2 d |
| NS4.2 | **Joint grounded space** — fuse modalities into one map (start simple: concat + learned projection; later contrastive). | held-out inscription localizes near its true geo/time/type neighbours. | NS4.1 | 3–5 d |
| NS4.3 | **Triangulation queries** — dialect gradient over geo; chronological drift; contested-word meaning via world-context neighbours. | ≥1 philologist-reviewed case where grounding changes the reading vs text-only. | NS4.2 | ongoing |

Risk/honesty: highest payoff, highest cost, hardest eval. It is the highest-risk
work package for decipherment *assistance*; treat NS4.3 as qualitative +
expert-reviewed, never a silent metric.

---

## Sequencing

```
WP0.min (NS0.2, NS0.3)  ─┐
NS1.1 → NS1.2 → NS1.3 ───┤→ decision gate → WP3 (NS3.*)  and/or  WP2
                          │
NS0.1 (needs philologist) ┘   WP4 runs in parallel (data assembly NS4.1 anytime)
```

Critical path to a decisive result: **NS1.1 → NS1.2 → NS1.3**. That's the
"does VSA beat embeddings on structural parallels" question, and it's cheap.

## Honest limitations (stated up front)

- The role parser is heuristic; its coverage caps everything downstream. Report it.
- "Structure" only helps where inscriptions *have* shared structure — fragments and one-word texts won't benefit; quantify how much of the corpus is in scope.
- Every "better" needs WP0 gold. No leaderboard theatre.
- WP4's grounding is only as good as the provenance data (34.9% documented — see the corpus provenance tiers).
