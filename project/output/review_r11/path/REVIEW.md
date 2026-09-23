# Existing independent Czech inflation path: bounded R11 review

Date: 9 September 2026. Read-only review of the existing R9/R10 implementation. No new model fits, repository edits, database writes or git operations. The only new files are in `work/core_split_research/path_review_r11/` in the parent workspace. They are scratch diagnostics, not an adopted forecast or a deliverable under `outputs/`.

Repository reviewed: `work/cpi-independent/` relative to the parent workspace `C:/Users/luis_/Documents/Codex/2026-09-05/c-users-luis-appdata-local-temp/`.

## Assessment

The existing **independent component bridge** is the appropriate main *research* path. It already exists; do not restart the historical F1b or step-five handoff chain. `forecast_independent.py:229–260` labels it `BRIDGE_HARD`, returns `primary_model='BRIDGE_HARD'`, and explicitly sets `production_certified=False`. Historical evaluation calls the same family `INDEPENDENT_BRIDGE`.

On the full common sample it has lower compounded YoY RMSE than the corrected aggregate trend, FX/labour trend, direct Minnesota regression, forest and five-year seasonal naive at **every h1–12**. This does not mean it wins every endpoint's m/m error, every regime, or every sensible benchmark. Its weakest useful research area is months 9–12. A newly checked simple y/y random walk beats it at h10–12 on the small recent-*origin* sample, a benchmark absent from the R9 independent roster.

The most actionable new finding is **food's accumulated positive long-horizon error**. In recent-target h12 forecasts, exact annual error accounting assigns food +0.9105 pp of mean error and core +0.4133 pp, before offsets from other blocks. In forecasts actually originated from January 2024 onward, food still contributes +0.5760 pp while core contributes −0.1452 pp. This supports testing the long food rule before a broad new macro model. The claim that its five-year average carries the inflation surge forward is a grounded **hypothesis**, not causation proved by this decomposition.

## Current structure and information content

- `independent_bridge_experiment.py:45–120`: h0 is supplied `HARD_BASE`. Core is the existing direct ridge at each h1–12. Food is origin-fitted X-13/direct ridge at h1–3, then mean of the last five released observations for the destination calendar month at h4–12. Administered prices use the existing January announcement gate. Alcohol/tobacco uses its existing rule. Fuel is the median of the last eight same-calendar-month observations, with a short-history fallback. The wedge is a reconciliation forecast. Future unpublished basket regimes retain origin weights (`:36–42`, `:79–107`).
- The hard policy applies at **every horizon**, not only to h0: `independent_bridge_experiment.py:72–73`; `models/independent_nowcast.py:11–20` drops `exp12`, `exp36`, `exp12_x_state`, `household_exp`, and `esi`. Measured CPI data sourced from the CNB is not a forecast expectation. LFS unemployment observations in the separate aggregate paths are also observed statistics, despite their survey collection method.
- The bridge's core predictors are EUR/CZK monthly change, the six-division proxy historically named `services_l1`, lagged import prices, core lags 1/2/12, high-inflation state, selected interactions, and month dummies. Food uses lagged food, agricultural prices and food PPI. See `output/independent_bridge_diagnostics.json:10–44`. The `services_l1` name remains a misleading description of the frozen historical input; `docs/CORE_SERVICES_REVIEW_2026-09-09.md:28` corrects it. No direct wages, retail demand, policy/real-rate path, or official services split enters the existing bridge.
- `independent_path_experiment.py:119–188`: the alternatives are (i) target-anchored ML headline trend/gap, (ii) add EUR/CZK twelve-month change at destination lag 3, (iii) add published unemployment change at destination lag 1, (iv) direct Minnesota-shrunk regression with 3 lags, and (v) fixed forest per horizon. `models/bvar.py:1–16` correctly describes its implementation as an equation-wise **direct regression**, not a joint structural VAR. The forest uses headline lags 1/2/3/12, trailing y/y, a state indicator, origin-edge U/FX and destination-month dummies (`models/path_inputs.py:64–92`).
- Target-only ML uses all contiguous headline history from February 1991 and robust centered month medians. It is a two-state headline model, not a component economic transmission model. `models/trend_gap.py:34` restricts rho to 0.90–0.999. On the 90 primary fits rho's median is 0.9810, approximately 36 months' half-life; this is consistent with slow disinflation but is not proof that changing rho improves forecasts. The target is a long-run policy anchor, not the CNB's forecast path.
- Aggregate ML passes known future lag rows and a flat future FX *level* scenario; unpublished U changes are zero (`models/path_inputs.py:37–61`, `independent_path_experiment.py:130–136`). Direct RF/BVAR use a fixed history-edge predictor set, omitting some more recent FX values already known at the cutoff. Specifically their edge source at t−1 carries FX12[t−3]; ML can propagate known FX12[t−2], [t−1] and [t] into destinations t+1, t+2 and t+3. This is unequal information exploitation, not a demonstrated remaining future-data leak.

