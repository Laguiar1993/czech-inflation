# Path product, step 2: declaration (no run yet)

Declared 7 September 2026, night, BEFORE any code beyond the index
accounting is written. Step 1 (PATH_SPEC_v1.md, corrected scoring)
established that the direct-horizon blocks beat the seasonal-naive path
by 38.5 / 35.4 / 15.8 percent at 3 / 6 / 12 months on common samples and
that the twelve-month under-forecast sits in the core and administered
blocks. Step 2 follows the reviewer's design: one index-accounting
system, three model families with few variants, the survey expectation as
a soft constraint shown separately, forests only after the three have
been scored. Nothing here feeds back into the release nowcast; the trio
stays frozen.

## 1. One index-accounting system (built first, tested before any model)

- Monthly headline index path with exact calendar labels (no positional
  shifts; a gap in an index fails loudly), continuous through the origin's
  release-eve information set.
- One definition of h: months after the last released CPI month t-1, so
  h = 1 is the month being nowcast. The nowcast at h = 1 is the frozen
  release-eve trio (BASE_RIDGE as the path's anchor; the two challengers
  reported as alternative anchors, not blended).
- Basket weights by as-of regime (`_basket_available_from`), the same rule
  as the nowcast; future Januaries beyond the published basket keep the
  latest published regime.
- Derived from the same path, never separately: m/m, y/y in exact percent
  (100 x (exp(L/100) - 1) with L the log sum, or chained index levels),
  quarterly averages, calendar-year averages, and the cumulative future
  price-level error.
- Targets: first-release y/y for the month being nowcast; the latest
  consistent vintage index path for h >= 2 (CZ CPI is unrevised in
  practice; the two coincide except for the flash-final difference, which
  is recorded).
- Scoring: common valid samples per horizon for every method, pointwise
  y/y RMSE in exact percent, cumulative price-level RMSE, and coverage
  where a method produces bands; Diebold-Mariano with HAC lag h-1 and a
  lag-12 sensitivity, plus a block bootstrap (block 12) of the loss
  differential; no unconditional "significant" claims.

## 2. Families (variants fixed here)

### F1 Component bridge (near-term candidate; the step-1 machinery, three changes)
- Horizons 1..12 as in step 1 (core ridge direct-h with the slow block from
  h >= 4, food X-13 + ridge direct-h, alcohol-tobacco same-month mean,
  wedge at t+h), with:
  (a) administered block = seasonal median plus the energy and excise
  calendar: documented / prospective January entries as in v2.7.1 at
  their as-of; excise steps for tobacco and alcohol from the law in force
  at the origin (a small table `data/excise_calendar.csv` with effective
  month, item, statutory change and publication date; only rows with a
  publication date before the origin count);
  (b) fuel: measured weekly for h = 1 (as now); for h = 2 the last
  observed weekly level carried flat against the h = 1 month's average;
  h >= 3 the same-month median of the official fuel m/m (as now). No
  futures.
  (c) no change to the estimators (the closed elastic-net and X-13-core
  experiments stand).
- Variants: none beyond (a) with and without the excise table (two runs
  of the same code, the difference is the table).

### F2 Trend-and-gap state-space (medium-term challenger)
- Monthly headline m/m (seasonally adjusted by the same one-sided X-13
  used in the food block, per origin) = trend_t + gap_t + noise, with
  trend_t a random walk (local level) and gap_t an AR(1) driven by a small
  set of lagged, publicly available variables. Estimated by the Kalman
  filter per origin on data released at the origin's release-eve clock;
  the filtered (not smoothed) state at the origin is projected forward.
  Two driver sets, no search:
  D1 (minimal): the core block's state variable (trailing y/y above 4%)
  as an intercept shift in the gap equation; nominal wage growth (CZSO
  quarterly, `czso.wages_headline`, last released quarter carried, no
  interpolation); EUR/CZK monthly change (`monetary.fx_monthly`).
  D2 (open economy): D1 plus import prices (`import_l2` as in the core
  frame) and the unemployment rate change (`czso.unemployment_ri`,
  released series, or `eurostat.unemployment_lfs`).
- Variance parameters estimated by maximum likelihood on the origin's
  window (minimum 96 months); a fixed signal-to-noise ratio variant
  (trend variance = 1/50 of the noise variance) as the robustness twin, so
  that four runs exist: D1-ML, D1-fixed, D2-ML, D2-fixed. Nothing else.
- The FMIE one-year expectation (`consensus.inflation_expectations`,
  cnb_fmie, 12 months, mean; survey month <= origin) enters ONLY as a
  measurement of the trend with its own noise variance (estimated), never
  as a pasted drift; a run without it is the control. Its implied
  twelve-month path is also reported on its own as the "soft constraint"
  line, separate from the model path.

