# Independent nowcast audit, 14 September 2026

Scope: `work/cpi-independent`, h0 nowcasts and the new consensus analysis. Read-only review of main files; all new evidence is in this directory. No network or live data loaders were used. Metrics were independently recomputed with Python 3.9 / numpy 1.21.5 / pandas 1.4.4 / statsmodels 0.13.2 from the stored release-level file; this is not a full forecast replay in the repository's pinned numerical runtime.

User scope update, 14 September: finding 2 below, the intraday basket-publication hour, is explicitly out of scope. Its original technical description is retained as audit history, not as a required fix or blocker. The main review reflects this decision.

## Actionable findings

1. **Incorrect shock concentration in the handoff.** `HANDOFF_TO_CODEX_2026-09-14.md:63` says three shock months are about 83% of squared error. Even the three largest HARD_BASE misses contribute only **57.31% of all SSE**: October 2022 +2.57295 pp, January 2023 -1.12685 pp, April 2022 -1.05814 pp. The named energy-policy trio January 2022 / October 2022 / January 2023 contributes **50.19%** of all SSE, or **68.38%** of 2022–23 SSE. January 2022 is actually one of the strongest model wins: forecast 4.378, actual 4.4, consensus 3.8. Clarify the denominator or replace the 83% assertion. Evidence: `audit_summary.json`.

2. **Basket publication timestamp loses nine hours.** `cz_struct.py:258` normalizes the detailed CPI release to midnight, although `_release_calendar` explicitly puts releases at 09:00 (`cz_struct.py:235–237`). `solve_weights` uses that normalized clock (`cz_struct.py:504`), as do petrol/energy basket selectors. Executing the exact pure functions reproduces 2026 basket availability at 2026-02-13 00:00 instead of 09:00. At 08:00, the new food/fuel/alcohol shares are used (.168584/.030631/.082871); at 23:59 the prior evening they are .177432/.035444/.084622. The correct CPI label gate still blocks January outcomes until 09:00. Preserve the original timestamp. This is an intraday correctness defect and does **not** alter the existing 90 release-eve forecasts. Evidence: `audit_clocks.py`, `clock_checks.json`.

3. **The recent regression t-statistic is conditional, not robust proof of survey skill.** The handoff's slope .583, t=3.50, R²=.297 reproduces exactly. `tools/review/nowcast_vs_consensus_20260914.py:45–47` uses ordinary homoskedastic OLS standard errors on 31 selected recent observations. January 2024 alone has leverage .713. HC3 yields t=1.68, p=.104, 95% CI [-.127, 1.292] for HARD_BASE; HALF/FULL yield t=1.37/1.42. HAC estimates are more significant, so this is sensitivity to covariance assumptions, not evidence of no signal. The separate paired loss test gives recent HARD_BASE t=-.844, p=.406; the RMSE edge is not statistically established. State this as promising retrospective evidence and preserve the explicit no-untouched-holdout / no-prospective-record qualification. Evidence: `surprise_regressions.csv`, `paired_loss_tests.csv`.

4. **Alert success is magnitude-only.** `independent_nowcast_experiment.py:59–62` counts an alerted large surprise even if the direction is wrong. October 2022 is counted as one of HARD_BASE's seven detected large surprises, despite forecast 1.173 versus consensus .9 and actual -1.4. This is internally consistent for a magnitude detector but must not be described as seven correct surprise calls. Directional large-alert hits are six for HARD_BASE/HALF, seven for FULL. The `big` frame's precision of 1 is tautological because rows were first conditioned on realized big surprises. Use full-sample alert precision, and separate direction and economic gains.

Minor robustness issue: the new review script's `abs() >= .4` lacks the scoreboard's epsilon. June 2020 (actual .6, consensus .2) is represented as .39999999999999997 and would be excluded. It lies before the February 2021 shrink scoring start, so the currently quoted shrink numbers are unaffected.

## Recomputed results

Every value in `output/independent_nowcast_scores.csv` matches independent recomputation within 1e-12, including counts, RMSE, MAE, bias, gains, wins/losses and alerts. There are 900 rows, ten models, and 90 common months from February 2019 through July 2026. Survey actuals and medians match the source survey file; every survey date matches the calendar's first-release date (71 regular, 19 flash).

RMSE in m/m percentage points:

| Model | All, n=90 | 2024+, n=31 | 2025+, n=19 | Big MAE, n=23 |
|---|---:|---:|---:|---:|
| HARD_BASE | .417952 | .218978 | .173002 | .484583 |
| HARD_HALF | .413696 | .219588 | .165601 | .479371 |
| HARD_FULL | .413931 | .225317 | .163827 | .476061 |
| LEGACY_BASE | .419917 | .216598 | .169696 | .505782 |
| Consensus | .381517 | .240966 | .194666 | .578261 |