## All forecast horizons

YoY RMSE in percentage points, ex ante, same independent h0, same origin/target keys within each column. Full sample origins are February 2019–July 2026; realized targets end July 2026. `Recent targets` selects destination month >=2024-01. `Recent origins` selects origin >=2024-01 and then requires a realized destination. The former includes forecasts made during 2023; the latter does not. Thus they answer different questions. All recent-target columns below have N=31. The current summary only prints h1/3/6/12; this review computed every horizon from the saved comparison forecast rows.

| h | Full N | Bridge full | Forest full | Naive full | Bridge recent targets | Recent-origin N | Bridge recent origins |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 88 | 0.9107 | 0.9751 | 1.0396 | 0.3650 | 30 | 0.3707 |
| 2 | 86 | 1.2946 | 1.4437 | 1.6231 | 0.5094 | 29 | 0.5249 |
| 3 | 84 | 1.5373 | 1.7719 | 2.1230 | 0.5465 | 28 | 0.5691 |
| 4 | 83 | 1.8237 | 2.0763 | 2.6157 | 0.5499 | 27 | 0.5353 |
| 5 | 82 | 2.1685 | 2.4296 | 3.1259 | 0.6477 | 26 | 0.5787 |
| 6 | 81 | 2.5164 | 2.8171 | 3.6329 | 0.7478 | 25 | 0.6777 |
| 7 | 80 | 2.9913 | 3.2841 | 4.1526 | 0.8450 | 24 | 0.8169 |
| 8 | 79 | 3.3333 | 3.7434 | 4.6446 | 0.9171 | 23 | 0.9243 |
| 9 | 78 | 3.9216 | 4.2141 | 5.1546 | 1.1824 | 22 | 1.0048 |
| 10 | 77 | 4.4988 | 4.6615 | 5.6340 | 1.4814 | 21 | 1.1538 |
| 11 | 76 | 5.0020 | 5.1359 | 6.1183 | 1.6926 | 20 | 1.2856 |
| 12 | 75 | 5.3948 | 5.6016 | 6.5719 | 1.8921 | 19 | 1.3473 |

All seven methods, all four samples, all twelve horizons, counts, RMSE/MAE/bias, and monthly endpoint scores are in `horizon_metrics.csv`. `analyze.py` reproduces 84 existing R9 score rows to a maximum absolute difference of 8.88e−16. Existing headline summaries and conventions: `docs/implementation/BRIDGE_RESULTS.md:90–140`, `independent_bridge_experiment.py:249–257`, `independent_path_experiment.py:36–62`.

Useful contrasts:

- Aggregate target ML full common h1/3/6/12: 0.9697 / 1.9566 / 3.3801 / 6.5919. BVAR: 0.9461 / 1.8912 / 3.1662 / 6.2234. Adding U/FX to ML does not close the gap.
- For recent targets, the forest is stronger than bridge at h1 and h2, then weaker at h3–12. For recent origins it is stronger at h1–3; its recent-origin h12 is 1.6141. This makes forest a useful challenger, not a universal replacement.
- Full-sample bridge h12 bias is −1.5636 pp. Crisis-target h12 is RMSE 6.8620 and bias −3.4966, N44. Recent-target h12 bias is +1.1800; recent-origin h12 bias is +0.7300. A universal positive or negative bias correction would attack one regime and hurt another.
- The twelve worst h12 bridge cases account for 75.25% of its full-sample squared error. The worst is origin June 2021 to June 2022: 2.9756% forecast, 17.1875% actual, −14.2119 pp error. Calm and crisis reporting are both essential.
- Bridge monthly endpoint RMSE at h1/3/6/12 on the full common path panel is 0.6910 / 0.8003 / 0.8213 / 0.9246. The forest's h3/6/12 endpoint errors can be smaller even while its annual path is worse. Annual path loss depends on persistence and covariance of monthly errors, not just each endpoint's error.

