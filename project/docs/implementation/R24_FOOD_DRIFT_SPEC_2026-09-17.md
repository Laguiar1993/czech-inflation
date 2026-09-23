# R24: the long-horizon drift of the food path

Declared by Claude on 17 September 2026, before any R24 fit or score. No existing model, output or evaluator is edited; every R24 file is new.

## Why food, and why the drift

Block attribution (`REVIEW_TO_CODEX_R23_2026-09-17.md`, and now standard output in `tools/path_diagnostics`) shows where the shared path's error sits for origins from 2024, as RMS of the cumulative weighted block error over h1–12 in percentage points of headline: food 0.73, fuel 0.44, administered 0.32, core 0.32. Three research rounds worked on core. Food is the largest block, and its twelve-month forecast is no better than forecasting no change:

| Food block, cumulative log change | h3 | h6 | h12 |
|---|---:|---:|---:|
| Model RMSE, full sample | 2.20 | 4.19 | 7.84 |
| Zero-change RMSE, full sample | 2.82 | 5.06 | 8.83 |
| Model RMSE, origins from 2024 | 1.31 | 2.45 | 4.13 |
| Zero-change RMSE, origins from 2024 | 1.36 | 2.27 | 3.69 |
| Model bias, origins from 2024 | +0.42 | +1.10 | +2.31 |

The cause is visible in `models/food_stable_r14b.py`. The three-variable monthly-rate system (farm prices, food producer prices, food CPI) is centred on calendar-month means estimated over the training window of at most 96 months, and its forecasts decay to that centre. The centre therefore carries the window's average drift. A window covering 2016–2023 contains the 2022 surge (+22.7 log points in one year) and has a mean of 4.9% a year. The path kept projecting +4.4 to +5.2% a year through 2025 while food prices fell. The near-term dynamics are useful (h3 beats zero change by 22% on the full sample); the long-horizon centre is the problem.

R24 changes only that centre. It asks one question: what is the best real-time estimate of where Czech food inflation settles?

**Trade-off stated in advance.** A lower drift would have under-predicted the 2021–22 surge even more at those origins. Every drift choice is a bet on regime, and one inflation cycle cannot settle it. I expect candidates to improve origins from 2023 and to worsen origins in 2021–22. Full-sample squared error may go either way.

Research-selection exposure: I have already seen the block scores above, including the 2024+ bias. The candidates are defined from the model's structure and standard robust statistics, not tuned to those numbers, but this is not an untouched test.

## Unchanged

- Baseline food path: `FOOD_STABLE_PIPELINE_R14B`, reproduced at every origin with `models.food_stable_r14b.forecast_origin` from the frozen `data/research_r14/food` inputs. The run asserts that this reproduction equals the `value_food` stored for `STATE_FAST_R15` in `output/research_r21/path_anchor/native_forecasts.csv` at h1–12.
- h0, core (FAST), fuel, administered, alcohol and tobacco, the wedge and all weights. Controls: FAST, current core, gentle slope, as stored.
- 90 origins, h0–h12, the 969-key primary support, both CNB clocks, the origin clocks stored in the native forecasts.

## Decomposing the centre

For food, let `m_c` be the twelve calendar-month means the baseline estimates on its training window. Define the window drift `mu_window = mean(m_c)` and the seasonal shape `s_c = m_c - mu_window`, which sums to zero. The baseline's forecast log rate at horizon h is `s_c + mu_window + d_h`, where `d_h` is the system's decaying deviation. Every candidate keeps `s_c`.

## Drift estimates

All use only observations published by the origin's clock. Units are log points a month.

- `mu_long`: the median of all complete overlapping twelve-month log changes of the food CPI from January 1996 to the latest published month, divided by 12. Before February 2015 the monthly changes come from the CZSO division-01 base-year index in `data/research_r14/food/coverage_extension/czso_cpi_1995_2025.csv` (the repository's audit found it identical to the model's food series on the whole overlap). From February 2015 they are the model's own food changes with their recorded publication dates. Earlier months are treated as published on the tenth of the following month.
- `mu_robust`: the same median, restricted to the baseline's training window.
- Zero.

