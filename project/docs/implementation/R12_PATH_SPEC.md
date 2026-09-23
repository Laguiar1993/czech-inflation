# R12 food and cumulative-path prespecification

Frozen before fitting on 9 September 2026. This implements the approved R12 plan,
not a replacement for the existing bridge. Four declared variants; no search,
post-result parameter changes, or blend selected from their realised errors.

## Information clock and invariant reference

Use exactly the 90 `independent_nowcast_forecasts.csv` origins, February 2019
through July 2026, and their saved release-eve clocks. Origin t means the release
being forecast, h0 is t, h12 is t+12. CPI labels end at t-1. Source inputs are the
frozen cleanup fixtures and `independent_path_frozen_inputs.csv`. Most statistical
values are latest stored vintage with reconstructed availability, not historical
vintages. Surveys, expectations, CNB forecasts and retailer data are excluded.

Reuse saved bridge short food/X13 and all unchanged components after checking
source hashes, component recombination, h0 against HARD_BASE, annual compounding,
and replaying the old h4..12 seasonal food rule from released inputs at all
origins. Preserve the original nonfinite short-history forecasts and associated
failure masks. No imputation of missing baseline paths for favourable coverage.
Stored forest and BVAR references are independent R9 forecasts, reused exactly.

## Shared trend and centred seasonality (fixed numerical choices)

Work in log percentage units q=100*log(1+monthly_percentage/100). Reject rates
<=-100 and interior missing released observations; trim initial padding only.
For each available observation, subtract its trailing 12-month q mean, requiring
12 months, to form a causal detrended seasonal observation. Use at most the last
120 such observations, mean by calendar month, missing calendar means zero,
then subtract the equal-weight mean of the 12 calendar effects. Their sum is
zero. At each origin compute an EWMA of deseasonalised released q, span=12,
adjust=False, initialised at the first released deseasonalised observation.
The latest EWMA is the evolving local trend; its forecast stays flat. Add the
destination calendar effect and convert back using 100*expm1(q/100). Minimum
history 24 observations; otherwise report a failure. No fitted decay parameter.

### FOOD_TREND_R12

Replace food h4..12 only with that trend-plus-seasonality forecast. h0..3 and
all weights/nonfood contributions stay identical to the bridge. This tests the
diagnosed long-food rule without altering the near-term nowcast model.

### FOOD_COST_R12

Start from FOOD_TREND_R12 and add a single decaying upstream-cost correction.
Predict the one-month food log-rate error relative to the causal trend/seasonal
forecast from the preceding information set, using two predictors: trailing
three source-month averages of agricultural price m/m and food-products PPI m/m,
both ending at r-2 for a pseudo-origin r. Source values are recovered by calendar
labels from `agri_l1[r]` (=agri[r-2]) and `food_ppi_l1[r-1]` (=PPI[r-2]).
Each source row must have an explicit reconstructed publication timestamp and
pass both its historical pseudo-origin clock and the current run clock. Missing
or unknown publication dates are unavailable. Reconstruct agriculture as day 26
of source month+1, and PPI with the existing day-16/month-exception rule. This
conservative extra source lag does not substitute later source observations.

Train on all complete one-month labels <=t-1 after a 24-month trend warmup;
minimum 24 complete training rows. Centre/standardise the two predictors using
training rows only (population SD; constant columns SD=1). Ridge minimises mean
squared residual plus 1.0*sum(beta^2), with **no intercept**: zero cost signal
means the trend forecast. The fitted current correction is multiplied by
2^(-h/3) at h4..12 (fixed three-month half-life). Missing current cost values or
too few rows give a declared zero-correction fallback to FOOD_TREND_R12. Report
all coefficients, row counts, training edge, availability edge and fallbacks.

## Separate target experiment, unchanged HARD_BASE h0

Two matched headline-only direct ridge models, independent of both food changes:
DIRECT_MONTHLY_R12 and DIRECT_CUMULATIVE_R12. Both use the above causal
trend/seasonality prior, minimum 24-month history and 60 complete training rows.
At every pseudo-origin r calculate three released-data predictors: last
deseasonalised q, mean last 3 deseasonalised q and mean last 12 deseasonalised q,
each minus that origin's EWMA trend. No exogenous future path or expectations.
Standardise on eligible training rows only. Ridge minimises mean squared
residual plus 1.0*sum(beta^2), no intercept. A missing/short fit falls back to its
specified trend/seasonality prior and is counted. No tuned clipping or capping.

For each h=1..12, eligibility is r+h <= t-1 and all required labels are finite.
The monthly target is q[r+h] less the prior forecast at r+h. The cumulative
target is the average of q[r+1]..q[r+h] less the average corresponding prior;
multiply the predicted average back by h. This excludes q[r] intentionally:
both models use supplied HARD_BASE for h0, and cumulative C0=0. Reconstruct
q_hat[h]=C_hat[h]-C_hat[h-1]; C_hat[h] is the direct total log change from t to
t+h. Monthly control forecasts each q_hat[h] directly. h1 is algebraically
identical between the two models. Both use exact exponentiation, and headline
YoY always compounds the exact 12 months ending at t+h (h12 uses h1..12).

## Scoring, integrity and reporting

Construct forecasts before evaluation. Evaluate original stored headline
monthly and compounded annual targets, without rounding or deleting bad years.
All h1..12: full origins, recent **targets** >=2024-01, recent **origins**
>=2024-01. Show RMSE, MAE, bias, intended origins, finite forecasts and common
counts. Use a horizon-specific common panel shared by the four new variants,
bridge, forest, BVAR and five-year seasonal naive, and paired bridge panels;
retain own-coverage diagnostics. Separately show the fixed last-released YoY
benchmark (hold t-1 YoY flat; its monthly path recursively solves that annual
identity and has its own h0). It is not a common-HARD_BASE model.

Also score cumulative future log change over h1..h as well as monthly endpoints,
to distinguish target fit from annual compounding. Annual known-history windows
must never import realised outcomes at/after t. Report every variant and failure.
Paired uncertainty: circular origin-block bootstrap, block length 12, 2,000
replicates, seed 1209, 95% percentile interval for difference in mean squared
annual error versus bridge. Overlapping windows and repeatedly inspected
pseudo-out-of-sample history preclude an untouched-holdout claim.

Tests precede estimators: future-label/cost poisoning; exact horizon and delayed
eligibility; historical/current availability including unknown dates; zero-mean
seasonality; cumulative differencing/product identity; h1 matched models;
unchanged h0..3/nonfood legs; baseline replay; common-sample scoring. Record
source/code hashes, package versions, effective training endpoints, and command.
All outputs belong under `output/research_r12/path/`; no baseline edits.
