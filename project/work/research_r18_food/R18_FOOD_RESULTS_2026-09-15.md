# R18 food h0 information: results and verification

Do not promote an additional future-food h0 update. Both fixed decay profiles
produce small full-history improvements, but worsen recent food and headline
paths. The chronological selector does not fix this. The independent HARD_BASE
headline h0 remains unchanged; these are h1..12 food-path experiments.

This is repeated research on the original sample, not a fresh holdout. R17's
negative core-h0 result remains relevant context but was not assumed to determine
food's result. No parameter, candidate or calendar was changed after this fit.

## Food and headline on the same original calendar

The original 969 R16 origin/horizon keys are preserved. Full h12 has 75 origins;
recent h12 has 19, with recent defined by origin >= January 2024. Food pooled
monthly counts are 969 full and 294 recent. Monthly and cumulative food errors
are different targets, and repeated overlapping horizons are not independent.

| Forecast | Full pooled food monthly RMSE | Recent pooled food monthly RMSE | Full food cumulative-log h12 RMSE | Recent food cumulative-log h12 RMSE | Full headline h12 RMSE | Recent headline h12 RMSE |
|---|---:|---:|---:|---:|---:|---:|
| STATE_FAST_R15 | 1.147418 | 0.832456 | 7.949015 | 4.129168 | 4.869472 | 0.857964 |
| FOOD_H0_FAST_R18 | 1.144695 | 0.838425 | 7.900378 | 4.198626 | 4.867189 | 0.890227 |
| FOOD_H0_SLOW_R18 | 1.140451 | 0.834941 | 7.857031 | 4.410609 | 4.866484 | 0.958020 |
| FOOD_H0_SELECT_R18 | 1.143626 | 0.834941 | 7.916744 | 4.410609 | 4.867971 | 0.958020 |

Monthly food is m/m percent, cumulative food is 100 log points, and headline is
annual CPI percentage points. The slow profile lowers full h12 headline RMSE by
only 0.0030 pp and raises recent RMSE by 0.1001 pp. Its full h12 food cumulative
RMSE improves about 1.2%, while recent worsens about 6.8%. These outcomes do not
justify an operating change. Uncertainty and any CNB comparison belong to the
parent's fixed-calendar evaluation, not an added component-specific search.

Full headline h3/h6/h12 RMSE is 1.459181/2.290294/4.869472 for FAST,
1.450995/2.287451/4.867189 for fast decay, and
1.451051/2.287700/4.866484 for slow decay. Recent h3/h6 also worsen under both
profiles. The selector's full h6 RMSE is 2.293055, slightly worse than control.

The wider finite component calendar contains 1,002 monthly observations. Its
pooled monthly food RMSE is 1.138115 for control, 1.135459 for fast decay,
1.131323 for slow decay, and 1.134417 for selection. These are reported separately
in food_summary.csv and must not be substituted for the original-calendar table.

## What was learned and when

For origin s, the signal is raw independent food h0 log rate minus the saved
FOOD_STABLE_PIPELINE_R14B state-only h0 log rate. The profiles are rho^h for
rho=.5 and .9, starting at h1. One beta applies to the whole path, with no
intercept. The standardized ridge coefficient is converted back to original
signal units before the fixed [0,1] restriction. The penalty halves the
unconstrained OLS slope. This is conditional incremental information, not an
independent observation or a posterior covariance update.

Each profile defaults to unchanged food for 24 origins, February 2019–January
2021. The first fitted update is February 2021, when 12 complete prior paths have
matured. Each has 66 fitted origins. Fitted-beta means are 0.822184 for fast decay
and 0.360833 for slow decay; July 2026 betas are 0.767413 and 0.318145, each from
the latest 60 fully matured origins. The raw coefficient and standardized scale
are retained, including coefficient restriction effects.

The selector chooses unchanged control in 44/90 origins, fast decay once, and
slow decay 45 times. Its first 24 controls are minimum-history defaults. Latest
selection is slow decay from the saved 36-origin validation window July
2022–June 2025; all twelve labels for every validation origin are published by
the July 2026 origin clock. It uses one path choice for all twelve horizons.

Raw food h0 is modestly better than the state-only h0: full monthly log-rate RMSE
0.904335 versus 0.921592 over 90 origins; recent 0.777315 versus 0.797504 over 31.
MAE also improves (full 0.674302 versus 0.740978; recent 0.615682 versus 0.686112).
These are separate current-month food diagnostics. They do not establish that
the h0 innovation is persistent or that it should improve future food dynamics.

