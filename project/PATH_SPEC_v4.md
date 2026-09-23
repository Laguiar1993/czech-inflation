# Path step 4: proper lags, wages, import prices, a robust seasonal

Declared 8 September 2026, BEFORE running. One run, frozen rules. Follows
PATH_SPEC_v3 RESULTS: the exchange rate and the real policy rate came out
wrong-signed at lags of one and six months; wages and import prices were
absent for lack of history; the expanding same-month seasonal means carry
the two shock Januaries.

## Changes declared

- **Robust seasonal (R).** The trend model's seasonal factor for a
  calendar month becomes the median of that month's released values
  minus the overall median (was mean minus mean). Applied as a variant to
  both the survey-anchored trend (F2R) and the target-anchored trend
  (E1R); the product's two trend lines switch to the robust seasonal
  only if the rule below says so.
- **Lags with economic content.** Exchange rate: the twelve-month change
  of EUR/CZK lagged three months (pass-through accumulates over a year,
  not a month). Real policy rate: 3-month PRIBOR minus trailing
  twelve-month headline inflation, lagged twelve months (E4) or eighteen
  months (E5), the range the CNB's own transmission accounting uses.
  Unemployment change unchanged (it worked).
- **Wages (E6).** Eurostat labour cost index, wages and salaries, whole
  economy, not seasonally adjusted, quarterly from 2000 (`lc_lci_r2_q`,
  D11, B-S, NSA, index 2020 = 100), as year-on-year growth of the latest
  quarter public at the month, carried monthly; Eurostat publishes about
  seventy-five days after the quarter, so the quarter ending in month e
  is used from month e + 3. Cached in `data/eurostat_lci_cz_quarterly.csv`
  at the first run. Expected sign positive.
- **Import prices (E7, conditional).** Only if a monthly import price
  index with a start no later than 2000 is obtainable from Eurostat
  (`sts_inpi_m`) at run time; otherwise E7 is not run and the real
  effective exchange rate deflated by producer prices (step 3) remains
  the imported-price channel.

Variants, all target-anchored, survey-free, maximum-likelihood variances,
robust seasonal: E1R (anchor only), E4 = E1R + {unemployment change,
EUR/CZK twelve-month change lag 3, real rate lag 12}, E5 = same with the
real rate at lag 18, E6 = E4 + wages, E7 = E4 + import prices (conditional).
Reference lines from earlier steps: E1 (step 3), F2 with the survey (step
2), F2R (survey, robust seasonal), F1b, naive, RW.

## Rules (frozen)

- Selection among E1R, E4, E5, E6 (and E7 if run): lowest h = 12 y/y RMSE
  on origins 2008-01..2018-12; a variant is eligible only if every driver
  has the expected sign in at least half of the origins.
- Robust seasonal for the survey-anchored second line: F2R replaces
  F2_D1_fixed if its long-span h = 12 RMSE is at least 3% lower.
- Target line of the product: the selected variant (if eligible),
  otherwise E1R if it beats E1 at h = 12 on the long span, otherwise E1.
- Product engine: F1b stays unless the selected variant beats it at h = 12
  on the component span by at least 5% on the full span and in both
  origin halves and passes the publish rule.
- Everything reported: long span by horizon, regimes, component span,
  the CNB comparison for the selected variant.

## Amendment 1 (8 September 2026, after the first run, before the second)

The first run (files `output/path_step4_*_uncentered_first_run.*`) used
the robust seasonal as declared: same-month median minus the overall
median. Those twelve factors do not sum to zero: on the 1998-2007 history
they sum to +1.04, on 1998-2018 to +0.75, on 1998-2026 to +0.96 (mean
factors: 0.00). A seasonal that adds a percentage point a year shifts the
seasonally adjusted series below the anchored level's target, so every
target-anchored variant with that seasonal ran about a point a year above
its own anchor (anchor-only line 2008-2018 h = 12: 1.745 with the
uncentered robust seasonal against 1.335 with the mean seasonal; bias
+0.19 against -0.39 on the long span). The survey-anchored line was
unaffected (its random-walk level absorbs the offset: 3.838 against 3.839).
This is a construction defect, not a result to tune: seasonal factors
must sum to zero. Amendment: the robust factors are the same-month medians
centred by their own mean. Everything else, including every rule, is
unchanged; the first run's parameter signs are reported as they were.

## Amendment 2 (8 September 2026, after the second run, before the third)

