# Classification Codebook (v2)

**Task:** Assign exactly one of 7 epigraphic-type labels to each Etruscan inscription.

**Status:** frozen at 2026-05-17. Edits require a v2.1 codebook bump and re-jury of any affected rows.

**Intended raters:** frontier LLMs in the jury phase, classical philologists in the adjudication phase. Both must follow the same rubric.

## The 7 classes

The 7-class taxonomy is the union of categories actually attested in the OpenEtruscan v1 corpus (`research/data/openetruscan_labels.csv`). Classes are listed in descending frequency:

| Class | v1 silver count | What it is |
|---|---:|---|
| `funerary` | 409 | Tomb / urn / sarcophagus inscriptions naming the deceased, often with parentage formulas (`larθ velus papas`). |
| `ownership` | 156 | "I am of X" formulas, maker marks, possessive identifiers on portable objects (vases, bronze utensils, dice). |
| `dedicatory` | 111 | Gifts to deities or persons, often with verb `tur-` / `mulu-` ("gave") or `cana` ("dedicated this"). |
| `votive` | 14 | Inscribed offerings deposited at sanctuaries with explicit vow language or sanctuary findspot. |
| `legal` | 10 | Boundary contracts, sale agreements, manumissions, sacred-law tablets (e.g. Tabula Cortonensis-style). |
| `boundary` | 10 | *tular* / *tular spural* markers; cippi delimiting sacred or civic land. |
| `commercial` | 2 | Trade-related: weights, measures, tags. Often pithos rim-marks naming quantities. |

The class set is **closed**: any inscription that does not fit must be marked `unsure` and routed to the adjudication queue. Do not invent new classes during labeling.

## Decision tree

Apply the tests in order. The first match wins.

```
1. Is the object a tomb, urn, sarcophagus, or grave-good with a personal name AND a kinship/death formula?
   ├─ YES → funerary
   └─ NO → 2

2. Does the text contain a verb of giving (tur-, mulu-, cer-) OR a dedicatory formula (cana, ame, fler) WITH a recipient (deity, person, sanctuary)?
   ├─ YES → 3
   └─ NO → 5

3. Was the object deposited at a known sanctuary, OR does the text contain a vow / ex-voto formula?
   ├─ YES → votive
   └─ NO → 4

4. Is the recipient a deity or person of higher status, and the act is a gift?
   ├─ YES → dedicatory
   └─ NO → return to 5

5. Does the text contain "mi" + genitive of a personal name (and nothing else substantive), OR is the object a portable utensil with a maker-mark?
   ├─ YES → ownership
   └─ NO → 6

6. Is the text on a stone marker delimiting land or sacred space, with the word "tular" or equivalent boundary-vocabulary?
   ├─ YES → boundary
   └─ NO → 7

7. Does the text contain legal vocabulary (sale, contract, manumission, sacred law) OR is the object a wax tablet / bronze tablet with formal contractual structure?
   ├─ YES → legal
   └─ NO → 8

8. Does the inscription record a quantity, a weight, a measure, or a trade mark on a transport amphora?
   ├─ YES → commercial
   └─ NO → unsure (route to adjudication)
```

### Tie-breaking

Real inscriptions often satisfy multiple branches. Resolve in this priority:
1. **Funerary trumps everything else** when the object is unambiguously sepulchral and the text is the deceased's name. A funerary urn that happens to say `mi larthal` is `funerary`, not `ownership`, because the find-context is decisive.
2. **Object > text** when text alone is ambiguous. A *cippus* with a single name on it is `boundary` if the cippus shape and findspot are diagnostic, regardless of whether the text resembles ownership.
3. **Verb > noun** when adjudicating dedicatory vs ownership. `mi tite vetiale tur-uce` (gave) → dedicatory. `mi tite vetiale` (no verb) → ownership.

## Positive and negative examples per class

### funerary

**POSITIVE:**
- `larθ velus papas` (Ta 1.66) — kinship-list, on tomb wall: `funerary`
- `larθia spurinas larisal puia` (Cl 1.1006) — "Larthia of Spurinas, wife of Laris" on urn: `funerary`
- `vel matunas larisal clan avils XXV` — "Vel Matunas son of Laris, aged 25": `funerary`

**NEGATIVE (commonly misclassified):**
- `mi larthia` on a small bronze mirror → this is `ownership`, NOT `funerary`. Mirror is a personal object, not a grave-good necessarily, and the formula is possessive without kinship.
- `mi tite vetiale tur-uce` — has a personal name but the verb is gift-giving → `dedicatory`.

### ownership

