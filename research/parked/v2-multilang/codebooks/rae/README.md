# Raetian codebooks (scaffold)

Raetian (probably Tyrrhenian, related to Etruscan and Lemnian; spoken in the central Alps c. 5th–1st century BCE). Corpus is ~400 short inscriptions, mostly votive bronzes from sanctuaries at Sanzeno, Magrè, and Castelfeder. Standard reference: Schumacher (2004) *Die rätischen Inschriften*.

## Status
Not yet drafted. The Etruscan codebooks at `../etr/` are the closest template (shared Tyrrhenian family) but the corpus is so small and so dominated by votive bronzes that the Etruscan 7-class taxonomy collapses.

## What needs to change vs Etruscan

| Codebook | Adaptation |
|---|---|
| `classification.md` | Probably collapse to 3-4 classes: `votive`, `funerary` (rare), `ownership`, `unsure`. Most Raetian texts are short names on dedicated objects. A nuanced typology requires more data than survives. |
| `rosetta.md` | Effectively NONE. Raetian is barely mentioned in classical sources (Livy, Pliny — and even there, mostly as an ethnonym, not glosses). Realistic scope: alignment with Etruscan cognates only, NOT bilingual extraction. Recommend skipping this codebook for Raetian or replacing it with an `etruscan_cognates.md`. |
| `lacunae.md` | Same Leiden conventions; corpus base is `schumacher_2004_raetian.jsonl` (TODO). Lacuna pool will be very small — most Raetian inscriptions are too short to have well-defined lacunae. |

## Suggested first move
The classification codebook is enough for v0.1. Rosetta and lacunae may not have enough corpus support to be worth building.

## Primary references
- Schumacher, S. (2004). *Die rätischen Inschriften: Geschichte und heutiger Stand der Forschung* (2nd ed.). Innsbruck: Institut für Sprachen und Literaturen.
- Marchesini, S. (2018). "Raetic." In: Klein, J. et al. (eds.), *Handbook of Comparative and Historical Indo-European Linguistics*. Berlin: De Gruyter.
- Rix, H. (1998). *Rätisch und Etruskisch*. Innsbruck: Institut für Sprachwissenschaft.
