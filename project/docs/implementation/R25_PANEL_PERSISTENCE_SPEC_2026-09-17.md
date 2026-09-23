# R25: how much of the core trend persists, estimated outside the Czech sample

Declared by Claude on 17 September 2026, before any R25 data are analysed, fitted or scored. No existing model, output or evaluator is edited.

## Why

FAST forecasts core inflation beyond a few months as a flat continuation of its filtered trend. The R23 review found that its twelve-month error correlates −0.54 with current core momentum: it over-extrapolates, and when inflation is far from normal the forecast stays far from normal. R21 tried the obvious repair, convergence of the trend toward 2% with a half-life of 12 or 24 months chosen a priori. That helped origins from 2024 and hurt the full sample, because during the 2021–22 build-up reversion made a bad under-prediction worse.

How fast core inflation returns to its norm, and whether that speed depends on how far away it is, cannot be learned from one Czech cycle. R21 to R23B all tried to learn corrections from the same 90 origins and all failed for that reason. R24 showed that replacing a recent-window quantity by a robust long-history norm works for food. R25 applies the same idea to the core trend, and takes the one parameter that matters, the persistence of deviations from the norm, from a cross-country panel **that excludes the Czech Republic**. The Czech evaluation sample then never touches the estimate, which makes 2019–2026 a genuine out-of-sample test of a mechanism estimated elsewhere. It also serves the stated end goal of portability to other countries.

## Data

Eurostat `prc_hicp_midx`, all-items HICP excluding energy, food, alcohol and tobacco (`TOT_X_NRG_FOOD`), index 2015=100, monthly, every EU member state except Czechia. One download is frozen with its hash and retrieval time under `data/research_r25/`. This HICP aggregate is not the CNB core measure (it has no imputed rent, includes administered services and is not tax-adjusted). Only a persistence parameter is borrowed from it, never a level or a forecast.

Availability: HICP for month m is treated as published on day 20 of month m+1. At a Czech origin t, whose clock is about the tenth of t+1, panel data therefore end at t−1, the same edge as Czech core.

## Panel construction

For each panel country and each quarter-end origin s (data through s−1), run the unchanged R15 filter `models.core_trend_residual_r15.state_at` on that country's monthly core rates. This yields the country's own-origin seasonal pattern and its FAST forecast log rates for h1–12, exactly as for Czechia. No panel country is treated differently, and no filter setting is re-tuned.

Per band b (h1–3, 4–6, 7–9, 10–12), with everything seasonally adjusted by the origin's own seasonal pattern:

- `f` = mean FAST forecast log rate over the band;
- `r` = mean realised log rate over the band;
- `mu` = the country's norm: the median of all complete overlapping twelve-month log changes of its core index available at the origin, divided by 12, requiring at least 60 months of history.

## The estimate

For band b at Czech origin t, pool every panel row whose band is fully published by the Czech clock (`s + 3b <= t - 1`) and estimate, without an intercept,

`r - mu = lambda_b * (f - mu)`.

`lambda_b` is the share of the filtered trend's deviation from the norm that survives to the band. It is clipped to [0, 1]: it is a combination weight between the filter and the norm. It is re-estimated at every Czech origin with the rows available then, so it is a real-time quantity.

## Candidates

| ID | Core forecast for band b | Estimated on |
|---|---|---|
| `CORE_PANEL_SHRINK_R25` | `mu_cz + lambda_b * (f_cz - mu_cz)` | panel, one `lambda_b` |
| `CORE_PANEL_STATE_R25` | the same with two values of `lambda_b`, for `abs(f - mu)` at or below and above the pooled real-time median of `abs(f - mu)` | panel |
| `CORE_OWN_SHRINK_R25` | as the first, estimated on Czech quarterly origins only (saved R15 states from 2010) | Czech history (control) |
| `CORE_PANEL_SHRINK_FOODNORM_R25` | the first candidate's core with R24's `FOOD_NORM_SHIFT_R24` food path | combination of two separately declared changes; not a new degree of freedom |

`mu_cz` is the same robust norm computed on CNB core from 2007 with observations published by the Czech clock. `f_cz` comes from the saved R15 FAST state. The band correction `(lambda_b - 1) * (f_cz - mu_cz)` is mapped to months with the band-mean-preserving `models.cost_gaps_r23.monthly_correction` and added to the saved FAST log rates. h0, every noncore block and all weights are untouched (except the food block in the fourth candidate, exactly as in R24). If fewer than 200 panel rows are available for a band, or the Czech norm is unavailable, the candidate equals FAST for that band and the fallback is recorded.

The two-regime candidate tests the regularity that persistence rises with the distance from normal. The Czech-only control shows what the panel adds.

## Expectation, stated in advance

`lambda_b` should fall with the horizon. I expect roughly 0.8 to 0.95 for h1–3 and 0.4 to 0.8 for h10–12. Shrinkage should help origins in 2022–23 and from 2024, and hurt origins in 2021, when the trend was above the norm and inflation went higher still. The full-sample result may go either way, as it did for R21's a-priori anchors. If the panel weight behaves like those anchors, that is a clean negative for unconditional mean reversion and the result will say so.

## Evaluation

1. **Audit before scores**: `lambda_b` at every origin with its row count, the panel's composition, the Czech norm over time.
2. **Core block first**: cumulative log-core RMSE and bias at h3, h6 and h12 by era (full, origins 2019–21, 2022–23, from 2024), and the needed-against-applied correlation.
3. **Assembled path** through `tools.path_diagnostics.standard`: the fixed 969-key scoreboard, same-support tables, circular bootstrap against FAST, leave-one-origin-year-out, CNB pairs and the lead test with base rates, block tables.

## What would count

A core candidate joins the research roster only if all four hold:

1. cumulative log-core h12 RMSE at or below FAST on the full sample and on origins from 2024;
2. cumulative log-core h3 and h6 RMSE no more than 2% above FAST on the full sample;
3. assembled headline h12 RMSE at or below FAST on the full sample and on origins from 2024;
4. a positive needed-against-applied correlation at h12.

If several pass, the simplest is preferred: single `lambda_b` before two regimes. The Czech-only control and the combination row are never promoted on their own. If only the recent sample improves, the result is reported as a regime trade-off and nothing is promoted.

## Implementation order

1. Freeze the panel download. Tests first: the norm uses only published months; panel rows mature by band; `lambda_b` is recovered exactly on synthetic data with known persistence, is clipped, and is invariant to poisoning of rows that mature after the clock; the two-regime split uses only rows available at the clock; zero deviation gives zero correction; the Czech application reproduces FAST when `lambda_b` is 1.
2. `data/hicp_panel_r25.py`, `models/panel_persistence_r25.py`, `tools/research_r25/run.py`, `tools/research_r25/evaluate.py`.
3. One full run into `output/research_r25/final` after tests pass; evaluation; independent review; results.
