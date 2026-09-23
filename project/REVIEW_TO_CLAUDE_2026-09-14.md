**Czech CPI forecasting — independent review, 14 September 2026**

The project contains a useful independent nowcast and several credible path experiments. The recent results deserve further work. They do not yet establish a dependable survey-beating nowcast or a generally superior alternative to the CNB forecast. My strongest path candidates for further testing are the bridge with current core and the plain QRF mean. TVW3 does not inherit the QRF mean's good results.

This review reads `HANDOFF_TO_CODEX_2026-09-14.md` and the active checkout on `codex/independent-cpi-20260909`, HEAD `709d4b3`, including its uncommitted work. I have preserved the existing forecasting code and outputs. New evidence, scripts, and the rebuilt local artifact are in `work/review_20260914/`. The detailed nowcast and forest reviews are in its `nowcast/REVIEW.md` and `forest/AUDIT.md` subfolders. File and line references below refer to this checkout.

The published Claude URL required a login. I audited its saved source and rebuilt the local HTML byte for byte. I cannot verify that the inaccessible remote page is identical to the local file.

**What independently checks out.** Every stored nowcast scoreboard metric reproduces across 900 rows, ten models, and 90 first releases. The survey actuals, medians and first-release dates reconcile, including the switch from regular releases to flash. I independently re-compounded 30,420 path values; the maximum discrepancy was 1.42e-14 percentage points. The artifact builder reproduces 2,184 scored forest months to 7.11e-15, and its resulting HTML is byte-identical to the saved file. The artifact currently uses object (a), the earlier models' own month-zero forecasts. It does not use realised month-zero inflation for those lines. The main bridge/forest paths use HARD_BASE at month zero.

The code correctly prevents outer-origin future CPI labels from entering the checked ridge, weight and forest training arrays. Those findings are narrower than a claim of fully historical-vintage, prospective validity. Several source histories are revised, release times are partly reconstructed, and the model choices were made after seeing these periods.

**Scope decision, 14 September:** the user explicitly excluded the intraday basket-publication-hour issue. It is not a required correction or a blocker. Existing release-eve scores are unaffected. Retain the historical evidence for reference; focus implementation on the remaining findings below.

**Remaining corrections, in priority order.**

1. **Make the realtime transform policy fixed and independent of future observations.** `tools/paper_replication/build_paper_panel.py:217–220,376–378` decides between log differences and simple differences by asking whether the entire supplied series ever becomes nonpositive. Adding a negative observation years later changes earlier realtime feature values. The test changes a 2007 feature using only a 2012 observation. Declare each row's transformation in the input catalog, and fail or apply a prospectively specified exception when its domain is violated. Do not change all earlier transformations automatically. The current evaluated sample is not demonstrated to be materially contaminated by this defect: the problematic nonpositive histories presently start before the first scored origins. It is nevertheless an important future-update failure. Add a raw-data prefix-invariance test.

2. **Correct what the TVW internal validation represents.** `models/paper_tvwqrf.py:107–118` holds out the last 12 direct training pairs without a horizon embargo. At outer edge December 2023, an h12 validation prediction for feature origin January 2022 trains on outcomes through December 2022. Those outcomes were unavailable at that validation origin. In addition, `models/paper_big.py:362–367` imputes using all outer training rows before the holdout split, so validation features influence imputed earlier training features.

   All these observations are known by the final outer forecast date. Thus this is **not** evidence that December 2023 forecasts use 2024 outcomes. It is a defect in interpreting the calibration forecasts as historical out-of-sample predictions. Prefer saved prior-origin quantiles: produce them with that origin's available data and preprocessing, then fit weights only after their target outcomes mature. A cheaper fixed-block validation needs an embargo through the first validation origin and an imputer fit only on that training slice. Preserve the QRF mean as a control.

   I tested causal reweighting using saved origin forecasts. Effects are mixed and modest, not a wholesale collapse. Corrected FULL path RMSE at h3/h6/h9/h12 is 2.014/2.981/4.160/5.515 versus bridge 1.537/2.516/3.922/5.395. FULL plus month also still fails the necessary h6/h12 promotion conditions. The calendar-month version's QRF mean is unaffected by changes to TVW weight fitting. Detailed comparisons and sample counts are in `forest/causal_reweight_scores.csv` and `forest/causal_reweight_path_scores.csv`.