## Benchmarks and CNB

The R9 independent roster contains the five-year seasonal naive. It does **not** include the last-released-y/y random walk (`independent_path_experiment.py:25–26`). This review added a cheap, no-fit diagnostic only: hold the y/y inflation computed through t−1 flat at each future destination. It never reads y[t] and does not use the independent h0, so it is explicitly outside the common-h0 roster. Its flat level benchmark should be added as a separate reference, not disguised as an h0-reconciled model.

| Sample | h1 RW / bridge | h3 RW / bridge | h6 RW / bridge | h12 RW / bridge |
|---|---:|---:|---:|---:|
| Full common | 1.5710 / 0.9107 | 2.6970 / 1.5373 | 4.2266 / 2.5164 | 6.9693 / 5.3948 |
| Recent targets | 1.3659 / 0.3650 | 1.9285 / 0.5465 | 2.8628 / 0.7478 | 6.2224 / 1.8921 |
| Recent origins | 1.0476 / 0.3707 | 0.9157 / 0.5691 | 1.1062 / 0.6777 | **1.1747 / 1.3473** |

Recent-origin RW is also slightly better at h10 and h11 (1.1286 vs1.1538; 1.1714 vs1.2856). N at h12 is only 19 and includes overlapping target windows. This prevents saying the bridge has established calm-regime long-horizon skill above every simple comparator. It does not overturn the strong full-sample comparison. `omitted_rw_benchmark.csv` retains all horizons and samples.

Stored F1b and stored survey-trend references remain optional historical comparisons, not newly estimated independent models (`independent_path_experiment.py:334–337`). Including their missing cases narrows full-sample h6 to N78 and h12 to N66; on that panel bridge h12 is 5.743, not 5.395. Recent target h12 stored F1b/survey-trend RMSE is 1.412/1.330 versus bridge1.892. Replacing only their h0 does not remove expectations or fix their older modeling conventions. Use these differences as diagnostics, not promotion evidence for a supposedly independent model.

CNB quarter construction is sound for the declared public-availability comparison: strictly pre-publication path cutoff, mean of three monthly y/y rates, actual only before origin, no substitution of later actuals into required forecast months, complete common report-quarter keys (`independent_bridge_experiment.py:123–187`). It is not an equal-internal-cutoff experiment against the CNB. Historical known CPI remains current-stored vintage.

Full matched CNB/bridge RMSE is 2.2954/2.3624, and recent-report RMSE 0.3718/0.5904. The full panel has 66 report-quarter pairs but only18 distinct quarters; recent has34 pairs,10 reports,10 distinct quarters. Recent quarter-ahead bridge versus CNB is:

| q ahead | N pairs | Bridge RMSE | CNB RMSE |
|---:|---:|---:|---:|
| 1 | 10 | 0.2990 | 0.2789 |
| 2 | 9 | 0.4267 | 0.3696 |
| 3 | 8 | 0.6431 | 0.4214 |
| 4 | 7 | 0.9266 | 0.4263 |

Quarter ahead is measured from the quarter containing the final observed month t−1. The recent weakness widens at q3–q4. No rule should optimize closeness to the CNB forecast. Score actual inflation; show the bank and optional survey-conditioned paths beside the independent view. Exact source: `output/independent_bridge_cnb_summary.csv`; definitions in `docs/implementation/BRIDGE_RESULTS.md:143–195`.

## Where the errors arise: exact accounting, not causal attribution

For a monthly path point m, define P_m and A_m as predicted and actual headline m/m **percentage rates**. For each economic block j, define e_jm = predicted contribution_jm − forecast-origin weight_jm × actual block m/m. Define the wedge error as the residual needed for `sum_j e_jm = P_m−A_m`; it consequently includes weight/reconciliation discrepancies and must not be named an economic cause.

