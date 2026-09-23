# Nested independent residual-forest tuning

Predeclared follow-on experiment, 9 September 2026. The user approved this bounded search after the core ridge experiment; no production promotion is authorized by this document.

## Fixed experiment

- Reuse only `output/independent_nowcast_hard_errors.csv`, the independent alpha-3 expanding ridge's sequential core errors beginning in 2015. Never read legacy forecast errors or substitute fitted residuals. Frozen cleanup hard features exclude `exp12`, `exp36`, `exp12_x_state`, `household_exp`, and `esi`.
- Four forests: minimum leaf size `[3, 8]` crossed with maximum features `[1.0, 1/3]`. Each has 200 trees, random seed 42, the existing five TVW quantiles and weight constraints, 12 chronological validation errors and six-month half-life. Reserve exactly 12 errors even when fewer than 60 errors are available, then refit the forest on all eligible errors. The existing TVW class's adaptive short validation window is not used.
- At least 40 errors must have occurred before the forecast origin and have detailed CPI-family publication timestamps at or before its release-eve clock. Train imputation/scaling only on the initial fitting subset for quantile-weight validation, then refit preprocessing on all available errors for the final forecast. No future observations enter either preprocessing step.
- Apply the existing publication-mask convention to the feature row used at each historical prediction date. The source feature vintage limitations remain unchanged.
- Set the forest's `n_jobs=2` before fitting. Fit origin/configuration pairs sequentially. Cache each pair using parameters, source hash, Python/numerical-package versions and hashes of only its eligible error/history features and prediction row; write progress after each origin. Cache hits must match those fingerprints and contain a finite correction.
- At each of the 90 outer release-eve origins, jointly select forest configuration and correction multiplier `[0, 0.5, 1]` using the latest 36 common published sequential core forecast errors, requiring at least 24. Minimize MSE of `independent_ridge_error - multiplier * forest_correction`. No headline error, survey, surprise or alert enters selection.
- Insufficient validation defaults to multiplier zero. Ties within `rtol=1e-10, atol=1e-12` on MSE prefer multiplier zero if tied for best, then lower multiplier and the fixed forest grid order. All four configurations must have produced a historical forecast from at least 40 eligible errors for an origin to enter the common validation pool.
- An actual forest fit failure produces an explicit zero correction and remains a scored strategy forecast; difficult origins are not silently deleted. The failure and cache status remain visible.
- Final headline comparison is `HARD_BASE + coreweight * selected_multiplier * correction`, using the saved independent nowcast forecasts and per-origin weights. Compare with HARD_BASE and report fixed forest/multiplier alternatives descriptively.
- Report all-release, ex-January, 2024+, 2025+ flash-era, realised-large-surprise and forecast-triggered-alert panels. Match the main experiment's thresholds exactly: large surprise `abs(actual-consensus) >= 0.4`, material win/loss absolute-error gain `>= +0.15` / `<= -0.15`, alert `abs(forecast-consensus) >= 0.2`, with `1e-9` boundary tolerance. These are forecast-error diagnostics, not trading returns.

## Acceptance and evidence

- [x] Observe failing tests for future-error invariance, training/publication eligibility, fixed 12-error validation, two-worker fitting, cache invalidation and deterministic selection/defaults.
- [x] Implement the experiment without modifying the independent history module or existing forest class.
- [x] Run all four configurations, retain full sequential forecasts, cache/progress metadata, selection schedule, release-level errors/events, scores and input/source/output hashes.
- [x] Verify zero future/unpublished-label violations, saved evidence hashes and seven scoped tests; record findings below.

## Results: modest and mixed, no promotion

The cold run took **151.8 seconds**, using two workers within each forest and fitting origin/configuration pairs sequentially. It processed **136 monthly origins** from April 2015 through July 2026: **544** configuration records, including **384 fitted forecasts** and 160 explicit insufficient-history zero corrections. There were **zero forest fit failures**. Eighteen early outer origins had fewer than 24 prior forest forecasts for selection and therefore used the declared zero-correction default.

All errors below are percentage points of monthly headline inflation, scored against first release.

| Sample | n | BASE MAE | Selected MAE | BASE RMSE | Selected RMSE |
|---|---:|---:|---:|---:|---:|
| All | 90 | 0.262516 | 0.262233 | 0.417952 | 0.413013 |
| Ex-January | 83 | 0.248251 | 0.248733 | 0.403333 | 0.398359 |
| 2024+ | 31 | 0.169039 | 0.168034 | 0.218978 | 0.221033 |
| 2025+ flash era | 19 | 0.139296 | 0.130776 | 0.173002 | 0.165500 |
| Realised large surprise | 23 | 0.484583 | 0.474699 | 0.698570 | 0.682542 |
| Large surprise, ex-January | 19 | 0.498690 | 0.490257 | 0.736556 | 0.720272 |

