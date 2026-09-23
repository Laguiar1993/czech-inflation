# CNB revision tracker: a separate, conditioned lane

Declared by Claude on 17 September 2026, before any tracker regression is estimated or scored.

## What it is, and what it is not

The user's objective includes anticipating changes in the CNB forecast. The R23 review and R23B/R24 lead tests show that the independent path alone has not done this since 2023: its gap against CNB three to four quarters ahead is mostly a structural persistence difference, and a constant 2% forecast scores as many "joint successes".

A CNB forecast revision is largely a response to news since the previous forecast's cutoff: inflation that came in away from CNB's own near-term forecast, a koruna away from the assumed path, oil away from the assumed path. All three can be measured from published CNB tables and public data. The tracker does exactly that.

**It uses CNB forecasts as inputs. It is therefore not part of the independent forecast and never feeds it.** It is a separate product that answers a different question: where is the next CNB forecast likely to move. A defensible call in the user's sense is one where the independent disagreement and the tracker point the same way.

## Data

- `data/cnb_mpr_tables_20260917/cnb_mpr_indicators_long.csv`: 19 reports, February 2022 to August 2026, with headline CPI, core, food (including alcohol and tobacco), fuel and administered prices with basket weights, CZK/EUR and Brent, and the bold-forecast flag. Report and cutoff dates are those already recorded in `data/cnb_mpr_cpi_quarterly.csv`.
- Realised headline and block monthly rates: `output/independent_path_frozen_inputs.csv` and `output/research_r14b/attribution/actual_component_targets.csv`, with the CPI release calendar.
- Daily EUR/CZK fixings: `data/cnb_daily_eur_fixings_20260912/eurczk_daily.csv`. Monthly Brent: the frozen Bloomberg monthly mean in `candidate_inputs_long.csv`.

## The panel

For each pair of consecutive reports k and k+1 (18 pairs). Let `q_k` be the calendar quarter of report k and `q_next = q_k + 1` that of report k+1.

**Targets.** For j = 0, 1, 2, 3 the revision `r_j = F_{k+1}(q_next + j) - F_k(q_next + j)` of the headline CPI forecast. j = 2 and 3 are the horizons of the lead test (three and four quarters ahead at report k).

**News, all known by the cutoff date of report k+1:**

- `cpi_news = A(q_k) - F_k(q_k)`: realised quarter-average annual inflation in the quarter of report k, less CNB's own forecast of it in report k. The run asserts that the last month of `q_k` was released on or before the next cutoff.
- `core_news`, `noncore_news`: the same by block, as contributions in percentage points of headline using CNB's printed weights. Noncore is food including alcohol and tobacco, fuel, and administered prices together.
- `fx_news = 100 * log(mean EUR/CZK over the ten fixing days ending at the next cutoff / F_k(CZK/EUR, q_next))`: positive when the koruna is weaker than CNB assumed for the quarter in which the next forecast is made.
- `brent_news = 100 * log(Brent mean of the last complete month before the next cutoff / F_k(Brent, q_next))`.

## Models

Ordinary least squares without an intercept, one equation per horizon j. A revision should be zero when there is no news, and with 18 observations every parameter is expensive.

| ID | Regressors |
|---|---|
| `T0_ZERO` | none: the revision is zero (benchmark) |
| `T1_CPI` | `cpi_news` |
| `T2_CPI_FX_OIL` | `cpi_news`, `fx_news`, `brent_news` |
| `T3_BLOCKS_FX_OIL` | `core_news`, `noncore_news`, `fx_news`, `brent_news` |

## Evaluation

1. **Leave one report pair out**: every revision is predicted with coefficients estimated on the other 17 pairs. This is not chronological, so it is supplemented by:
2. **Expanding window**: the first 8 pairs initialise, and pairs 9 to 18 are predicted with coefficients from earlier pairs only.
3. Per horizon and model: RMSE against `T0_ZERO`; correlation of predicted and actual revision; sign hit rate on revisions of at least 0.15pp in absolute value, with the count.
4. Against the independent path: on the pairs of the lead test (report clock, targets j = 2 and 3), the sign agreement of the FAST gap and of the R24 food-norm gap with the subsequent revision, next to the tracker's. Same rows, same revisions.
5. Full-sample coefficients with conventional standard errors, for interpretation only.

## What would count

The tracker is worth maintaining as a live side product if, for j = 2 and j = 3 together, under **both** leave-one-out and the expanding window: its RMSE is below the zero-revision benchmark, and its sign hit rate on material revisions exceeds both 50% and the FAST gap's hit rate on the same rows. With 18 pairs, anything short of that is reported as not established. Whatever the result, the limits are stated: 18 overlapping pairs, one inflation cycle, revised data for realised inflation, and no model of CNB judgement.

## Live reading

After the historical evaluation, the tool prints a reading for the next CNB report from whatever frozen data exist after the latest cutoff, clearly marked partial when the quarter of the latest report is not yet complete. It is a side product and carries no promotion claim.