3. **Qualify the paper-replication claim.** `paper_tvwqrf_experiment.py:141–157` deliberately gives `_TMH` benchmarks outcome history only through t−h and makes a 2h-step forecast of t+h. The forest uses X_t and eligible labels through t. Matching published RMSEs with those different cutoffs is a numerical diagnostic, not verification of a common-information experiment. The specification itself acknowledges this at `PAPER_TVWQRF_SPEC_2026-09-12.md:413`. The paper's timing prose is ambiguous; request the authors' code before asserting its exact protocol. Do not infer an author error solely from the table.

   The four saved TVW3 monthly RMSEs do reproduce: 0.706783/0.694749/0.713808/0.649849. They pass the project's declared ±0.05 tolerance, while the declared weighting-gain condition fails. Describe this as an approximate implementation with numerical agreement on those cells. Also correct the statement that all other models are within about 0.03: the h12 median differs by about 0.054 and mean by 0.040. Finally, `yoy6()` at `paper_tvwqrf_experiment.py:196–215` combines six h6 forecasts from six different origins. Its 2.083 RMSE does not evaluate a single-origin h1–h6 path. The separate path scorer uses the correct same-origin construction.

4. **Separate a detected large event from a correct, useful surprise call.** `independent_nowcast_experiment.py:59–62` counts `alert & big`, regardless of direction. October 2022 is one such magnitude hit even though the model predicted 1.173, consensus was 0.9 and actual was −1.4. Keep the magnitude statistic if useful, but add directional hits and material-gain hits; never describe all magnitude hits as successful calls. Precision computed inside the realised-big frame is tautological. Measure alert precision on all eligible releases. Use the same numerical tolerance around 0.4 in every scoring script.

5. **Repair the reproducibility chain without undoing the NFC data fix.** The direct R14B integration manifest verifies. Its transitive import-history manifest does not: `data/research_r14b/imports/manifest.json` contains the earlier hash of `data/local_adapter.py`. The file now includes the valid NFC total-versus-maturity-buckets correction. `test_core_history_extension_r14.py::test_extension_fingerprints_include_its_separate_design_declaration` fails at the manifest guard. This is a replay blockage, not evidence that the archived import values are wrong. Preserve the original manifest and inputs, document the source change, and issue a new verification receipt after proving the import-producing calculation is unchanged. Do not merely replace old hashes to obtain a green test.

6. **Distinguish historical reconstruction from an archived live forecast in the artifact.** `tools/cnb_rounds/cnb_rounds_template.html:442` says the path run was “made” at its historical decision clock. These are models developed and replayed in 2026, using current-vintage histories. Replace this with “historical replay; simulated information cutoff”, and display actual generation date separately. Likewise, replace “we saw the 2022 surge earlier” with “this retrospective model specification predicts a higher 2022 path”. The handoff's rule requiring a path “already published” before the CNB report cannot be satisfied by these reconstructions. They still provide useful pseudo-out-of-sample evidence.

The artifact's automatic object-(b) fallback at `tools/cnb_rounds/build_cnb_rounds.py:93–94` is not active now. Remove that automatic switch from any live-comparison product: insufficient object-(a) coverage should leave a model unscored or place it on a separate conditional benchmark board. Also score full-precision forecasts before display rounding, assert unique per-model clocks and complete coverage, and turn the printed forest consistency check into an assertion. Current rounding differences are below 0.001 pp and do not explain the substantive results.

**How good the nowcast currently is.** Units below are percentage points of monthly CPI inflation; the large-surprise column is MAE, not RMSE. Large means |actual − consensus| ≥ 0.4 pp.

| Model | All 90 releases: RMSE | 2024 onward, 31: RMSE | Flash era, 19: RMSE | Large surprises, 23: MAE |
|---|---:|---:|---:|---:|
| HARD_BASE | 0.418 | 0.219 | 0.173 | 0.485 |
| HARD_HALF | 0.414 | 0.220 | 0.166 | 0.479 |
| HARD_FULL | 0.414 | 0.225 | 0.164 | 0.476 |
| Consensus | 0.382 | 0.241 | 0.195 | 0.578 |

The recent BASE RMSE improvement is about 9%, and about 11% in the flash era. It survives deleting any one recent month. This is encouraging. But the five recent large-surprise months provide the net recent improvement; on the other 26 months BASE loses, 0.178 versus consensus 0.168. The five large months have the right deviation direction, but only two cross the 0.2 pp alert threshold. This distinction matters directly to the user's objective.

Over all 90 releases BASE is closer on 45, with 12 material wins and 15 material losses at a 0.15 pp threshold. It issues 20 alerts: seven coincide with a large event, six of those have the correct direction, and 16 large events are missed. Since 2024 it has four alerts, two large-event hits and three large-event misses; material wins/losses across all 31 months are 4/2. The two false large-event alerts have different economic meanings: July 2024 is costly and wrong-way; December 2025 is directionally correct and materially better than consensus. Avoid equating every false large-event alarm with a bad forecast.

There is only **one** large surprise in the 19-release flash-era sample, and none of the HARD models triggers an alert for it. The flash-era RMSE result therefore does not validate a high hit-rate claim on large flash surprises.

