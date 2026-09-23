# R14 independent core path: level, moving trend and adaptive learning

Declared before any R14 empirical candidate fit. The user authorized path research
and experiments; the main independent forecast excludes surveys, FMIE, household
expectations and ESI. This adds research challengers without altering the nowcast
or the operating bridge. Existing R9--R13 historical results are already inspected,
so this is sequential pseudo-OOS research, not a new untouched holdout.

## Question and alternatives

R13's expanding mean-loss ridge penalty1 shrank coefficients strongly toward a
historical unconditional mean and constrained aggregate history to the shorter
category sample. Test whether aggregate core's longer history, learning changes
relative to a moving inflation trend, nonlinear response and strictly delayed
validation improve its path. Preserve a level-target control and a simple trend
control. Do not force a2% core rate or calibrate to survey/CNB predictions.

## Targets and monthly reconstruction

Use CNB aggregate core m/m from the frozen January2007+ history. q=100*log1p(core/100).
At each historical origin r, keep only months <=r-1 whose detailed CPI release is
known by its own saved release-eve clock. Require contiguous finite history ending
exactly r-1 and at least36 months. Source publication dates use the existing
core_split_experiment.publication_dates (pre-calendar fallback20th09:00).
Recorded outer clocks are23:59 Prague; earlier historical clocks use _eve.

Estimate seasonality at EACH r: q minus its trailing12-month mean, take the latest
120 available detrended observations, compute calendar-month means, then center
the12 coefficients to zero. All12 months must be represented. Define trend[r] as
the mean of the last12 q observations (a complete year's centered seasonal
coefficients sum to zero). Define adjusted last1/3/12-month core means from this
origin's seasonal coefficients; never use an outer-origin estimate for older rows.

Four direct horizon bands are h1..3,4..6,7..9,10..12, relative to r (h0 is the month
being nowcast). Response level for each band is the mean of its three future
q[r+k] minus the destination-month seasonal coefficient estimated at r. Response
gap subtracts trend[r] from that level. At outer t all three band labels must be
released and <=t-1. This is not a forecast of a calendar quarter. In each band,
reconstruct predicted q[t+h] as predicted band mean + season[t][destination month],
and convert exactly back with100*expm1(q/100). Retain original HARD_BASE h0 and all
noncore contributions/weights; reaggregate headline monthly and compound annual
inflation with the existing exact routine. Forecast smoothing inside a band is
intentional and must be disclosed; h1/h2 use a3-month target with longer label delay.

## One fixed predictor set and data timing

Ten columns, no feature search: last adjusted core month, mean adjusted core last3,
mean adjusted core last12, difference of3-month and12-month means; mean and sum
log import-price changes over last3 and12 sources respectively; mean and sum log
EUR/CZK changes over last3 and12 sources respectively; target band's mean sine
and mean cosine of destination months (known deterministic calendar).

More precisely imports use arithmetic m/m recovered from core_features.import_l2
with fixture row u+2 for source u; fixed newest source r-3. Every source is gated by
reconstructed publication16th of u+2 at00:00 Prague. FX uses fixture eurczk_mm[u],
newest source r-1, available at start of u+1. Current r's partial/full FX row is
not used. Three-month features are means of100*log1p(rate/100);12-month features
are sums in log percentage points. Each historical row is built at its own clock;
later source rows cannot fill it. Missing required values imply unavailable row,
not imputation. Latest stored import/FX observations have reconstructed availability,
not historical revision vintages. No unemployment/wage proxy is added this round.

## Frozen roster and estimation

- CORE_LOCAL_R14: adjusted mean fixed at current trend12 for all bands.
- CORE_LEVEL_RIDGE_R14: band level target, expanding training, sum-loss alpha30.
- CORE_GAP_RIDGE_R14: band gap target, otherwise identical; add current trend.
- CORE_GAP_ADAPT_R14: same gap features/target, select alpha3/30/300 crossed with
 60-calendar-month or expanding training (six options). Default alpha30/expanding.
- CORE_LEVEL_RF_R14 and CORE_GAP_RF_R14: matching targets, expanding training,
 RandomForestRegressor200trees, min_samples_leaf5, max_features1/3, seed42,
 bootstrap=True, n_jobs1. The gap forest can extrapolate overall inflation levels
 through its moving origin trend; the residual response itself remains bounded
 by tree leaves. Do not claim a calibrated predictive distribution.

Ridge centers/scales predictors using its eligible training slice only (population
SD, constant columns scale1). Unpenalized target intercept; solve X'X+alpha I,
NOT X'X+n*alpha I. Minimum48 complete released training rows;60m window means
pseudo-origin >=t-60, not latest60 eligible rows. RF uses same expanding eligible
calendar/48minimum. No clipping, fallback predictions or post-fit bias adjustment.

Adaptive selection is separately by band. First generate and save every candidate's
sequential prediction at its own historical clock. At t select only from prior
origin errors whose complete band outcomes are published by t and <=t-1. Use
latest36 origins common to all six configurations; minimum24, otherwise default.
Loss is MSE of the native band gap/level forecast (same error). Exact/near ties
rtol1e-10,atol1e-12 prefer default, then alpha order3/30/300 and window60/expanding.
The current or future realised target cannot enter selection. Export the full
validation calendar, final release, each candidate loss and chosen configuration.
No additional windows, grids, forests, transformations or blend weights after scores.

## Evaluation, implementation and acceptance plan

Files: models/core_learning_r14.py (pure timing/features/fit/selection),
core_learning_experiment_r14.py (offline runner), test_core_learning_r14.py,
output/research_r14/core/ (forecasts, fit/selection evidence, scores, coverage).
All six plus bridge and naive references get common and own-coverage tables at
h1..12, full sample, recent targets>=2024 and recent origins>=2024. Report exact
core cumulative log errors as well as headline YoY, MAE,bias and coverage. Primary
pair gaps vs level, adaptation vs fixed, each vs bridge. Circular origin blocks12,
2000draws,seed1409 for annual squared-error differences; dependence is not removed.
Quarterly CNB and available1y survey comparisons are evaluation only, with explicit
definition and clock mismatch. No6m survey is invented from1y/3y forecasts.

- [ ] Write synthetic behavioural tests first and observe missing-module failure:
 future outcomes/features poisoning, delayed band-label eligibility, frozen older
 trend/seasonality, exact log reconstruction, sum-loss normalization, train-only
 scaling, six-option selection with unpublished errors poisoned, minimum history,
 deterministic ties, current origin independence from future history.
- [ ] Commit declaration before empirical fitting; then implement helpers and
 runner. Reuse source-hash-verified original bridge and retain all90 origins,
 including unavailable forecasts. Store predictions before scoring joins.
- [ ] Run focused tests; independently replay selected fits and selections, then
 appropriate existing regression tests. Refitting offline must reproduce payloads.
- [ ] Combine only the independently declared food/fuel primary models with fixed
 CORE_GAP_RIDGE_R14 and separately CORE_GAP_RF_R14. Also keep food+fuel with original
 core as a control. No ex-post winning-component cross product.
- [ ] Deliver results, code/source archive, limitations and an operating recommendation.

Scientific rationale: CNB WP9/2026 documents dynamic distributional learning and
tree extrapolation failure during2021--23; BoE BBIM2025 distinguishes its forecasting
exercise with fixed complexity from richer explanatory fits. This specification
is an original limited test informed by those lessons, not a replication claim.