Full-sample headline RMSE improves **1.18%**, while MAE improves only **0.11%**. The 2024+ RMSE worsens **0.94%**; the 2025+ flash-era RMSE improves **4.34%**. The evidence is mixed and the overall gain is small. It is a research comparison, not a basis for automatic production promotion.

The selected core correction lowers full-sample core MAE from **0.240864 to 0.229805**, but increases core RMSE from **0.299717 to 0.303976**. In 2024+, core RMSE improves **0.190140 to 0.181114**; in 2025+, it improves **0.132017 to 0.103478**. These differences explain why evaluating only one forecast object or only one recent period would give an incomplete picture.

On the 23 realised large surprises, material wins/losses against consensus change from **7/3 for HARD_BASE to 8/1 for selection**. This conditional result does not identify those events in advance. The selected forecast triggers **23 alerts**: 11 are closer than consensus, with 9 material wins and 8 material losses. Their total absolute-error gain against consensus remains **-0.697695 pp**, or **-0.030335 pp per alert**. Of the 23 alerts, **8** coincide with a large realised surprise and **15** are false alarms under that definition; **15** large surprises are missed. Precision and recall are both **34.8%**. The experiment therefore does not establish a reliable alert rule or a trading-return advantage.

The selected multiplier is zero at 21 origins, one-half at 42, and one at 27. Among the 69 nonzero corrections, leaf 8 / one-third features is selected 30 times; leaf 3 / one-third features 26; leaf 8 / all features 7; leaf 3 / all features 6. A forest label attached to multiplier zero has no effect on the forecast and should not be interpreted as a useful forest choice.

## Evidence, integrity and replay

- `output/forest_tuning_predictions.csv` contains all 544 sequential configuration records, with forecast clock, eligible-error start/end and last publication, validation count, status, correction and cache fingerprints.
- `output/forest_tuning_cache/` contains the corresponding JSON cache entries. `output/forest_tuning_progress.json` records completed origins and elapsed time. Cache hits are accepted only when the eligible-input, parameter, implementation and numerical-runtime fingerprints match, and the cached correction is finite. The manifest uses the same runtime identity as the cache. Older keyed entries remain separate.
- `output/forest_tuning_schedule.csv` records each outer decision, multiplier, correction, exact prior validation months, publication cutoff and selection reason.
- `output/forest_tuning_releases.csv` contains unrounded first-release actuals, consensus, core weights, existing independent reference forecasts, selection and all fixed forest/multiplier alternatives.
- `output/forest_tuning_events.csv` and `output/forest_tuning_scores.csv` retain release-level errors, capture ratios, large-surprise/alert flags and fixed-threshold scoreboards. `output/forest_tuning_core_scores.csv` separately scores the core object.
- `output/forest_tuning_manifest.json` records the predeclared settings, numerical runtime, timestamps, **29 verified input/source/output SHA256 hashes**, counts and eligibility checks.

All **544 cache entries referenced by the current predictions** were matched to the saved predictions. The manifest records **zero** future error-month violations, unpublished error-label violations, future validation-month violations or unpublished validation-label violations. The provided independent errors exactly reproduce the released outer ridge baseline where they overlap; maximum difference is **zero**.

After review added runtime fingerprints and rejection of nonfinite cached corrections, a fresh cold verification run completed in **157.1 seconds** with zero cache hits and zero forest failures. All **544 corrections** and **90 selections** were exactly unchanged; the schedules, release rows, events and score tables were byte-for-byte identical. `output/forest_tuning_runtime_verification.json` records the comparison and prior artifact hashes. The original implementation is preserved at `docs/implementation/archive/forest_tuning_before_runtime_fix.py`, with its original manifest source hash. The current manifest records the new implementation and the shared cache/runtime identity.

Eleven scoped tests cover actual forest/cache invariance to future or unpublished labels, future predictor rows and excluded survey inputs; cache invalidation when eligible inputs, parameters or numerical-runtime versions change; rejection of cached NaN and both signs of infinity; exactly 12 internal validation errors; two-worker fitting; selection on full core forecast loss; insufficient/tied-loss zero correction; and event threshold boundaries. Test with `python -m pytest test_forest_tuning_r9.py -q`. Run or resume with `python forest_tuning_experiment.py`. Preserve dated output evidence before rerunning, because the summary CSVs and manifest are replaced while the keyed cache is retained.

This is a further pseudo-out-of-sample research search on an already studied historical window, not an untouched holdout. Nested selection prevents direct future-label leakage within the experiment, but does not erase earlier research selection or historical feature-vintage limitations. No result is promoted automatically.
