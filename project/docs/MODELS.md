# Which models to use

## R17 completed research — 14 September 2026

[Full assessment](../R17_RESULTS_2026-09-14.md) · [CNB replay](../output/research_r17/path/evaluation/cnb_rounds_replayed_r17.html).
The 30-model experiment is a research record, not the operating roster. All h0
forecasts are unchanged and independent of surveys; latest frozen origin July 2026.

| Role | Keep/use | R17 verdict |
|---|---|---|
| Next-release forecast | Existing independent nowcast and its raw/HALF/FULL comparisons | Unchanged; no new next-release consensus claim |
| Responsive path reference | `STATE_FAST_R15` | Retain |
| Recent-period path comparison | `STABLE_LOCAL_CORE_R14B` | Retain; no post-hoc regime switch |
| Headline path sensitivity | `DAMPED_P95_Q001_R16` | Retain cautiously; standalone core is weaker than FAST |
| Conditional energy comparison | `FUEL_ANNUAL_R17` | Scenario with unverified exact annual-index maturity/roll; mixed performance |
| Category diagnosis | Shared category AR outputs | Better pressure proxy, without a better core path |
| Unpromoted experiments | R17 robust/news/h0 updates, food variants, generated category core models, fixed combinations, selectors | No consistent general replacement established |
| Household energy policy | Corrected facts and explicit bill/commodity scenarios | National point candidate fails closed pending exposure and baseline data |

The new robust filter is a near-tie with the existing gentle slope. The current
core/FAST half path is a fixed monthly path average, **not** the nowcast HALF
correction. A favorable headline error does not by itself validate the component
mechanism. Read the same-support component and CNB omission tables before making
promotion claims. Earlier sections remain the development history.

## R16 path research — 14 September 2026

Read the [completed experiment and assessment](../R16_RESULTS_2026-09-14.md)
and [CNB round replay](../output/research_r16/evaluation/cnb_rounds_replayed_r16.html).
This is the preceding research map. No operating model is promoted or replaced;
all paths end at the July 2026 historical origin and retain reconstructed
availability with current-vintage inputs.

| Role | Model | Evidence and use |
|---|---|---|
| Independent release nowcast | Existing `HARD_BASE`, HALF/FULL comparisons | Unchanged |
| Path reference | `INDEPENDENT_BRIDGE` / `STABLE_PIPELINE_R14B` | Fixed benchmarks and noncore accounting |
| Simple responsive benchmark | `STATE_FAST_R15` | Retain; R16 headline gains do not establish improved standalone core accuracy |
| Recent-period comparison | `STABLE_LOCAL_CORE_R14B` | Stronger recent-origin accuracy; no demonstrated material CNB edge |
| New headline research challenger | `DAMPED_P95_Q001_R16` | Better headline h3/h6/h12 RMSE than FAST in full and recent-origin frames, but weaker core forecasts and more favourable retained-error interactions; underlying-turn skill unproven |
| More responsive sensitivity | `DAMPED_P95_Q010_R16` | Best full-history headline scores, weaker recent-origin accuracy and larger revisions |
| Unpromoted research | Other slopes/adaptive selection, four `TRANSMISSION_*` variants, `BLEND_DAMPED_TRANSMISSION_R16` | Extra complexity does not establish consistent gains; intermediate signals often lose to persistence |

All R16 candidates preserve HARD_BASE h0, noncore paths and weights. All five
controls and the original R15 common scoring support are unchanged. No survey,
expectations or sentiment input is used. CNB-relative RMSE advantages of the
two .95 slopes reverse when the February 2022 report is omitted. Neither a
post-hoc crisis/calm switch nor a new blend has been adopted.
The [same-support error attribution](../output/research_r16/attribution/paired_vs_fast_summary.csv)
explains why headline improvement does not justify replacing the core mechanism.

## R15 path research — 14 September 2026

Read the [completed experiment and assessment](../R15_RESULTS_2026-09-14.md)
and [CNB round replay](../output/research_r15/evaluation/cnb_rounds_replayed_r15.html).
This is the preceding path research roster; operating formulas were not promoted or
replaced. Inputs are frozen current vintages with reconstructed availability,
and July 2026 is the final historical origin.

