# Predeclared experiment: weekly SZIF farmgate/processor prices in the food block

Declared 7 September 2026, BEFORE any forecast is computed with these data.
Executes the experiment proposed in `RETAIL_FOOD_SPEC.md` (6 Sep) under the
user's brief: food is the first ordinary-month improvement project; first
verify that the weekly observations genuinely arrive before CPI; then test
whether they improve the existing food forecast beyond the monthly farmgate
(CEN0203B) and food-PPI inputs. The food state-space challenger stays closed
(`FOOD_EXPERIMENT_SPEC.md`); this is a materially different information set
(within-month, weekly), which is what reopening the food block required.

Attribution recomputed on the v2.5 baseline (per-origin weights, first-release
actuals): food carries 42.7% of the headline squared-error variance 2024+
ex-January at BOTH decision times (core 19.9, alcohol/tobacco 18.0, admin
4.5, fuel -0.9, reconciliation remainder 15.7); flash era 2025+ ex-January
35.5-38%. Food block 2024+ ex-Jan: RMSE 0.682, MAE 0.567, bias +0.136 pp;
worst calendar months April (1.26), October (1.00), May (0.93), September
(0.87). Food is therefore the right first target.

## 1. Sources and timing (metadata inspected; no CPI comparison made)

- **SZIF Cenový a informační servis, weekly "Cenové hlášení"**: dairy
  products (folder 01), pig carcasses (04), cattle carcasses (05). Each
  listing page shows the report's week label (ISO year-week) and its
  publication date; the archive runs 2005-2026. That publication date is
  the availability stamp used below, per week.