The declaration made E7 conditional on a Eurostat import price index with a
2000 start; Eurostat holds no Czech series in `sts_inpi_m` (empty for every
unit and coverage). The user pointed out that the CZSO publishes one. It
does: "Indexy cen vývozu a dovozu", monthly since 1998, open data from 2008
(SITC-classified set CEN0303, total, not adjusted for the exchange rate;
the CPA-classified set CEN0301 starts in 2015; the 1998-2007 history is in
the CZSO public database, which offers no programmatic export, and the CNB
ARAD key is not on this machine). Amendment: E7 = E4 + the import price
index month-on-month change from CEN0303 (total, `Index dovozních cen`),
value minus 100, in percent, cached in
`data/czso_import_prices_sitc_monthly.csv`. Availability: the CZSO
publishes month m around the middle of month m + 2 (June 2026 on 11 August
2026), after the CPI release eve of origin m + 1, so at the eve of origin t
the last public month is t - 2; the driver row for month s therefore
carries the change of month s - 1, and the model's own one-month lag makes
the gap in month t depend on the change of month t - 3. Months before
2008-02 are zero (the declared treatment of missing change-type drivers),
so the coefficient is identified on 2008 onward and the 2008-2018
selection window understates the driver's value; this is reported, not
corrected. Expected sign positive. Every rule unchanged; the other variants
are re-run unchanged (deterministic) so the third run's files are complete.

## RESULTS (8 September 2026; three runs as declared and amended; final files `output/path_step4.csv`, `_params.csv`, `_summary.csv`, `_run.log`, `_cnbq_E7.*`, `_cnbq_E5.*`; earlier runs kept as `*_uncentered_first_run.*` and `*_run2_centered_noE7.*`; new data caches `data/eurostat_lci_cz_quarterly.csv`, `data/czso_import_prices_sitc_monthly.csv`)

### Estimated parameters (final run; means over 222 origins; share of origins with the expected sign)

| variant | rho (half-life) | drivers |
|---|---|---|
| E1R anchor only, centred robust seasonal | 0.908 (7 months) | none |
| E4 | 0.913 | unemployment change -0.648 (100%), koruna/euro twelve-month change lag 3 +0.010 (100%), real rate lag 12 -0.002 (72%) |
| E5 | 0.909 | unemployment -0.635 (100%), koruna +0.009 (94%), real rate lag 18 -0.009 (76%) |
| E6 | 0.917 | as E4 plus wages -0.007 (0%): not eligible |
| E7 | 0.913 | as E4 plus import prices +0.004 (71%) |

The proper lags repair the two signs that failed in step 3: the koruna's
twelve-month change lagged three months carries the pass-through sign in
every origin (the one-month change never did), and the real policy rate
lagged twelve to eighteen months carries its sign in three origins out of
four (six months: one in five). Import prices enter with the right sign in
71% of origins and a small coefficient (the koruna term already carries
most of the imported-price information, and the series only exists from
2008). Wages come out negative in every origin: Czech nominal wage growth
follows inflation (the real-wage catch-up of 2018-19 and 2023-25 came
after the price moves), so the labour cost index is a lagging variable at
this horizon and is not a driver of the gap; it stays out.

Robust seasonal: with the factors centred it is neutral (anchor only,
2008-2018 h = 12: 1.332 against 1.335 with the mean seasonal; long span
3.963 against 3.955; survey line 3.838 against 3.839). The uncentered
first version was harmful for the reason recorded in amendment 1. Under
the rule the survey-anchored second line keeps the mean seasonal.

### Selection (origins 2008-01..2018-12, h = 12, object (b), n = 132)

E1R 1.332, E4 1.201, E5 1.206, E6 1.234 (ineligible), E7 1.197; step-3
E1 1.335; survey-anchored F2 1.052. Selected by the rule: E7. The three
eligible driver variants are within 0.01 of each other on this window;
the ten-percent gain over the anchor-only line comes almost entirely from
2008-2009, where the unemployment term caught the post-crisis
disinflation that the anchor alone did not.

### Long span, origins 2008-01..2026-07, object (b), y/y RMSE in exact percent (bias)

| h | E1 (step 3) | E4 | E5 | E7 | survey-anchored F2 | naive | RW |
|---|---|---|---|---|---|---|---|
| 1 | 0.57 | 0.59 | 0.57 | 0.59 | 0.57 | 0.63 | 1.10 |
| 3 | 1.22 | 1.29 | 1.22 | 1.30 | 1.21 | 1.37 | 1.83 |
| 6 | 2.02 | 2.17 | 2.00 | 2.18 | 2.02 | 2.30 | 2.80 |
| 9 | 2.95 | 3.14 | 2.88 | 3.14 | 2.93 | 3.21 | 3.71 |
| 12 | 3.96 (-0.39) | 4.21 (-0.18) | 3.83 (-0.61) | 4.18 (-0.25) | 3.84 (-1.23) | 4.09 | 4.47 |