| Role | Model | Evidence and use |
|---|---|---|
| Independent release nowcast | `HARD_BASE`, existing HALF/FULL comparisons | Unchanged by R15 |
| Path reference | `INDEPENDENT_BRIDGE` / `STABLE_PIPELINE_R14B` | Fixed benchmarks and component accounting |
| Responsive path research line | `STATE_FAST_R15` | Best R15 full-history h3/h6/h12 accuracy; lower CNB-relative RMSE but worse MAE, with gains concentrated in one 2022 round |
| Recent-period path comparison | `STABLE_LOCAL_CORE_R14B` | Stronger recent accuracy than FAST; small CNB-relative MAE edge does not establish a material trading advantage |
| Nonlinear diagnostic challenger | `RF_RESIDUAL_R15` | Trend plus forest correction; some headline-direction improvement, weak exact core-turn record, no automatic blend |
| Unpromoted research | Slow/moderate/adaptive states; domestic/imported/both/wide elastic nets; two fixed blends | All results retained. Extra predictors often shrink to zero; no consistently superior mixture |

Every R15 candidate preserves HARD_BASE h0 and the stable pipeline's noncore
path/weights. Surveys and confidence inputs are absent. FAST's underlying-core
path is monotonic toward its estimated trend; its annual-CPI accuracy gains must
not be presented as demonstrated ability to anticipate fresh core peaks/troughs.
The earlier roster below documents the preserved history.

## Current independent roster — 9 September 2026

**R13 update:** [Latest model map](../RESEARCH_R13_START_HERE.md) and
[measured results](implementation/R13_RESULTS_2026-09-09.md) supersede earlier
research recommendations. The BASE/Category correction matrix is complete:
Category Raw remains the accuracy challenger; Category Half/Full worsen core
and ordinary accuracy despite a small large-event MAE gain. Existing BASE
Half/Full stay unchanged. The independent bridge remains the path reference;
category-monthly core is retained as component research, with better full-sample
core error but weaker recent persistence and worse whole-path accuracy. CNB
agreement is evaluated separately from realised accuracy and is not validation
by itself. No R13 model was promoted into the live pipeline.

**R11 decision:** the operating reference remains BASE. The simple category
model is the research accuracy challenger; HALF and FULL remain comparisons
within the aggregate-core family. HALF means half of FULL's learned error
correction, not a BASE/category blend. Two remainder-information diagnostics
are closed without adoption. The path starting point is the already-built
independent component bridge. Read the [latest assessment](LATEST_MODEL_ASSESSMENT_2026-09-09.md)
for the compact decision table, non-core audit and measured path priorities.

**R10 services experiment:** the five-category `TARGET_OWN` forecast is now a
research accuracy challenger, not a replacement for the main forecast or a
certified live model. Its headline RMSE is 0.408947 versus BASE 0.417952; core RMSE
is 0.246455 versus 0.299717. Since 2024 headline RMSE improves to 0.197798.
However, large-surprise MAE worsens from 0.484583 to 0.511988, and directional
success falls from 17/23 to 13/23. The full-sample headline gain reverses when
October 2022 is omitted. Keep the accuracy and surprise objectives separate.
Run `core_split_experiment.py --verify` for the frozen offline experiment and
read [the services/core review](CORE_SERVICES_REVIEW_2026-09-09.md).

**Input-description correction:** the historical `services_l1`/`services_cpi_mm`
name denotes the monthly change in an equal-weight mean of six whole CPI division
indices, not an official services aggregate. R9 numerical inputs remain frozen
for reproducibility. R10 tests dropping the proxy and adding official ARAD
tax-inclusive annual tradables/nontradables instead. The new five-category
monitor reports base-weight contribution projections, not exact official shares.

