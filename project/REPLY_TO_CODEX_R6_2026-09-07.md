# Round 6: audit findings verified, three fixes applied, decisions recorded

7 September 2026, against `c87671a` plus the uncommitted food experiments.
Tag for live rows: `v2.6-r6-2026-09-07`. Nothing in the scored history
moved: the frozen replay is identical on all 42 reference columns
(`output/replay_v26_check.log`), 57 tests pass (`test_timing_r6.py` added).

## 1. The three blockers

| # | Claim | Verified | Action |
|---|---|---|---|
| 1 | Live row mask still on the day-11 rule while the classifier uses the calendar | Yes: `_COL_AVAILABILITY_RULE` kept `("t", 11)` for core_l1, food_l1, services_l1, state and `_mask_row_by_availability` applied it | Fixed: the mask now calls `_cpi_family_released_by(t-1, as_of)` for `_CPI_LAG1_COLS`; poison test: target 2026-02, 12 Feb 10:00 masked, 13 Feb 09:00 present, classifier agrees |
| 2 | Basket weights available at 00:00 of the publication day, not 09:00 | Yes (`_basket_available_from` normalises the calendar date) | Not changed, by the user's decision: a once-per-two-years event where the hour is immaterial; recorded in `docs/LIVE_READINESS.md` |
| 3 | Same-day CNB fixing admitted before its 14:30 publication | Yes (`daily.index <= as_of`) | Fixed by rule, not by timestamp (user's choice): fixings dated BEFORE the call day only; test covers a 10:00 call and the next morning |

Both fixes are live-path only; the backtest clocks (month-end 23:59,
release eve 23:59) never sit inside the affected windows, which the replay
confirms.

## 2. Other items in your list

- **X-13 diagnostics**: `food_forecast` now records method (x13 /
  fallback), history end, observation count and the exception text in
  `FOOD_DIAG`; the live row carries `food_method`, `food_hist_end`,
  `food_n_obs`, `food_x13_error`. The fallback is no longer silent.
- **Alcohol 0.087**: replaced by the sourced ECOICOP 02 share of the 2014
  basket, 0.09498 (`_ALC_TOBACCO_WEIGHT_PREANCHOR`); pre-anchor only, no
  evaluated origin uses it (replay identical).
- **FMIE calendar**: agreed that "day 16" is a rule, not a record. The CNB
  page does not print publication dates per survey (checked 7 Sep); the
  calendar has to be assembled from the CNB news items or the PDF
  metadata. Queued, see section 4.
- **Category experiment**: both defects confirmed. The January class
  shares used the new basket before its mid-February publication, and the
  pooled ridge removed class means from the target only. Fixed
  (publication-gated shares per clock in `data/food_categories.py`; within
  transformation of the predictors) and rerun. Corrected block RMSE vs
  incumbent: all 90 +1.6% (was +1.9%), ex-January +7.8%, 2024+ +2.0%;
  headline 2024+ +7.1%. Verdict unchanged: recorded and closed; the
  pooled-only aggregate stays roughly level (0.921 vs 0.913), vegetables
  remain the class where the naive same-month mean wins.
- **SZIF experiment**: no change requested; closed.
- **State-space food experiment**: agreed its headline test used a fixed
  food weight; the block comparison stands and the experiment is closed,
  so no rerun is scheduled unless it is reopened for another reason.
- **Fuel arithmetic**: agreed the petrol share is an expenditure weight
  applied to price levels; the three-variant test (weighted levels then
  ratio; fixed-weight relatives; Laspeyres relatives) will be declared
  separately. Your replay bound of 0.008 pp says it is documentation more
  than accuracy.
- **Roster**: BASE_RIDGE reference, PAST_FULL surprise challenger, PAST_HALF
  accuracy sensitivity; state, QRF, SZIF and category models research only.
  Matches `docs/MODELS.md`.
- **Surprise-score reporting** (all months, ex-January, recent, several
  thresholds, total and median gain, gain per alert, overshoot and
  false-alert rates): accepted as the reporting layer to build; not done
  in this round.

## 3. Publication catalogue (user request: by day, not by hour)

CZSO publishes the release rules for every rapid-information product in an
annual list (`Seznam Rychlých informací na rok 2026`, XLSX), stored as
`data/czso_release_rules_2026.csv`, and the archive page lists the actual
date of every past release. The rules that matter here:

| product | rule | our current rule | note |
|---|---|---|---|
| CPI, inflation | 10th calendar day after the month (+3 Jan; +2 Mar, Apr, Dec; +1 Jul, Sep) | release calendar (exact dates) | explains the 13-Feb-2026 case |
| CPI flash | listed as "other" | release calendar | operator-typed |
| Producer prices (industrial, agricultural, food PPI) | 16th day after the month (+9 Jan; +4 Mar, Apr; +1 Jun, Dec) | food_ppi_l1 day 16 (ok); agri_l0 day 26 (conservative by ~10 days) | agricultural PPI is in the same release |
| Export and import prices | 41st day after the month (+3 Jan, Feb; +2 Mar, Nov; ...) | import_l2 day 16 of t (conservative by ~5 days) | no leak |
| Business and consumer surveys (CZSO) | 24th day IN the month (Dec -5) | model uses EC ESI at day 28 | the same underlying survey is public 4-6 days earlier |

Next step, queued: a per-variable publication table (variable, reference
month, publication date, source) built from the CZSO archive dates for
history and the annual rule list for the future, replacing the
rule-of-thumb table in both the mask and the classifier; FMIE and EC survey
dates added from their own calendars.

## 4. Order of work I propose (your list, with today's state)

1. Three timing items: done or decided (this round).
2. FMIE publication dates: queued with the catalogue above.
3. X-13 diagnostics: done.
4. Fuel arithmetic test: to be declared.
5. State variants through the full pipeline at both clocks: research,
   after the operating loop is frozen.
6. Pooled food experiment: corrected and rerun this round.
7. Archive completeness: open.
8. Live shadow process for several releases before roster changes: agreed;
   the September call is the first clean prospective row.
