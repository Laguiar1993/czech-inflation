# Independent review of R27: an error-correction term for the food block, h1-6

18 September 2026. Reviewer working read-only on the repository; every probe and its output is under
`work/research_r27_review/`. Nothing outside this directory was modified. All numbers below come from the
reviewer's own code (`probe_common.py` and `probe_0*.py`), which reads the exported run files and the CSV
inputs directly and imports nothing from `models/food_ecm_r27.py`, `tools/research_r27/` or
`tools/path_diagnostics/` (the mutation probe is the one place the model file is loaded, as copies).

Summary of the verdicts: no look-ahead found (1); every headline number reproduces to 1e-15 (2); the gain is
real, broad-based and needs the producer-price level (3, 5); but the "estimator" is a constant, the speed
sits at the maximum of the formula's own closure curve, the declared dynamics are contradicted by the data,
the farm-price regressor is unjustified, and the tests do not exercise the one number that is the candidate
(4, 6, 7). **Promote with a re-labelled claim**, not as declared.

---

## 1. Look-ahead audit: nothing used at an origin was unpublished by its clock

**Checked** (`probe_01_lookahead.py`, outputs in `probe_01_lookahead/`): the 90 origin clocks against the
release calendar; the food stamps against the calendar; the producer/farm stamps against the reconstruction
rule and against five observed CZSO release pages; the slack of every series at the last common month;
`published_levels`/`last_common_month` by re-derivation; the vintage question.

- Clocks (`clocks.csv`): identical in R27, R24 and the FAST rows. For the 71 origins 2019-02 to 2024-12 the
  clock is 23:59 Prague on the eve of the origin month's CPI detail release (9.0 h before it). For the 19
  origins from 2025-01 it is the eve of the **flash** release (`first_release_kind = flash`), 81-201 h before
  the detail release. That is stricter than "the eve of the CPI release" and is not a problem: the origin
  month's food level is visible at 0 of 90 origins, the previous month's at 90 of 90.
- Food stamps: 139 of 139 months equal the detail release date at 09:00 Prague (`pipeline_available_from.csv`
  is built from `release_calendar_cz_cpi.csv` in `tools/r14_food/prepare_inputs.py`).
- Producer and farm stamps are **reconstructed, not observed**: PPI on day 16 of the following month
  (+9 January, +4 March/April, +1 June/December), farm prices on day 26, midnight Prague; the rule matches
  139/139 rows of the file. Observed CZSO "Producer price indices" publication dates
  (`web_checks_czso_release_dates.md`): June 2025 data on 16 Jul 2025, July 2025 on 18 Aug 2025, December 2025
  on 19 Jan 2026, January 2025/2026 on 25 Feb. The PPI reconstruction is within +/-2 days of these; the farm
  stamp is 7-10 days later than the release (conservative). Slack between the stamp of month t-1 and the
  clock (`slack_at_L.csv`): PPI minimum 7.0 days (median 24), farm 6.0 (median 15), food 18.6 (median 30);
  the minima are the 2025-26 flash-clock origins. A 2-day reconstruction error cannot move the last common
  month at any origin.
- `published_levels` / `last_common_month` (`reproduction_of_audit.csv`): L = origin-1 at 90/90 origins, equal
  to `ecm_audit.csv`; window length and start equal the audit at every origin (49 months at the first origin,
  the full 96 at the 43 origins from 2023-01); the reviewer's own gap, raw speed and h1-6 corrections reproduce the audit
  and `food_log_rates.csv` to 7e-15, 1e-15 and 1e-15; h7-12 corrections are exactly zero; h0, h7-12 food and
  every other block are identical between candidate and baseline in `native_forecasts.csv` (probe 9, 0.0).
- Vintages: the CZSO pages state "except for the construction work price indices, the published figures are
  final data", so the producer and agricultural price indices are not revised after release; the CPI is not
  revised. The farm panel here is the physical average producer prices of four products
  (`Průměrná cena zemědělských výrobků`, `data/cz_agri_prices_raw.csv`), for which the reviewer has no
  vintage evidence. Sensitivity if the last level were later revised (`vintage_sensitivity.csv`): a 1 log-point
  revision of the last PPI level moves the h6 cumulative correction by 0.28 (median; max 0.53) against a
  median absolute correction of 0.555; a 1-point farm revision by 0.06 (max 0.20). PPI monthly changes have
  SD 0.88, farm 1.99.

