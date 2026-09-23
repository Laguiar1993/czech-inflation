# R23B: measurement repair of the quarterly cost-pressure correction

Declared by Claude on 17 September 2026, before any R23B fit or score. It follows `REVIEW_TO_CODEX_R23_2026-09-17.md`. R23 and its sealed evidence stay untouched; every R23B file is new.

## Why a rerun, and what is expected

R23 reported that cost gaps add nothing to FAST. The review found that R23 did not test that proposition:

1. The ULC input is not seasonally adjusted, and the level-against-median gap keeps the seasonal (44% of the feature's variance).
2. Sign bounds sat on zero in 82–98% of fits for imports, PPI and FX, so the imported channel never operated.
3. The active term was a penalized intercept. Labels mature 13–15 months late, so its correction correlated −0.58 with the correction FAST needed.

R23B repairs those three defects on the identical harness and support, so that the negative is clean or a bounded near-term positive appears. **My expectation, stated before fitting, is no promotion.** The run closes the lane properly; it is not a search for a winner.

Research-selection exposure: the momentum-differential transformation below was chosen after the review's in-sample inspection of the R23 targets (about 60 overlapping quarterly rows, one inflation cycle). Coefficients are still learned only from matured labels, but the choice of transformation is not innocent. No result here is an untouched test.

## Unchanged from R23

- Baseline: `STATE_FAST_R15` from `output/research_r15/states.json`, with the identical saved R15 seasonal pattern at every origin.
- h0, all noncore blocks, weights and controls from `output/research_r21/path_anchor/native_forecasts.csv`. Controls: FAST, current core, gentle slope, R21 core feedback.
- 90 origins (February 2019 to July 2026), horizons h0–h12, the 969-key primary support, both CNB clocks.
- Sources and publication masks: `data.cost_gaps_r23.load_inputs` (CNB core, A6 series 11, 17, 26, 47, monthly EUR/CZK, release calendar). Every source value is masked by its publication date before any transformation. Missing publication dates fail closed.
- The seasonally adjusted core log level is built exactly as in R23 (strict chain of `100*log1p(core/100)` less the origin's saved seasonal pattern).
- One training origin per calendar quarter (March, June, September, December). ULC stays quarterly and is never interpolated.
- Band-mean-preserving monthly mapping `models.cost_gaps_r23.monthly_correction`.

## Features

All are oriented so that a positive value is hypothesized upward pressure on core relative to FAST, and all are defined so that **zero means neutral**.

1. `ulc_sameq`. Let `rel_q = 100*log(ULC_q) - mean core log level in quarter q`. The reference quarter `q` is the latest published quarter whose last month is at most t−1. The feature is `rel_q - median(rel_{q-4}, rel_{q-8}, rel_{q-12})`. Comparing a quarter only with the same quarter of the three previous years removes stable seasonality while keeping R23's twelve-quarter lookback and timing. All four quarters must be published with complete core months; otherwise the feature is missing.
2. `tightening`. As R23: minus the twelve-month change in the published SA unemployment rate.
3. `import_mom`. Six-month log change of import prices minus the six-month change of the seasonally adjusted core level over the same months. The reference month is the latest published import month at most t−1. It is the sum of the six latest published monthly log changes; all six must be published and finite. No dependence on the start of the chain.
4. `ppi_mom`. The same for the manufactured PPI log level.
5. `fx_news`. As R23: log EUR/CZK change since the import reference month.
6. `import_gap` and `ppi_gap`. Exactly R23's level gaps, kept only for the control candidate below.

A momentum differential asks whether upstream prices are rising faster than consumer core prices already are. The review's diagnosis was that R23's level gaps are late-cycle measures: by the time the relative level is high, FAST's adaptive trend already carries the pass-through.

## Targets and label maturity

For training origin `s`, band 1 is the mean of realised minus saved-FAST monthly log core over h1–3, and band 2 the same over h4–6. **Bands 3 and 4 (h7–12) receive no learned correction.** The review showed that a correction learned from labels 13–15 months old is close to anti-phase with the need.

Maturity is band-specific. A band-1 label is usable at decision origin `t` when month `s+3` is at most t−1 and all three target releases are published by the decision clock. A band-2 label needs `s+6` at most t−1 and all six releases published. R23's single twelve-month rule delayed even h1–3 learning by a year; this is handoff question 2.

## Estimation

For each candidate and each band separately:

- Training rows: the latest 40 eligible quarter-end origins, minimum 24. A row is eligible only if **all seven features** are complete at that origin, so every candidate uses the same rows and differences isolate the predictors.
- Predictors are divided by their training root-mean-square (floor: a scale below 1e-8 is set to 1). They are **not centered, and there is no intercept**. Zero pressure therefore maps to zero correction, and the delayed-echo intercept is gone.
- Ridge: minimize mean squared error plus `alpha` times the squared coefficients. Unrestricted candidates use the closed form. The sign-restricted candidate solves the same objective with coefficients bounded at zero or above.
- Grid `alpha` in {0.3, 1, 3, 10, 30}, plus the explicit option **no correction**.
- Nested chronological selection, per band: among the outer training rows, take the latest 8 validation origins for which at least 16 earlier rows were matured at that validation origin's own clock. Inner fits use at most 40 rows and their own scaling. The loss is the squared error of the band prediction. At least 4 folds are required; with fewer, no correction is applied.
- **Do-no-harm rule.** The chosen `alpha` is applied only if its mean validation loss is strictly below the loss of no correction on the same folds. Ties favour the stronger penalty, then no correction. No outer outcome ever selects a setting.

## Candidates

| ID | Predictors | Coefficients |
|---|---|---|
| `PRESS_ULC_R23B` | `ulc_sameq` | free |
| `PRESS_DOMESTIC_R23B` | `ulc_sameq`, `tightening` | free |
| `PRESS_MOMENTUM_R23B` | `import_mom`, `ppi_mom`, `fx_news` | free |
| `PRESS_JOINT_R23B` | the five above | free |
| `PRESS_SIGNED_R23B` | the same five | bounded at zero or above |
| `PRESS_LEVELS_R23B` | `ulc_sameq`, `tightening`, `import_gap`, `ppi_gap`, `fx_news` | free |

`PRESS_LEVELS_R23B` is R23's joint feature set with the ULC repaired, under the R23B estimator. It separates the estimation repair from the change of transformation. `PRESS_SIGNED_R23B` keeps the economic sign prior so that its binding share can be reported as a specification test, which R23 did not do.

The monthly correction is `monthly_correction([c1, c2, 0, 0])` added to the saved FAST log rates, then converted back to simple monthly rates. No clipping. Non-finite values fail visibly. If current features are missing, or fewer than 24 rows are eligible, the candidate equals FAST for that band and the fallback is recorded.

## Evaluation

The R23 evaluation stack runs unchanged on the new roster (fixed 969-key scoreboards, component scoreboards, CNB pairs at both clocks, leave-one-report-out, leave-one-origin-year-out, strict core-turn test, lead test at 0.30 and 0.50). R23B adds the diagnostics the review asked for, from the new `tools/path_diagnostics` package:

1. **Input gates**, computed before scores are read: the share of each feature's variance explained by its reference period-of-year; the share of fits in which a bounded coefficient sits on zero; the share of unrestricted coefficients with the wrong sign.
2. **Needed against applied**: correlation between the correction FAST needed (realised minus FAST, cumulative log core over h1–6) and the correction applied.
3. **Circular block bootstrap** for paired squared-loss differences against FAST: block 12 when n is at least 48, block 6 when n is 24 to 47, and no interval below 24. This replaces the truncated moving-block intervals whose point estimates fell outside their own intervals at n=19.
4. **Core figures on the same 75-origin support** as the headline table.
5. **Lead-test base rates**: constant 2%, random-walk annual rate, previous CNB forecast and CNB revision momentum, passed through the same call, confirmation and episode rules; counts of distinct reports behind gains and losses; a dominant-block label on every call.
6. **Block attribution**: RMS and bias of the cumulative weighted block errors at h6 and h12, full sample and origins from 2024.

## What would count

Nothing is promoted automatically. A candidate is worth carrying as a research challenger only if all four hold:

1. headline h6 RMSE at or below FAST on the full sample and on origins from 2024;
2. cumulative log-core h6 RMSE at or below FAST on both samples;
3. a positive needed-against-applied correlation;
4. no feature with more than 25% of its variance explained by period-of-year.

Otherwise the cost-pressure correction lane is closed, and the results document says so plainly.

## Implementation order

1. Tests first: same-quarter gap is seasonally neutral on a synthetic seasonal series and ignores unpublished or future values; momentum features need exactly six published changes; band-specific maturity for outer rows and inner folds, with future-label poisoning; zero pressure gives zero correction; the do-no-harm rule; far bands stay zero on average; diagnostics (gates, circular bootstrap coverage, lead baselines, attribution identity).
2. `data/cost_pressure_r23b.py`, `models/cost_pressure_r23b.py`, `tools/path_diagnostics/`, `tools/research_r23b/run.py` and `evaluate.py`.
3. One full run into `output/research_r23b/final`, after tests pass. Verify FAST path equality before substitution and exact preservation of h0, noncore values and weights.
4. Independent review of code against this specification, then the results document and a handoff.
