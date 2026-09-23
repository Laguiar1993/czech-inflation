# Path step 1b: backtest of the longer horizons (h = 1..12), diagnostics and declared improvement candidates

Declared 8 September 2026, BEFORE running. One run, frozen rules. User
request: "backtest the longer-term horizon ones, not h0; how good is it
and how can we improve it." The object is the path from h = 1 to h = 12;
the nowcast (h = 0) is frozen and out of scope here.

## Sample, clock, targets

The 90 origins 2019-02..2026-07 at the release-eve clock (CPI known
through t-1, first release of t not yet out), horizons h = 1..12 (target
months t+h through 2026-07, common valid samples per horizon for every
method). Targets are the headline m/m prints of the current vintage
(Czech CPI is not revised in practice) and the exact-percent y/y path
chained from them. Two path objects:

- (a) product path: h0 = the frozen nowcast `STRUCT_EVE`, h >= 1 = the
  candidate; what a user of `path_live.py` gets;
- (b) horizon-only path: h0 = the REALISED print; isolates the quality of
  h = 1..12 from the nowcast. (b) is the primary object of this spec.

## Diagnostics of the incumbent (no changes; all reported)

D1 by horizon: m/m RMSE, MAE, bias; y/y RMSE and bias for (a) and (b);
direction hit rate (sign of y/y(t+h) minus the last known y/y); naive
alongside.
D2 by regime of the target month (2019-02..2021-12, 2022-01..2023-12,
2024-01..2026-07) and horizon group (1-3, 4-6, 7-12): y/y RMSE (b) and
bias, naive alongside.
D3 January targets versus other months by horizon group: m/m RMSE.
D4 block decomposition of the m/m error by horizon (weighted forecast
minus weighted realised per block: core, food, administered,
alcohol-tobacco, fuel, wedge): RMS per block at h = 1, 3, 6, 12 and the
share of the m/m mean squared error each block carries including its
covariance with the rest.
D5 quarterly averages: for each origin, the average y/y of the next four
whole quarters that fall inside h <= 12 (path (b) and (a)) against the
realised quarterly average; RMSE by quarters-ahead, naive alongside.
D6 calendar-year averages against the CNB staff forecast: for every
Monetary Policy Report vintage in `cnb.mpr_vintages` (series
consumer_price_index, publication date d, forecast year Y in {report
year, report year + 1}), our path's calendar-year average of y/y for Y
from the first origin whose clock is at or after d (known months official,
the rest forecast; only when every month of Y lies within h <= 12), the
CNB number, the realised average; RMSE of both over the matched cases.
D7 persistence: first-order autocorrelation across consecutive origins of
the h = 6 and h = 12 y/y errors (b), as a reminder that the overlapping
windows make the DM statistics approximate.

## Improvement candidates (declared now; nothing added after the run)

All change one thing relative to the incumbent P0 (core ridge on the
plain frame for h <= 3 and the slow frame for h >= 4, food X-13 + ridge
direct-h, administered seasonal median with the documented gate,
alcohol-tobacco same-month mean, fuel same-month median, wedge, regime
weights of t+h).

- P1 plain frame at every horizon (no slow block).
- P2 slow frame at every horizon.
- P3 incumbent frame, ROLLING training window of the last 120 released
  labels instead of expanding from 2007 (targets the level bias).
- P4 incumbent frame, LOCAL-LEVEL target: the ridge is trained on
  core(u+h) minus the trailing twelve-month mean of core known at u, and
  the forecast adds back the trailing mean known at the origin (targets
  the shrinkage toward the 2007-2019 mean without discarding history).
- P5 shrink to the seasonal naive at long horizons: h <= 6 incumbent,
  h >= 7 equal-weight average of the incumbent m/m and the five-year
  same-month mean (fixed weights, no fit).
- P6 survey-anchored drift at long horizons: h <= 6 incumbent, h >= 7
  m/m = monthly drift implied by the CNB FMIE one-year expectation
  (survey month <= origin) plus the calendar month's deviation from the
  long-run mean of released headline m/m (the "pasted drift" the reviewer
  warned against, scored so the warning is measured, not assumed).
- P7 food block at h >= 4 = five-year same-month mean of released food
  m/m (is the direct-h food ridge worth anything beyond a quarter?).

Benchmarks: B1 seasonal-naive path, B2 nowcast + seasonal naive (object
(a) only), B3 random walk in y/y, B4 FMIE at h = 12, B5 CNB report annual
averages (D6).

## Adoption rule (frozen)

Horizon groups 1-3, 4-6, 7-12; criterion y/y RMSE of object (b) in exact
percent on the common sample of the group; time split of ORIGINS
2019-02..2022-12 ("first half") and 2023-01..2026-07 ("second half"). A
candidate replaces the incumbent for a horizon group only if it improves
the group RMSE by at least 5% in BOTH halves and does not worsen the
2024+ target split by more than 2%. Two candidates qualifying for the same
group: the one with the larger full-sample gain, ties to the lower number.
No candidate is combined with another in this step; no weight, window,
half-life or threshold is searched. Fail means closed and recorded. An
adopted candidate changes `path_live.py`'s h >= 1 engine and PATH_SPEC_v2's
F1 definition; it changes nothing in the nowcast.

