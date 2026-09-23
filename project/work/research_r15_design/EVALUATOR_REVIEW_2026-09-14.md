# Independent R15 evaluator review

Read-only review of `tools/review/evaluate_r15.py`, its test cases, and `output/research_r15/evaluation`. This reviewer changed no model, forecast, evaluator implementation or generated result. The final reviewed evaluation manifest was created at **2026-09-14T11:49:25.034721+00:00**.

**Verdict: no remaining blocker found in the evaluated scope.** All 12 evaluator input hashes, all 33 output hashes and the evaluator source hash match the final manifest. Numerical checks below independently reconstruct calculations from saved forecasts and raw frozen outcomes; they do not call the evaluator's scoring helpers. Interactive browser rendering and the parent's JavaScript/test-suite checks are outside this numerical receipt.

## Corrections during review

The first revision-summary implementation required realised annual inflation in addition to finite revisions. That unnecessarily excluded 924 valid future-target revision rows, from origins September 2025 through July 2026. The evaluator author changed its matching requirement to finite forecast revisions only. Independently recomputed final common-support summaries contain 14,490 rows and retain all 924 of those future-target rows; their per-model counts and mean absolute revisions match. The raw revision ledger contains 14,919 rows.

The author also renamed the endpoint-direction statistic from `material_turn_hit_rate` to `material_direction_hit_rate`, avoiding confusion with the separate local-peak/trough diagnostic. Bootstrap intervals now remain unavailable if any matched origin cannot belong to a complete twelve-month calendar block. No existing interval has that partial-coverage condition, so this guard changes no current interval values.

An initial artifact Unicode mismatch was a **reviewer decoding error**: the JSON read omitted explicit UTF-8 in a Python runtime whose default locale is cp1252, while the HTML read used UTF-8. Explicit UTF-8 reads show exact embedded-payload equality and zero replacement characters. No generator encoding bug remains or is asserted.

## Matched metric support

Common support is reconstructed separately for each metric and horizon, including absent or nonfinite models. Selected FAST and ENET_BOTH score cells match independent calculations. Core and headline counts differ because fixed noncore failures affect headline availability:

| Metric | h3 common origins | h12 common origins |
|---|---:|---:|
| Monthly core | 87 | 78 |
| Cumulative core logs | 87 | 78 |
| Annual headline | 84 | 75 |

Monthly core comes from the original frozen core target. Cumulative core includes h1 through h, with missing intermediate months propagating missingness. Headline annual inflation combines known history with one origin's monthly forecasts. The evaluator does not import or run model fitting, and no outcome or CNB value changes an estimator or selected configuration.

## CNB clocks, quarter arithmetic and scores

All **38 report/cutoff clock choices** match independent date filtering of the actual saved forecast clocks. Report clocks are strictly before report-day midnight in Prague. Cutoff clocks extend through the stated cutoff day, strictly before next-day Prague midnight. The local calendar-day operation precedes timezone conversion.

All **1,980 scored model/CNB rows** match independent reconstruction exactly, including quarterly means, realised values, absolute-error gains and material gain/loss flags. Each clock has 66 common report-quarter pairs, over 18 scoreable reports and 18 unique realised target quarters. Nineteen reports are available for display; the latest does not yet have a complete realised forecast quarter. Repeated quarters across reports remain identifiable rather than being described as independent events.

For each quarter, months before the selected origin use known annual inflation; every remaining month uses that same selected origin's forecast. All three months, all fourteen models, CNB and the realised quarter must be finite for scoring. No monthly forecast is borrowed from another origin. The separate cross-clock intersection retains matched report-quarter keys across both clocks.

Selected full-sample checks:

| Clock | Model | Pairs | MAE | RMSE | Material gains / losses vs CNB |
|---|---|---:|---:|---:|---:|
| Report | CNB | 66 | 1.060549 | 2.295453 | 0 / 0 |
| Report | FAST | 66 | 1.259695 | 1.986704 | 15 / 32 |
| Report | ENET_BOTH | 66 | 1.493070 | 2.308397 | 14 / 37 |
| Report | Current core | 66 | 1.431652 | 2.339299 | 17 / 29 |
| Cutoff | CNB | 66 | 1.060549 | 2.295453 | 0 / 0 |
| Cutoff | FAST | 66 | 1.335018 | 2.129457 | 13 / 31 |
| Cutoff | ENET_BOTH | 66 | 1.723630 | 2.618340 | 15 / 41 |
| Cutoff | Current core | 66 | 1.539826 | 2.544964 | 17 / 31 |

Material gain is CNB absolute error minus model absolute error at least 0.15pp, with the declared numerical tolerance; a material loss is at most -0.15pp. Merely deviating from CNB in the right direction does not count as a gain. FAST's lower pooled RMSE coexists with higher MAE and more material losses than gains; the evaluation supports that mixed interpretation.

## Underlying core-turn diagnostics

All **5,040 band values** and **2,520 turn records** independently reconcile exactly to the raw core outcome and each origin's saved seasonal factors. Each band is twelve times its average monthly seasonally adjusted log-core rate. A peak/trough requires two opposite changes of at least 0.5pp annualized at interior band 2 or 3. Ineligible incomplete paths do not enter the matched summary.

The full common summary has **159 origin/band opportunities**, including 77 actual-turn flags. These are overlapping diagnostic opportunities, not 77 independent economic turning events.

| Model | Predicted turns | Exact-band hits | Missed actual turns | False predicted turns |
|---|---:|---:|---:|---:|
| Independent bridge | 38 | 11 | 66 | 27 |
| ENET_BOTH | 47 | 8 | 69 | 39 |
| Residual forest | 20 | 3 | 74 | 17 |
| Adaptive state | 4 | 0 | 77 | 4 |
| FAST | 0 | 0 | 77 | 0 |
| MID | 0 | 0 | 77 | 0 |

The fixed state paths cannot generate an interior turn in the seasonally adjusted conditional mean: the forecast trend is constant and the positive AR coefficient decays its residual monotonically. Their zero predicted-turn count is therefore structurally expected, not a counting bug. Better annual-headline RMSE is not evidence that those fixed states predict underlying core peaks/troughs. There is no CNB core-path comparison in these tables.

## Bootstrap checks

Three independent seeded moving-block reconstructions match the saved point estimate, interval and improvement frequency. Blocks contain twelve consecutive calendar origins; missing origin gaps are not bridged. Draws=2,000, seed=1509. Loss differences are model squared error minus stable-pipeline squared error.

| Model / sample / horizon | N | Mean loss difference | 95% descriptive interval |
|---|---:|---:|---:|
| FAST / full / h6 | 81 | -1.131151 | [-3.480621, 0.222123] |
| FAST / origins2024+ / h12 | 19 | -0.728006 | [-1.159368, -0.693736] |
| ENET_BOTH / full / h12 | 75 | 2.038524 | [-2.238537, 9.122075] |

The short recent sample and overlapping forecasts remain limitations; these descriptive intervals do not supply a new promotion rule or remove model-selection/multiplicity concerns.

## Artifact data and labels

The embedded HTML data exactly equals the UTF-8 `replay_data.json` series and report payloads. Checked 7,448 displayed forecast/anchor points and 540 panel score values against the saved forecast and CNB ledgers; maximum difference was zero. Every path belongs to its displayed origin, and per-panel scores use fixed complete-roster support independent of visible checkboxes.

Both clock selectors, round selection and model checkboxes are present. The artifact labels the paths historical replays with simulated cutoffs and current-vintage inputs, says they were reconstructed later, distinguishes CNB quarterly averages from monthly paths, and states the limits of the core-turn diagnostic. External Google-font dependencies are absent. The final payload has zero Unicode replacement characters.