The handoff's statement that three shock months account for 83% of squared error is incorrect. The three largest BASE errors account for **57.3%**; the January 2022 / October 2022 / January 2023 policy trio accounts for **50.2%**. Do not discard those errors: policy measurement changes are part of the task.

The recent deviation-on-surprise OLS slope 0.583 and ordinary t=3.50 reproduce. January 2024 has leverage 0.713; HC3 uncertainty gives t=1.68 and p=0.104. The paired squared-loss comparison gives t=−0.84, p=0.406. These are sensitivity checks, not proof of no signal. They show why the result should be described as promising rather than established. The many historical specification choices are an additional source of uncertainty.

The separate, past-only consensus-shrink experiment also reproduces. FULL shrink has RMSE 0.4207 versus consensus 0.4244 over its **66-month** sample, and 0.2137 versus 0.2410 recently. The all-sample advantage is only 0.0037 pp. Keep it optional and clearly survey-conditioned; it does not turn the independent nowcast into an established survey beater.

**What the CNB panels actually support.** These are RMSEs of quarterly average year-on-year inflation, unlike the artifact's per-report average absolute miss. Every model in this table uses the same report-quarter observations.

| Model | All scored reports, 66 pairs | Reports from 2024, 34 pairs |
|---|---:|---:|
| CNB | 2.295 | 0.372 |
| Component bridge | 2.362 | 0.590 |
| Bridge with current core | 2.339 | 0.402 |
| Bridge with long-run core level | 2.280 | 0.512 |
| QRF mean, FULL plus month | 2.990 | 0.409 |
| TVW3, FULL plus month | 2.980 | 0.752 |

The local-core and plain-mean lines are close to the CNB recently. TVW3 is appreciably weaker. Across the full scored report sample CNB MAE is 1.061, versus 1.409 for the long-core variant and 1.814 for TVW3; the long-core variant's slight aggregate RMSE lead should not be read as broad dominance. The 34 recent observations cover only ten realised quarters and ten scored reports, with repeated outcomes. Summer 2026 is the nineteenth displayed report and has no fully realised quarter to score yet.

The chart's selected model run is the latest release-eve run before **report publication**, not necessarily before the CNB's **data cutoff**. In 14 of 19 displayed reports these rules select different model origins. I recomputed a stricter sensitivity using the latest existing model snapshot before the CNB cutoff, keeping the same scored quarters and models:

| Model | 2024 onward: before report | 2024 onward: before CNB cutoff |
|---|---:|---:|
| CNB | 0.372 | 0.372 |
| Component bridge | 0.590 | 0.783 |
| Bridge with current core | 0.402 | 0.395 |
| QRF mean, FULL plus month | 0.409 | 0.331 |
| TVW3, FULL plus month | 0.752 | 0.727 |

The QRF-mean result deserves attention: it improves under the stricter timing rule. It remains an exploratory sensitivity, not a new promotion test. These earlier snapshots can be stale relative to the actual CNB cutoff; I did not rerun all models at that exact date or recover historical vintages. The earlier-run result also shows why “more recent information always improves the forecast” is not a safe assumption. Over all 66 pairs, the cutoff comparison still favors CNB over each of these model families. Keep both timing boards; do not choose whichever makes a model win.

The recent-origin h12 result for current core, 0.708 against bridge 1.347, is useful but incomplete. On recent **targets**, which also include forecasts issued during the disinflation, current core scores 2.619 versus bridge 1.892. Its simple persistent core trend can work well in a stable regime and adapt too slowly through a reversal. This is an economic weakness worth modeling, rather than explaining away every large error as an unknowable shock.

**My model assessment and suggested roster.**

| Purpose | Model to retain | Role and interpretation |
|---|---|---|
| Independent next-release estimate | HARD_BASE | Current operational reference; survey-free inputs; finish timing/live checks |
| Alternative next-release estimate | HARD_HALF | A serious, more conservative residual-correction challenger; the tiny historical RMSE differences do not settle selection |
| Larger residual correction | HARD_FULL | Retain on the same board; strongest of the three on flash RMSE and large-event MAE, with no established general advantage |
| Independent monthly path | Component bridge | Accounting and comparison reference for h0–h12 |
| Main structural path challenger | Bridge with current core | Simple, interpretable and strong recently; monitor reversal risk |
| Broad-data path challenger | QRF mean plus month | Promising recent research result; FULL includes inflation expectations and sentiment |
| Research/calibration diagnostic | TVW3 | Correct internal validation and retain as an experiment; current evidence does not justify replacing the mean |
| Optional external-information comparison | Consensus shrink / FULL-policy path | Clearly labeled; never silently replace the independent output |

HARD_FULL and the path forest's FULL policy are different concepts. HARD_FULL means the full residual correction in the independent nowcast. Forest FULL means the broad input policy, including FMIE inflation expectations and survey balances. The attractive 0.409/0.331 path results belong to that latter policy; they are not evidence for the strictly survey-free forest. LUCI's survey content in the independent policy was an explicit user exception, and should stay disclosed.

