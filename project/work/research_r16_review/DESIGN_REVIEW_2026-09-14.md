# R16 independent specification and source-timing review

This review is read-only with respect to model, data, output and specification files. Evidence is written only in `work/research_r16_review`. No forecast score was inspected to change a model, penalty, selection rule or blend.

## Prefit assessment

The approved architecture is internally coherent: a three-state damped-slope filter can express a changing slope and an oppositely signed decaying temporary component; two distinct broad annual-rate forecasters can supply chronological generated regressors to a monthly-core residual learner. Neither architecture establishes causal shock identification or turning-point skill.

The critical generated-regressor rule is that each historical second-stage row uses the first-stage forecast selected at that row's own historical origin. Later first-stage refits must not replace historical projections. Second-stage training eligibility depends on all core target months being released and earlier than the current origin. It does not additionally require the future broad outcomes to have matured at the original forecast origin, because the inputs there are forecasts, not those outcomes. Required missing generated forecasts must exclude a training row and yield an unavailable current forecast; ordinary raw-input gaps may use training-only imputation. A whole-history cache of raw band outcomes is safe only if every actual fit and configuration selector filters release date and last target using its own decision clock.

Whole-path slope selection must average the twelve squared monthly-log errors for each historical path, then select using the last 36 common matured paths with 24 required. Squaring an averaged twelve-month error would instead allow cancellation and violate the specification. Keeping one selected configuration across all twelve horizons avoids band-switching artifacts. h1 requires two state transitions after the t−1 observation; h12 requires thirteen.

## Timing correction identified before fitting

The new January 2006 first-stage warmup exposes a difference between two legacy fallback clocks. `path_experiment._eve(t)` is next-month day 7 at 23:59 before the release calendar begins in 2010. The consumed A6 panel's `release_eves` puts row t−1 at next-month day 9 at 00:00. The panel clock therefore exceeds the generic fallback by 24 hours and one minute. This did not affect R15's usable state calendar, which begins January 2010.

The parent accepted a prefit clarification: use the A6 t−1 cutoff as the pre-2010 first-stage decision clock; from 2010 onward retain R15's own clocks and assert A6 cutoff is no later. The 90 scored origins remain unchanged. Broad publication dates must be constructed over the broad-series index independently of the monthly-core index, because the latter begins in January 2007 and would otherwise truncate broad history. No raw-series change is required.

Independent checks in `audit_inputs.py` verify all 38 R15 input/code/output hashes; 336 selected-source observations across the 48 warmup origins reconstruct the frozen panel exactly. All 48 broad t−1 observations are available under their stated next-month day-20 09:00 historical proxy before the corrected origin clock. None of the 336 selected raw source observations actually falls inside the clock discrepancy, so the defect is a declared information-set inconsistency rather than a measured value difference in these selected columns. The clock should still be corrected before fitting.

Evidence: `r15_integrity.csv`, `warmup_clocks.csv`, `warmup_raw_lineage.csv`, `input_summary.json`. The initial audit import hit an existing filesystem restriction on a runtime dependency; the independent pre-2010 clock formulas avoid importing unrelated model packages. The successful source reconstruction is recorded in the JSON summary.

## Source concepts and inherited limits

The frozen ARAD metadata identifies 283 contiguous annual-rate observations for each broad series, January 2003–July 2026. Goods are other tradables excluding food and fuel; services are nontradables excluding regulated prices. Both are NSA and include first-round tax effects. These are neither all-goods/all-services headline series nor an exact partition of tax-corrected monthly CNB core. Using `100*log(1+yoy/100)` preserves an annual log-percentage-point target. Dividing a projected annual-log change by twelve merely rescales a predictor; learned coefficients are not official component weights.

The first-stage FX fixture begins January 2007. Its earlier missing values must remain missing. Import-price A6 row 26 begins in March 2008, and earlier gaps likewise remain ordinary missing predictors. R15 states and own-core features begin January 2010, so the independent first stage must construct its own earlier features without backfilling R15 states.

The consumed ULC source is `bbg__nominal_ulc_quarterly__as_reported`, T0, the quarterly NSA index level. The twelve-snapshot log change is consistent with that concept; a different panel carrying an annual growth rate could not be substituted. IP uses its existing SA level and snapshot change. Cost rows retain their frozen log-difference transforms. Three-row cost averages can contain repeated source months, and snapshot changes need not span three or twelve distinct reference-period observations. Describe these as changes/averages of available snapshots, not newly identified distributed economic lags.

The data remain current-vintage histories with reconstructed historical publication gates. No live vintage claim is supported. The source notes and prefit declaration appropriately retain this limitation. Corrected futures are not used by the small first-stage groups, so their inherited correction cannot improve R16 transmission merely by entering unnoticed.

## Initial engine review

The first source pass over `models/core_slope_transmission_r16.py` finds the declared transition and innovation matrices, initialization, h+1 forecast transitions, train-only standardization/imputation, penalized constant with n*lambda, and original target units. The whole-path selector averages twelve squared monthly errors and requires all twelve finite forecasts for every configuration on common matured origins. No arithmetic or selector blocker was found in this source pass. Missing generated-forecast exclusion belongs to the runner rather than the generic ridge function.

One interpretation limit follows directly from the declared model, without observing scores: when phi equals the temporary damping 0.8, the seasonally adjusted expectation is `level + 4*slope + 0.8^k*(cycle - 4*slope)`. These two fixed configurations are monotonic. The phi=0.95 configurations provide the family's capacity for a reversal. This is a limitation to report, not a reason to change a declared parameter after fitting.