HARD_BASE's recent reduction is 9.13% in RMSE, and 11.13% in the flash era. The recent edge survives removal of any individual month: model-minus-consensus RMSE ranges from -.03838 to -.00674; removing April 2024 reduces the edge most. Across the 26 recent non-big months HARD_BASE loses, .17796 versus .16756 RMSE. Thus the five recent large-surprise months supply the total recent improvement. Those five all have the right deviation direction, but only two cross the .2 alert threshold.

Material means at least .15 pp improvement/deterioration in absolute forecast error. An alert means deviation from consensus at least .2 pp in magnitude; a large surprise means actual minus consensus at least .4 pp in magnitude.

| Model/frame | Closer | Material wins/losses | Alerts | Magnitude big hits | False big alerts | Missed big |
|---|---:|---:|---:|---:|---:|---:|
| HARD_BASE all | 45/90 | 12/15 | 20 | 7 | 13 | 16 |
| HARD_HALF all | 43/90 | 10/11 | 22 | 7 | 15 | 16 |
| HARD_FULL all | 42/90 | 13/14 | 23 | 7 | 16 | 16 |
| HARD_BASE 2024+ | 19/31 | 4/2 | 4 | 2 | 2 | 3 |
| HARD_HALF 2024+ | 18/31 | 3/1 | 5 | 2 | 3 | 3 |
| HARD_FULL 2024+ | 17/31 | 4/3 | 5 | 2 | 3 | 3 |
| HARD_BASE 2025+ | 12/19 | 2/1 | 1 | 0 | 1 | 1 |

Recent HARD_BASE material wins: April 2024 +.3355 pp, June 2024 +.1504, September 2025 +.1797, December 2025 +.1824. Losses: July 2024 -.2900, July 2026 -.1523. The two recent false *large-surprise* alerts are July 2024 (wrong direction and costly) and December 2025 (correct direction, materially better). A false large-event alarm is therefore not automatically a bad forecast. In the flash-era sample the only big surprise was November 2025, and none of the HARD variants triggered an alert for it.

The expanding shrink rule faithfully uses past rows only for its coefficient. On its **66-month**, February 2021–July 2026 sample:

| Model shrink | RMSE all | Consensus all | RMSE 2024+ | Consensus 2024+ | Big MAE, n=20 | Consensus big MAE |
|---|---:|---:|---:|---:|---:|---:|
| HARD_BASE | .428770 | .424443 | .227401 | .240966 | .575622 | .600000 |
| HARD_HALF | .424297 | .424443 | .218771 | .240966 | .559349 | .600000 |
| HARD_FULL | .420722 | .424443 | .213669 | .240966 | .547962 | .600000 |

These numbers validate the handoff arithmetic; the full shrink only improves all-sample RMSE by .00372 pp (0.88%). The `all` shrink sample differs from the 90-month board. Chronological coefficient fitting does not make the model/specification choice, chosen window or latest-vintage inputs prospectively out of sample.

## Timing and model checks that passed

- `forecast_independent.py:27–31` requires timezone-aware input and consistently converts it to Prague wall time.
- Core ridge training restricts labels to past months and actual detailed release dates (`cz_struct.py:558–561`), with means/scales from the training slice only (`565–574`). Mutating all target-and-future outcomes to 999 leaves the exact extracted ridge prediction unchanged.
- Weights similarly use prior released outcomes (`cz_struct.py:485–489`). Mutating future headline/components/core/regulated/alcohol leaves all weights unchanged. Anchors sum to one through residual core, correctly described as a statistical projection rather than official decomposition.
- Independent residual errors are generated by sequential ridge forecasts, not the legacy error cache (`models/independent_nowcast.py:33–47`), and error labels are gated again before forest training (`59–60`). The 09:00 prior-day error clock versus 23:59 actual release-eve clock is inconsistent in convention but no affected observation was established on this release-eve sample.
- Food X13 is fit on released history only (`cz_struct.py:595–600`); fuel has an explicit observation +7 day cutoff (`863–875`).
- Announcement magnitudes admitted to the scored lane require allowed provenance and an available-from date before the clock (`cz_struct.py:706–715`); documented contributions use published basket item weights and the call's own administered coefficient. Historical magnitudes remain retrospective constructions; the 1.1 pp gate/January-only design is a specification-selection limitation, not a new proven target leak.
- Missing modern CPI calendar dates fail closed (`cz_struct.py:355–358`). `forecast_independent.py:205–217,328–331` requires both readiness and completion before release for prospective eligibility. The manifest and selection record explicitly retain pseudo-OOS/latest-vintage/no untouched holdout limitations.

No main repository files were modified. The exact source hashes and evidence output paths are in `audit_summary.json`.
