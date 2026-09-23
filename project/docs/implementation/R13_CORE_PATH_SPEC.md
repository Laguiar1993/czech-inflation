# R13 independent core path prespecification and implementation plan

Declaration prepared 9 September 2026 before candidate fits. Parent must commit
this declaration before empirical estimation. Four primary candidates plus one
matched two-series labour diagnostic; no parameter
search, no post-result tuning, no promotion from historical score selection.

## Goal and boundaries

Test aggregate versus the existing five service categories plus reconciliation
remainder, crossed with monthly versus cumulative CORE targets. Preserve the
independent component bridge, HARD_BASE h0, every noncore contribution and every
destination weight. No food/energy experiments, retailer collection, expectations,
surveys, CNB forecasts as predictors, global wage interpolation, or new live input.
CNB comparison and shared-shock interpretation are separate parent work.

Models, in fixed reporting order:

1. CORE_AGG_MONTHLY_R13
2. CORE_AGG_CUMULATIVE_R13
3. CORE_SPLIT_MONTHLY_R13
4. CORE_SPLIT_CUMULATIVE_R13

Separate bounded labour diagnostic: CORE_AGG_CUMULATIVE_LABOUR_R13 and
CORE_AGG_CUMULATIVE_LABOUR_CONTROL_R13. These use identical labour-eligible
training dates and outer forecast coverage, and compare inclusion/exclusion of
the one declared unemployment predictor. They do not change the main factorial.

Historical references are INDEPENDENT_BRIDGE, RF_U_FX, BVAR_U_FX, NAIVE, and
LAST_YOY_RW, retaining the latter's distinct native h0. Forecast origins are the
same 90 February 2019 through July 2026 saved release-eve clocks. h0=t, h12=t+12.

## Exact component definition and selected arithmetic target

Use original CNB core m/m percentage c[m] and raw CZSO category m/m percentages
g[j,m]=100*(level[j,m]/level[j,m-1]-1). At each actual outer origin t obtain the
five basket fractions w[j,t] through data.core_split.weights_at and the solved
origin core fraction W[t] from independent_nowcast_forecasts.csv. Verify W[t]
equals the original bridge's current origin weight (solve_weights replay checks
this). Reconstruct the ENTIRE historical target panel at those same outer-origin
weights, never a precomputed remainder from changing historical basket regimes:

    R[t,m] = W[t]*c[m] - sum_j(w[j,t]*g[j,m]).

R is a headline percentage-point reconciliation projection, not a price rate or
an independently measured economic component. Category groups are actual_rent,
imputed_rent, catering, accommodation, package_holidays. Their weights are base
expenditure fractions, not price-updated official contributions; the residual
also reconciles raw tax-inclusive groups to the narrower CNB core concept.
Require every group and core observation finite on the same historical calendar.
The aggregate control uses exactly this detailed-data calendar.

For each pseudo-origin r and horizon h=1..12, fit either y[r+h] (monthly) or
mean(y[r+1],...,y[r+h]) (cumulative) for c and each category/remainder. The latter
prediction is multiplied by h to obtain the cumulative SUM of arithmetic monthly
percentage rates C[h]; recover monthly rate yhat[h]=C[h]-C[h-1], C[0]=0.
h0 is excluded from these targets and is supplied HARD_BASE for headline.

This preserves the exact linear category/remainder identity in both monthly and
cumulative target units, and gives identical h1 fits. Arithmetic cumulative sums
are a first-order approximation to log cumulative price changes, not compounded
component inflation. We deliberately do not exponentiate the remainder as though
it were a price index. This is the single selected coherent target design; no
alternative log-target model will be fitted after seeing these scores.

Recombine category forecasts into core m/m as
    chat[h] = (sum_j(w[j,t]*ghat[j,h]) + Rhat[h]) / W[t].
For both aggregate and split replace ONLY original bridge value_core[h] and
contribution_core[h]=weight_core[h]*chat[h]; headline is the sum of this new core
contribution and the original noncore contributions. Original bridge destination
weights may differ from W[t] when a future basket was already published. Preserve
that policy exactly; category projection weights remain fixed at origin t.
Exact headline gross factors are then multiplied with the released pre-origin
history and HARD_BASE h0. No realised post-origin value may enter a forecast.

## Single frozen predictor block, timing, and units

Every group and aggregate use three own lags y[r-1], y[r-2], y[r-12], the same
two external predictors (imports and FX) below, and 11 destination-month dummies for r+h,
February through December (January omitted). Each h has its own fit. The monthly
and cumulative models at that h have IDENTICAL X and training row masks, so target
averaging is the only target-factor change. For fixed h a complete set of
destination calendar dummies also represents the calendar pattern of its full
cumulative window. No destination economic observation is a predictor.

External predictors are fixed once, with no interactions or alternative spans.
Unemployment is used only in the separate aggregate cumulative labour diagnostic:

| Exact model column | Frozen source | Transformation and units | Availability |
|---|---|---|---|
| import_mm_l3 | cleanup/core_features.csv import_l2[r-1] | import-price arithmetic m/m percentage at source r-3; loader index minus 100 | reconstructed day 16 of source+2 (r-1), from existing import_l2 rule; require <= pseudo-origin and outer clock |
| eurczk_mm_l1 | cleanup/core_features.csv eurczk_mm[r-1] | arithmetic monthly percent change of monthly-average CZK per EUR; positive is CZK depreciation | start of source+1 (=r), from existing full-month FX rule; require <= both clocks |
| unemployment_rate_l3 | data/vintages/unemployment.csv.gz | exact reference r-3 unemployment %, total age 15-64; latest released SA/trend-cycle as officially published at the pseudo-origin | actual archived available_from <= pseudo-origin and outer clock; retain adjustment/provenance; never backdate a later revision |

