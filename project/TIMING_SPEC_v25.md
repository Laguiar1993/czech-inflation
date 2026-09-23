# Predeclared change v2.4 -> v2.5-timing (provisional pending Codex)

Declared 7 September 2026, BEFORE the rerun. Closes the four blockers in
`docs/LIVE_READINESS.md` that are code, and establishes the corrected
baseline at two decision times. Scope is timing and information sets only;
no estimator, weight rule, feature or hyperparameter changes.

## What changes

- **T1 Release calendar replaces the day-11 rule.** New file
  `data/release_calendar_cz_cpi.csv` with, per target month, the FIRST
  release (regular CPI before 2025-01, flash from 2025-01) and the DETAILED
  release date, each with a source tag. Historical dates come from the two
  Bloomberg ECO_RELEASE_DT tables already in `data/` (first release from the
  extended table; detailed release from the regular table's 2025+ rows,
  identical to the first release before 2025), cross-checked against the
  CZSO release pages for 2026 (13 Feb, 10 Jul, 11 Aug, 10 Sep detailed;
  5 Aug, 4 Sep flash). Future rows are typed from the "Next News Release"
  line of each CZSO release page (operator step, RUNBOOK). All CPI-family
  inputs (headline, divisions, CNB core and regulated) are public from the
  DETAILED release at 09:00 Prague; `_cpi_family_released_by` looks the
  month up in the calendar. Months outside the calendar (before 2010) use a
  conservative fallback of the 20th of the following month, flagged.
  `_basket_available_from` uses the January DETAILED release (D6).
- **T2 Food history filtered by the clock before X-13.** `food_forecast`
  restricts the history to months released by `as_of` before seasonal
  adjustment, in the primary and the fallback path.
- **T3 Content-keyed X-13 cache.** Key = (origin, last eligible month,
  length, hash of the eligible values); a changed input vintage refits.
- **T4 Eligibility applied to every component.** `solve_weights`,
  `admin_forecast`, `alc_forecast` and `_weighted_wedge` drop months not
  released by `as_of` in addition to the `known_through` cut. The cold and
  warm past-error histories already use the clock.
- **T5 Two decision times in the backtest.** For every origin the full
  pipeline is evaluated at (A) month-end, `as_of = last instant of t`, and
  (B) release eve, `as_of = first_release_dt(t) - 1 day, 23:59`. Existing
  columns keep their meaning (A). New columns carry suffix `_EVE`:
  `STRUCT_EVE`, `STRUCT_PE_WARM_EVE`, `STRUCT_PEH_WARM_EVE`, `STRUCT_PE_EVE`,
  `STRUCT_QRF_EVE`, `fuel_eve`, plus `elig_edge_eom` / `elig_edge_eve`
  (latest CPI-family month eligible at each clock). `STRUCT_PRE` and
  `STRUCT_PE_PRE` are retained and expected to equal their `_EVE`
  counterparts; the run prints the maximum difference as a self-check.
  Components whose eligible information set is identical at both clocks
  are reused, not refitted (the eligible index is compared explicitly).
- **T6 Live: month-to-date FX, aware clock, refresh report, stage from
  the calendar.** `eurczk_mm` for an incomplete month is the mean of CNB
  daily EUR fixings with date <= as_of over the previous full-month average
  (complete months keep the monthly-average table). The live clock is taken
  in Europe/Prague; rule comparisons use its wall time, the log stores the
  zone-aware timestamp (so the evaluation classifier can judge timeliness).
  The stage is derived from the calendar (pre_flash / pre_final /
  post_release) unless given explicitly. A per-source refresh report
  classifies each input at `as_of` as OK, STALE (expected but absent) or
  NOT_DUE, and the row records `n_stale` and `stale_sources`.
- **T7 Scoreboard: separate tables per decision time.** Same metric set
  for (A) and (B) for the reference and the challenger, with the consensus
  as the like-for-like comparator of (B) (the survey closes at release eve;
  at (A) the model has strictly less information than the survey).
- **T8 Tests.** The three strict expected failures in
  `test_known_limitations.py` become passing tests; new tests cover the
  calendar lookup (Jan-2026 detail not released on 11-12 Feb, released 13
  Feb 09:00), the food history filter, the cache key, eligibility in
  weights/admin/alcohol/wedge, the refresh classification, the MTD FX
  helper, and the zone-aware log stamp under the evaluation classifier.

## Expected effect (stated before the rerun)

- Backtest (A) columns: bit-identical to v2.4 for every origin. Reason:
  every eligibility change only bites when `as_of` precedes a release; at
  month-end of t all CPI-family months <= t-1 are released, and the
  calendar dates are all before month-end of the following month.
