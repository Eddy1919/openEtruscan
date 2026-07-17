# Lacuna-restoration evidence (Stream C) — v2.0.2 and v2.0.3

Raw jury outputs and computed metrics backing the lacuna tables in
[`README.md`](../../../../README.md), [`CHANGELOG.md`](../../../../CHANGELOG.md) §2.0.3,
[`docs/INTELLIGENCE_V2.md`](../../../../docs/INTELLIGENCE_V2.md) §3, and
[`PRE_REGISTRATION.md`](../../PRE_REGISTRATION.md) Deviation §B. Promoted from
local-only staging on 2026-07-17 so the published claims are checkable from the
public repository; previously these paths existed only on the maintainer's
machine.

| File | What it is |
|---|---|
| `lacuna_jury_raw_v2_0_2.jsonl` | Raw per-row jury output of the **retracted** v2.0.2 run (375 rows, incl. the 114 empty Sonnet completions that caused the retraction). Kept as the audit trail of the harness artifact. |
| `lacuna_v2_0_2.json` | Computed metrics of the retracted run. **Do not cite** except to discuss the retraction. |
| `lacuna_jury_raw_v2_0_3_rerun.jsonl` | Raw per-row output of the corrected v2.0.3 re-run (210 rows = 3 raters × 70 unique tasks; `no_parse` flag present). |
| `lacuna_v2_0_3.json` | Computed v2.0.3 metrics (66 clean-gold tasks, 10 000-resample bootstrap, seed=42). This is the file the published tables come from. |
| `SHA256SUMS` | Integrity manifest. Verify with `shasum -a 256 -c SHA256SUMS`. |

Recompute the metrics from the raw file with
[`research/v2/eval/compute_lacuna_v2.py`](../../eval/compute_lacuna_v2.py).