A median of twelve-month changes ignores a single extreme year by construction, carries no seasonal, and needs no tuning constant.

## Candidates

| ID | Food forecast log rate at horizon h | Refit |
|---|---|---|
| `FOOD_ZERO_DRIFT_R24` | `s_c + d_h` | no |
| `FOOD_ROBUST_WINDOW_R24` | `s_c + mu_robust + d_h` | no |
| `FOOD_NORM_SHIFT_R24` | `s_c + mu_long + d_h` | no |
| `FOOD_NORM_REFIT_R24` | system refitted with the food centre `s_c + mu_long`; farm and producer centres unchanged | yes |

The three shift candidates reuse the baseline's deviation `d_h` and differ only by a constant, which makes the experiment transparent: the zero-drift row shows what removing the drift does, and the other two show what a robust drift adds back. The refit is the internally consistent version: deviations are measured against the same centre the forecast returns to. It reuses `fit_rate_var`, `condition_state` and `simulate_rates` unchanged, with the same training dates, priors, scale and stability contraction. A test asserts that the refit routine reproduces the baseline exactly when given the baseline's own centre.

Each candidate replaces the food block of the `STATE_FAST_R15` frame with `r17_common.replace_block`. Monthly log rates convert to simple rates; non-finite values fail visibly; if the baseline reports insufficient history the candidate equals it and the fallback is recorded.

Not in this round: an error-correction term between retail, producer and farm price levels. In-sample the spread gap has the right sign at h3 and h6, but it needs level states inside the stability and ragged-edge machinery. It is a separate declaration if this round shows the near-term dynamics are the next limit. Administered prices are also left alone: their recent misses were policy events entered in the announcement ledger only once announced, which no drift estimate can anticipate.

## Evaluation

1. **Block first.** Food cumulative log change at h3, h6 and h12 against realised food, with zero change and seasonal-naive as benchmarks (`tools.path_diagnostics.benchmarks`), full sample, origins 2019–21, 2022–23 and from 2024. RMSE, bias and the correlation of forecast with outcome.
2. **Assembled path.** The R23B evaluation stack on the roster of controls plus candidates: fixed 969-key headline scoreboard, same-support tables, circular block bootstrap against FAST, leave-one-origin-year-out, CNB pairs at both clocks, the lead test with base-rate rows and report clusters, call attribution, the block error table.
3. **Drift audit.** `mu_window`, `mu_robust` and `mu_long` at every origin, exported before any score is read.

## What would count

A candidate replaces the baseline food path in the research roster only if all four hold:

1. food-block h12 RMSE at or below the baseline on the full sample and on origins from 2024;
2. food-block h3 and h6 RMSE no more than 2% above the baseline on the full sample;
3. assembled headline h12 RMSE at or below FAST on the full sample and on origins from 2024;
4. a smaller absolute food-block h12 bias on origins from 2024.

If the recent sample improves and the full sample does not, the result is reported as a regime trade-off and nothing is promoted. If several pass, the simplest is preferred in this order: `FOOD_NORM_SHIFT_R24`, `FOOD_ROBUST_WINDOW_R24`, `FOOD_NORM_REFIT_R24`. `FOOD_ZERO_DRIFT_R24` is a control and is never promoted.

## Implementation order

1. Tests first: drift estimators use only published months and ignore an extreme year; centre decomposition sums to zero and reconstructs the baseline centre; the refit routine equals `forecast_origin` under the baseline centre; shift candidates differ from the baseline by exactly the declared constant in log rates; block replacement leaves h0, other blocks and weights untouched.
2. `models/food_drift_r24.py`, `tools/research_r24/run.py`, `tools/research_r24/evaluate.py`.
3. One full run into `output/research_r24/final` after tests pass, then the evaluation, an independent review, the results document and a handoff.
