# Oscan codebooks (scaffold)

Oscan (Italic, Sabellic branch; spoken in Samnium and Campania, attested c. 4th–1st century BCE). Corpus is bigger than commonly assumed: ~600 inscriptions catalogued by Crawford (2011) *Imagines Italicae*, plus the Tabula Bantina, Cippus Abellanus, Iguvine Tablets fragments, and the inscriptions on coins from Aesernia, Beneventum, etc.

## Status
Not yet drafted. The Etruscan codebooks at `../etr/` are the template; adapt rather than copy.

## What needs to change vs Etruscan

| Codebook | Adaptation |
|---|---|
| `classification.md` | Class set probably: `funerary`, `ownership`, `dedicatory`, `votive`, `legal`, `civic` (magistrate offices: `meddix`, `quaestor`), `coin_legend`, `boundary`. Drop `commercial` (no attested examples), add `civic` and `coin_legend`. Decision tree branches on Sabellic-specific formulas (e.g. `aamanaffed` = "had dedicated"). |
| `rosetta.md` | Source language list: Latin only (Festus, Varro, Verrius Flaccus, glossae). No Greek glosses for Oscan. Category set adds `magistracy` and drops `theonym` (most Oscan deities have direct Latin cognates without ancient explicit glossing). |
| `lacunae.md` | Same Leiden conventions; corpus base is `imagines_italicae_oscan.jsonl` (TODO: stage in `gs://openetruscan-rosetta/corpus/`). |

## Suggested first move
Adapt Etruscan `classification.md`, change the class list and the formula examples, ship as `osc/classification.md` v0.1. Test the LLM-jury on 5 rows. If output is sensible, build the test split.

## Primary references
- Crawford, M. H. (2011). *Imagines Italicae: A Corpus of Italic Inscriptions*. London: Institute of Classical Studies.
- Untermann, J. (2000). *Wörterbuch des Oskisch-Umbrischen*. Heidelberg: Universitätsverlag C. Winter.
- McDonald, K. (2015). *Oscan in Southern Italy and Sicily*. Cambridge University Press.