**Verdict: no issue.** The candidate uses only levels published by each origin's clock. Limit to carry: the
producer/farm availability is a day-of-month rule, verified against five releases, not a recorded calendar;
the levels are current vintage, which the CZSO says is final for the indices.

## 2. Reproduction of the headline numbers

**Checked** (`probe_02_reproduce.py`, `probe_02_reproduce/`): block cumulative log changes recomputed from
`value_food` and `actual_component_targets.csv` on the 969 support keys; headline annual rates recompounded
from `mm_forecast` and the frozen headline history; CNB pairs; bootstrap; phase gates; concentration.

- Block RMSE: 96 (model x horizon x era) cells agree with `food_family_scores.csv` to 2e-15, same n
  (84/81/75; 32; 24; 28/25/19). Candidate/baseline ratios: h3 0.960 / 0.962 / 0.969 / 0.902; h6 0.933 / 0.936
  / 0.946 / 0.833; h12 0.954 / 0.967 / 0.945 / 0.878 (full / 2019-21 / 2022-23 / 2024+). All twelve below 1.
- Assembled path: recompounded `yy_exante` equals `forecasts.csv` to 0.0; the nine condition-6 cells agree to
  9e-16 (h12 full 4.8008 -> 4.7689; 2024+ 0.6646 -> 0.6590; h6 2024+ 0.4912 -> 0.4629). CNB pairs from 2024,
  report clock, 34 pairs: 0.4386 -> 0.4053 (the pair forecasts equal the quarterly means of the recompounded
  path to 9e-16); by quarters ahead 0.245/0.394/0.520/0.583 -> 0.236/0.363/0.478/0.537 (n 10/9/8/7); 24 of 34
  pairs improve, the three largest carry 46% of the squared-loss gain.
- Bootstrap: the reviewer's copy of the scheme gives the same intervals to 1e-15 (h6 [-3.79, -0.84],
  h12 [-8.40, -2.34]); the upper bound stays below zero for all 200 seeds, for blocks 3/6/9/12/18/24 and for a
  stationary bootstrap. Support is contiguous (h6 2019-05..2026-01, 81 months; h12 2019-05..2025-07, 75).
- Phase: correlations 0.360 / 0.435 / 0.551 / 0.690 and sign agreement 0.61 / 0.61 / 0.73 / 0.64 (h3 full,
  h3 2024+, h6 full, h6 2024+), identical to `rule_verdicts.json`. 54 of 81 origins gain at h6; the top five
  (2022-01, 2021-12, 2021-11, 2022-04, 2023-03) carry 42.7% of the h6 squared-loss gain.

**Verdict: no issue.** Every figure in the claim is reproduced from the exported files.

## 3. Mechanism: the producer-price level is needed; the "equilibrium relation" is not stable