By regime of the target, h 7-12, E7 / E1 / survey / naive: 2008-09 1.71 /
2.24 / 1.19 / 1.95; 2010-12 0.96 / 0.97 / 0.84 / 0.96; 2013-16 1.05 /
1.05 / 0.78 / 1.15; 2017-19 0.66 / 0.67 / 1.00 / 1.13; 2020-21 1.73 /
1.74 / 2.10 / 1.75; 2022-23 8.62 / 8.29 / 8.76 / 8.45; 2024-26 3.68 /
2.80 / 0.87 / 3.84.

Two facts sit side by side. E5 (real rate at eighteen months) is the best
survey-free line ever run on the long span at every horizon from three
months out, and at twelve months it edges the survey-anchored line (3.83
against 3.84) with half its bias. E7, the variant the rule selected, is
worse than the anchor-only E1 on the long span at every horizon (4.18
against 3.96 at twelve months) and worse than the naive path at twelve
months: its 2008-2009 gain is paid back in 2022-2026, where the koruna's
2024 depreciation and the 2023 real-rate peak pushed the gap the wrong
way while inflation was already home. The selection window and the
long-span rule disagree, and the rule as declared has no long-span
safeguard for the target line (the second-line rule of step 3 had one).

### Component span 2019-02..2026-07, object (b): F1b 0.77 / 1.56 / 2.57 / 4.05 / 5.79 at h 1 / 3 / 6 / 9 / 12; E7 0.86 / 1.97 / 3.49 / 5.23 / 7.27; survey line 0.82 / 1.83 / 3.25 / 4.89 / 6.66; naive 0.94 / 2.10 / 3.65 / 5.28 / 6.99.

### Against the CNB quarterly forecasts (matched reports, object (a))

Reports 2022-2023 (27 quarters): CNB 3.50, E7 4.28, E5 3.72, E1 3.70,
F1b 3.19, naive 4.03. Reports 2024-2026 (26): CNB 0.39, E7 0.75, E5 0.84,
E1 0.77, survey line 0.59, F1b 0.70.

### Rules, applied as declared

- Second line: F2R is 0.0% better than F2 at twelve months; the
  survey-anchored trend with the mean seasonal stays the scored second
  line.
- Target line: E7 is the selected variant and eligible, so it becomes the
  product's target line (`path_live.py`, information only, never scored
  as the product). FLAG for the user: on the full 2008-2026 record E7 is
  worse than the line it replaces (E1) and than the seasonal-naive path
  at twelve months, and it fails the publish rule on the component span
  (+6.1 / +4.5 / -3.8% against naive at 3 / 6 / 12 months). E5 would have
  been the better line on every span except the declared selection
  window. I applied the rule rather than the outcome; the decision to
  amend the rule (a long-span safeguard, or a selection window that ends
  at the last complete regime) is the user's and would be declared as
  PATH_SPEC_v5 before any further run.
- Product engine: F1b stays (E7 is 26% worse at twelve months on the
  component span and not publishable).

### Today's product with the new target line (origin 2026-09, clock 8 September 2026 10:50)

Quarterly y/y, product / survey trend / target (E7) / CNB summer report:
Q4-26 2.44 / 2.15 / 2.21 / 2.39; Q1-27 3.02 / 3.21 / 3.06 / 2.83; Q2-27
3.04 / 2.97 / 2.65 / 2.42 (FLAG product +0.62, trend +0.55); Q3-27 3.31 /
2.98 / 2.58 / 2.50 (FLAG product +0.81). The target line moved from
2.10 / 3.08 / 2.72 / 2.60 (E1, morning rows) to these values; the product
path is unchanged.

### Data notes

- Import prices: Eurostat holds no Czech series; the CZSO does (open data
  from 2008, SITC set CEN0303; public database from 1998 without a
  programmatic export). Publication about the 11th to the 17th of the
  second month after; the driver uses month t - 2 at the eve of origin t.
- Wages: Eurostat labour cost index (wages and salaries, whole economy,
  NSA, quarterly from 2000), used from quarter end + 3 months.
- Both caches must be refreshed before the month-end run (delete the two
  files under `data/`; the loaders re-download).
