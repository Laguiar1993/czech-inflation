# R16 changing slopes and separately forecast cost signals — frozen plan

**Goal:** execute the user's approved follow-on to R15: damped core slopes, separate services/imported-goods transmission, and fixed combinations, while preserving nowcast h0 and all noncore paths.

**Architecture:** one small three-state core filter; two separate first-stage forecasts of broad annual services/goods inflation; chronological second-stage core residual regressions trained on saved first-stage forecasts. Use the same 90 outer origins and h0..12; compare against bridge, pipeline, current core, R15 FAST and R15 residual forest. Research-only, current-vintage historical inputs, no expectation/sentiment inputs or downloads. The user has approved this conceptual direction by saying Continue; routine choices below are declared before fitting. Existing isolated checkout and unrelated WIP are preserved; source hashes freeze the declaration without a sweeping commit.

**Tech stack:** existing offline Python/numpy/pandas/scikit-learn and R15 release gates, state snapshots, feature inputs and evaluator arithmetic. Tests precede numerical implementation. Use subagent-driven-development for the isolated numeric engine, followed by independent specification and code review; the parent builds the input/runner and independently assesses results.

## Exact experiment

### A. Damped local slope

Reuse each R15 origin's published core history through t-1 and its own frozen seasonal vector. Filter adjusted monthly log core with state (level,slope,temporary):

`F=[[1,phi,0],[0,phi,0],[0,0,0.8]]`, observation H=(1,0,1), R=1, Q=diag(.05,q_slope,.20).

Initialize level=mean(first12 adjusted observations), slope=0, temporary=0, covariance=diag(1,.01,1); update from observation13. Four fixed configurations phi=.8/.95 crossed with q_slope=.001/.01. Forecast t+h by h+1 transitions from last observation t-1 and add destination seasonality. No clipping, anchor or post-fit parameter changes. A changing slope plus oppositely signed decaying temporary component can create an internal reversal; this is an architectural capability, not a claim of skill.

Keep all four fixed paths. DAMPED_ADAPT_R16 selects one configuration for the entire h1..12 path using last36 common matured own-origin twelve-month forecast errors (mean of12 squared monthly log-core errors), min24 otherwise default p80_q001. All12 actual months must be published and earlier than t. Ties retain default then declared order. Whole-path selection avoids artificial quarter-by-quarter parameter switching.

### B. Two separately forecast signals

The ARAD broad goods/services inputs are annual NSA rates including first-round tax effects, not a monthly CNB core partition. Set z=100log(1+yoy/100), in annual log percentage points. Never infer monthly rates from annual rates or claim official component weights.

Build own-origin first-stage predictors from January2006 onward (broad history begins2003). Use released t-1 broad rates and their changes from t-4/t-13. All source series are the frozen R15 input files and paper-panel transformation/availability conventions, with the same corrected current-available futures treatment though futures are not included in these small first-stage groups.

Prefit clock clarification from independent review: before2010 the legacy synthetic _eve clock precedes the A6 panel's assumed cutoff by24hours and1minute. These additional signal-warmup origins use the actual A6 row t-1 cutoff as their decision clock. From2010 onward retain R15's saved clocks and assert the A6 cutoff does not exceed them. All90 outer clocks remain unchanged. Build broad publication dates across broad.index, not the shorter core index. Never backfill R15 states before their2010 start. For efficient computation a final-origin eligible outcome table may be cached, but every earlier fit and selection must additionally filter last_target<t and available_from<=its own clock before any preprocessing.

The phi=.8 slope variants share the temporary state's decay and therefore still have monotonic adjusted paths (a level plus a single .8-power term). The phi=.95 variants permit internal reversals. Retain both as a declared structural comparison, without suggesting every candidate can anticipate a turn.

- Services: current z, z minus3months earlier, z minus12months earlier, unemployment change3, ULC growth12, SA industrial production growth3.
- Goods: current z, changes3/12, import-price cost_26 mean3, industrial PPI cost_45 mean3, manufacturing PPI cost_47 mean3, FX3, metals cost_62 mean3. These names retain the frozen paper transform; coefficients are predictive, not structural causal pass-through.

For each group and band h1:3/4:6/7:9/10:12, forecast mean future z minus z(t-1). Separate ridge regressions use up to120 eligible monthly origins, min48. Drop constant/allmissing training columns; train-mean impute and scale. Include an explicitly penalized constant. Ridge objective is mean squared error +lambda*sum(coefficients squared), lambda=.1/1/10 (default1); solve with the equivalent alpha=n*lambda. Target stays in its original units. No coefficient sign constraints or hidden outcome winsorization. Record coefficients/means/scales and training dates. First-stage selection uses saved candidate forecasts and last36 common matured errors, min24, R15 tie/default rules.

Save the selected first-stage prediction at every origin, including warmup origins. Its projected future signal is observed z(t-1)+predicted change. Later model fits cannot revise a past selected projection. Observe maturity separately for both broad targets.

### C. Translating projected signals into core

Forecast the same mean band residual relative to **saved R15 FAST** at each own origin, using only saved selected first-stage predictions. Four small ridge variants with the identical lambdas/training/selection above:

- TRANSMISSION_OWN_R16: own core3-core12 acceleration only.
- TRANSMISSION_SERVICES_R16: own acceleration + projected services change divided12.
- TRANSMISSION_GOODS_R16: own acceleration + projected goods change divided12.
- TRANSMISSION_BOTH_R16: all three predictors.

Dividing annual log changes by12 is a predictor-unit normalization, not a conversion into observed monthly component inflation. Learned coefficients translate signals to monthly core residual units; they are not official basket shares. The second stage never trains on realised future services/goods in place of the projections that were actually made at its historical origins. All second-stage target months are core-published and precede the current origin; first-stage predictions already obey their own earlier clocks. Preserve NaN if a required first-stage prediction is unavailable; do not fabricate it from realised data. Training may impute individual ordinary predictor gaps, but rows with missing generated first-stage forecasts are not admitted to the corresponding second-stage model.

The band correction is constant within each three-month band. Keep this limitation explicit; do not claim a continuous structural system. BLEND_DAMPED_TRANSMISSION_R16 averages DAMPED_ADAPT and TRANSMISSION_BOTH monthly log forecasts, with fixed half weights.

### D. Roster and unchanged components

Ten new models: DAMPED_P80_Q001_R16, DAMPED_P80_Q010_R16, DAMPED_P95_Q001_R16, DAMPED_P95_Q010_R16, DAMPED_ADAPT_R16; the four TRANSMISSION variants; BLEND_DAMPED_TRANSMISSION_R16.

Five controls: INDEPENDENT_BRIDGE, STABLE_PIPELINE_R14B, STABLE_LOCAL_CORE_R14B, STATE_FAST_R15, RF_RESIDUAL_R15. Use the original frozen forecasts, not recalculated control fits. Replace only core in the stable pipeline h1..12; preserve all h0/noncore/weights. Primary accuracy comparisons use all15 common support, also show pairwise vs FAST and pipeline. Report any difference in support from R15's primary table.

## Evaluation and acceptance

Maintain R15's outcome definitions: headline annual CPI from same-origin monthly compounding; monthly/cumulative-log core; h1..12 per-horizon RMSE/MAE/bias, full and origin eras2019-21/2022-23/2024+, recent targets. CNB at both report/cutoff clocks, common quarter support, material absolute-error gains/losses >=.15pp. Headline direction threshold .25pp; underlying annualized SA core bands with >=.5pp adjacent changes and exact peak/trough hits/misses/false calls. Saved R15 seasonal factors are the common reference for all models. Twelve-origin blocks,2000draws seed1509; no unearned independence/significance claim or war exclusions. Include revisions without requiring actual outcomes and leave-one-CNB-report-out sensitivity across every report. Also score the first-stage signals on their own targets, to distinguish a weak first-stage forecast from a weak core mapping.

No learner, hyperparameter or blend is selected using CNB or outer results. These historical data have already supported many research rounds: chronological nesting is not an untouched holdout. FAST was chosen for this new baseline after R15; this fact remains explicit. Live vintage capture, policy measurement and trade calibration are outside this bounded experiment.

## Implementation tasks

- [ ] Numeric engine `models/core_slope_transmission_r16.py`; tests `tests/test_core_slope_transmission_r16.py`. APIs: slope_state(adjusted_history,origin,seasonal); ridge_fit(x,y,now,lambda_value); released_band_means(series,available,origins,origin,as_of,band); choose_slope(saved_paths,core_log,available,origin,as_of). Tests include independent matrix powers, a synthetic opposite-slope/temporary reversal, future poisoning, released-band maturity, penalized constant, train-only scale/drop/imputation, missing generated forecasts, deterministic config defaults/ties. Run failing tests before implementation, then all pass.
- [ ] Inputs `data/core_slope_transmission_r16.py` and chronological runner `path_slope_transmission_r16.py`; tests `tests/test_r16_inputs.py` and `tests/test_r16_runner.py`. Validate R15 hashes; build source-gated historical signal rows, first-stage predictions/selections then second-stage forecasts using saved projections; generate slope selection and fixed blends. Smoke2 origins in a new output directory, independently inspect maturity and component parity, then full run in output/research_r16. Export model inputs, all candidate forecasts, selected configs, fit diagnostics, labels, projection paths and source hashes; refuse overwrite.
- [ ] Isolated evaluator `tools/review/evaluate_r16.py` and tests `tests/test_r16_evaluation.py`. Reuse R15 pure scoring helpers with explicit roster arguments; do not modify frozen R15 source. Export full/paired/CNB/turn/revision/sensitivity/signal scoreboards and self-contained CNB replay adapted from original template. Verify quarter compounding, fixed support, generated-regressor timing and artifact data.
- [ ] Independent specification and code-quality review, including raw refits and at least one first-stage-to-second-stage lineage replay per band; fix implementation blockers before reporting. Preserve the declaration after its run hash is frozen.
- [ ] Fresh targeted test suite and final hashes, report `R16_RESULTS_2026-09-14.md`, update README/model map only with measured findings. Explain weak results and do not promote a hindsight-selected mixture. Preserve all original R15 and earlier outputs.
