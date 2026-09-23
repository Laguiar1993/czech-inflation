# R23: quarterly cost-gap corrections around an adaptive core trend

Declared before fitting/scoring R23. The user approved the R22 recommendation and explicitly prioritizes occasionally anticipating changes before CNB. This bounded experiment keeps the independent h0 and noncore blocks fixed and adds a dedicated CNB revision-lead assessment. No operating promotion is automatic.

## Design and alternatives

Use the existing FAST adaptive trend/cycle and **the identical saved R15 seasonal layer**. This avoids the R22 seasonal-comparison confound. Rather than another joint VAR forecasting all drivers, predict four future three-month average core errors from a few observed cost-to-consumer-price gaps. Quarterly training origins avoid treating repeated ULC readings as separate monthly labour observations. This is a quarterly direct cost equation producing monthly paths, not a full mixed-frequency state-space model and not an exact services/goods disaggregation.

Alternatives retained explicitly: (a) intercept-only correction on identical quarterly rows; (b) positive cost-coefficient ridge vs unrestricted ridge; (c) elastic net; (d) half-sized correction. A fully structural wage/productivity system is deferred: current frozen ULC consolidates both, and separate vintage-compatible compensation/productivity series are absent from this experiment. No raw retailer collection, new Bloomberg pull, survey input, forecast target anchor, or future commodity-price forecast is required.

Economic motivation: CNB's [price vertical discussion](https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/boxes-and-articles/Pricing-and-its-importance-for-monetary-policy-from-the-perspective-of-the-g3-model/) distinguishes domestic costs, imported costs and delayed price adjustment. The [ECB January 2025 Bulletin, pp39–40](https://www.ecb.europa.eu/pub/pdf/ecbu/eb202501.en.pdf) illustrates quarterly wage/productivity/input-cost equations. Our reduced-form proxies are not a replication or causal identification of either system.

## Frozen inputs and features

Use CNB monthly core in `tests/fixtures/cleanup/cnb_core_mm.csv`; raw A6 series11 unemployment,17 quarterly nominal ULC,26 import monthly changes,47 domestic manufactured PPI via the existing `load_raw`, and monthly EUR/CZK from `output/independent_path_frozen_inputs.csv`. Sources and publication rules are the same as R22, with current-vintage/reconstructed-availability limitations. Hash the raw inputs and adapters. Avoid the A6 full-sample transformed panel entirely.

At each saved R15 origin/clock, core is known only through t−1; all source values are individually masked by publication date before transformation. Monthly upstream and unemployment reference periods must be <=t−1; FX may include month t if released by the clock. Export every feature's reference period, last publication date and source quarter. Missing publication dates fail closed. No filling through unpublished endpoints.

Construct the core log-price level by cumulatively summing 100log(1+monthly core/100) minus that origin's saved R15 seasonal pattern. Chaining is strict across calendar months: an unavailable interior value breaks the chain. The arbitrary initial level cancels in the following gaps.

Five predictors, all oriented so a positive value hypothesizes upward price pressure:

1. `ulc_gap`: 100log(quarterly ULC index) minus mean core log-price level over that complete reference quarter, less the median of that real-cost ratio in the preceding12 complete consecutive quarters. Use the latest published quarter with complete core data. ULC stays quarterly: no bridge or interpolation.
2. `tightening`: minus the change in the published SA unemployment rate over12 reference months, using the latest permitted month and its exact year-earlier endpoint.
3. `import_gap`: reconstruct the log import-price level from published monthly percent changes. Subtract the same-month core log-price level; subtract the median relative level in the preceding36 complete consecutive months. Use the latest permitted paired month.
4. `ppi_gap`: same36-month relative-price gap using manufactured PPI log levels.
5. `fx_news`: 100log(EUR/CZK_latest/EUR/CZK_import_reference_month), with both endpoints published. This measures FX news since the latest import-cost measurement, not a projection of future FX.

These ratios are statistical cost-pressure proxies: whole-economy ULC and broad imports/PPI are not exact marginal costs of the CNB core basket. Their rolling medians are backward-looking reference levels, not estimated equilibrium markups. Missing required consecutive history yields missing features. Every family uses the same complete-feature training origins so differences isolate additional predictors. The current prediction fails back to unchanged FAST when its required input/history is missing; retain the original scoring support and report that fallback.

## Target, estimation and nested selection

Use one historical forecast origin per calendar quarter (March,June,September,December) from the saved R15 state archive. At each such origin freeze all five features and the original FAST log-core predictions. Four targets are the average actual-minus-FAST log-core residual in h1:3,h4:6,h7:9,h10:12. A training origin is eligible only when its entire h1:12 target has ended strictly before the decision origin and all12 detailed CPI publications are available. This deliberately uses identical rows across four output equations. The four outcomes are not four independent quarters of labour information.

Outer fitting uses the last40 eligible quarterly origins, minimum24. Each band has an intercept and its predictor coefficients. Center and scale predictors from that fit's training data only, floor constant-column scale at1. No target scaling or imputation. Minimize mean squared error plus alpha times squared standardized coefficients, including the intercept. For positive fits constrain predictor coefficients >=0; intercept is unrestricted but penalized. This is a predictive shape restriction to test, not an ex-post sign repair.