| Role | Model | Use |
|---|---|---|
| Main release nowcast | `HARD_BASE` | Independent component forecast; no FMIE, household inflation expectations or ESI |
| Research accuracy challenger | `TARGET_OWN` | Five-category core split; offline research pending live archive integration |
| Conservative correction comparison | `HARD_HALF` | Half of the correction learned from this independent ridge's own past errors |
| Surprise challenger | `HARD_FULL` | Full correction; better conditional large-surprise accuracy, unproven alert rule |
| Research comparison | `SENTIMENT_*` | Adds ESI only; fails the predeclared promotion rule |
| Optional comparison | `OPTIONAL_EXPECTATIONS_*` | Original expectations-conditioned inputs; never silently blended into the main forecast |
| Main research path | `BRIDGE_HARD` / `INDEPENDENT_BRIDGE` | Independent component bridge at h1–12; same BASE h0; explicit `production_certified=False` |
| Path challengers/benchmarks | corrected independent trend, FX/labour, BVAR and forest | New `independent_path_*` and `independent_bridge_*` evidence; old path outputs cannot validate corrected implementations |
| Mechanism research | `models/energy_ledger.py` | Monetary energy-policy scenarios; missing exposure mapping prevents promotion |

Run `forecast_independent.py`; follow `implementation/OPERATING_GUIDE.md`.
Overall baseline RMSE on 90 first releases is 0.417952; HALF 0.413696 and
FULL 0.413931, versus consensus 0.381517. On the 23 large surprises FULL's
MAE is 0.476061 versus consensus 0.578261. Large-surprise conditional accuracy
is not a tested live trade-selection rule. Scores use first-release outcomes
and the corresponding ordinary/flash survey; the suspect August 2026 survey
is excluded. Forecasts are historical reconstructions, not archived live calls.

## Historical roster (superseded for current operation)

The operating roster is deliberately small. These independent forecasts do
not use the current consensus as a predictor. The consensus is a comparison
benchmark, available only at its own recorded publication time.