For each complete h12 path define:

`L_P = sum_m log(1+P_m/100)`; `L_A = sum_m log(1+A_m/100)`; `D=L_P−L_A`.

`k_m = [log(1+P_m/100)−log(1+A_m/100)] / (P_m−A_m)`, with continuous limit `1/(100+A_m)`.

`C = 100 × [exp(L_P)−exp(L_A)] / D`, with continuous limit `100×exp(L_A)`.

Allocate annual percentage-point error to block j as `E_j = C × sum_m k_m e_jm`.

Then **sum_j E_j equals the exact compounded annual forecast error in percentage points**, not an approximation. The code verifies this within1e−10 for every complete observed h12 path. At h12 the annual window contains h1–12 and not h0. The allocation is a chosen proportional log-space accounting convention; it is neither a causal effect nor an ex-ante achievable error reduction. Nonlinearity is allocated by this convention, rather than ignored. `h12_log_error_allocation.csv` contains the origin-level allocations.

| Block | Mean allocated h12 error, full N75 | Recent targets N31 | Recent origins N19 |
|---|---:|---:|---:|
| Core | −0.2033 | +0.4133 | −0.1452 |
| Food | −0.0892 | **+0.9105** | **+0.5760** |
| Administered | −1.1025 | −0.1229 | +0.2675 |
| Alcohol/tobacco | −0.1507 | +0.0519 | +0.0840 |
| Fuel | −0.0145 | +0.1314 | +0.1270 |
| Wedge/residual | −0.0035 | −0.2041 | −0.1793 |
| Sum | −1.5636 | +1.1800 | +0.7300 |

On recent-target monthly endpoints, food contribution bias is +0.0292 pp at h3 versus +0.0871 at h6 and +0.0886 at h12; overall monthly headline bias moves from +0.0062 at h3 to +0.0704 at h6. The rule explicitly changes to five-observation same-month means at h4 (`independent_bridge_experiment.py:89–95`). This is evidence motivating a food trend/seasonality experiment. It does not isolate the rule as the sole cause: windows, feature relevance, composition and actual food regime also change.

January explains 55.69%,57.45%,49.70%,57.00% of full-sample monthly squared headline error at h1/3/6/12 respectively. October adds14.68%,16.50%,9.21%,9.37%. Administered-price contribution errors dominate those full-sample monthly endpoints. But for the **annual** crisis path, the covariance allocation `mean(E_j × total_error)` is about50.0% core,21.2% food,19.5% administered. These shares can be negative when a block offsets other errors; they are an additive MSE accounting identity, not shares of individual-block variance. Both views are needed: fixing one January endpoint is different from anticipating persistent core inflation over twelve months.

`bridge_block_errors.csv` uses each horizon's finite **monthly** cases, so h6/h12 full sample has N84/N78 there; compounded annual path comparisons have N81/N75 because earlier failed food months break some paths. This distinction is intentional and must accompany any quoted endpoint block number.

## Correctness and readiness boundaries

No new arithmetic correctness blocker was found in this bounded inspection. The claimed repaired boundaries are supported by the code and saved data: path h = underlying last-observation h+1 (`independent_path_experiment.py:31–33`); direct outcome labels end t−1 (`models/path_inputs.py:64–92`; `cz_struct.py:547–580`); exact twelve-month compounding and missing-intermediate propagation (`models/path_inputs.py:95–115`); constant independent h0 across candidates; h12 conditional/ex-ante equality; strict pre-report clocks. This review checked keys, all13 horizon rows, h0/h12 identities and CNB clocks against saved outputs. It did not rerun the full fit suite.

Remaining limitations should not be disguised as algorithm bugs:

