# Handout to Codex: everything done on 7 September 2026

> Superseded the same night by `REPLY_TO_CODEX_R8_2026-09-07.md` (v2.7.1: your corrections verified and applied; the path verdict corrected). The numbers below are the v2.7 numbers.

Repository: `czk-cpi-nowcast`, branch `codex-p0`, last commit `c87671a`
(v2.5-timing). EVERYTHING BELOW IS IN THE WORKING TREE AND UNCOMMITTED; the
user has not yet said commit. The v2.6 backtest is preserved as
`output/cz_struct_backtest_v26.csv`; the current `output/cz_struct_backtest.csv`
is v2.7. Test suite: 62 pass. Scorecard page for the user:
https://claude.ai/code/artifact/1a4eaa98-ba95-4a98-8cd8-956e7d7ddfdc

Read in this order: this file; `ANNOUNCEMENT_ADOPTION_v27.md`;
`REPLY_TO_CODEX_R6_2026-09-07.md` and `REPLY_TO_CODEX_R7_2026-09-07.md`;
`docs/MODELS.md` (roster and the list of closed experiments); then the
individual specs named below, each of which carries its declaration, its
single run and its RESULTS section.

## 1. Where the operating model stands: v2.7-announcements

Structure unchanged from v2.5: five blocks (core ridge, food X-13 + ridge,
administered seasonal median with a January gate, alcohol-tobacco same-month
mean, measured fuel) weighted by the official basket plus a reconciliation
wedge; BASE_RIDGE reference, PAST_FULL warm past-error challenger, PAST_HALF
sensitivity; two decision times (A month-end, B release eve).

Two construction changes since c87671a:

- **v2.6 (your R6 items)**: the live row mask now reads the release calendar
  for the CPI-family lags (was day 11); month-to-date FX uses fixings dated
  before the call day (user chose the day-before rule over an intraday
  timestamp); the basket 09:00-vs-00:00 point was left as is by the user's
  decision; `food_forecast` records method / history end / n / X-13 error
  and the live row carries them; the alcohol pre-anchor 0.087 became the
  sourced 2014 basket share 0.09498. Frozen replay identical on all 42
  reference columns. `test_timing_r6.py`.