**Checked** (`probe_03_mechanism.py`, `probe_03_mechanism/variant_ratio_to_baseline.csv`): eight variants on
the same window, centring, speed rule, clip, decay and h1-6 activation, scored on the same support.
Era-balanced score = mean over the twelve cells of RMSE relative to the baseline (the evaluator's measure).

| Variant | h6 full | h6 2024+ | h12 full | era-balanced | 12 cells pass | alpha raw median |
|---|---:|---:|---:|---:|---|---:|
| CAND (trend + PPI + farm) = `FOOD_ECM_R27` | 0.933 | 0.833 | 0.954 | 0.932 | yes | -0.499 (100% clipped) |
| PPI (trend + PPI) = `FOOD_ECM_PPI_R27` | 0.917 | 0.893 | 0.952 | 0.930 | yes | -0.499 (100% clipped) |
| AGRI (trend + farm) | 1.035 | 1.414 | 0.992 | 1.105 | no | -0.251 |
| **TREND (own level on constant + trend)** | 1.036 | 1.078 | 1.010 | 1.033 | no (9 of 12 worse) | -0.028 |
| CONST (own level minus window mean) | 1.005 | 0.998 | 1.005 | 1.003 | no | +0.002 |
| MARGIN (food - PPI minus window mean, centred) | 1.002 | 0.885 | 1.018 | 0.994 | no | -0.040 |
| MARGIN_NC (same, uncentred) | 1.005 | 0.992 | 1.015 | 1.012 | no | -0.038 |
| MARGIN_T (food - PPI on constant + trend) | 0.897 | 0.785 | 0.977 | 0.905 | no (h12 2022-23 1.010) | -0.271 |

- The own-level control does **not** score like the candidate: it is worse than the baseline in nine cells and
  its unclipped speed is -0.03 a month. The mechanism is not reversal of the retail level around its own
  trend; the producer-price level carries the signal (h6 CAND minus TREND squared loss -3.43 [-7.56, -0.93]).
- The undetrended margin adds nothing (0.994); with a free trend and the coefficient fixed at 1 (MARGIN_T) it
  beats the candidate on the era-balanced score (0.905) but fails condition 1 in one cell. What matters is the
  trend plus a producer-price level; the estimated coefficient and the farm price are second order.
- The relation is not an equilibrium relation (`probe_08_other/relation_by_year.csv`): the PPI coefficient
  averages -0.39 in 2019, +0.32 in 2020, +0.53 in 2021, +0.78 in 2023 and +0.99 in 2025-26; the farm
  coefficient +0.43 in 2019 and -0.11 to -0.18 from 2024. In 2019-21 the gap is the residual of a curve fit
  in which producer prices enter with the wrong sign; the correction still helps in 2020 (0.71 at h6), so the
  economic story in the specification is not what the early-sample object is.
- The two declared candidates trade eras and are not distinguishable: PPI-only is better on the full sample
  and in 2019-21 and 2022-23 at h3 and h6 (0.917 against 0.933 at h6 full), the farm version from 2024
  (0.833 against 0.893); h6 CAND minus PPI +0.48 [-0.16, +1.24]; PPI is better at 54% of origins. The
  specification predicted "close"; the ratios differ by up to 6 points. The choice of `FOOD_ECM_R27` as the
  promoted object over `FOOD_ECM_PPI_R27` rests on the 2024+ cells alone, and the farm coefficient has had
  the wrong sign for a pass-through relation since 2023.

**Verdict: limits the claim.** The gain is not an own-level artefact, but "an equilibrium relation between
retail, producer and farm prices" is not what was estimated; the promoted object should not carry the farm
price unless the 2024+ preference is declared as the reason, and the two candidates should be reported as
equivalent.

## 4. Speed: -0.25 is not a clip artefact, it is the maximum of the formula's own closure curve; the estimator is a constant

**Checked** (`probe_04_speed.py`, `probe_04_speed/speed_ratio_to_baseline.csv`): fixed speeds -0.02 to -1.0 on
the candidate's own gap, plus the unclipped estimator (RAW), same formula, h1-6.

| speed | -0.02 | -0.05 | -0.10 | -0.15 | -0.20 | **-0.25** | -0.30 | -0.35 | -0.40 | -0.50 | -0.60 | -0.75 | -0.90 | -1.0 | RAW |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| h6 full | 0.986 | 0.969 | 0.951 | 0.940 | 0.935 | 0.933 | 0.933 | 0.934 | 0.937 | 0.944 | 0.953 | 0.969 | 0.987 | 1.000 | 0.941 |
| h6 2024+ | 0.965 | 0.923 | 0.878 | 0.852 | 0.838 | 0.833 | 0.833 | 0.836 | 0.842 | 0.861 | 0.884 | 0.924 | 0.968 | 1.000 | 0.872 |
| h12 full | 0.991 | 0.980 | 0.968 | 0.960 | 0.956 | 0.954 | 0.954 | 0.955 | 0.957 | 0.963 | 0.969 | 0.980 | 0.992 | 1.000 | 0.960 |
| era-balanced | 0.986 | 0.969 | 0.951 | 0.940 | 0.934 | 0.932 | **0.932** | 0.933 | 0.935 | 0.941 | 0.949 | 0.965 | 0.985 | 1.000 | 0.941 |
| h1-6 closure of the gap | 0.11 | 0.25 | 0.42 | 0.53 | 0.59 | 0.62 | 0.62 | 0.60 | 0.57 | 0.49 | 0.40 | 0.25 | 0.10 | 0.00 | |

- The score is flat between -0.20 and -0.40; the optimum is -0.30 in all eight h6 and h12 cells and -0.35 in
  three of the four h3 cells. Every speed from -0.02 to -0.90 passes condition 1; -1.0 equals the baseline.
- The reason is mechanical, not statistical: with L = t-1 and the h0 month skipped, the fraction of the gap
  the formula applies over h1-6 is sum_{k=1..6} a(1+a)^k, which peaks at a = -0.27 (0.617 at -0.25, 0.618 at
  -0.30); at h3 the peak is at a = -0.38. Faster speeds apply *less* correction because more of the gap
  "closes" in the unapplied h0 month. The grid therefore explores a one-parameter family whose total
  correction cannot exceed 0.62 of the gap; -0.25 sits where that cap binds. Finding 6 shows the data ask
  for about 2.5 times that.
- The estimator contributes nothing. Raw estimates are -0.30 to -0.58 at every origin (median -0.50), so
  alpha = -0.25 at 90 of 90 origins; the unclipped estimator scores 0.941, worse than the clip. The clip bound
  is the parameter, and it happens to sit on the plateau.
- Condition 3 as evaluated ("estimator distinguishable from the best fixed speed": -0.243 [-0.47, -0.07]
  against -0.15) is an artefact of a grid that stops at -0.15. Against -0.30 the interval is +0.003
  [+0.001, +0.006], "excluding zero" the other way by a trivial amount; against -0.20 it is -0.071
  [-0.14, -0.02]. The interval criterion has no materiality threshold and cannot say what it is asked to say.
  By the rule's own fallback ("the best fixed speed in the set passing condition 1, chosen by the era-balanced
  score") the promoted object is a fixed speed, -0.30 on the extended grid, -0.25 on the declared grid plus
  the estimator's own constant.
- Stability across years (h6, `best_speed_by_origin_year_h6`): -0.30 is best in 2020, 2021, 2022, 2023, 2024
  and 2025; 2019 (8 origins) and 2026 (1) prefer no correction (2019: 2.673 against baseline 2.478).

**Verdict: limits the claim; re-label.** The candidate is a fixed correction of about 0.6 of the gap over
six months, not an estimated adjustment speed. The specification's own expectation for this case
("if so, the promoted object is a fixed speed, and the results say so") applies.

## 5. Robustness: the h6 and h12 gains survive; the h3 gain is not established

**Checked** (`probe_05_robustness.py`, `probe_05_robustness/`): leave-one-origin-year-out, gain shares, sign
agreement per era and year, dependence and Diebold-Mariano, monthly errors.

- Leave one origin year out: worst ratio h6 0.949 (omit 2023), h12 0.963 (omit 2023), h3 0.981 (omit 2023).
  Year-only ratios at h6: 2019 1.079 (8), 2020 0.711, 2021 0.944, 2022 0.980, 2023 0.735, 2024 0.698,
  2025 0.895, 2026 1.108 (1).
- 2021-22 origins carry 39% of the h6 and 50% of the h12 squared-loss gain, but that is scale, not fragility:
  without them the ratio is 0.825 (h6) and 0.841 (h12); without the six origins 2021-11..2022-04 it is 0.907
  and 0.940; without the five largest gains it is 0.937 (h6, DM t -2.83) and 0.957 (h12, t -4.36).
- Sign agreement (needed against applied): h6 0.69 / 0.88 / 0.64 by era, h3 0.53 / 0.71 / 0.61. In 2019
  alone the correction is out of phase (h3 agreement 0.25, correlation -0.55; h6 correlation -0.51).
- Bootstrap validity: origins contiguous at h6 and h12 (finding 2); loss-difference autocorrelation 0.61 at
  lag 1 (h6) and 0.64 (h12), near zero by lag 6, so 12-month blocks are adequate. Newey-West DM t
  (lag 12): h3 -1.52, h6 -3.08, h12 -3.38; non-overlapping 12-month block-mean t significant at 5% in 4 of 12
  alignments at h3, 9 of 12 at h6, 11 of 12 at h12.
- Monthly food rates (`monthly_rate_errors.csv`): the candidate lowers the RMSE of every monthly rate h1-h6
  in every era (h1 0.985-0.994, h2 0.965-0.997, h3 0.973-0.980); h7-12 unchanged.

**Verdict: no issue at h6 and h12; limits the h3 wording.** The claim's "all twelve cells" is true as point
estimates; at h3 the full-sample gain (4%) is within noise.

## 6. Double counting and dynamics: no double counting, but the declared error-correction dynamics are wrong

**Checked** (`probe_06_double_counting.py`, `probe_06_double_counting/monthly_error_on_gap.csv`): the
baseline's food error (realised minus `FOOD_NORM_SHIFT_R24`, log points) at each monthly horizon and
cumulatively at h3/h6/h12 regressed on `gap_last` across origins, with Newey-West t; the same for the
candidate's error and for FAST's; an encompassing regression; the least-squares multiplier of the applied
correction.

| h | applied coefficient a(1+a)^h | slope of baseline error on gap | t (NW) | slope after correction | FAST slope |
|---:|---:|---:|---:|---:|---:|
| 1 | -0.188 | -0.173 | -1.85 | +0.015 | -0.188 |
| 2 | -0.141 | -0.196 | -2.05 | -0.056 | -0.211 |
| 3 | -0.105 | -0.295 | -2.79 | -0.190 | -0.310 |
| 4 | -0.079 | -0.304 | -2.56 | -0.225 | -0.319 |
| 5 | -0.059 | -0.456 | -3.41 | -0.397 | -0.472 |
| 6 | -0.044 | -0.466 | -3.03 | -0.421 | -0.481 |
| 7-12 | 0 | -0.42, -0.27, -0.33, -0.31, -0.25, -0.24 | -2.9 to -1.7 | unchanged | -0.43 .. -0.25 |

- At h1 the correction is right-sized (slope -0.173 against -0.188 applied; nothing left afterwards, t 0.16)
  and FAST's h1 error responds to the gap exactly as the R24 path's does (-0.188): the rate VAR carries no
  level information, so there is **no double counting**. The encompassing regression gives the gap a
  coefficient of -0.20 (t -2.9) at h1 and -2.07 (t -4.1) at cumulative h6 next to the baseline forecast.
- But the response does not decay as (1+a)^h; it **grows** through h5-h6 and persists to h12 with nothing
  applied. Cumulatively the baseline error loads on the gap with slope -1.92 at h6 (applied -0.617, 3.1x),
  -3.71 at h12 (6x), R2 0.30 and 0.37; by era at h6: -2.26 (2019-21), -4.04 (2022-23), -1.45 (2024+), all with
  |t| > 3. The least-squares multiplier of the applied h6 correction is 2.53 (2.5 / 2.8 / 2.2 by era); h6 block
  RMSE would be 3.65 with 2.5x the correction against 3.82 as applied and 4.10 for the baseline.
- These are pooled in-sample regressions on outcomes and are diagnostics, not a candidate; they say that
  what the candidate captures is the sign and a fraction of a slow-moving signal, not a six-month
  error-correction with speed -0.25.

**Verdict: limits the claim.** "Error correction at speed alpha" is not validated; the declared form applies
about 40% of the gap's h6 content and none of its h7-12 content. Promoting it as the mechanism locks in a
mis-specified shape.

## 7. Mutation probes: 3 of 16 mutants survive, including the clip bound

**Checked** (`probe_07_mutants.py`, copies in `probe_07_mutants/mutants/`, logs in `probe_07_mutants/`): 16
single-edit copies of `models/food_ecm_r27.py` loaded under the module name before pytest collected
`tests/test_food_ecm_r27.py`. An unmodified copy passes 8/8; a sabotaged copy fails (2 failed): the harness
works.

Killed (13): drop the trend; flip the sign of the correction; (1+a)^(steps-1); apply h1-12; ignore the
publication mask; no clip; speed on the contemporaneous gap; no minimum window; positive alpha allowed;
constant correction without decay; centring by the window mean instead of the month; window of 97 months;
last common month from food alone.

Survived (3):
- **M07 clip at -0.5 instead of -0.25.** The synthetic panel's estimated speed is -0.222, inside the clip, so
  the bound is never exercised. The clip bound is the candidate at all 90 origins (finding 4).
- **M08 gap taken at L-1 instead of L.** No test checks which month's gap is used.
- **M06 uncentred residual returned as the gap.** `test_gap_is_centred...` checks the audit numbers
  (residual mean, centred share) rather than the returned series; an OLS residual has mean zero anyway.

**Verdict: limits the claim.** The tests do not cover the one number that is the promoted object, nor the
gap month. Three tests to add before promotion: a panel whose raw speed is below -0.25 asserting alpha ==
-0.25; a test that the correction uses `gap.loc[last]`; a test that the returned gap has zero calendar-month
means.

## 8. Other things that bear on promotion

**Checked** (`probe_08_other.py`, `probe_09_misc.py`, `probe_10_headline_all_h.py`).

- **CNB lead test** (`cnb_lead_first_call_episodes.csv`, report clock, 0.30): full sample baseline 19 mature
  calls, 6 gains, 12 losses, 3 joint; candidate 17 / 4 / 10 / 3. From 2024: baseline 7 / 2 / 4 / 0, candidate
  5 / 0 / 2 / 0, mean absolute-error gain against CNB -0.27 against -0.22. The verdict "no lead over CNB"
  is unchanged; the 0.439 -> 0.405 pair RMSE does not produce lead calls, and from 2024 the candidate has no
  material gain where the baseline had two. (No issue for the rule; limits the assembled-path reading.)
- **Interaction with the R24 drift**: the same corrections on FAST's food block give h6 full 0.927 (R24: 0.933)
  but h6 2024+ 0.897 (R24: 0.833) and h12 2024+ 0.957 (R24: 0.878). Half of the 2024+ h6 gain and two thirds
  of the h12 2024+ gain exist only with the drift shift in place; the 10-17% from 2024 is a joint result with
  R24. The candidate worsens the block bias in every era (h6: full -0.93 -> -1.14, 2022-23 -1.47 -> -2.00,
  2024+ +0.07 -> +0.25; h12 2024+ +0.19 -> +0.50): the mean correction is -0.19, -0.54 and +0.21 by era
  against needs of the opposite sign on average; the whole gain is variance (h6 full variance 15.9 -> 13.3,
  squared bias 0.87 -> 1.29). (Limits the claim: it is a phase gain that adds a small bias.)
- **One-off months**: the largest monthly food surprises are 2022-04 (+3.1), 2022-01 (+2.6), 2022-05 (+2.4),
  2022-10 (+2.4), 2023-04 (-2.2); the origins whose h1-6 windows hold each of the first three carry 26-39%
  of the h6 gain, but removing all ten such origins gives a ratio of 0.894 at h6 and 0.975 at h3. The gain is
  not a one-off. (No issue.)
- **Assembled headline at every horizon** (`probe_10_headline_all_h/headline_ratio_by_h_era.csv`): 46 of 48
  (h x era) cells improve; two are worse by 0.05% (h1 and h2 in 2022-23). h12 gains are 0.7% (full) and
  0.8% (2024+); h6 2024+ 5.8%. (No issue.)
- **Benchmarks**: ZERO recomputed equals the evaluator's in all twelve cells; the candidate beats the best
  feasible member at h6/h12 (2024+ 1.84 against ZERO 2.27; 2.96 against 3.69). (No issue.)
- **Expectations written before the run** were wrong where it matters: median alpha expected -0.03..-0.10
  (got the clip, -0.25, at every origin); h12 expected within +/-2% (got -4.6%, inherited from h1-6);
  2019-21 expected to be the cell most likely to fail (got -6.4% at h6, because 2020 is the best year).

---

## Overall verdict

**Promote with a re-labelled claim.** Every accuracy condition of the R26 rule holds under independent
reproduction, the origins are contiguous so the intervals are valid, there is no look-ahead, the gain is
broad-based across years and does not depend on the surge months, and the producer-price level is what
carries it (the own-level control fails). What does not hold is the declaration:

1. It is not an estimator. alpha = -0.25 at 90 of 90 origins; the raw estimates (-0.30 to -0.58) score worse
   unclipped; any fixed speed from -0.20 to -0.40 scores the same, and the declared grid's stop at -0.15 is
   the only reason condition 3 read "distinguishable". Under the rule's own fallback the promoted object is
   a fixed speed (-0.25 or -0.30, equivalent), named as a number, exactly as R24 was re-labelled.
2. It is not error correction with those dynamics. The gap's effect on the baseline's monthly error grows from
   -0.17 at h1 to -0.47 at h6 and persists at -0.24 to -0.42 through h12; the declared shape applies 0.62 of the
   gap over six months where the data load 1.9 at h6 and 3.7 at h12. The right label is "a fixed level
   correction of sign minus the gap, closing about 0.6 of it over h1-6"; a follow-up round should declare the
   persistent form before anyone reads the speed as economics.
3. The relation is not the equilibrium of the specification: the producer-price coefficient is negative in
   2019-20 and the farm coefficient negative from 2023; the PPI-only candidate is as good or better
   everywhere except from 2024. Carry both as equivalent, or declare the 2024+ cells as the reason for the
   farm price.
4. Three tests must be added first (clip bound, gap month, centring of the returned gap): three of sixteen
   mutants survive, and one of them changes the promoted number.

Points 1-3 change what is written on the roster, not whether the food block improves; point 4 is a
precondition. If the author will not re-label, the honest alternative is to record the round as "passes
conditions 1, 2, 4, 5, 6; condition 3 not met as an estimator; promoted as fixed speed -0.25 pending tests".
