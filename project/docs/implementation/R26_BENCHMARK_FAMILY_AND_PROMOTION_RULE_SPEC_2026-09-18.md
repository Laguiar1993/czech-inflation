# R26 specification: a sell-side benchmark family and a promotion rule with power

18 September 2026, Claude. Declared before any code or data work for this round; committed before the code, the code before the single run.

## Why

Two facts from the last rounds. The R24 reviewer showed that my promotion rule could not tell an estimator from a constant: a plain 2.6% food drift scores the same as the long-history median, and every constant from 1.75 to 4.75 would have passed. And the user relayed, on 18 September, a practitioner's description of the standard sell-side approach: split inflation into food, fuel/energy and core; work on seasonally adjusted month-on-month rates; let each block follow a simple ARMA process; make food and energy a function of commodity prices; and expect that split plus a correct seasonal adjustment to carry the nowcast and the one-month-ahead forecast, with longer horizons a matter of the labour market and second-round effects.

We already split the basket (core, food, fuel, administered prices, alcohol and tobacco, a wedge), we already work on monthly rates with own-origin seasonal patterns, and fuel already carries commodity pass-through. What we do not have is the plain sell-side model itself, built the same way at every origin, as the thing our models must beat. Block benchmarks so far are zero change and a three-year seasonal-naive path. This round adds the practitioner's benchmark to the family, assembles it into a full path, and writes down a promotion rule that a future candidate must satisfy before it can replace anything.

No new forecasting candidate is declared here. The round scores the existing roster (FAST, the R24 research path, current core, gentle slope) against the family. If the benchmark path beats a roster block somewhere, that is a finding about the roster, not a promotion of the benchmark.

## Benchmark family

All members use only realised block monthly rates (`output/research_r14b/attribution/actual_component_targets.csv`, current vintage) published by the origin's clock under the same publication rules as the R17 stack (`r17_common.publication_dates`), on the original 90 origins. Nothing is fitted on outcomes after the origin.

| Member | Definition |
|---|---|
| `ZERO` | 0% a month at every horizon (already in `tools/path_diagnostics/benchmarks.py`) |
| `SEASONAL_NAIVE` | mean of the same calendar month over the latest three published years (already there) |
| `SA_AR` (the sell-side benchmark) | Trailing window of the latest published monthly rates, at most 96 and at least 36 months, the same window rule as the food system. Seasonal pattern: calendar-month means of the window, centred on the window mean so that the pattern sums to zero. Seasonally adjusted deviation: rate minus the pattern minus the window mean. An AR(1) coefficient on the deviations, ordinary least squares through the origin, clipped to [0, 0.95]. Forecast at h: window mean + pattern(t+h) + phi^h × last published deviation. Months missing at the ragged edge (a block not yet published for t−1) use the forecast in their place, so the last deviation is the last published one |
| `SA_AR_TARGET` | as `SA_AR`, but the window mean is replaced by a fixed 2% a year (0.165% a month) for core; blocks other than core keep their window mean. This is the anchor the practitioner's benchmark implies at long horizons |
| `CONSTANT_ORACLE` (ceiling, not feasible) | the single constant monthly rate per block that minimises full-sample cumulative RMSE at h12 on the primary support; used only to measure a candidate's specificity, never as a forecast |

The assembled benchmark path, `SELL_SIDE_PATH`, replaces every block of the FAST path (core, food, fuel, administered, alcohol and tobacco) with the block's `SA_AR` forecast, keeps h0, the wedge and the basket weights unchanged, and is compounded exactly as every other path. `SELL_SIDE_TARGET_PATH` does the same with `SA_AR_TARGET`. Neither is a candidate.

## Promotion rule

A candidate block path replaces the roster's block only if all of the following hold on the fixed 969-key primary support at h3, h6 and h12, using the block's cumulative log change over h1..h:

1. **Baseline, every era.** RMSE at or below the baseline block's in all twelve era-by-horizon cells (full sample; origins 2019–21; 2022–23; from 2024). Unchanged from R24.
2. **Feasible benchmarks.** RMSE at or below the best of `ZERO`, `SEASONAL_NAIVE`, `SA_AR` and `SA_AR_TARGET` at h6 and h12 on the full sample and from 2024. A block that loses to a forecast that needs no model is not promotable, whatever it does against the baseline.
3. **Specificity.** If the candidate contains an estimated constant, drift or shift, its declaration names the grid of fixed constants it is compared with. The candidate is promoted as an estimator only if its full-sample h12 squared-loss difference against the best grid constant has a circular block bootstrap interval excluding zero. Otherwise the promoted object is the simplest equivalent member of the grid, named as a fixed number, and the results document says so. This is the R24 lesson written down.
4. **In phase.** Needed-versus-applied correlation of the candidate's change against the baseline at or above zero at h6 and h12, full sample and from 2024 (gate from `tools/path_diagnostics/gates.py`).
5. **Interval.** Full-sample h12 squared-loss difference against the baseline block with a circular block bootstrap interval excluding zero.
6. **Assembled path.** With the block swapped in, headline annual-rate RMSE at or below the baseline path's in every era cell at h6 and h12, and RMSE on the matched report-clock CNB pairs from 2024 at or below the baseline path's. A headline gain with a worse block is error cancellation and does not count; a block gain with a worse assembled path does not count either.

A candidate that fails one condition is recorded with the condition it failed. There is no partial promotion.

## What is run

One evaluation, `tools/research_r26/evaluate.py`, on the frozen R24 run (`output/research_r24/final`), which already holds FAST, current core, gentle slope and the R24 candidates on the 90 origins. It writes, in a new directory:

- `benchmark_paths.csv`: every family member's block path at every origin (h1–12).
- `block_family_scores.csv`: block cumulative-log RMSE and bias for every roster model and every family member, by horizon and era, on identical origins.
- `block_verdicts.csv`: for each roster model and block, whether conditions 1, 2, 4 and 5 hold against FAST (condition 3 needs a declaration, condition 6 an assembled candidate; both are reported for the R24 food block, which is the one promoted object so far, with the reviewer's constant grid 1.75–4.75% a year in steps of 0.25).
- `assembled_scores.csv`: headline annual-rate RMSE of `SELL_SIDE_PATH`, `SELL_SIDE_TARGET_PATH` and the roster on the primary support, by horizon and era, and on the matched CNB pairs from 2024.
- `checks.json` and an input manifest with hashes.

Tests in `tests/test_benchmarks_r26.py` cover: publication gating (a month published after the clock is not used), the centred pattern summing to zero, the AR clip, the ragged-edge substitution, the oracle constant being the RMSE minimiser on a toy series, and the rule returning the failed condition.

## Expectations, written before running

- `SA_AR` core will be close to FAST core at h3 (within 10%) on the full sample, worse at h6–12 for 2019–21 and 2022–23 origins (its window mean lags a rising core), and better than FAST from 2024 at h6–12 (reversion is the right call in the unwind). `SA_AR_TARGET` will be worse than `SA_AR` in 2021–23 and better from 2024.
- `SA_AR` food will carry the same window drift as the R14B system and score near FAST food from 2024 (both biased up), and worse than the R24 path in every era at h12.
- `SA_AR` fuel will be close to `ZERO` at every horizon and worse than FAST fuel at h1–3, where pump-price pass-through of already observed oil and koruna moves is real information.
- `SA_AR` administered will be worse than `ZERO` from 2024, because its window holds the 2022–23 energy repricing.
- The assembled `SELL_SIDE_PATH` will be 5–10% worse than FAST at h3 and h6 on the full sample and within 5% of FAST at h12; from 2024 it will be between FAST and the R24 path at h12. If it beats the R24 path at h12 from 2024, the roster's long-horizon machinery adds nothing over the practitioner's benchmark in this regime, and that is the headline of the results document.
- The R24 food block will pass conditions 1, 2, 4 and 5 and fail condition 3 (the reviewer's result): it will be re-labelled as a fixed drift near 2.6% a year.

## Rules kept

Specification committed before code; code committed before the single run; evaluation rehearsed on a scratch copy; no hash-frozen file edited (the R24 run, `tools/path_diagnostics/*`, `tools/research_r23/lead.py`, `tools/review/*` are read only); every figure in the results document reproduced by an exported file. No survey, expectations series or CNB forecast enters any member of the family.