The component architecture is economically sensible. Fuel, food, policy prices and persistent core have different information and dynamics, so they should not be forced into one mechanism. Its weaknesses are also concrete: solved administered weights are statistical projection coefficients rather than official expenditure contributions; reconstructed policy events have limited independent validation; long-horizon seasonal fallback food/fuel paths can miss changing cost pressure; and the persistent local core extrapolation is slow to reverse. The large forest adds nonlinear information, but weighted historical target values have limited ability to extrapolate into a new inflation regime. More trees alone do not solve that issue.

**The next work should improve those mechanisms and the evidence, in this order.**

First, fix the transform and validation issues, repair the replay environment and manifest chain, and unify the live entry point. The basket-hour issue is excluded by the user's scope decision. The calendar currently ends with the August target; the independent archived backtest ends in July. The handoff correctly reports no prospective first-release record. Add the sourced September release schedule, capture inputs and hashes, and verify that both the forecast start and completion precede release. Test replay of that exact capture on the destination computer. A successful archived replay, including X13 and quantile-forest versions, is a necessary portability check.

Second, freeze the roster and scoring protocol. Score next-release point accuracy, large-surprise conditional performance, and all-release alerts separately. For actual A, consensus C and forecast F, retain gain in pp = |A−C|−|A−F|, material wins and losses at 0.15 pp, and predefined sensitivity at 0.10/0.20. An optional robust aggregate capture statistic on a fixed large-event set is 1−sum|A−F|/sum|A−C|. It rewards movement toward the print, penalizes wrong-way predictions and progressively penalizes overshoot; a forecast twice as far as the surprise earns zero gain, not full credit. A tiny 0.0001 improvement cannot qualify as a material win. For path forecasts, publish monthly/cumulative/quarterly losses, bias, recent origins and recent targets, and both CNB comparison clocks. Confidence intervals should respect overlap, and model selection across many experiments must remain disclosed.

Third, I would test a **core residual path model**, not another unconstrained headline forest. At each horizon or prespecified horizon band, start from a modest, slowly adapting core trend and forecast its residual with ridge and a small forest. Use already available imports, FX, wage/labour-cost pressure and activity indicators. Allow shrinkage toward zero residual. Compare a damped trend, fixed ridge and the residual forest on exactly the same origins; fit calibration only to matured historical forecasts. This addresses both the plain forest's limited extrapolation and the current-core model's excessive persistence. It is a proposal, not an improvement already demonstrated by this audit.

Fourth, extend the energy-policy ledger as an explicit bill/contribution calculation: measure starts and expiries jointly, source dates and tariffs, pass-through assumptions, and high/central/low scenarios. Keep these events separate from a statistical January dummy. For commodity paths, use the available Brent and TTF forwards as dated scenarios, distinguish the supplied rolling one-year contracts from a complete futures curve, and compare them with frozen-price controls. Estimate lagged pass-through from matured data. Never backfill a missing historical curve with today's strip.

Fifth, add joint uncertainty for the monthly path. Resample historically available forecast-error vectors across horizons and components, allowing dependence, then compound each simulated path. Do not obtain a purported 90% annual interval by compounding every month's 5th and 95th percentiles separately. Check coverage and interval scores through regimes. A rates view ultimately needs the persistence and source of the CPI deviation, not just its headline magnitude. Keep any mapping into market pricing as a separate model and evaluation task.

The relevant CNB paper is [AI-Based Forecasting of Czech Inflation: Quantile Regression Forests with Dynamic Weights, WP 9/2026](https://www.cnb.cz/export/sites/cnb/en/economic-research/.galleries/research_publications/cnb_wp/cnbwp_2026_09.pdf). It motivates nonlinear predictors, component forecasts and distributional evaluation. Its numerical results do not remove the need to validate this implementation's timing, data, and same-origin paths.

**Scope of verification and remaining limits.** There were 204 passing targeted tests across the final path suite (149) and forest suites (55). One path test fails the transitive import-manifest hash guard described above; another cannot execute in the available bundled runtime because `duckdb` is missing. Initial default pytest temporary-directory permission errors were resolved by using an audit-owned directory. This review used the bundled Python 3.12 and existing libraries, plus an independent Python 3.9 statistical recomputation. It does not claim a bit-for-bit refit of every forest or a complete live-data replay in the original pinned environment. The artifact rebuild itself is byte-identical. The review's arithmetic, clock counterexamples, causal reweighting and comparison-clock sensitivity are reproducible from the supplied frozen files.

The development record is valuable, but another favorable historical chart will not settle the remaining uncertainty. A small stable roster, corrected information handling, economically explicit scenarios and an accumulating prospective record are the most useful next steps.