- **Numbers**: EU agri-food data portal API
  (`ec.europa.eu/agrifood/api/{pigmeat,beef,dairy}/prices?memberStateCodes=CZ`),
  the Commission's publication of the SAME weekly reports Czechia files
  through SZIF under Reg. (EU) 2017/1184 and 2017/1185, in EUR at the ECB
  weekly average rate that SZIF prints on every report. Verified exact
  before this declaration: week 35/2026 pigs S 4008 and E 3925 CZK/100 kg
  -> 166.21 / 162.77 EUR = API; dairy butter/Edam/Emmental 132.04 / 105.35
  / 145.05 CZK/kg -> 547.57 / 436.90 / 601.53 EUR = API (547.55 / 436.88 /
  601.53); week 51/2024 cattle: 15 of 15 classes carried by the API match
  the SZIF report to the cent at the ECB week mean 25.095. Prices are
  converted back to CZK with the ECB daily reference rate (EXR
  D.CZK.EUR.SP00.A), mean over the report week (SZIF's own convention).
- Local access to szif.gov.cz is currently blocked by the workstation's web
  filter ("Outbound Malware or Phishing" page); the API is the operational
  number source, the SZIF listing supplies the publication dates. Both
  continue to publish (continuing-source rule).
- Verification to be reported in the results: the lag distribution
  (publication date minus ISO-week end) over the full 2005-2026 record for
  the three folders, and for each target month whether the last week of the
  month was public at decision time A (month-end) and B (first-release eve).

## 2. Series (chosen on continuity and CPI relevance, before any CPI comparison)

- Pigs: class **E** carcass price (weekly since 2004-05; S only from 2014, R
  from 2019). Known gap: weeks 14-30 of 2017 absent for every class -> the
  affected months carry NaN.
- Cattle: young bulls U2, R2, O2 (API codes AU2, AR2, AO2) and cows R3, O3
  (DR3, DO3) -- all 52 weeks a year since 2004 and all printed on the SZIF
  report. The Commission's "adult male indicative price" (ACZURO) is not on
  the SZIF report and is not used.
- Dairy products: **butter** (blocks), **Edam**, **Emmental** -- weekly
  since 2004; butter and Emmental have data-protection gaps (2012,
  2018-2021), Edam is continuous. Powders (SMP, WMP, whey) are excluded as
  industrial/export items; drinking milk, cream and Gouda are excluded
  because their series start in 2021/2018.

## 3. Feature: one column `szif_mm`, food block only

- Week -> month: the month containing the ISO week's Thursday.
- For product p, month M and clock `as_of`:
  `d_p = 100 * [ mean log CZK price over the weeks of M published on or before the as_of date  -  mean log CZK price over the weeks of M-1 published by as_of ]`,
  defined only when both means exist.
- Commodity signal = mean of `d_p` over the commodity's available products;
  `szif_mm(M)` = mean over the commodities with a signal; NaN when none
  (then the ridge's training-mean imputation applies, i.e. no information,
  as for every other missing input).
- Two panels, one per clock type: A = month-end 23:59 of M; B = first-release
  eve 23:59 from `data/release_calendar_cz_cpi.csv` (months before the
  calendar's first month use month-end + 7 days). Training rows use the
  panel of the same clock type as the origin, so the ridge learns exactly
  the partial-month mapping it is given at that decision time.
- Publication dates per (folder, ISO year-week) from the SZIF listing
  record; a week without a recorded date uses week end + 4 days (counted
  and reported).
- **Amendment to RETAIL_FOOD_SPEC's wording** ("last weekly observation
  published by the cutoff vs the prior month's average"): the mean of the
  published weeks replaces the last observation. Reason, fixed before any
  run: the CPI food index is a within-month average of collected prices and
  the farmgate feature already in the block is a monthly average; a single
  week adds sampling noise without a corresponding CPI concept. The
  last-observation version is NOT run.

## 4. Model

Incumbent food block unchanged: per-origin one-sided X-13 on food m/m,
expanding ridge (alpha 3) on `food_l1, food_l12, agri_l0, agri_l1,
food_ppi_l1`, seasonal factor added back. Challenger = the identical
pipeline with `szif_mm` as the sixth ridge feature. Nothing else changes:
weights, other blocks, wedge, X-13, alpha, the 48-row minimum.

## 5. Evaluation

- The 90 first-release origins of `output/cz_struct_backtest.csv`
  (2019-02..2026-07), at both clocks (A month-end, B first-release eve as in
  `cz_struct.main`). Harness check first: the incumbent recomputed by the
  driver must equal the backtest's `food_pred` and `food_pred_eve` to 1e-9,
  and the recombined headline must reproduce `STRUCT`; otherwise stop.
- Food-block RMSE and MAE vs realised food m/m: all 90, ex-January, 2024+,
  2025+ (flash era). Headline effect: `STRUCT + w_food(t) * (challenger -
  incumbent)` with the origin's solved food weight; headline RMSE on the
  same splits, plus big-surprise MAE and W-L@0.15 vs the survey for
  information.
- Diagnostics reported, not used for adoption: weeks used per month at each
  clock; correlation of `szif_mm` with realised food m/m and with the
  incumbent's error; the ridge coefficient path on `szif_mm`.

## 6. Adoption rule (frozen from RETAIL_FOOD_SPEC, made two-clock)

ADOPT only if, at clock B, food-block RMSE improves by at least 5% on the
full window AND on 2024+, AND headline RMSE is not worse on either; AND at
clock A the food-block RMSE is not worse on either window. Otherwise record
and close: no second variant, no series substitution, no parameter change.
If adopted, `szif_mm` joins the food frame with an availability rule, a
refresh step (EU API + SZIF listing), STALE/NOT_DUE classification and the
8-week live continuing-source check declared in RETAIL_FOOD_SPEC.

## RESULTS (7 September 2026) -- RECORDED AND CLOSED

### Timing verification (full SZIF listing record 2005-2026)

3,342 weekly reports recorded (cattle 1,114 / dairy 1,113 / pigs 1,114;
five mislabelled entries such as a "2050" week excluded automatically).

- Publication lag after the ISO-week end: median 3 days (67% Wednesday,
  23% Thursday), p90 4, p99 11-12, maximum 25-26 in holiday weeks; within 4
  days for 90-92% of reports, within 7 for 93-95%.
- Decision time A (month-end): 76-77% of a month's weeks are public; the
  last week only in 10-11% of months (it appears the following Wednesday).
- Decision time B (first-release eve): 98.5-98.8% of weeks over 2010-2026,
  the last week in 94-95% of months; in the flash era, with release eve on
  day 3-5, the last week is public in only 45% of months for pigs and
  cattle and 65% for dairy.
- The feature respects the recorded date week by week. 438 of 9,913 weekly
  rows (4.4%: 2004 to early 2005, before the archive, plus the mislabelled
  weeks) use the week-end + 4 day fallback.

Answer to the first question: the observations do arrive before CPI --
3-4 of a month's 4-5 weeks at month-end, every week at release eve except
the final one in about half the flash-era months.

### Run of record

The first execution used an incomplete publication record (a parser bug on
the markdown listing pages left 365 of 3,342 weeks recorded). It was
discarded without reading its scores; its log is kept as
`output/food_szif_run_DISCARDED_partial_record.log`. The complete-record
run followed. A reporting-only change afterwards (headline scored against
first-release actuals with the scoreboard's definitions, section 5) was
rerun and reproduced every model column to 0.0.

Harness: the incumbent recomputed in the driver equals the backtest's
`food_pred` / `food_pred_eve` to 2.2e-16 at both clocks. Signal coverage:
236 months 2007-01..2026-08 at both clocks.

### Food block, RMSE (MAE) vs realised food m/m

| split | n | A incumbent | A +szif | d | B incumbent | B +szif | d |
|---|---|---|---|---|---|---|---|
| all 90 | 90 | 0.913 (0.678) | 0.923 (0.688) | +1.1% | 0.913 (0.678) | 0.923 (0.687) | +1.1% |
| ex-January | 83 | 0.782 (0.598) | 0.780 (0.601) | -0.2% | 0.782 (0.598) | 0.786 (0.603) | +0.5% |
| 2024+ | 31 | 0.780 (0.617) | 0.797 (0.632) | +2.2% | 0.780 (0.617) | 0.793 (0.629) | +1.7% |
| 2024+ ex-Jan | 28 | 0.682 (0.567) | 0.687 (0.575) | +0.7% | 0.682 (0.567) | 0.685 (0.572) | +0.4% |
| 2025+ flash era | 19 | 0.567 (0.464) | 0.568 (0.472) | +0.2% | 0.567 (0.464) | 0.566 (0.468) | -0.2% |

### Headline, RMSE vs first release (origin's solved food weight)

| split | A STRUCT | A +szif | d | B STRUCT | B +szif | d | survey |
|---|---|---|---|---|---|---|---|
| all 90 | 0.7307 | 0.7339 | +0.4% | 0.7292 | 0.7303 | +0.2% | 0.3815 |
| ex-January | 0.4048 | 0.3999 | -1.2% | 0.4041 | 0.4006 | -0.9% | 0.3801 |
| 2024+ | 0.2141 | 0.2129 | -0.5% | 0.2144 | 0.2134 | -0.5% | 0.2410 |
| 2024+ ex-Jan | 0.1973 | 0.1976 | +0.2% | 0.1983 | 0.1984 | +0.1% | 0.2315 |
| 2025+ flash era | 0.1659 | 0.1640 | -1.1% | 0.1650 | 0.1629 | -1.3% | 0.1947 |

Big surprises (23, consensus MAE 0.578): BASE_RIDGE A 0.642, W-L 6-3, 3
halved; +szif A 0.633, 8-3, 4; BASE_RIDGE B 0.642, 6-2, 3; +szif B 0.637,
6-3, 3. Information only.

### Diagnostics (not used for the decision)

Correlation of `szif_mm` with the realised food m/m +0.06 at both clocks;
with the incumbent's error -0.05. Mean absolute change of the food
forecast 0.08 pp (A) / 0.07 pp (B); largest 2022-03 (0.44), 2022-06
(0.33), 2023-01 (0.27). Months moved by more than 0.1 pp at B: 6 improved,
8 worsened. Weeks used per month: 3.4 of 4.3 at A, 4.3 at B.

### Decision

RECORD AND CLOSE under the section-6 rule: the block is 1.1% worse over the
90 origins and 1.7-2.2% worse on 2024+ at both clocks; the headline moves
by less than 1.3% in either direction on every split. Reading: at the
monthly horizon the within-month change of pig, cattle and dairy
processor prices carries no usable same-month information about the CPI
food m/m beyond the lagged farmgate PPI already in the block; the
pass-through to shelf prices runs with lags that the monthly agricultural
PPI (M-1) already captures. The information set was materially different
from the closed state-space challenger (weekly, within-month), which is
what justified reopening the food block; the question is now answered on
the record. No variant is run. The data infrastructure
(`data/szif_weekly.py`, `data/eu_agrifood/`, `data/szif_publication_dates.csv`,
`test_food_szif.py`) stays as research material; `szif_mm` is NOT in the
food frame and nothing in `cz_struct.py` changed.