Monthly FX/import values remain the latest stored statistical history with
reconstructed availability, not full historical vintages. Source mapping is
verified against the existing assemble_feature_frames/loader definitions and
written with exact row/source month and release timestamps to an audit table.
The declared archived labour policy has an official SA-to-trend-cycle transition;
we carry the adjustment label rather than silently claim a homogeneous SA series.
No latest unemployment snapshot fallback. No wage feature exists in the frozen
core frame, and the legacy Chow-Lin wage interpolation uses future information;
therefore wages are explicitly excluded. Unsupported columns are rejected.

For each historical pseudo-origin use path_experiment._eve(r), overridden by the
saved clock when r belongs to the 90 outer origins. Select labour at that clock,
not the later outer-origin vintage. CPI own-lag observations must be released by
both clocks. Detailed component outcomes use core_split_experiment.publication_dates
(historical fallback day 20, 09:00 before the sourced calendar). Unknown releases
are unavailable. Training requires the complete h-window of all category/core
outcomes released by the outer cutoff and each month <=t-1 even for monthly models.
This stricter common label mask makes monthly/cumulative and aggregate/split
comparisons fair. No filling missing targets or predictors.

## Fixed estimator and coverage

Expanding training calendar, minimum 48 complete pseudo-origin rows. All models
and groups at h share an intersection mask across their own lags, the two
primary external predictors, and all h-window labels. Ridge objective is mean squared
error plus 1.0*sum(beta^2), with unpenalised intercept. Center and standardize all
predictors on this eligible training slice only (population SD, constant column
scale=1, including floating-point constant detection). Center target by its
training mean; fit closed-form ridge and add the mean. No clipping, capping,
post-fit rescaling, fallback prior, alpha/window search or tuning from errors.

Missing current predictors, invalid weights or too few rows return explicit
unavailable predictions with reason. Missing original noncore contributions
remain missing. Cumulative monthly h requires finite C[h] and C[h-1]; do not
skip failed cumulative horizons. All 90 origins and every model/horizon survive
into output including initial missing forecasts. Detailed category rates start
2015-02; therefore initial candidate history will be unavailable, especially at
longer horizons. The separate labour pair additionally requires archived labour,
first published March 2018, at each historical pseudo-origin and current origin;
both labour series require the same available current labour observation even
though the control does not include its value as a predictor. This prevents a
late-coverage change from masquerading as labour predictor value. Report
the first finite origin, n_train, training start/end and final label/release per
fit, intended origins, available outcomes, finite predictions and common counts.

## Scoring and interpretation

Save predictions and diagnostics before joining realised scoring outcomes.
Reuse R12 scoring arithmetic for exact headline monthly and annual percentages
and cumulative future log price change h1..h. Show all h1..12 for full origins,
recent targets >=2024-01, and recent origins >=2024-01. Report common roster
panels (primary four plus references, excluding the labour pair), pairwise bridge
panels, each model's own coverage and matched factorial
pairs (aggregate/split within target and monthly/cumulative within partition).
Also score core monthly and cumulative arithmetic targets to distinguish core
signal from headline error cancellation; use the same common primary candidate
panel, and a separate common labour diagnostic panel. Report the divergence of
arithmetic cumulative core sums from exact compounded core percentage changes,
including largest observed/forecast differences, without adding another model.

Paired annual squared-error differences: circular origin block bootstrap length
12, 2,000 replicates, seed 1309, 95% percentile intervals. Report bridge and
matched factorial pair comparisons with N and no independent-row claim.
Repeated historical inspection and overlapping outcomes preclude fresh holdout
evidence. Judge economic plausibility, bias, coverage, large misses and panels
together; unanticipated shared war/oil shocks are not by themselves evidence
that the core mechanism is weak. No automatic promotion; prospective evidence
is still required. Parent separately diagnoses CNB/shared shocks.

## Files, tests, execution and verification plan

Architecture: pure target/timing/fit functions in models/core_path_r13.py; frozen
loading, bridge reuse checks, output and scoring in core_path_experiment_r13.py;
behavioural tests in test_core_path_r13.py. Only those new files, this declaration,
and output/research_r13/core_path/ are owned by this experiment. Existing files
remain untouched. Python/numpy/pandas, existing local frozen fixture adapters.

- [ ] Write tests first and record the expected missing-module failure before
  adding model code. Test delayed complete-window eligibility; future-label,
  future feature and future labour-vintage poisoning; exact h1 equivalence;
  arithmetic cumulative reconstruction; destination calendar; origin weights;
  exact noncore/HARD_BASE preservation including NaNs; no fallback coverage;
  train-only scale; unsupported feature rejection; historical labour release
  selection with adjustment metadata; common-sample scoring.
- [ ] Parent commits declaration and sends declaration-committed confirmation.
  No empirical candidate fit until that message.
- [ ] Implement pure helpers against synthetic tests. Implement runner with
  offline inputs and source/hash checks, replay original bridge through existing
  R12 verify_baseline (short unchanged food X13 reused as already documented).
- [ ] Run test_core_path_r13.py and existing R12 path/core split/timing tests.
  Python command: python -m pytest -q test_core_path_r13.py
- [ ] Run python core_path_experiment_r13.py; preserve every candidate and failed
  row, fit audits, predictor source audit, baseline checks, scores and uncertainty.
- [ ] Run python core_path_experiment_r13.py --verify for full offline refitting
  with network/database calls blocked and deterministic output comparison. Hash
  all consumed source files, new code, spec, package versions and output payloads.
  Avoid timestamps/output path in deterministic payloads. Manifest may timestamp
  the run separately. Parent performs commits and overall report.