### F3 Small shrinkage BVAR (independent benchmark)
- Monthly VAR in: headline m/m (SA as above), core m/m, EUR/CZK change,
  Brent in CZK change (`data/bbg_commodities_daily.csv` monthly average),
  the 3-month PRIBOR change (`monetary.pribor_daily`), the ESI level
  (`eurostat.bcs_survey`); 6 variables, 6 lags, Minnesota prior with the
  literature defaults (overall tightness 0.2, cross-variable 0.5, lag
  decay 1, sum-of-coefficients 1), estimated per origin on released data;
  the code is `models/bvar.py` (ported in August) with the prior fixed a
  priori. One variant. Direct-h forecasts of the headline m/m chained
  through the index accounting.

### Benchmarks
Seasonal-naive path (B1), nowcast + seasonal naive (B2), random walk in
y/y (B3), the FMIE line at h = 12 (B4), and the CNB Monetary Policy
Report calendar-year inflation forecast from the vintage table
(`cnb.mpr_vintages`, annual only) scored on the calendar-year average of
the path for the years it covers (B5).

## 3. Evaluation and publish rule (frozen)

Origins 2019-02..2026-07, release-eve clock; horizons 1..12 with the
common-sample rule; splits: ex-January targets, 2024+ targets, 2022-23
targets. A family is "publishable" when it beats B1 by at least 10% in
exact-percent y/y RMSE at h = 3, 6 and 12 AND beats B3 at 6 and 12 on the
common samples, with the DM statistic negative at lag h-1 and lag 12. The
product is the best publishable family by CRPS-free RMSE at h = 12, with
the near-term months (h <= 3) always taken from F1 when F1 is publishable
at those horizons; no blending weights are fitted. If two families are
publishable and within 3% of each other at h = 12, both are published
side by side (the roster rule: one reference, one challenger). Forest
challengers (direct-h TVW-QRF on the core block, CNB WP 9/2026 pattern)
are declared only after this step's results, as their own spec.

## 4. Order of work

1. Index accounting module with tests (calendar join, weights as-of, exact
   percent identity against the official y/y, cumulative level).
2. F1 with the excise table; rerun on the same harness; record.
3. F2 four runs; F3 one run; benchmarks; the DM and bootstrap tables.
4. RESULTS section here; then the roster line in docs/MODELS.md.
Data tasks before 3: excise calendar table (sourced, dated); confirm the
wage and unemployment release dates in `meta.release_calendar`.

## Amendment, 8 September 2026 (after PATH_BACKTEST_H_SPEC RESULTS; before any step-2 run)

- F1 is scored in two definitions: F1a = the step-1 engine as is (P0 of the
  horizon backtest); F1b = plain frame at every horizon, food seasonal
  mean from h = 4, plus the excise calendar. Both are scored; F1b is a
  simplification with a documented rationale (P1 and P7 of the horizon
  backtest), not a tuned variant.
- F2 gains a variant with the CNB Monetary Policy Report's quarterly CPI
  path (`data/cnb_mpr_cpi_quarterly.csv`, available from each report
  date) as a second noisy measurement of the trend, alongside the FMIE.
  Both measurements enter with estimated noise variances; a control run
  without either is kept. Neither is pasted into the path.
- Benchmark B5 is the CNB quarterly path itself, matched at the first
  origin after each report date (not annual averages; the vintage table's
  annual values are first-quarter values, see the horizon backtest
  RESULTS).
- Publication rule unchanged; add to the product output the quarterly
  averages up to three quarters ahead and the twelve-month point flagged
  "level, not timing".

## Amendment 2, 8 September 2026 (data-availability decisions, written BEFORE the step-2 run)

- Training history for F2 and F3 starts 1998-01 (the inflation-targeting
  regime); the extended headline series (`load_headline_cpi_mm_extended`,
  CZSO from 2015, FRED/OECD before) carries transition-era Januaries of
  1991-1993 that would dominate an expanding seasonal mean.
- F2 drivers as the database allows over that span: D1 = no drivers; D2 =
  EUR/CZK monthly change (`monetary.fx_monthly`), the change in the LFS
  unemployment rate (trend-cycle, total, `czso.unemployment_ri`, lagged
  one extra month for its publication lag) and the ESI deviation from its
  training mean (`eurostat.bcs_survey` BS-ESI-I). Wages (quarterly from
  2015) and import prices (from 2015) are too short for a 1998 start and
  are left to a later variant.