## What this step does not do

It does not build F2 (trend-and-gap) or F3 (BVAR) of PATH_SPEC_v2; those
remain the next declared runs. It does not produce calibrated path bands.

## RESULTS (8 September 2026, single run; logs `output/path_backtest_h_run.log`, `output/path_backtest_h_cnbq.log`, `output/path_backtest_h_cases.log`; rows `output/path_backtest_h.csv`; chart `output/path_backtest_h_hairy.png`)

### How good it is (object (b), h0 = the print; exact percent; common samples)

| h | n | m/m RMSE model / naive | y/y RMSE model / naive / RW | y/y bias model | direction hit model / naive |
|---|---|---|---|---|---|
| 1 | 88 | 0.70 / 0.86 | 0.77 / 0.94 / 1.57 | -0.11 | 0.85 / 0.78 |
| 3 | 84 | 0.81 / 0.88 | 1.56 / 2.09 / 2.70 | -0.34 | 0.76 / 0.74 |
| 6 | 78 | 0.87 / 0.91 | 2.62 / 3.65 / 4.31 | -1.04 | 0.81 / 0.58 |
| 9 | 72 | 0.94 / 0.94 | 4.16 / 5.28 / 5.92 | -1.93 | 0.74 / 0.62 |
| 12 | 66 | 0.99 / 1.03 | 5.93 / 6.99 / 7.43 | -3.14 | 0.56 / 0.55 |

Quarterly averages (D5): 1 / 2 / 3 / 4 quarters ahead RMSE 1.62 / 2.72 /
4.21 / 5.51 against naive 2.12 / 3.69 / 5.31 / 6.51; bias -0.38 / -1.05 /
-1.99 / -3.09.

By regime of the target (D2), y/y RMSE (b) model / naive / RW and bias:
2019-2021: h 1-3 0.60 / 0.63 / 0.91 (-0.29); h 4-6 1.26 / 1.25 / 1.42
(-0.84); h 7-12 2.08 / 1.85 / 1.84 (-1.50): the model LOSES to both
naive paths beyond six months in the pre-shock years, by under-forecasting
a 2.5-3.5% inflation regime toward its 2007-2018 training mean.
2022-2023: 2.09 / 2.59 / 3.52; 3.87 / 4.99 / 6.11; 7.46 / 8.45 / 8.97
(bias -0.37 / -1.68 / -4.97): better than naive at every horizon, and
five points too low a year out. 2024-2026: 0.43 / 1.14 / 1.71; 0.65 /
2.21 / 2.54; 1.40 / 3.84 / 4.86 (bias -0.03 / -0.05 / -0.28): the model's
strong regime; the naive paths are poisoned by the 2022-23 Januaries.

Where the m/m error sits (D3, D4): January targets have m/m RMSE 1.9 to
2.5 at every horizon group against 0.5 to 0.6 for other months; the
administered block carries 60 to 71% of the m/m mean squared error at h =
1, 3, 6 and 12 (RMS 0.60 to 0.70 pp), core 12 to 19%, food 8 to 13%, the
rest under 5%. Error persistence (D7): lag-1 autocorrelation of the y/y
error across origins 0.81 at h = 6 and 0.89 at h = 12; the DM statistics
of step 1 are approximate for that reason.

Case tables (`path_backtest_h_cases.log`, December origins): from Dec-2021
the model path ran 10-12% through mid-2022 against 14-18% realised (naive
6%); from Dec-2022 it fell to 1-3% by late 2023 against 7-9% realised
(the January-2023 credit reversal is in the h = 1 month, the persistence
after it is not); from Dec-2023 it ran 0.7-1.9% against 2.0-3.0% realised
(under-forecast in a 2-3% regime again); from Dec-2024 3.0-3.7% against
2.1-2.9% (over-forecast for once); from Dec-2025 1.3-1.8% against 1.4-2.5%.

### Against the CNB staff forecast (D6, quarterly, 19 reports Feb-2022..Aug-2026, `data/cnb_mpr_cpi_quarterly.csv`)

Source correction first: `cnb.mpr_vintages` stores the FIRST QUARTERLY
column of each year as if it were the annual average (11.23 for 2022 is
2022Q1, 16.4 for 2023 is 2023Q1, 1.63 for 2026 is 2026Q1, 2.83 for 2027
is the 2027Q1 forecast). The morning's `path_live.py` line quoting "CNB
2026 1.6, 2027 2.8" was therefore quoting quarters, not years; the
product now shows the report's quarterly path (`tools/cnb_mpr_cpi_quarterly.py`).
The comparison matches each report to the first origin whose release-eve
clock follows the report date, so our path has equal or more CPI
information than the report.