## Source lineage and availability audit

The raw h0 is `output/cz_struct_backtest.csv:food_pred_eve`; its SHA256 exactly
matches the independent-nowcast manifest's recorded source
`9678c25530d6bb684a2e74ba962f121a10fadf3db97887b2ca6777ff54d4e9cd`.
The independent-nowcast generator keeps that noncore food leg when replacing
core for HARD_BASE. The raw source's own features are food lags and agricultural
and food-PPI predictors, with no consensus/expectation/sentiment feature.

The pipeline h0 is index 0 of the saved 13-rate vector in
`output/research_r14b/food/origin_diagnostics.json`. Indices 1..12 reproduce every
FAST future food value with maximum difference exactly zero. There is no
`output/research_r14b/nowcast` directory and no earlier common h0 lineage; the
experiment honestly starts in February 2019 rather than fabricating warmups.

All 90 source clocks match R15 states, pipeline diagnostics, nowcast metadata
and native FAST UTC clocks after Europe/Prague localization. All are 23:59 on
the calendar day before FIRST release. Only 71 are also the eve of DETAIL
release, because flash and detailed publication differ. Training independently
gates both actual food-index endpoints on their detailed availability and
requires target month < current origin. Source clocks and data release sources
are exported per origin in source_audit.csv.

The original headline nowcast archive and downstream native CSV differ at
machine serialization precision; source reconciliation allows at most 1e-15 pp.
Every candidate nevertheless preserves its inherited native h0 exactly. The
independent cleanup food replay differs from the authoritative food archive by
at most 2.33318e-7 pp; it is an audit comparison, not a replacement input.

These are saved pseudo-OOS forecasts calculated from frozen current-vintage
histories with reconstructed availability. They are not certified historical
revision vintages or an as-issued live forecast archive. No live refit, network,
consensus data or earlier reconstructed forecast was used for the update.

## Verification and files

Canonical outputs: `output/research_r18_food/`. Three models each contain all 90
origins and h0..12: 3,510 native rows and 3,240 finite future food predictions.
Coverage contains every origin/horizon status and realized/unrealized outcome
reason. All six contributions rebuild headline monthly exactly; nonfood values,
contributions and weights are exact; h0 is exact. Annual paths are recomputed
with known history and unchanged HARD_BASE, and h12 properly excludes h0.

The declaration preceded fitting and the runner refuses existing output
destinations. Before and after checks verify complete R15/R16 manifest graphs,
all R14B food outputs, original food inputs and the authoritative h0 source.
The canonical manifest hashes all 17 payloads and 103 source/code files,
including the evaluator and prefit specification. Old files were not modified.

Fresh relevant suite: **58 passed** in 5.34 seconds:

```powershell
$env:PYTHONPATH='../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m pytest tests/test_food_h0_r18.py tests/test_food_transmission_r17.py test_food_stable_r14b.py test_food_path_r14.py -q -p no:cacheprovider --basetemp work/research_r18_food/pytest_regression
```

Tests cover future poisoning, both release endpoints, unknown release rejection,
calendar gaps, complete-path maturity, h1 timing, train-only RMS/50% shrinkage,
insufficient-history and zero-signal defaults, whole-path selection, source
clock/horizon corruption, six-block accounting, h0/nonfood preservation and
refusal to overwrite. Runner tests were observed failing before implementation.

Independent `verify_r18_food.py` reconstructs all **180 coefficients**, all
**90 path selections**, and **68,400 training rows** directly from frozen
snapshots/actuals without invoking the engine fit/selection functions. Maximum
coefficient discrepancy is 7.77e-16 and log-path discrepancy 4.44e-16. All
training maturity/endpoints, saved selections, exact h0/nonfood values, native
keys and 103 input/17 output hashes pass. Its receipt is
`work/research_r18_food/verification_receipt.json`.

The first red run used pytest's default external temporary folder and hit its
pre-existing Windows access restriction. The destination-refusal test was made
read-only and the regression run uses the explicit workspace temp directory.
A CSV serialization mismatch and reset row-index fixture mismatch were corrected
before the full fit; they did not change generating equations or sources.

The original three-origin smoke is separately retained under
`work/research_r18_food/smoke`. Reproduction uses a fresh destination:

```powershell
$env:PYTHONPATH='../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' food_h0_experiment_r18.py --output work/research_r18_food/replay
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r18_food/verify_r18_food.py
```

No operating model was promoted. Retain FAST's original food path and independent
h0 anchor; keep this negative recent-path result for comparison against future
new data and independently motivated improvements.