- F3 variables: seasonally adjusted headline m/m (same expanding
  same-month means as F2), CNB core m/m (2007+, adjusted the same way),
  EUR/CZK monthly change, ESI level, 3-month PRIBOR monthly change (ARAD
  SFTP04M2206), unemployment change. Three lags (six with this sample
  would leave under three observations per parameter before the prior);
  Minnesota prior as declared; origins from 2013-01 (core from 2007 plus
  the minimum window).
- Seasonality in F2 and F3: expanding same-month means of the released
  history removed before estimation and added back to the forecasts;
  no X-13 on the headline (deterministic, cheap, no leakage).
- F2 variant selection is made on the origins 2008-01..2018-12 ONLY (h =
  12 RMSE, object (b)), before any comparison on the component span
  2019-02..2026-07, so that the family comparison is out of selection.
- Object (b) (h0 = the print) is the primary object over the long span;
  object (a) (h0 = the frozen nowcast) exists from 2019-02 only.
- The publish rule of section 3 is applied on the component span; the
  long span is reported for F2, F3 and the benchmarks as context.

## Note, 8 September 2026: a first run of the step-2 harness scored F2 and F3 one month off (their history ends at t-1 while the path's h counts from the nowcast month t; the forecast for t+h needs the model's h+1 step). Its files are kept as `output/path_step2_*_misaligned_first_run.*`; F1a, F1b and the benchmarks were unaffected. The RESULTS below are the corrected rerun.

## RESULTS (8 September 2026, corrected rerun; logs `output/path_step2_run.log`, `output/path_step2_combo.log`, `output/path_step2_cnbq_F1b.log`, `output/path_step2_cnbq_F2_D1_fixed.log`; rows `output/path_step2.csv`, `output/path_step2_combo.csv`)

### The pillars, as built

1. Anchor: the frozen release-eve nowcast (BASE_RIDGE) for the month
   being nowcast; published flashes enter as known first releases.
2. Near term (F1, component bridge): the five blocks forecast directly
   at each horizon with the information released at the origin, weighted
   by the basket regime of the target month, priced administered events
   from dated documents only.
3. Medium term (F2, trend and gap): a slowly moving level plus a decaying
   gap on the headline, estimated by the Kalman filter per origin from
   1998, with the CNB financial-market one-year expectation as a noisy
   measurement of the level. Seasonality by expanding same-month means.
4. Benchmarks that must be beaten and a rule written before the run.
Nothing feeds back into the nowcast; every forecast uses only what was
public at the origin's clock.

### F2 variant selection (origins 2008-01..2018-12, h = 12, object (b), n = 132)

D1-ML 1.053, D1-fixed 1.052, D1 without the survey measurement 1.890,
D2-ML 1.072, D2-fixed 1.070. Selected: D1-fixed (signal-to-noise 1/50, no
drivers). The survey measurement is what makes the trend model work:
without it the twelve-month error is 80% larger. The open-economy drivers
add nothing at this sample size.

### Long span, origins 2008-01..2026-07, object (b), y/y RMSE in exact percent

| h | n | F2 (D1-fixed) | bias | naive | RW |
|---|---|---|---|---|---|
| 1 | 222 | 0.57 | -0.09 | 0.63 | 1.10 |
| 3 | 220 | 1.21 | -0.29 | 1.37 | 1.83 |
| 6 | 217 | 2.02 | -0.60 | 2.30 | 2.80 |
| 9 | 214 | 2.93 | -0.90 | 3.21 | 3.71 |
| 12 | 211 | 3.84 | -1.23 | 4.09 | 4.47 |

The trend model beats the seasonal-naive path at every horizon on
eighteen years of origins (10% at one month, 12% at three, 6% at twelve)
and the y/y random walk by more. Against the survey's own one-year
expectation at h = 12 (n = 211): FMIE 3.68, F2 3.84, naive 4.09. F3
(Minnesota BVAR, origins 2013+): 0.65 / 1.43 / 2.42 / 3.55 / 4.65 at h 1 /
3 / 6 / 9 / 12 against F2 0.65 / 1.39 / 2.36 / 3.44 / 4.52 and naive 0.72 /
1.57 / 2.66 / 3.72 / 4.77: the BVAR is a close second to the trend model
everywhere and never better.

By regime of the target, h 7-12, F2 / F3 / naive / RW: 2008-09 1.19 / - /
1.95 / 4.56; 2010-12 0.84 / - / 0.96 / 1.19; 2013-16 0.78 / 1.61 / 1.15 /
1.08; 2017-19 1.00 / 0.59 / 1.13 / 1.08; 2020-21 2.10 / 1.90 / 1.75 / 1.55;
2022-23 8.76 / 8.83 / 8.45 / 8.97 (F2 bias -6.88); 2024-26 0.87 / 1.72 /
3.84 / 4.86. No family forecasts the 2021-23 surge; the trend model
under-forecast it by nearly seven points a year out, as did every
benchmark and the central bank.