| quarters ahead | n | RMSE CNB / ours (a) / naive | bias CNB / ours | ours closer than CNB |
|---|---|---|---|---|
| 1 | 17 | 1.45 / 1.73 / 1.72 | -0.10 / -0.05 | 5 of 17 |
| 2 | 16 | 1.79 / 2.47 / 3.01 | -0.49 / -0.04 | 4 of 16 |
| 3 | 15 | 3.31 / 2.71 / 4.26 | -1.22 / -0.53 | 4 of 15 |
| 4 | 5 | 4.07 / 3.53 / 5.17 | -2.02 / -2.39 | 2 of 5 |

Reports of 2022-2023 (27 quarter forecasts): RMSE CNB 3.50, ours 3.35,
naive 4.03; bias CNB -1.41, ours -0.73; the CNB was better one and two
quarters out (2.09 / 2.50 against 2.46 / 3.41), we were better three and
four quarters out (3.55 / 4.51 against 4.51 / 5.24) because the CNB's
paths returned to target within a year while inflation stayed at 15-17%.
Reports of 2024-2026 (26): RMSE CNB 0.39, ours 0.84, naive 2.51; ours
closer in 6 of 26. In the calm regime the CNB staff forecast is about
twice as accurate as this path at every quarter ahead (0.32 / 0.41 / 0.41
/ 0.52 against 0.50 / 0.80 / 1.18 / 0.81). Read together: the path is a
strong beat of any mechanical benchmark, it beat the central bank when
the central bank was wrong-footed by the energy shock, and it is clearly
second to the central bank's judgemental forecast in normal times.

### Candidates under the frozen rule (y/y RMSE (b), full / first-half origins / second-half origins / 2024+ targets; gain against P0)

Group 1-3 (P0 1.192 / 1.575 / 0.510 / 0.434): no candidate within 5% in
both halves (P3 +4.8% first half but -8.9% second; P2 and P4 worse).
Group 4-6 (P0 2.270 / 3.062 / 0.697 / 0.652): P3 +9.3% first half, -31.6%
second; P7 +1.4% / +7.2% / +8.5%; P1 +0.3% / -0.7% / +7.8%.
Group 7-12 (P0 4.542 / 6.111 / 1.385 / 1.403): P6 +2.5% / +31.1% / +34.3%;
P1 +1.3% / +16.6% / +25.2%; P7 +0.2% / +14.2% / +14.7%; P5 +2.0% / +7.4% /
+8.5%; P3 +4.3% / -32.1% / -10.8%; P2 worse; P4 nil.
ADOPTION: none, for every group. The first half is the 2022-23 surge,
which no candidate forecasts; the rule required both halves.

Bias check (mean m/m forecast against realised): 2019-21 h 7-12 P0 0.13
against 0.39 realised; 2022-23 h 7-12 P0 0.29 against 0.90 (rolling
window 0.52, local level 0.47); 2024-26 h 7-12 P0 0.19 against 0.24
(rolling window 0.35, over). The two crude level fixes trade one regime
for the other; that is the case for an estimated trend state, not a
window.

### What the evidence says about improving it (in order)

1. The level of core inflation at long horizons is the first-order
   problem: an anchor to the 2007-2018 mean under-forecasts every regime
   above 2%. P3 and P4 show a window or a trailing mean is not the answer;
   P6 shows that survey level information at h >= 7 would have cut the
   2024-26 error by a third. The principled version is F2 of PATH_SPEC_v2:
   a filtered trend with the FMIE expectation as a noisy measurement. The
   CNB's own published quarterly path is a second candidate measurement of
   the same kind (public at report dates; 0.39 RMSE in 2024-26 against
   our 0.84), to be declared in step 2 as an F2 variant, never pasted.
2. The slow block (M3, house prices, construction) hurts beyond three
   months in the recent regime (P1 +17% second half, +25% 2024+ at
   h 7-12) and never helps by more than 1.3%: F1's definition in step 2
   should use the plain frame at all horizons (a simplification, scored).
3. The food direct-h ridge beyond three months is worse than its own
   seasonal mean recently (P7 +7% to +14% second half): F1 should use the
   seasonal mean for food from h = 4.
4. January energy events are 60 to 70% of the m/m error at every horizon;
   the November documents reach origins from December onward only. The
   excise calendar (tobacco and alcohol steps legislated a year ahead) is
   the part that is knowable earlier and belongs in F1.
5. Direction at twelve months is a coin flip (0.56); quarterly averages up
   to three quarters ahead are where the path has value. Publish those,
   with the historical error scale, and treat the twelve-month point as
   information about level, not timing.

Nothing above is adopted by this step; items 1-4 are the content of the
step-2 declaration (amended today), item 5 is a presentation rule for
`path_live.py`.
