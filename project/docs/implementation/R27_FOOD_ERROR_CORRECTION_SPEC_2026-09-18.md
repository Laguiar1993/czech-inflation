# R27 specification: an error-correction term for the food block, h1–6

18 September 2026, Claude. Declared before any code or data work on outcomes; committed before the code, the code before the single run. Judged by the R26 promotion rule.

## Why

R24 fixed the level of the food path (its drift), not its dynamics: from 2024 the forecast-outcome correlation of the food block at h12 is still −0.59, and R26 shows the R14B system beats the sell-side benchmark at h3 by 16–23% but is no better than zero change at h6 from 2024. The R23 review found the one short-horizon signal with the right in-sample sign: the retail-to-upstream spread gap (−0.43 at h3, −0.33 at h6 against the block's error). The R14B food system is a VAR on monthly *rates* of farm, producer and retail food prices, so it carries pass-through of upstream *changes* and nothing about the *level* of retail prices relative to the pipeline. The margin between retail and producer food prices has moved from 0.2 log points in 2015 to 3.5 in 2022 and 10.6 in 2026 (levels frozen in `data/research_r14/food/pipeline_log_levels.csv`). The candidate here lets a share of that gap close through retail food inflation over the next six months.

## Candidates

Both act on the R24 research path (`FOOD_NORM_SHIFT_R24` on the frozen R24 run) and change the food block for h1–6 only; h0, h7–12, every other block, the wedge and the weights are untouched. Nothing else in the tree is refitted.

At origin t with clock c, from the three published log-level series (`agri4`, `food_ppi`, `food`) and their publication dates:

1. **Last common month** L: the latest month at which all three levels are published by c (usually t−2 or t−1).
2. **Window**: the latest published months ending at L, at most 96 and at least 36, the food system's window rule.
3. **Equilibrium relation** by ordinary least squares on the window: `food_s = a + b·s + c1·food_ppi_s + c2·agri4_s + e_s` (candidate `FOOD_ECM_R27`), or without `agri4` (candidate `FOOD_ECM_PPI_R27`). The trend absorbs the secular widening of the retail margin. The gap series is the residual, centred by calendar-month means over the window so that the retail seasonal pattern does not enter it.
4. **Adjustment speed** α: least squares through the origin of the centred monthly food rate on the previous month's gap, over the window: `Δfood_s − m(month) = α·gap_{s−1} + u_s`, where `m` is the window's calendar-month mean of the food rate (the R14B centring). α is clipped to [−0.25, 0]; a positive estimate means no correction and is counted as a wrong sign.
5. **Correction**, in log points per month, for h = 1..6: `α · gap_L · (1 + α)^((t+h−1) − L)`, added to the R24 food log rate at h; the correction decays from the last gap month as the gap closes through retail prices alone, with producer and farm prices treated as random walks beyond their published months. For h ≥ 7 the R24 rate is kept.

Everything above uses only observations published by the clock; no forecast error and no outcome after the origin enters any parameter.

## Gates, read before any score

- Wrong-sign share of α over the 90 origins (expected below 20%); the median and the range of α.
- Share of the gap's variance explained by calendar months before centring (expected below 25% after centring; if the raw share is above 40% the centring is doing real work and the audit says so).
- Needed-against-applied correlation of the correction against the R24 block at h3 and h6, full sample and from 2024.
- Size: the median absolute cumulative correction over h1–6, in log points, against the block's RMSE at h6 (4.10 log points). A correction below 0.3 log points is too small to matter and the round says so.

## Promotion rule

The R26 rule against the R24 path as baseline, with two readings declared here for a candidate that acts at h1–6:

1. Block RMSE at or below the baseline in all twelve era-by-horizon cells (h3, h6, h12).
2. At or below the best feasible benchmark (zero change, seasonal-naive, `SA_AR`, `SA_AR_TARGET`) at h6 and h12, full sample and from 2024.
3. Specificity against fixed adjustment speeds: α ∈ {−0.02, −0.05, −0.10, −0.15} with the same gap; the estimator is promoted as an estimator only if its h6 full-sample squared-loss difference against the best fixed α has a circular block bootstrap interval excluding zero. Otherwise the promoted object, if any, is the best fixed speed in the set passing condition 1, chosen by the era-balanced score.
4. In phase: sign agreement of needed and applied at least one half and correlation at or above zero at h3 and h6, full sample and from 2024 (the R26 amendment for corrections that are not constant across origins is not needed here, both tests are reported).
5. Interval: h6 and h12 full-sample squared-loss differences against the baseline with circular block bootstrap intervals excluding zero.
6. Assembled path: headline RMSE at or below the R24 path's in every era cell at h6 and h12, and on the matched report-clock CNB pairs from 2024.

A candidate that fails one condition is recorded with the condition it failed.

## What is run

- `models/food_ecm_r27.py`: gap, speed, correction, candidate paths at an origin.
- `tools/research_r27/run.py`: the 90 origins on the frozen R24 run; writes `native_forecasts.csv` and `forecasts.csv` in the R24 format with controls `STATE_FAST_R15`, `FOOD_NORM_SHIFT_R24` and the two candidates plus the four fixed-α variants of `FOOD_ECM_R27` for condition 3; `ecm_audit.csv` with L, window, coefficients, α, gap and correction per origin; `fits.jsonl`; `manifest.json` with hashes.
- `tools/research_r27/evaluate.py`: the standard evaluation (`tools.path_diagnostics.standard`), then the R26 family scores and the six conditions against the R24 baseline.
- `tests/test_food_ecm_r27.py`: publication gating of the last common month, the trend and centring of the gap, the sign clip of α, the decay of the correction, h7–12 untouched, the exact reproduction of the R24 food path when α = 0.

## Expectations, written before running

- α negative at 80% or more of origins, median between −0.03 and −0.10 a month; the gap's raw seasonal share above 25% (retail food has a strong seasonal pattern that producer prices do not), below 10% after centring.
- Food block RMSE 3–8% lower at h3 and h6 on the full sample and 5–10% lower from 2024, where the 2025–26 widening of the margin points to the low food inflation actually printed in 2026. h12 within ±2% of the baseline.
- The risk is 2019–21: the margin was already wide in 2020–21 (8 log points) and food inflation then surged with producer prices; a negative correction at those origins hurts. I expect the 2019–21 h6 cell to be within +3% of the baseline and condition 1 to be the one most likely to fail.
- `FOOD_ECM_PPI_R27` close to `FOOD_ECM_R27`; farm prices add little once producer prices are in the relation.
- Specificity: I expect the estimated α to be distinguishable from a fixed −0.02 and not from −0.05 or −0.10; if so, the promoted object is a fixed speed, and the results say so.

## Rules kept

Specification committed before code; code committed before the single run; evaluation rehearsed on a scratch copy; hash-frozen files untouched (the R24 run, `tools/path_diagnostics/*`, `tools/review/*`, `tools/research_r23/lead.py`, the R26 code); every figure in the results document reproduced by an exported file; no survey, expectations series or CNB forecast enters the candidate.