The independent first-stage input reconstruction in `first_stage_predictor_reference.csv` contains 494 group/origin rows across January 2006–July 2026, and was built before reading the R16 runner. Runner, smoke lineage and direct-refit checks remain to be completed before authorizing the full fit.

## Runner and smoke audit

The runner constructs every first-stage historical prediction once, then supplies those stored selected changes to the corresponding second-stage rows. Its stage-two builder removes required missing generated predictors before selecting the last 120 training rows. A current origin whose generated prediction is absent returns an unavailable forecast. The reviewer also identified a theoretical case where an unavailable current broad level could still permit an imputed first-stage change; the parent added a current-level gate and a regression test before the successful smoke. Actual frozen t−1 broad levels are all available, so this hardening changes no selected input in this run.

The successful `output/research_r16_smoke` contains two scored origins. Fresh reviewer execution of `audit_run.py` found no blocker to the full fit:

- All 59 recorded input/code/output hashes match.
- All 3,048 ridge configuration selections and both whole-path slope selections match independently reconstructed raw targets and delayed validation calendars. Maximum loss difference is 6.94e−18.
- First-stage predictors match the prebuilt independent reference to 3.47e−18; every raw target label and generated second-stage predictor match exactly.
- All 444 saved fixed slope paths independently reproduce using raw core, own-origin R15 seasonal factors, a Joseph-form covariance update and matrix-power forecasts. Maximum path difference is 2.22e−16 monthly-log percentage points.
- Twenty direct scikit-learn Ridge refits rebuild training eligibility, the last 120 rows, means, imputation, scales and penalized constant without importing the R16 engine/runner. These include one complete first-stage-to-second-stage historical lineage replay per band, plus the current first-stage refits. Maximum forecast difference is 7.14e−15.
- All 260 native rows preserve h0, noncore inputs/contributions and weights exactly; the fixed half-weight blend is exact.

At the first scored origin, February 2019, TRANSMISSION_BOTH has 103/97/91/85 eligible training origins across the four bands. Their first training origins are April/July/October 2010 and January 2011; their latest training origins are October/July/April/January 2018. All latest core training targets are January 2019, preceding the scored origin. Each replayed first-stage fit uses 120 eligible rows. Thus the explicit generated-prediction warmup leaves adequate second-stage coverage without inventing early projections.

The first lineage illustrates the clock separation. The February 2019 h1–3 core fit consumes the services/goods projections saved at October 2018, its last eligible training origin. Rebuilding those projections at the October 2018 clock uses first-stage training only through June 2018, rather than refitting them using the February 2019 information set. The other bands reproduce the corresponding longer maturity delays.

Reviewer command (successful, with no R16 source edits):

```powershell
$env:PYTHONPATH='../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r16_review/audit_run.py output/research_r16_smoke
```

Evidence is in `research_r16_smoke/summary.json`, `research_r16_smoke/independent_refits.csv` and `research_r16_smoke/integrity.csv`. A fresh independent numeric test command also passed all 52 engine tests; parent-run feature/runner checks are separate. No accuracy table was used to select or alter parameters during this audit. Full-run verification remains pending.

## Completed full-run audit

The completed `output/research_r16` numerical run passes the same independent audit, extended to every recorded fit calendar and native path. No forecasting arithmetic, source timing, generated-regressor lineage or component-preservation blocker was found. This verdict covers the numerical experiment and its ledgers; the dedicated evaluator, score interpretation and HTML artifact remain separately reviewed work.

All 59 recorded hashes match. Every one of 5,160 ridge configuration selections and 90 whole-path slope selections matches independent reconstruction from raw outcomes and release clocks. Every one of the 5,160 selected-fit training calendars and its recorded count agrees with the last 120 eligible design rows. Maximum selection-loss difference is 1.67e−16. Raw target labels and generated second-stage designs match exactly; the maximum first-stage input difference is 3.47e−18.

All 796 fixed slope paths (199 origins × four configurations) independently reproduce within 8.88e−16 monthly-log percentage points. All new native core paths reconcile to the actual selected configuration and own-origin saved FAST baseline. Monthly simple/log conversion and the half-weight blend are exact. All 11,700 native rows preserve h0, noncore inputs/contributions and weights exactly.

Twenty direct scikit-learn Ridge refits include four complete generated-regressor lineage replays across distinct eras:

| Second-stage origin | Band | Core training rows | Last core training origin | First-stage training through at that historical origin |
|---|---|---:|---|---|
| 2019-02 | h1–3 | 103 | 2018-10 | 2018-06 |
| 2022-06 | h4–6 | 120 | 2021-11 | 2021-04 |
| 2024-06 | h7–9 | 120 | 2023-08 | 2022-10 |
| 2026-07 | h10–12 | 120 | 2025-06 | 2024-05 |

For every row, both services and goods projections were independently refitted at the final historical training origin's own earlier clock, and those saved predictions were traced into the second-stage fit. The current-origin first-stage predictions were also refitted. Maximum forecast difference is 7.11e−15 in the respective target's log-percentage-point units. These refits reproduce training means, scales, coefficients and the explicitly penalized constant, not merely the final forecast.

The full-run prefix is exactly equal to the successful smoke: 240 core predictions, 1,272 selected first-stage projections, 9,144 candidate forecasts, and all 111 smoke slope-state objects are unchanged. Later information did not rewrite the earlier predictions.

Evidence: `research_r16/summary.json`, `research_r16/independent_refits.csv`, `research_r16/integrity.csv`. The reproducible independent audit is `audit_run.py` with `reference_helpers.py`; neither imports the R16 engine or runner. It consumes only the frozen experiment and source files and writes reviewer evidence. The source-input audit and reference predictor table are preserved alongside it. No parameter, model forecast, original output or evaluator definition was changed by this reviewer.