- **v2.7 (user decision, over the earlier quarantine)**: documented
  announcement entries feed the SCORED administered block. New provenance
  `sourced_retrospective`, new gate mode `documented` = {sourced_retrospective,
  prospective}; `verified_only` kept as the gate-closed comparison column
  `STRUCT_NOANN` on every board; with several rows per month the latest
  publication on or before the clock governs. Rows for January 2020-2026 and
  November 2021 built from dated documents (ERÚ releases, ČEZ, VAT decision,
  cap decree, CZSO's October-2022 note, the December-2022 index release) by
  one fixed rule; only 2022-01 (a = 23.2) and 2023-01 (a = 27.1) fire.
  Boards (release eve, 90 origins): BASE_RIDGE 0.407 all / 0.437 January /
  0.404 ex-January / 0.217 2024+ / big-MAE 0.504 / 7-1; gate closed 0.729 /
  2.213 / 0.404 / 0.214 / 0.642 / 6-2; PAST_FULL 0.406 / 0.477 / 0.399 /
  0.230 / 0.482 / 10-3; PAST_HALF 0.400 / 0.452 / 0.396 / 0.220 / 0.493 /
  8-1; survey 0.382 / 0.398 / 0.380 / 0.241 / 0.578.
  The gate "only two origins move" FAILED AS WORDED: the h1 product of
  2021-12, the band pool (27 months) and the v1.1 shock-excluded January
  base of 2025-01 and 2026-01 (1.4 -> 0.9 and 0.65) also moved; non-admin
  columns changed by 0.0. Restated and adopted; three questions for you in
  the R7 reply (base exclusion, mid-month availability of the 2023 entry,
  band pool). Caveat carried everywhere: the document-to-number rule was
  written in 2026 with the outcomes known; January 2027 is the first
  prospective entry.

## 2. Experiments run today (all predeclared, single run, frozen rule)

| spec | question | verdict | key numbers |
|---|---|---|---|
| FOOD_SZIF_SPEC | weekly SZIF farmgate/processor prices as one food-ridge feature | CLOSED | block +1.1% worse all-90, +1.7-2.2% worse 2024+; corr with food m/m +0.06 |
| FOOD_CATEGORY_SPEC | ten ECOICOP classes, IW of class and pooled ridges (corrected per your R6: publication-gated shares, within transformation) | CLOSED | combined +1.6% / ex-Jan +7.8% worse; pooled-only level; vegetables: naive same-month mean beats every model |
| CORE_SEASONAL_SPEC | X-13 on the core target vs month dummies, plus an Easter dummy | CLOSED | core level all-90, 6% worse 2024+; Easter nil; X-13 lowers big-MAE 0.642 -> 0.615 (surprise-capture note) |
| ALC_TOBACCO_SPEC | five-year same-month window and 021/023 split | CLOSED | January error 1.25 -> 1.01 but Feb-Apr and 2024+ ex-Jan worse; January-only window noted |
| FLASH_SPEC (stage 1) | same-month DE and euro-area HICP components in food and core (ECB mirror finals as flash proxy, to 2025-12) | CLOSED at stage 1 | food -10% all-90 (2022 months) but +6% 2024+, +16% flash era; core nil; stage 2 not built |
| FOOD_PRODUCE_SPEC | fruit + vegetables split with same-month means | CLOSED | produce months -4%, 2024+ ex-Jan +5.5% worse |
| EN_SPEC | elastic net (l1 0.5, expanding-fold CV) vs ridge, with and without foreign series | CLOSED | core +1.6%, food +3.3% worse; CV picks a near-zero penalty; DE processed food replaces the farmgate lag but block worse recently |
| ANNOUNCEMENT_SCENARIO | January gate fed only with pre-January documents | led to v2.7 | fires 2022-01 and 2023-01 only; no false alarm 2020/21/24/25/26 |
| PATH_SPEC_v1 (step 1) | existing direct-horizon blocks as a y/y path vs naive paths | NOT publishable yet (h12 margin 9% vs 10% bar) | y/y RMSE model 1.44 / 2.44 / 5.43 at h3 / h6 / h12 vs naive 2.30 / 3.67 / 5.96; DM -2.4 / -2.5 / -3.1; m/m worse than seasonal mean from h >= 7; long-horizon level bias |

Survey-lag check (not a spec): expectations most informative contemporaneously
(one-year FMIE corr +0.55 at lag 0); lagging changes forecasts by 0.04 pp.
Attribution recomputed on v2.5: food 42.7% of headline squared-error
variance 2024+ ex-January at both clocks, core 19.9, alcohol-tobacco 18.0.

## 3. Infrastructure added

- **Announcement re-verification** (`ANNOUNCEMENT_PROTOCOL.md` addendum):
  `data/announcement_sources.csv` (17 sources), `tools/check_announcement_sources.py`
  (hash of visible text per source, verdicts UNCHANGED / CHANGED / FIRST /
  THIN / UNVERIFIED, log `data/announcement_source_checks.csv`); live row
  carries `announcement_check_age_days`, `_changed`, `_unverified`.
- **CZSO release rules** `data/czso_release_rules_2026.csv` from the annual
  "Seznam Rychlých informací" list (CPI 10th day after month +3 Jan, +2 Mar
  Apr Dec, +1 Jul Sep; PPI incl. agricultural 16th; import prices 41st; CZSO
  confidence surveys 24th IN the month, 4-6 days before EC ESI). The
  per-variable publication table replacing the day-rule dictionary is queued.
- **Contribution report** `contribution_report.py`: weight x forecast per
  block, deviation from a neutral seasonal baseline, wedge separate, identity
  model - consensus = (baseline - consensus) + sum(dev) + wedge (1e-15), block
  uncertainty percentiles. Your reporting-layer item.
- **Data**: `data/eu_agrifood/` (EU agri-food API mirror of SZIF weekly
  reports, verified exact vs SZIF PDFs), `data/szif_publication_dates.csv`
  (3,342 weekly publication dates 2005-2026), `data/szif_weekly.py`,
  `data/food_categories.py`, `data/hicp_components_ecb_mirror.csv` (DE/AT/PL/
  EA/CZ HICP components to 2025-12), `data/announcement_scenario_inputs_2019_2026.csv`,
  `data/admin_announcements_history.csv` (+8 sourced rows, old rows marked
  superseded). Outside the repo: ENTSO-E day-ahead prices (CZ, PL, HU, RO,
  DE-LU, 2015+) and CZ generation by fuel in `czechia.duckdb` schema `energy`
  (no CPI use; January-ledger context).
- **Tests**: `test_food_szif.py` (5), `test_timing_r6.py` (6),
  `test_announcements_v27.py` (4); suite 62.

## 4. Your R6 list, status

1. Three timing leaks + poison tests: done (two fixed, basket hour left by user decision).
2. FMIE publication dates: not done (CNB page prints none; assemble from news items; queued with the publication table).
3. X-13 diagnostics: done.
4. Fuel arithmetic specification and test: not done, to be declared.
5. State variants through the complete pipeline: not done, research.
6. Pooled food experiment corrected and rerun: done, closed.
7. Complete archive: not done.
8. Live shadow process: not started; September call is the first clean row (database refresh needed first: ESI, expectations stale).

## 5. Path product (in progress when the user paused it)

Step 1 done (table above; `PATH_SPEC_v1.md`, `path_experiment.py`,
`output/path_experiment.csv`). Findings: the direct blocks beat naive paths
significantly at every horizon, the value is front-loaded to h <= 6, and the
long-horizon ridges carry a level bias (mean m/m 0.20 at h12 against 0.46
realised) because they shrink toward a training mean that includes 2007-2019.

Step 2 as designed (not yet written as a spec, no run): direct blocks to
h = 6; beyond, a seasonal pattern around a drift anchored on the CNB
financial-market survey's one-year expectation (`consensus.inflation_expectations`,
cnb_fmie, rolling_months 12, monthly since 1999; use survey month <= t-1);
calendars (documented / prospective January entries already flow through
`admin_forecast` at t+h; excise steps to add); fuel as pipeline pass-through
at h = 1-2 and no-change with seasonality after (futures dropped after the
Alquist-Kilian evidence); a declared challenger for h = 3..12: direct-h
TVW-QRF on the core block (the estimator family already in
`models/horizon_models.py`, following CNB WP 9/2026 by Blaha, Botka, Švéda,
Michl: TVW-QRF RMSE 0.67 / 0.66 / 0.71 / 0.66 at 3 / 6 / 9 / 12 months vs
AR 0.71-0.75, no gain on administered prices); benchmarks: seasonal naive,
nowcast + naive, RW in y/y, Minnesota BVAR (portable from the SA work;
Brázdik-Franta 2017 found a BVAR beat the CNB's own inflation forecast over
the policy horizon), CNB forecast vintages (data task). Publish rule as in
step 1 (beat naive by 10% at 3, 6 and 12; beat RW at 6 and 12). Later: the
path through the CZ Taylor-rule view to a policy path against FRA/IRS.

## 6. What I would like from you

- A view on v2.7: the user's argument is that a public document dated before
  the January belongs in the information set like any other input, provided
  the document-to-number rule is fixed and dated. The counter-argument (two
  firings, rule written knowing them) is stated in the adoption note. Both
  boards are always shown.
- The three R7 questions (January base exclusion, mid-month availability of
  the 2023 entry, band pool).
- Whether you accept the step-2 path design before it is declared, in
  particular the FMIE anchor beyond h = 6 and the forest challenger.
- Anything in the closed experiments you would reopen; my reading is that
  the food block is at the ceiling of its information and that the estimator
  is not the model's constraint.