Nested selection at each outer origin: among its fully matured training origins, validate on the latest8 for which at least16 strictly earlier, fully12-month-matured quarterly training origins existed at that validation origin's own clock. Inner training uses at most40 rows and its own scaler. Score the four cumulative core residual errors (3*cumsum of band errors), average their squared losses across validation origins. Require at least4 usable validation origins; otherwise fixed defaults below. Never use the outer realised error to choose a setting. Ties favor stronger regularization.

Ridge alphas {.1,1,10}, default1. Elastic net uses l1_ratio=.5, alphas {.01,.1,1}, default.1, max_iter50000,tol1e−8; convergence failures surface. Explicit constant is penalized; sklearn has fit_intercept=False. Positive ridge solves bounded augmented least squares; free ridge solves the same objective without bounds. Export all candidate losses, inner training dates/publication maxima, selected setting and outer coefficients.

Seven candidates:

- GAP_CALIBRATION_R23: intercept only on common quarterly rows; fixed alpha1.
- GAP_DOMESTIC_R23: positive ridge on ulc_gap,tightening.
- GAP_IMPORTED_R23: positive ridge on import_gap,ppi_gap,fx_news.
- GAP_JOINT_R23: positive ridge on all five.
- GAP_FREE_R23: unrestricted ridge on all five.
- GAP_ENET_R23: unrestricted elastic net on all five.
- GAP_HALF_R23: half the GAP_JOINT monthly log-core correction around FAST.

Convert four band-average corrections into12 monthly corrections with fixed linear interpolation at band centers2,5,8,11, constant extrapolation at endpoints, then solve the4x4 band-mean mapping so each resulting three-month mean exactly equals its fitted target. This smooths transitions without changing cumulative corrections at h3/6/9/12. Add to original FAST log rates and convert back to simple monthly rates. No new seasonality, repeated current nowcast shock or horizon reindexing. No clipping of adverse forecasts; nonfinite values fail visibly.

## Evaluation and the user's CNB objective

Preserve the original90 origins, h0–h12 and969 primary headline keys. Controls: FAST,current core,gentle slope,R21 core error feedback. Reuse full/recent headline/core scoreboards, both CNB clocks, materiality .15pp, report omissions, fixed-support bootstrap, strict underlying turns and false/sustained signals. Use coefficients to reconcile the monthly correction exactly; they are predictive contributions, not causal shocks.

Add a **fixed, separate CNB lead test**, never a model input/selector. For every available current CNB report, compare its quarterly forecast with our already frozen model path at that clock. Join the immediately next report's forecast for the identical target quarter; require the target quarter to be strictly after the next report's calendar quarter, so the next observation is still a forecast. Keep both clocks and missing-pair coverage. A call requires |model−current CNB|>=.30pp (also report predeclared .50 sensitivity). A confirming CNB revision has the same sign and reduces its distance to the original model forecast by at least .15pp. Record revision direction agreement separately, including overshoot cases. Eventual success also requires model absolute error at least .15pp below the original CNB forecast; count material losses and unconfirmed calls.

Score every eligible call, not only large realised errors. Report all pairs and an episode table that retains only the first call in a consecutive same-direction report streak for each model,target quarter and clock. A missing/non-call report or sign change resets the streak. This avoids counting the same signal repeatedly; adjacent target quarters can still share one inflation shock. Show representative hits and failures without using the cases to tune models. Leading CNB revisions is not proof of causal anticipation: CNB subsequently observes additional news. A model's eventual accuracy and future CNB movement are distinct outcomes.

## Implementation plan and acceptance

1. Add tests first: unpublished-feature poison invariance; strict quarterly and monthly gap construction; missing endpoints; quarterly training/date gating including inner folds; band-average-preserving interpolation; constrained-coefficient signs; future-label poison; next-report/target-quarter joining, all-call denominator and episode deduplication.
2. Implement `data/cost_gaps_r23.py`, `models/cost_gaps_r23.py`, `tools/research_r23/run.py` and `tools/research_r23/evaluate.py`. Keep prior numeric sources unchanged. Verify original FAST state paths equal saved native core before substitution.
3. Export feature snapshots/provenance, targets/date gates, inner selection records, fit diagnostics and all seven forecasts. Run the fixed batch once after correctness tests.
4. Run existing evaluator plus CNB lead tables and fixed-support bootstrap. Independently review code, source timing, coefficients/accounting and lead cases before interpreting winners.
5. Produce R23 results, CNB-style replay, charts and `HANDOFF_TO_CLAUDE_R23_2026-09-16.md` in this repo root. Include exact run commands, directory map, model status, negative findings and research questions. Hash sources/outputs and verify earlier deliveries unchanged. Research improvements do not automatically establish live superiority or a rates-trading strategy.

Self-review: user objective and existing authorization are sufficient to execute; no new permission gate. Seven declared candidates, fixed thresholds, fixed support, explicit post-R22 research lineage. Quarterly data remain quarterly. No claim that this implements the separately deferred wage/productivity measurement system.
