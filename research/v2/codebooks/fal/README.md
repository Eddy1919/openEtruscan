# Faliscan codebooks (scaffold)

Faliscan (Italic, closely related to Latin; spoken in the ager Faliscus around Falerii, c. 7th–2nd century BCE). Corpus is ~400 inscriptions, often grouped with archaic/Old Latin studies. Key source: Bakkum (2009) *The Latin Dialect of the Ager Faliscus*.

## Status
Not yet drafted. The Etruscan codebooks at `../etr/` are the template; adapt rather than copy.

## What needs to change vs Etruscan

| Codebook | Adaptation |
|---|---|
| `classification.md` | Class set very similar to Etruscan: `funerary`, `ownership`, `dedicatory`, `votive`, `legal` (rare), `boundary` (rare). Faliscan funerary formulas (e.g. `loferta` = freedwoman, cognate to Etr. `lautni`) need explicit examples. |
| `rosetta.md` | Mostly redundant: Faliscan is so close to Latin that 'bilingual pair extraction' becomes 'identify Faliscan cognates vs Latin', not 'extract glosses from classical sources'. May want a fundamentally different protocol — propose to skip this codebook for Faliscan and instead build a `cognate_pairs.md` codebook against Latin. |
| `lacunae.md` | Same Leiden conventions; corpus base is `bakkum_2009_faliscan.jsonl` (TODO). |

## Suggested first move
Same as Oscan: adapt classification.md, ship as v0.1, smoke-test LLM-jury.

## Primary references
- Bakkum, G. C. L. M. (2009). *The Latin Dialect of the Ager Faliscus: 150 Years of Scholarship*. Amsterdam University Press.
- Joseph, B. D. & Wallace, R. E. (1991). "Is Faliscan a Local Latin Patois?" *Diachronica* 8(2): 159–186.