### Component span, origins 2019-02..2026-07 (the product's span)

Object (b), h0 = the print:

| h | n | F1a | F1b | F2 | F3 | naive | RW |
|---|---|---|---|---|---|---|---|
| 1 | 88 | 0.77 | 0.77 | 0.82 | 0.83 | 0.94 | 1.57 |
| 3 | 84 | 1.56 | 1.56 | 1.83 | 1.87 | 2.10 | 2.70 |
| 6 | 78 | 2.62 | 2.57 | 3.25 | 3.29 | 3.65 | 4.31 |
| 9 | 72 | 4.16 | 4.05 | 4.89 | 5.01 | 5.28 | 5.92 |
| 12 | 66 | 5.93 | 5.79 | 6.66 | 6.81 | 6.99 | 7.43 |

Bias at h = 12: F1a -3.14, F1b -2.36, F2 -3.42, F3 -3.35. Object (a),
h0 = the nowcast: F1b 0.93 / 1.61 / 2.68 / 4.18 / 5.79. Quarterly averages
1 / 2 / 3 / 4 quarters ahead: F1b 1.59 / 2.62 / 4.05 / 5.27, F2 1.84 / 3.26 /
4.89 / 6.08, naive 2.10 / 3.65 / 5.24 / 6.37. By regime at h 7-12, F1b /
F2 / naive: 2019-21 2.23 / 2.35 / 1.86; 2022-23 7.30 / 8.76 / 8.45;
2024-26 1.10 / 0.87 / 3.84.

### Publish rule (component span, object (b))

F1a: gains over naive +25.7 / +28.3 / +15.1% at h 3 / 6 / 12, DM -1.9 /
-2.5 / -3.1 (lag 12: -1.9 / -2.5 / -3.2), block-bootstrap p 0.06 / 0.03 /
0.00, beats RW: PUBLISHABLE. F1b: +25.7 / +29.6 / +17.2%, DM -1.9 / -2.5 /
-2.9, p 0.07 / 0.02 / 0.01: PUBLISHABLE. F2: +12.5 / +10.8 / +4.6%, DM at
h = 12 -0.66: not publishable. F3: +10.9 / +9.9 / +2.7%: not publishable.

### Against the CNB staff forecast (quarterly report paths, matched at the first origin after each report)

Reports 2022-2023 (27 quarters): CNB 3.50, F1b 3.19, F2 3.62, naive 4.03;
F1b bias -0.08 against CNB -1.41. Reports 2024-2026 (26 quarters): CNB
0.39, F1b 0.70, F2 0.59, naive 2.51; by quarters ahead F2 0.58 / 0.69 /
0.51 / 0.39 against CNB 0.32 / 0.41 / 0.41 / 0.52 and F1b 0.48 / 0.68 /
0.93 / 0.66. In the calm regime the central bank's judgemental path is
the most accurate of the three; the trend model closes about a third of
the bridge's gap to it at two quarters and more beyond. In the shock the
bridge was the best of the three, the CNB second.

### Step 2b, declared before computing: bridge for the near months, trend beyond

C3 (F1b for h <= 3, F2 after) and C6 (F1b for h <= 6, F2 after), rule:
replace F1b only if at least 5% better at h = 12 on the full span, not
more than 2% worse in either origin half, and publishable. Result: C3
-5.8% (first half -5.9%, second half -1.6%), C6 -2.9% (-3.0%, +0.1%);
both publishable, neither replaces F1b. By regime at h 7-12: 2024-26 F1b
1.10, C6 1.01, C3 0.98, F2 0.87; 2022-23 F1b 7.30, C6 7.42, C3 7.69, F2
8.76. The combination helps only in the calm regime, and there the trend
line alone helps more.

### Decisions

- Product engine for h >= 1: F1b (plain frame at every horizon, food
  seasonal mean from h = 4). `path_live.py` DEFAULT_ENGINE = F1b. The
  near-term months are identical to F1a.
- Second line, always published next to the product: the trend-and-gap
  path (F2 D1-fixed), labelled "trend line". It is the better path when
  nothing breaks (2024-26 beyond six months 0.87 against 1.10; against
  the CNB 0.59 against 0.70) and the worse one when something does
  (2022-23: 8.76 against 7.30); the user sees both with this evidence.
- F3 stays research. The excise calendar was deferred (alcohol-tobacco
  carries 2-3% of the path error). Wage and import-price drivers, the CNB
  path as a second trend measurement, and forest challengers remain
  declared, not run.
- No calibrated path bands; the per-horizon historical RMSE is the error
  scale. Direction at twelve months is near a coin flip for every family;
  quarterly averages up to three quarters ahead are the useful product.
