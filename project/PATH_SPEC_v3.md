# Path step 3: the path without surveys, anchored in economics; the CNB as a flagged comparison

Declared 8 September 2026, BEFORE running. One run per variant, frozen
rules. User direction: remove the surveys from the nowcast, try the path
without them, make the model economically sound, and flag where it differs
from the CNB's own forecast rather than lean on it.

## 1. Nowcast

The frozen trio (BASE_RIDGE, PAST_FULL, PAST_HALF) is not changed before
its prospective record starts on 30 September 2026. A fourth column is
logged beside them from now on: `h0_base_ridge_ns`, the reference with
the four survey columns and the survey interaction removed from the core
frame (SURVEY_ABLATION_SPEC: 0.418 against 0.420 on all 90, 0.219 against
0.217 on 2024+, indistinguishable). Both accumulate a prospective record;
the switch to the survey-free reference is a later decision on that
record, not a backtest decision. No other change.

## 2. Path: the trend pillar without a survey

The step-2 trend-and-gap model (models/trend_gap.py) is kept; the survey
measurement is removed and the level is anchored to the inflation target
instead:

    level_t - mu_t = rho (level_{t-1} - mu_{t-1}) + eta_t,   rho in (0.90, 0.999), estimated
    gap_t = phi gap_{t-1} + gamma' x_{t-1} + eps_t
    y_t (SA headline m/m) = level_t + gap_t + e_t

mu_t is the CNB target converted to a monthly rate: 2% from January 2010;
3% in 2006-2009; a straight line from 4% (January 2002, band 3-5) to 3%
(December 2005, band 2-4); 4% for 1998-2001 as the declared approximation
of the net-inflation-targeting years. Beyond the sample mu stays at its
last value. Economic content: a credible target is where inflation
returns when nothing else moves, at a speed the data decide.

Drivers of the gap (hard data only, sentiment indices count as surveys and
are excluded), each lagged one month inside the model:
- E1: none (anchored level only).
- E2: E1 + EUR/CZK monthly change (a weaker koruna raises the gap), the
  change in the LFS unemployment rate, trend-cycle, with its extra
  publication month (more slack lowers the gap), and the real policy
  rate, 3-month PRIBOR minus trailing twelve-month headline inflation,
  lagged six months for transmission (a higher real rate lowers the gap).
- E3: E2 + the monthly change of the real effective exchange rate
  deflated by producer prices (ARAD SREERM101; real appreciation lowers
  imported inflation).
- E0 (control): the step-2 level-random-walk model without the survey
  (F2_D1_noFMIE, already computed).
Each of E1-E3 is run with maximum-likelihood variances and with the fixed
signal-to-noise ratio of step 2 (six fits per origin). The estimated
signs of gamma are reported as the economic-soundness check; a variant
whose signs are wrong on average is reported as such and not adopted
whatever its RMSE.

## 3. Evaluation and rules

Origins 2008-01..2026-07 at the release-eve clock, object (b) primary,
object (a) on the component span; the step-2 columns (F1b, F2 with the
survey, naive, RW, realised) are reused from `output/path_step2.csv`.
- Variant selection among E1-E3 (ML and fixed): lowest h = 12 y/y RMSE on
  origins 2008-01..2018-12, before any look at 2019+.
- Second line of the product: the survey-free trend E* replaces the
  survey-anchored trend line if its long-span h = 12 RMSE is within 5% of
  the survey version's and its signs are right; otherwise the survey
  version stays and both are reported.
- Product engine: F1b stays unless E* beats it at h = 12 on the component
  span by at least 5% on the full span and in both origin halves and
  passes the publish rule (the step-2 rule, unchanged).
- Publish rule as in PATH_SPEC_v2 section 3.

## 4. The CNB as a flagged comparison

`path_live.py` prints, for every quarter the latest Monetary Policy Report
covers, our product path, our trend line and the report's number, and
flags a quarter when either of ours differs from the report by 0.5 pp or
more, stating whether the quarter contains a January whose administered
block is the seasonal median only (no announcement entry yet). The
comparison is information; nothing in any path uses the CNB number.

## 5. Not in this step

Wage, import-price and oil drivers (histories too short for a 1998
start); the excise calendar; forest challengers; calibrated path bands.

## RESULTS (8 September 2026, single run; logs `output/path_step3_run.log`, `output/path_step3_cnbq_E1_ML.log`, `output/path_step3_cnbq_E3_ML.log`; rows `output/path_step3.csv`, parameters `output/path_step3_params.csv`)

### Estimated parameters (means over 222 origins; share of origins with the expected sign)

| variant | rho (half-life of the level deviation) | phi | drivers |
|---|---|---|---|
| E1 ML | 0.908 (7 months) | 0.11 | none |
| E1 fixed | 0.931 (10 months) | 0.22 | none |
| E2 ML | 0.911 (7 months) | 0.10 | koruna/euro -0.007 (right sign 32%), unemployment change -0.500 (100%), real rate lag 6 +0.013 (18%) |
| E3 ML | 0.911 (7 months) | 0.10 | koruna/euro -0.025 (1%), unemployment -0.497 (100%), real rate +0.013 (18%), real effective rate -0.021 (89%) |

