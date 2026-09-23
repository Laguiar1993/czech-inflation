# Nested core ridge tuning

Approved scoped experiment, 9 September 2026. This document fixes the rules before the run; it does not authorize changing production defaults.

**Goal:** test whether modest ridge regularization/window tuning improves the independent hard-policy core nowcast and its headline contribution.

**Architecture:** `models/core_tuning.py` fits each configuration at each historical release-eve origin and selects using only earlier published core errors. `core_tuning_experiment.py` loads hashed frozen fixtures, attributes the core change to a fixed noncore headline reference, and writes unrounded evidence. `test_core_tuning_r9.py` checks publication timing, alignment, imputation, selection and future-data perturbations. NumPy and pandas provide the numerical runtime.

## Rules fixed before inspecting results

- Inputs exclude `exp12`, `exp36`, `exp12_x_state`, `household_exp` and `esi`. No legacy ridge error history is read.
- The grid is alpha `[0.3, 3, 30, 300]` crossed with trailing calendar training windows `[60, 120, expanding]`: 12 configurations. Minimum training sample: 48 eligible core outcomes.
- Training always uses months strictly before the forecast month and only labels published by that origin's actual release-eve timestamp. A fixed window means calendar months, not a compressed count of nonmissing observations.
- Imputation means and standard deviations are fitted only to the eligible training rows. Entirely missing training columns are excluded; constant columns have unit scaling.
- Each outer origin selects the lowest core mean squared error over the latest 36 common eligible sequential validation errors. At least 24 are required. The default is alpha 3 with an expanding window when validation is insufficient; ties prefer that default if tied for best, then a fixed configuration order. The tie tolerance is `rtol=1e-10, atol=1e-12` on MSE.
- Each validation prediction was itself fitted at its own historical release eve. Its error enters selection only after the detailed core/CPI-family publication, including the flash era's delay between headline and detailed release.
- Selection is repeated monthly. No outcome-triggered grid expansion, surprise-metric optimization or best-full-sample parameter choice is permitted.
- Compare the selected model with alpha 3 expanding on the same 90 release-eve origins, February 2019–July 2026. Show core and headline MAE/RMSE for all origins, ex-January, 2024+ and the 2025+ flash era.
- Headline attribution uses `STRUCT_EVE - w_core * core_pred_eve + w_core * candidate_core`, with core weights solved from the frozen component data at each actual eve. The reference noncore term is fixed across candidates and never enters selection.
- The cleanup fixture lacks the later release-eve columns, so the existing `output/cz_struct_backtest.csv` supplies the hashed `STRUCT_EVE`/`core_pred_eve` reference. Its origins must exactly match the frozen cleanup reference. First-release headline actuals come from the stored release-survey history; its survey columns are not read or used for tuning.

## Execution checklist

- [x] Add and observe failing tests for release eligibility, rolling windows, strict monthly indexes, train-only imputation, default/tie decisions and future-target/feature perturbation invariance.
- [x] Implement the fixed estimator and nested selector; match alpha 3 expanding against the existing core ridge estimator on frozen data.
- [x] Run the experiment, persist all configuration predictions, selection schedule, release-level comparisons, split scores and input/source/runtime hashes.
- [x] Inspect eligibility evidence, run the 10 scoped tests and record findings and limitations below.

## Results: no overall improvement

The predeclared search completed in **17.6 seconds** with **2,244 estimated sequential forecasts** across 12 configurations. Every one of the 90 outer origins had the full 36 eligible common validation errors. No annual selection shortcut was needed.

All errors below are percentage points of monthly inflation. Headline actuals use first release; core actuals use the frozen CNB core series.