**POSITIVE:**
- `mi larthia` (Ve 6.2) on a bronze hand-mirror: `ownership`
- `eca suthi velasnas` (rare formula meaning "this tomb of-Velasnas") IS funerary not ownership, despite the form — see tie-breaking rule 1.

**NEGATIVE:**
- `mi tite vetiale tur-uce` — verb of giving present → `dedicatory`.
- Any "mi" formula on a tomb chamber wall → `funerary` (rule 1).

### dedicatory

**POSITIVE:**
- `mini muluvanice mamarce velthuru` — "Mamarce Velthuru dedicated me": `dedicatory`
- `cana arnθal larisalisla suθinaśia` (TCa 8) on funerary marker BUT containing dedication verb to deceased — adjudication-queue (could be either; the `suθina` formula leans funerary). Rate as `unsure`.

**NEGATIVE:**
- `mi larthia` (no verb) → `ownership`, not dedicatory, even if found in a sanctuary.
- A votive dedication explicitly at a sanctuary with vow language → `votive`, not dedicatory (more specific).

### votive

**POSITIVE:**
- A bronze figurine deposited at the Portonaccio sanctuary with `flerś` ("offering") on the base: `votive`
- An ex-voto leg or arm with `mini turuce X` and an explicit healing context: `votive` (more specific than dedicatory).

**NEGATIVE:**
- A gift between named individuals, not to a deity: `dedicatory`.

### legal

**POSITIVE:**
- The Tabula Cortonensis (Co 8.5): land sale contract → `legal`.
- The Cippus Perusinus (Pe 8.4): boundary contract between Velthina and Afuna families → `legal` (NOT `boundary` — the contractual structure dominates).

**NEGATIVE:**
- A simple boundary cippus with just `tular spural` → `boundary`, not legal.

### boundary

**POSITIVE:**
- Cippi with `tular spural` ("public boundary"): `boundary`.
- Bronze plaques or stones delimiting sacred precincts.

**NEGATIVE:**
- The Cippus Perusinus is NOT `boundary` despite its name. Its content is a contract → `legal`.

### commercial

**POSITIVE:**
- Pithos rim with a numerical mark and a personal name as supplier: `commercial`.
- Lead trade-tag with a weight notation.

**NEGATIVE:**
- An inscribed weight that is a *votive offering* of a weight → `votive`.

## Edge cases and `unsure`

Mark a row `unsure` (which routes to the adjudication queue) when:
- The text is a single personal name with no context (most common reason).
- The find-context is unknown and text alone permits multiple readings.
- The inscription is heavily fragmentary (intact-token ratio < 0.5) and the visible portion does not contain a discriminating verb or formula.
- The text is in a script other than Etruscan (Greek, Latin, Faliscan loan).

The jury runner is expected to mark roughly 25–40% of v1 silver rows as `unsure`. That is correct and reflects the genuine difficulty of the task on short-name fragments. Do not force a label to avoid the queue.

## Confidence rubric

Each rater also returns a confidence in {high, medium, low}.

- **high**: the decision tree branch was unambiguous and supported by ≥2 features (e.g., funerary find-context + kinship formula).
- **medium**: the branch matched but on a single feature; reasonable scholars might disagree on the tie-breaker.
- **low**: the rater forced a label but the evidence is thin. Treat as one step from `unsure`.

## What the jury must output (per row, per model)

```json
{
  "id": "Ta 1.66",
  "model": "claude-opus-4-7",
  "label": "funerary",
  "confidence": "high",
  "rationale": "Tomb-wall inscription with kinship genitive 'velus papas'; object class is sepulchral; rule 1 of decision tree.",
  "features": ["kinship_formula", "sepulchral_findspot"],
  "alternates_considered": ["ownership"],
  "codebook_version": "v2.0"
}
```

The rationale is required. A model that returns a label without a rationale is treated as `unsure` and routed to the queue.

## Adjudication protocol (for the human philologist)

Each queue row arrives with:
- The text + all available metadata (findspot, object type, date range, translation if any)
- The label proposed by each LLM rater + their rationales + confidences
- The disagreement type (e.g., 2× funerary, 1× ownership)

The adjudicator returns one of:
- `accept(label_X)` — pick one of the proposed labels
- `relabel(new_label, reason)` — none of the proposals is right; pick another class
- `unsure(reason)` — even the human cannot decide; row enters a `irreducibly_ambiguous` set (reported as a separate metric in publications)

A second adjudicator labels a held-out 50-row sub-sample independently. **Krippendorff α between the two human raters must reach ≥ 0.80** before the gold set ships. Below that threshold, the codebook needs revision.