Unemployment behaves as a Phillips curve says, in every origin. The real
effective exchange rate deflated by producer prices has the right sign
in most origins. The bilateral koruna rate and the six-month-lagged real
policy rate come out tiny and wrong-signed once the level is anchored:
their information is absorbed by the level and the anchor, or their
proper lags are longer than one and six months. Under the rule a variant
with wrong signs is not adopted whatever its error.

### Variant selection (origins 2008-01..2018-12, h = 12, object (b), n = 132)

E1 ML 1.335, E1 fixed 1.330, E2 ML 1.328, E2 fixed 1.378, E3 ML 1.325,
E3 fixed 1.370; the control with a random-walk level and no survey 1.890;
the survey-anchored F2 1.052. Selected by the rule: E3 ML. The target
anchor recovers most of what removing the survey loses (1.89 to 1.33) but
the survey-anchored level remains 20% better on these origins.

### Long span, origins 2008-01..2026-07, object (b), y/y RMSE in exact percent

| h | n | E1 ML | E2 ML | E3 ML | random-walk level, no survey | survey-anchored F2 | naive | RW |
|---|---|---|---|---|---|---|---|---|
| 1 | 222 | 0.57 | 0.57 | 0.57 | 0.58 | 0.57 | 0.63 | 1.10 |
| 3 | 220 | 1.22 | 1.20 | 1.20 | 1.24 | 1.21 | 1.37 | 1.83 |
| 6 | 217 | 2.02 | 1.98 | 1.99 | 2.16 | 2.02 | 2.30 | 2.80 |
| 9 | 214 | 2.95 | 2.88 | 2.90 | 3.24 | 2.93 | 3.21 | 3.71 |
| 12 | 211 | 3.96 | 3.93 | 3.95 | 4.45 | 3.84 | 4.09 | 4.47 |

Bias at h = 12: E1 -0.39, E2 -0.31, E3 -0.30, survey version -1.23. Over
eighteen years the survey-free lines are within 3% of the survey version
at twelve months and marginally better at three to nine, with a quarter
of its bias.

By regime of the target, h 7-12, E3 ML / survey version / naive: 2008-09
2.08 / 1.19 / 1.95 (E bias +1.98: the 3% target held the level up while
inflation fell to 1); 2010-12 1.00 / 0.84 / 0.96; 2013-16 1.08 / 0.78 /
1.15; 2017-19 0.72 / 1.00 / 1.13; 2020-21 1.68 / 2.10 / 1.75; 2022-23 8.39
/ 8.76 / 8.45; 2024-26 2.32 / 0.87 / 3.84 (E bias +0.85). The survey
earns its place at regime changes: in 2023 the expectations survey already
said 2.5% while the target-anchored level was still shedding the 2022-23
memory at a half-life of seven months; the reverse held in 2017-2021.

### Component span 2019-02..2026-07, object (b)

| h | F1b | survey-anchored F2 | E3 ML | random-walk level, no survey | naive |
|---|---|---|---|---|---|
| 1 | 0.77 | 0.82 | 0.80 | 0.82 | 0.94 |
| 3 | 1.56 | 1.83 | 1.79 | 1.83 | 2.10 |
| 6 | 2.57 | 3.25 | 3.14 | 3.36 | 3.65 |
| 9 | 4.05 | 4.89 | 4.75 | 5.21 | 5.28 |
| 12 | 5.79 | 6.66 | 6.79 | 7.47 | 6.99 |

### Against the CNB quarterly forecasts (matched reports)

Reports 2022-2023 (27 quarters): CNB 3.50, F1b 3.19, survey-anchored trend
3.62, E1 3.70, E3 4.09. Reports 2024-2026 (26): CNB 0.39, F1b 0.70,
survey-anchored trend 0.59, E1 0.77, E3 0.78. Without a survey the trend
line is no closer to the central bank than the component bridge.

### Rules

- Second line: E3 ML is within 5% of the survey version at twelve months
  on the long span (+2.9%) but fails the sign check; the survey-anchored
  trend stays the scored second line. E1 ML (no drivers, so no sign to
  fail) was not the selected variant and is therefore not adopted by this
  rule; it is added to the product output as a third, information-only
  line ("target line") because it is the cleanest economically stated
  path and the user asked to see the path without surveys.
- Publish rule for E3 ML on the component span: gains +14.5 / +14.0 /
  +3.0% at h 3 / 6 / 12: not publishable at twelve months.
- Product engine: F1b stays (E3 ML is 17% worse at twelve months on the
  full component span).

### What this says about improving the path

1. The level pillar needs forward-looking information at regime changes;
   the target anchor alone reacts with a seven-month half-life. The two
   candidates for that information without a survey are the CNB's own
   published path (a forecast, public, but the user wants it as a flag
   rather than an input) and market-implied inflation (Czech inflation-
   linked bonds are illiquid; swap-implied measures are not available).
   The honest statement is that the expectations survey is the cheapest
   carrier of that information and the nowcast does not need it; the
   path does.
2. Slack works; the exchange rate needs its proper lag and the real rate
   a longer one (12 to 18 months in the CNB's own transmission accounting);
   both are declared for the next variant together with import prices
   and wages once a long enough history is assembled.
3. The seasonal means from 1998 carry the shock Januaries; a robust
   (median or trimmed) seasonal is the next declared change to the trend
   model.