| Sample | n | Core MAE default / selected | Core RMSE default / selected | Headline MAE default / selected | Headline RMSE default / selected |
|---|---:|---:|---:|---:|---:|
| All | 90 | 0.240864 / 0.247432 | 0.299717 / 0.312035 | 0.262516 / 0.270661 | 0.417952 / 0.419449 |
| Ex-January | 83 | 0.239080 / 0.249583 | 0.298514 / 0.316265 | 0.248251 / 0.254356 | 0.403333 / 0.404826 |
| 2024+ | 31 | 0.149108 / 0.157329 | 0.190140 / 0.201009 | 0.169039 / 0.165597 | 0.218978 / 0.213740 |
| 2025+ flash era | 19 | 0.116580 / 0.140693 | 0.132017 / 0.165111 | 0.139296 / 0.138530 | 0.173002 / 0.175689 |

Relative to alpha 3 expanding, nested selection worsens full-sample core RMSE by **4.11%**, headline RMSE by **0.36%**, and headline MAE by **3.10%**. The 2024+ headline RMSE improves **2.39%**, despite worse core accuracy; this is compatible with error cancellation against the fixed noncore residual and does not establish a better core model. Flash-era headline RMSE deteriorates **1.55%**. The search does not justify replacing the default.

The selector chose alpha 3 / 60 months 49 times; alpha 0.3 / expanding 18 times; alpha 0.3 / 60 months 10 times; alpha 3 / 120 months 9 times; alpha 0.3 / 120 months 3 times; alpha 300 / expanding once. These are decisions made using earlier published core errors. Scores for all fixed configurations are retained descriptively, not used to select an alternative after viewing the full evaluation window.

## Evidence and replay

- `output/core_tuning_predictions.csv`: every attempted historical configuration forecast, with prediction timestamp, training start/end, last training-label publication and fit status; unavailable short histories remain visible.
- `output/core_tuning_schedule.csv`: all 90 selected configurations, validation counts, exact validation months, last validation publication and prior MSE-derived RMSEs.
- `output/core_tuning_releases.csv`: selected/default/legacy core and headline forecasts, fixed noncore contribution, per-origin core weights, actuals and unrounded errors.
- `output/core_tuning_outer_candidates.csv`: all 1,080 outer-origin candidate forecasts and their identical noncore attribution.
- `output/core_tuning_scores.csv`: common-sample scores for all configurations, the fixed default and nested selection.
- `output/core_tuning_manifest.json`: timestamps, 12 configurations, source/input/output SHA256 hashes, numerical runtime, selection counts and verification checks.

The manifest records **zero** future training-month violations, unpublished training-label violations, future validation-month violations or unpublished validation-label violations. Independent alpha 3 expanding predictions exactly equal the existing ridge estimator on the frozen inputs. Recomputed legacy core predictions differ from the saved release-eve reference by at most **1.33e-15**.

The perturbation test changes all outcomes at/after a chosen cutoff, later predictor rows and all excluded survey columns. Every forecast and selected configuration through that cutoff remains unchanged. Separate tests delay a prior target's publication beyond the forecast clock and ensure neither training nor validation can use it; train-only mean imputation is tested with extreme future values and an entirely missing training column. Ten scoped tests pass.

Replay with `python core_tuning_experiment.py`; test with `python -m pytest test_core_tuning_r9.py -q`. The runner loads local frozen files and calendar rules; it does not refresh inputs or call live data loaders. Re-running replaces only the `core_tuning_` evidence files, so preserve a dated copy before comparing future experiments.

This was a cheap, completed tuning search, not evidence that unlimited compute would improve the forecast. Additional computation would need a new predeclared question and honest evaluation; repeating searches against these same 90 outcomes would increase selection bias.

## Interpretation limits

This is a frozen-input, nested rolling-origin research experiment. The fixture includes reconstructed/revised historical features and therefore does not certify real-time vintage availability. The 90-month evaluation window has already informed earlier model research; nested selection avoids direct future-label use within this test but does not turn the window into a pristine prospective holdout. Headline attribution isolates the core change and is not a rebuilt forest or uncertainty calibration. Production adoption requires separate review and prospective confirmation.