- Backtest (B) columns: new. Expected `STRUCT_EVE == STRUCT_PRE` and
  `STRUCT_PE_EVE == STRUCT_PE_PRE` to floating point, because between (A)
  and (B) only the fuel Mondays change (FX is a complete month at both).
- Live: numbers change only when a call is made before the detailed
  release of t-1 (food history, weights, admin, alcohol, wedge all shrink
  by one month) or before month-end (FX becomes month-to-date). The
  August dry run (pre_final, after the July detail release) is expected
  unchanged at BASE_RIDGE +0.38 / PAST_FULL +0.39.

## RESULTS (filled in after the rerun, 2026-09-07)

- (a) Every pre-existing backtest column bit-identical to v2.4 over all 90
  origins (`output/cz_struct_backtest_v24.csv` vs the v2.5 run): MET.
- (b) `STRUCT_EVE == STRUCT_PRE` and `STRUCT_PE_EVE == STRUCT_PE_PRE`: max
  difference 0.00e+00 over 90 origins: MET. The eligible CPI-family edge is
  t-1 at both clocks for every origin (as reasoned: the detailed release of
  t-1 always precedes month-end of t, and the calendar dates all precede
  release eve of t+1).
- (c) Tests: 49 pass, including the three former strict expected failures
  (`test_known_limitations.py`) now required to pass.
- (d) August dry run (pre_final, inferred from the calendar, 71 h before the
  10-Sep detailed release): BASE_RIDGE +0.38 / PAST_FULL +0.39 / PAST_HALF
  +0.39, identical to v2.4; the four missing inputs are now labelled STALE
  (published, absent from the database). September dry run: month-to-date
  FX from 4 fixings, stage `unknown` because its release dates are not yet
  published, 3 interaction columns correctly NOT_DUE.
- (e) Frozen replay: identical on all 42 reference columns of the v2.4
  expected file; 14 new columns reported.
- Final-code reruns: the backtest and the replay were repeated after the
  last two live-only edits (interaction classification, fail-closed for
  months absent from the calendar); see the reply to Codex for the
  byte-identity of run 2 vs run 1.

Two decision times, 90 first releases (consensus 0.3815 / 0.2410 / 0.3801 /
big-MAE 0.5783):

| Model | Clock | RMSE | 2024+ | ex-Jan | big-MAE | W-L@0.15 | sum g big | halves |
|---|---|---|---|---|---|---|---|---|
| BASE_RIDGE | A month-end | 0.7307 | 0.2141 | 0.4048 | 0.6416 | 6-3 | -1.458 | 3 |
| BASE_RIDGE | B release eve | 0.7292 | 0.2144 | 0.4041 | 0.6418 | 6-2 | -1.462 | 3 |
| PAST_FULL | A | 0.7273 | 0.2267 | 0.3989 | 0.5995 | 10-4 | -0.490 | 7 |
| PAST_FULL | B | 0.7262 | 0.2275 | 0.3992 | 0.5997 | 9-4 | -0.494 | 7 |
| PAST_HALF | A | 0.7258 | 0.2173 | 0.3959 | 0.6206 | 7-2 | -0.974 | 5 |
| PAST_HALF | B | 0.7244 | 0.2179 | 0.3957 | 0.6208 | 7-2 | -0.978 | 5 |

B minus A for BASE_RIDGE: mean +0.0012 pp, sd 0.009, largest 0.034 pp
(2022-02), no month beyond 0.05. Reading: in the historical record the
information that arrives between month-end and release eve and that this
model consumes is the last fuel Monday or two; it changes the headline by
less than a hundredth of a point on average. Before 2025 release eve fell
on days 8-15 of the following month, so every fuel Monday of the target
month was already in; in the flash era it falls on days 3-6 and the last
Monday can be missing. The consensus is itself a release-eve object, so B
is its like-for-like comparison and A understates the model's information
relative to the survey by construction.

**ADOPTED provisionally** under the rule below (all gates met). Codex
sign-off requested in REPLY_TO_CODEX_R5. Committed as the v2.5 baseline.

## Adoption rule

ADOPT v2.5 if (a) every pre-existing backtest column is bit-identical to
v2.4 (`output/cz_struct_backtest.csv` at `699e2e6`, preserved as
`output/cz_struct_backtest_v24.csv`), (b) the `_EVE` columns equal the
`_PRE` columns to 1e-9 where both exist, (c) the full test suite passes with
the three former expected failures now passing, (d) the August dry run is
unchanged, (e) the frozen replay reproduces the (A) columns of the v2.4
expected file exactly. If any (A) number moves, STOP: that is a found bug.