| Role | Model | Saved column | Intended use |
|---|---|---|---|
| Short-term reference | BASE_RIDGE | STRUCT / live h0_base_ridge | Main point forecast and reproducibility anchor |
| Short-term challenger (surprise capture) | PAST_FULL | STRUCT_PE_WARM / live h0_past_full | Test whether historical sequential core errors improve material surprise capture |
| Short-term challenger (accuracy) | PAST_HALF | STRUCT_PEH_WARM / live h0_past_half | Promoted 7 Sep (Codex R8): the best all-90 and 2024+ RMSE of the three with a clean material record (v2.7 release eve: 0.400 all / 0.396 ex-January / 0.220 2024+ / 8-1); half of the PAST_FULL correction, still not an independently selected winner |
| Research | Legacy residual QRF, cold past-error QRF, ST | STRUCT_QRF, STRUCT_PE, STRUCT_ST | Retain for diagnosis; do not interchange with PAST_FULL |
| Scenarios | Reconstructed announcement rows (16.5), energy calculator, policy ledger | *_R and energy outputs | Mechanism checks; reconstructed magnitudes do not establish historical ex-ante skill |
| Gate closed | The reference and both challengers without any announcement entry | STRUCT_NOANN, STRUCT_NOANN_EVE, STRUCT_PE_WARM_NOANN(_EVE), STRUCT_PEH_WARM_NOANN(_EVE) | v2.7: permanent comparison for the documented January entries (ANNOUNCEMENT_ADOPTION_v27); the month-end column equals the v2.6 STRUCT, the release-eve column the v2.6 STRUCT_EVE (v2.7.1 gate G3) |
| Path product (step 2, 8 Sep) | `path_live.py`: origin = the month the live nowcast targets; h0 = the frozen trio (BASE_RIDGE anchor); h1..h12 = F1b, the component bridge with the plain frame at every horizon and the food seasonal mean from h = 4 (publishable under PATH_SPEC_v2: +25.7 / +29.6 / +17.2% over the seasonal-naive path at h 3 / 6 / 12, DM -1.9 / -2.5 / -2.9); second line always shown: the trend-and-gap path F2 (Kalman level + gap with the CNB survey expectation as a measurement, `models/trend_gap.py`), not publishable on the component span; beats the naive path at every horizon on origins since 2008 and is the better line in calm regimes (2024-26 beyond six months 0.87 vs F1b 1.10; against the CNB quarterly path 0.59 vs CNB 0.39 and F1b 0.70), the worse one in shocks; chained on the official index with published flashes as known first releases; naive path, RW, FMIE and CNB report averages as benchmarks; historical y/y error scale per horizon (all / 2024+) instead of bands; third line always shown, information only: the target line, the same trend-and-gap model anchored to the CNB target with no survey (PATH_SPEC_v3 E1 on 8 Sep morning; E7 from 8 Sep 10:50 by the PATH_SPEC_v4 rule: drivers unemployment change, koruna/euro twelve-month change lagged 3, real rate lagged 12, CZSO import prices; centred robust seasonal; FLAGGED: worse than E1 on 2008-2026 at h 12, 4.18 vs 3.96, and not publishable; rule amendment is the user's call); CNB quarterly report comparison printed with 0.5 pp flags, never an input | output/path_live_latest.csv; append-only output/path_live_log.csv (first row 8 Sep 2026, origin 2026-09) | Run after every live call; never edit a logged row; step 2 replaces the h >= 1 engine when it passes its rule |
| Path research, horizons 1-12 | PATH_BACKTEST_H_SPEC.md (8 Sep): diagnostics by horizon, regime, block and target month; quarterly averages; CNB quarterly report paths as benchmark (data/cnb_mpr_cpi_quarterly.csv); seven declared candidates, none adopted under the frozen rule | output/path_backtest_h*.csv and .log, path_backtest_h_hairy.png | y/y RMSE (h0 = print) 0.77 / 1.56 / 2.62 / 5.93 at h 1 / 3 / 6 / 12 vs naive 0.94 / 2.09 / 3.65 / 6.99; bias -0.1 to -3.1 (under-forecast, core level); January energy = 60-70% of m/m MSE; vs CNB quarterly forecasts: better 3-4 quarters out in 2022-23, half as accurate in 2024-26 (0.84 vs 0.39). Evidence -> step-2 F1b (plain frame, food seasonal from h 4, excise calendar) and F2 (trend with FMIE and CNB path as measurements) |
| CNB comparison rule (user, 8 Sep 2026) | `path_backtest_h_cnbq.py --match before` (default) and `path_step2_charts.py`: compare with the CNB only at its report dates, using the path we had already published when the report came out (last origin whose first release is on or before the publication date; that origin's release-eve path re-based on the known print, object b); publication dates read from cnb.cz (six 2024-26 placeholders corrected), cut-off dates stored beside them (`tools/cnb_mpr_cpi_quarterly.py`) | output/path_step2_cnbq_F1b.csv, output/path_step2_cnbq_F2_D1_fixed.csv (+ `_match_after` copies of the old convention), output/path_vs_cnb_*.png, artifact d7180026 | Product line vs CNB: reports 2022-23 (32 quarters) 3.23 vs 3.27, closer in 14 of 32; reports 2024-26 (34) 0.55 vs 0.37, closer in 16 of 34 (one quarter out 0.28 vs 0.28; four out 0.79 vs 0.43). Survey trend line 4.47 / 0.45 (four out 0.37 vs 0.43). The old convention (first origin after the report) gave us up to a month more information than the CNB had |
| Path research, step 5 (semi-structural gap model, CNB architecture) | PATH_SPEC_v5.md (8 Sep, declared before the run; amendment 1 = IS curve in annual differences): `models/gap_model.py` + `path_step5_backtest.py`: anchored expectations (A) or model-consistent fixed point (M, credibility weight 0.5), open-economy Phillips curve (level of the unemployment gap, koruna twelve-month change), IS curve on the ex-post real rate, market rate path from the Bloomberg FRA curve at the eve, random-walk koruna, handover from the nowcast and bridge for months 0-3 (H) | output/path_step5*.csv/.log (run 1 kept as `_run1_level_is`), output/path_step5_cnbq_*.csv | Phillips-curve signs right (slack 100%, koruna 94%); IS curve wrong-signed in 95% of origins in both forms (ex-post real rate is endogenous to inflation surprises) -> not eligible; S_A misses the long-span safeguard (4.05 vs E1 3.96); handover S_A_H publishable, 5% behind F1b at h 12, level with the CNB in the 2022-23 reports (3.25 vs 3.27). Model-consistent expectations best of any family in 2017-19 and 2024-26 (0.70 in run 1 vs survey 0.87), worst in 2010-16 and 2022-23 -> time-varying credibility weight and ex-ante real rate declared as the v6 candidates. Nothing adopted |
| Path research, steps 3-4 (survey-free trend) | PATH_SPEC_v3.md + PATH_SPEC_v4.md (8 Sep): target-anchored trend-and-gap variants E1-E7, hard-data drivers with sign checks, robust seasonal, wages (Eurostat LCI), import prices (CZSO CEN0303) | output/path_step3*.csv/.log, output/path_step4*.csv/.log (three runs kept) | Signs: unemployment right in 100% of origins; koruna right only as a twelve-month change lagged 3 (100%); real rate right only at 12-18 months (72-76%); wages wrong-signed in every origin (lagging variable, out); import prices right 71%, small. Long span h 12: E5 3.83 best survey-free (survey line 3.84, E1 3.96, naive 4.09); selected E7 4.18 (selection window 2008-2018 vs long span disagree). Robust seasonal neutral once centred (uncentered version biased the anchored level by ~1 pp a year, amendment 1). Nothing replaces F1b or the survey second line |
| Path research | Direct h1..h12 blocks evaluated as a y/y path (PATH_SPEC_v1.md, 7 Sep; scoring corrected the same night per Codex R8: common samples, exact percent) | STRUCT_H1/H3/H6/H12; output/path_experiment.csv, output/path_experiment_summary.csv | Beats the seasonal-naive path by 38.5 / 35.4 / 15.8% at h = 3 / 6 / 12 and the y/y random walk at 6 and 12 on common samples (DM −2.3 / −2.4 / −3.1; lag-12 sensitivity −1.9 / −2.3 / −3.2), so the frozen rule passes; long-horizon under-forecast carried by core and administered; still research, not a product; step 2 DECLARED 7 Sep (PATH_SPEC_v2.md, no run yet): index accounting first, then component bridge with the excise calendar, trend-and-gap state-space (two driver sets, ML and fixed signal-to-noise), small Minnesota BVAR, FMIE as a soft measurement of the trend shown separately, CNB report vintages as an annual benchmark |

**Frozen roster (7 September 2026, v2.7.1).** Three nowcasts are frozen for
the prospective record: BASE_RIDGE (reference), PAST_FULL (surprise-capture
challenger) and PAST_HALF (accuracy challenger). No further estimator or
feature change enters any of the three without a new declared spec, a
single run and its gates; the prospective record starts with the September
2026 call. For the first release, log all three side by side. Do not select
a different winner after each print or combine one model's point with
another model's position size: its predictive distribution and loss function
would not match that decision. Neither challenger is a proven survey beater.
Bands for the trio (BANDS_SPEC_v1.md, 7 Sep, single run): five declared
variants of the models' own past first-release errors; NONE met the
frozen coverage rule (80 / 90 coverage within 5 points on all origins and
on 2024+): the 90 band under-covers overall (0.82-0.86) and every variant
over-covers 2024+ (0.94-1.00) because the 2022-23 errors dominate the
pools. Per the rule the live row carries V1 (January / non-January pools)
flagged `band_status = uncalibrated`: `h0_<model>_lo80 / hi80 / lo90 /
hi90`, `band_n_pool`. Read them as the historical error spread, not as
calibrated probabilities. The reliability table in the spec is the sizing
input: a model 0.4 pp or more from the survey was closer to the print in
only 3 to 5 of 8-10 cases; PAST_FULL's useful zone is 0.2-0.4 pp (64%
closer, +0.08 pp, 22 months). The legacy `band_lo / band_hi` columns
still describe the residual forest.

The historical first-release comparison is regular CPI before 2025 and flash
from January 2025. Later detailed-release forecasts require a separate final
target and matching final consensus. Never compare a pre-final forecast with
the earlier flash and count that as first-release skill.

**Two decision times (v2.5).** Every backtest origin is evaluated twice
with the full pipeline: A = month-end of the target month (columns without
suffix: `STRUCT`, `STRUCT_PE_WARM`, `STRUCT_PEH_WARM`) and B = the day
before the first release (suffix `_EVE`). The scoreboard prints the same
metrics for both. B is the like-for-like comparison with the consensus,
which closes at release eve; at A the model has strictly less information
than the survey. In the backtest the two differ only through the fuel
Mondays published in between (FX is a complete month at both); live, the
month-end call can also differ through month-to-date FX. Accuracy at one
cutoff does not establish accuracy at the other; report both.

For large surprises use |actual-consensus| >= 0.4 pp and report actual error
reduction g = |actual-consensus| - |actual-forecast|. Keep material wins and
losses at 0.15 pp, sensitivity at 0.10/0.20, total error reduction, and every
alert including false calls. Direction alone does not establish an economic
win. Keep January, ex-January and recent periods separate; do not silently
exclude January from the headline claim.

Reporting layer (Codex R6, built 7 Sep; wedge error corrected 7 Sep per R8):
`contribution_report.py` prints, per origin, each block's weight x forecast,
its deviation from a neutral seasonal baseline (expanding same-month median
of the block's released history), the wedge separately as a reconciliation
residual, and the identity model - consensus = (baseline - consensus) + sum
of block deviations + wedge (holds to 1e-15); plus block-level uncertainty
as percentiles of the historical contribution error. The wedge's error is
forecast wedge minus the realised reconciliation (first-release print minus
the weighted realised block m/m), so the five block errors and the wedge
error sum exactly to the headline error (RMS of the wedge error 0.084 pp,
not the 0.022 the first version reported). Never read the wedge as a cause.
Output: output/contribution_report.csv.

Source map: cz_struct.py orchestrates the active components; data/struct_inputs.py
holds shared enrichment loaders; data/local_adapter.py accesses the database
and live sources; models/components.py contains measured fuel; models/horizon_models.py
contains TVWQRF; evaluation/ contains evidence classification; scoreboards_codex_p0.py
is the evaluation command. The root backtest_* scripts, food_experiment.py,
food_szif_experiment.py, food_category_experiment.py, late_info_tilt.py and
the earlier run_nowcast.py are research entry points. They remain
reproducible research, not the monthly operating command.

Closed food experiments (each predeclared, one run, frozen adoption rule;
the incumbent food block is unchanged by all three):
FOOD_EXPERIMENT_SPEC.md (level state-space, closed 6 Sep);
FOOD_SZIF_SPEC.md (weekly SZIF farmgate/processor signal, closed 7 Sep:
block 1-2% worse, correlation with the food m/m +0.06; the SZIF
publication-timing record in data/szif_publication_dates.csv and the EU
agri-food mirror in data/eu_agrifood/ stay as research material);
FOOD_CATEGORY_SPEC.md (ten ECOICOP classes, Individual Weighting of
class and pooled ridges, closed 7 Sep: combined aggregate worse than the
incumbent, pooled-only aggregate roughly level, vegetables the one class
where the naive same-month mean beats every model);
CORE_SEASONAL_SPEC.md (X-13 on the core target vs month dummies, plus an
Easter dummy, closed 7 Sep: core block level overall and 6% worse 2024+,
Easter term nil; X-13 lowers big-surprise MAE 0.642 -> 0.615 at the cost of
recent accuracy, logged as a possible surprise-capture challenger);
ALC_TOBACCO_SPEC.md (five-year same-month window and a sub-index split
for the alcohol-tobacco block, closed 7 Sep: January error down a fifth,
February-April and 2024+ ex-January worse, block 1-4% worse overall;
January-only window noted as the follow-up);
FLASH_SPEC.md (stage 1: same-month German and euro-area HICP food, goods
and services moves in the food and core ridges, release eve, finals as
flash proxy, closed 7 Sep: food block -10% over 90 origins from the 2022
months but +6% worse 2024+ and +16% worse in the flash era, core unmoved;
stage 2 not built);
FOOD_PRODUCE_SPEC.md (fruit and vegetables split out with same-month
means, closed 7 Sep: produce months -4%, 2024+ ex-January +5.5% worse);
EN_SPEC.md (elastic net in place of ridge in core and food, with and
without the foreign series, closed 7 Sep: core +1.6% worse, food +3.3%
worse; CV picks a near-zero penalty for core; the foreign food print
substitutes for the farmgate lag but the block is worse recently).

Next modelling work should be separately declared: repair publication clocks
and X13 cutoff/cache first, then food measurement and energy/tax accounting.
Only after an honest live loop is frozen should further forests, ensembles
or medium-term specifications compete on locked sequential evaluations.
