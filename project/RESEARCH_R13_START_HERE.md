# CZK Cpi Forecasting - Latest models

R13, 9 September 2026. Read
`docs/implementation/R13_RESULTS_2026-09-09.md` first. This supersedes earlier
research recommendations where they conflict; older evidence remains preserved.

## Model map

| Product | Current reference | Research comparisons |
|---|---|---|
| Next first CPI release | HARD_BASE / R9_BASE | Existing HARD_HALF/HARD_FULL; Category Raw TARGET_OWN |
| Nowcast correction matrix | No replacement | CATEGORY_HALF_CORRECTION, CATEGORY_FULL_CORRECTION; BASE_MATCHED_HALF/FULL |
| Independent monthly inflation path | BRIDGE_HARD / INDEPENDENT_BRIDGE | R13 aggregate/category monthly/cumulative core; separate labour pair |
| Economic interpretation | Own components and dated assumptions | CNB agreement/shared errors, same-quarter revisions, ex-post core error accounting |

Half/Full scale a family's predicted own past-core-error correction. The older
TARGET_OWN_HALF is a 50/50 BASE/category blend, not Category Half correction.
R9_BASE/HALF/FULL refer to the independent hard-data forecasts, not the older
expectations-conditioned LEGACY_* models.

All new categories remain research-only; forecast_independent.py's main numerical
forecast has not changed. No expectations, surveys or retailer predictors were
added. New paths do not improve the whole-path score enough for promotion.

## Reproduce with the supplied scientific requirements lock

From this repo directory, with requirements-r9-lock.txt installed:

```text
python -m pytest test_nowcast_family_r13.py test_core_path_r13.py test_path_diagnostics_r13.py test_core_path_attribution_r13.py -q
python nowcast_family_experiment_r13.py --verify
python core_path_experiment_r13.py --verify
python path_diagnostics_r13.py --verify
python tools/r13_review/attribute_core_path.py --verify
```

The first two --verify commands re-estimate all new forecasts from frozen inputs;
the latter two reconstruct evaluation tables. Source and payload hashes are
checked. No live economic database, retailer scraping or X13 run is required for
the new R13 replay. The inherited short-food/X13 outputs are reused only after
baseline source/accounting validation. Legacy/full live runs have their separately
documented X13 and data-refresh dependencies.

## Evidence locations

- `output/research_r13/nowcast/`: all eight unique forecasts, sequential errors,
  clocks, warmup, scores, alerts, bootstrap intervals and attribution.
- `output/research_r13/core_path/`: six variants, unchanged references, all failed
  rows, source clocks, coefficients, monthly/annual/cumulative scores and replay.
- `output/research_r13/path_diagnostics/`: CNB agreement, shared error, revisions,
  information-age differences, coverage and interpretation notes.
- `output/research_r13/core_attribution/`: separate post-fit error accounting;
  realised future core is an evaluation-only replacement, never a predictor.
- `output/research_r13/integration/`: combined regression evidence.
- `docs/implementation/R13_INDEPENDENT_REVIEW.md`: independent audit findings.

The final ZIP includes all tracked source/data/evidence and Git history. Its
external delivery receipt records extracted-copy replays and unchanged original
project hashes. This certifies frozen research replication, not a live trading
system or a forecast made with fully archived historical vintages.
