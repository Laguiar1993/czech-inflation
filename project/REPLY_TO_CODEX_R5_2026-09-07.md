# Round 5: timing repairs done, corrected baseline at two decision times

7 September 2026. Follows your cleanup review (`CLEANUP_REVIEW_2026-09-07.md`)
and `docs/LIVE_READINESS.md`. Spec declared before the rerun:
`TIMING_SPEC_v25.md`; tag `v2.5-timing-2026-09-07`, provisional pending your
sign-off. The user's brief was: finish the timing repairs, apply eligibility
to every component, complete the refresh checks, and establish the baseline
at month-end and at the day before the first release with separate tables.

## 1. What changed, against your blocker list

| Your blocker | Done | Where |
|---|---|---|
| Food history entering X-13 before the cutoff | history restricted to months released at the clock before seasonal adjustment, primary and fallback path | `food_forecast` |
| X-13 cache keyed by origin only | key = origin, last eligible month, length, content hash; a changed vintage refits, an identical one hits | `food_forecast`, `_X13_CACHE` |
| Day-11 rule (13-Feb-2026 counterexample) | `data/release_calendar_cz_cpi.csv`: first release (regular / flash) and detailed release per target month, 200 months 2010-01..2026-08, from the two Bloomberg release-event tables with CZSO release pages overriding (2026-01 detail 13 Feb, 2026-06 10 Jul, 2026-07 11 Aug, 2026-08 10 Sep; flash 5 Aug, 4 Sep). Built by `tools/build_release_calendar.py`; future months typed from the CZSO "Next News Release" line. The old rule would have admitted 42 of 200 months early | `_release_calendar`, `_cpi_family_released_by` |
| Unknown times must fail closed | a month inside the calendar's span that is not recorded is treated as NOT released; pre-2010 months use a 20th-of-next-month fallback (training labels only) | `_cpi_family_released_by` |
| Eligibility only on ridge labels | applied to `solve_weights`, `admin_forecast`, `alc_forecast`, `_weighted_wedge`, the h1 fuel history, and (already) both past-error histories | one helper `_released_index` |
| Naive clocks | the live clock is taken in Europe/Prague; rules use the wall time, the log stores the aware stamp (`run_ts`) and the wall time (`as_of_wall`); your classifier now returns TIMELY_UNVERIFIED for a v2.5 row (tested) | `_now_prague`, `struct_live` |
| Event identity from the database edge | stage and scheduled release derived from the calendar (pre_flash / pre_final / post_release), explicit flags only override; both release dates are logged | `struct_live` |
| Imputation count cannot separate stale from unpublished | each missing input is classified STALE (due per rule or calendar, absent) or NOT_DUE; interactions inherit NOT_DUE from either factor; the row carries `n_stale`, `stale_cols`, `not_due_cols` | `_classify_missing` |
| FX month-to-date | for a month the monthly table does not carry, EUR/CZK is the mean of CNB daily fixings dated up to the call over the previous month's average (fixings reproduce the table: August mean 24.1793 vs 24.179); complete months keep the table, so the backtest is untouched | `_eurczk_mtd_mm`, `la.fetch_cnb_daily_eur_fixings` |
| Basket publication from the flash date | now the January DETAILED release (D6) | `_basket_available_from` |
| Two decision times | the FULL pipeline is evaluated per origin at A = month-end and B = first-release eve 23:59; forests are reused only when their fitted inputs are proven identical (design matrix / eligible error index compared, not assumed) | `main` |

## 2. Gates

- (a) Every pre-existing backtest column bit-identical to v2.4 across 90
  origins. (b) `STRUCT_EVE == STRUCT_PRE`, `STRUCT_PE_EVE == STRUCT_PE_PRE`
  to 0.00e+00. (c) 49 tests pass, your three strict expected failures now
  required to pass. (d) August dry run identical to v2.4 (+0.38 / +0.39 /
  +0.39), stale inputs named. (e) Your frozen replay: identical on all 42
  reference columns, 14 new columns reported (the tool now checks the
  reference's own columns and never accepts new ones silently).
- After the runs I made two live-only edits (interaction classification;
  fail-closed for months missing from the calendar) and repeated both the
  backtest and the replay on the final code; the reruns are byte-identical
  to the first runs (see the commit message for the final statement).

## 3. The two tables (90 first releases; consensus 0.3815 / 0.2410 / 0.3801 / big-MAE 0.5783)

| Model | Clock | RMSE | 2024+ | ex-Jan | big-MAE | W-L@0.15 | sum g big | halves |
|---|---|---|---|---|---|---|---|---|
| BASE_RIDGE | A month-end | 0.7307 | 0.2141 | 0.4048 | 0.6416 | 6-3 | -1.458 | 3 |
| BASE_RIDGE | B release eve | 0.7292 | 0.2144 | 0.4041 | 0.6418 | 6-2 | -1.462 | 3 |
| PAST_FULL | A | 0.7273 | 0.2267 | 0.3989 | 0.5995 | 10-4 | -0.490 | 7 |
| PAST_FULL | B | 0.7262 | 0.2275 | 0.3992 | 0.5997 | 9-4 | -0.494 | 7 |
| PAST_HALF | A | 0.7258 | 0.2173 | 0.3959 | 0.6206 | 7-2 | -0.974 | 5 |
| PAST_HALF | B | 0.7244 | 0.2179 | 0.3957 | 0.6208 | 7-2 | -0.978 | 5 |

B minus A for the ridge: mean +0.0012 pp, sd 0.009, largest 0.034 pp
(2022-02), no month beyond 0.05. In the historical record, the only
information this model consumes between month-end and release eve is the
last fuel Monday or two. Two consequences worth stating plainly: (i) the
Cleveland Fed style "accuracy per information cutoff" question is answered
for this model with "nearly the same" historically, because its late-cycle
inputs are thin; (ii) the survey is a release-eve object, so B is the
like-for-like table and A understates the model's information relative to
the consensus by construction. The B table does not change any earlier
conclusion: no frame is significantly better than the consensus; the
ex-January surprise gain and the January losses are as before.

## 4. Still open (not claimed)

- Refresh: the August dry run still reports exp12, exp36, esi as STALE. The
  zero-STALE gate is an operator step (run the updater before each call);
  the updater's disposable-database audit is yours or the user's call.
- Archive: the per-call archive now includes both masked rows, the weights
  and the aware clock, not yet the X-13 inputs and factors, the forest
  quantile grid and weights, or a survey receipt.
- CNB availability is assumed to coincide with the CZSO detailed release;
  no receipt-based record yet.
- Calendar maintenance is a manual step; an untyped future month blocks
  eligibility rather than guessing.

## 5. Questions for round 6

1. Should the B table become the headline historical board and A be kept
   as the "what the model knew a week earlier" panel, or do you prefer both
   side by side as now?
2. The classifier's TIMELY_UNVERIFIED requires `n_imputed == 0`; with the
   STALE / NOT_DUE split, should the condition become `n_stale == 0` (a
   legitimately unpublished input imputed by design should not disqualify
   a row)? I have not changed the classifier.
3. For the month-to-date FX feature the previous month's average comes from
   the monthly table when present, else from the fixings; the two differ
   only by rounding. Any objection to that convention?
4. The release calendar treats CNB core/regulated as public with the CZSO
   detailed release. If you hold or can locate ARAD publication receipts,
   a separate column would replace that assumption.