1. Mixed/current-stored historical vintages and partly rule-based release availability prevent claiming a fully archived real-time test. The bridge's input row is masked at its clock, but historical feature rows retain the documented conventions (`cz_struct.py:311–345`). The genuine103-release U archive only covers later path origins and changes from SA to trend-cycle publication; `docs/implementation/VINTAGE_FINDINGS.md` explains this. The bridge itself has no U input. These are certification limitations; the declared retrospective comparisons remain useful.
2. Conditional h0 uses stored/index-derived CPI, not rounded first release. The path's actual y/y is also compounded from stored monthly index rates. Compare that scoring target consistently; do not blend it with the nowcast first-release leaderboard.
3. The first three bridge origins have six missing food endpoint estimates. They are retained and disclosed, not silently filled. The comparative complete-path sample is correspondingly smaller (`docs/implementation/BRIDGE_RESULTS.md:67–88`).
4. H0 replacement changes index accounting only. It does not feed the independent nowcast back into a recursive latent state, and changing h0 cannot change h12 y/y (`models/path_inputs.py:98–99`). The bridge's direct monthly forecasts are not a recursive structural model. This is a documented conditioning/design boundary, not a hidden arithmetic inconsistency.
5. Old stored F1b/survey-trend paths are not evidence that the corrected new path implementations are validated. No untouched historical holdout or calibrated probability distribution exists. Repeated horizons, origins and report-quarter pairs overlap.

## Three bounded next experiments, in priority order

1. **Food level and seasonality at h4–12.** Keep h0, h1–3, every other component, dates and weights fixed. Compare the current five-year same-month level with one predeclared candidate that separates centered same-month seasonal effects from an origin-estimated recent food trend. Freeze the trend window/robustness rule before looking at the comparison; no grid search. Evaluate exact annual and monthly food contribution errors at every horizon, especially recent origins and recent targets, with a crisis/full-sample non-regression guard. The +0.9105/+0.5760 annual food bias is the reason to test it, not a promised obtainable gain.
2. **Carry the independent core-category work into a single path challenger.** Once the current R10/R11 nowcast diagnostics are settled, extend that frozen category definition and hard-input policy to direct h1–12 core forecasts, keeping the incumbent food/admin/fuel/other rules fixed. No expectation input. Compare aggregate-core monthly, cumulative and annual contribution loss; a nowcast gain alone does not establish path skill. This is the largest accumulated crisis-error channel, and the recent-target h12 core contribution has large dispersion. Retain the aggregate ridge so the effect of disaggregation can be isolated. A cumulative-log-target or horizon-pooling change is a later separate experiment, not something to bundle into this one.
3. **Dated all-month administered-energy accounting, as a scenario challenger first.** The current rule returns its seasonal baseline immediately for non-January destinations (`cz_struct.py:833–842`), so known October credits/VAT changes/expiry are outside that gate. Use the existing R9 monetary ledger and dated event sources, not a new bill-change heuristic; recover or explicitly bound customer/product exposure and CPI allocation, replace the embedded baseline once, and compare separate near-horizon and annual shock effects. The ledger already treats these mechanisms (`models/energy_ledger.py:126–131`,`:254–275`,`:319–337`), but missing exposure mapping is a blocker to a certified point override. Do not score an event before its announcement, and do not expect a 2021-origin path to know later war/policy outcomes.

Before running any of these, add both recent-origin and recent-target panels and the simple y/y RW to the *reporting* baseline; lock common samples and loss definitions. This is cheap evaluation hygiene, not a fourth model project. Do not tune to CNB proximity or import forecast expectations to force a calmer path.

## Reproduction and integrity

From the parent workspace run:

`C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe work/core_split_research/path_review_r11/analyze.py`

The script resolves the repository via its own location (`parents[2]/'cpi-independent'`), only reads existing repository files, and writes its own sibling scratch CSVs/receipt. It uses bundled pandas3.0.1 and NumPy2.3.5, not the original fitting runtime; no estimator is executed. The saved-score agreement demonstrates that this runtime difference did not change these descriptive recomputations.

Files: `analyze.py`; `horizon_metrics.csv`; `bridge_block_errors.csv`; `h12_errors.csv`; `h12_log_error_allocation.csv`; `omitted_rw_benchmark.csv`; `validation.json`; this note.

Read-only hashes match the original recorded outputs:

- `output/independent_path_forecasts.csv`: `83cb8f37206af9a3a85f14c5d5875aca93a9a7442cb6d572024bd0b0c241b26e`.
- `output/independent_bridge_forecasts.csv`: `b1377d1c45373b7571a47edd3c373a6b149cae49e9efbd37853566ded00a88d8`.

No literature detour or extra path-model build is required to act on this roadmap.
