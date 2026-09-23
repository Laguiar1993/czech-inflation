# Path product, step 1: evaluate the existing horizon machinery as a year-on-year path

Declared 7 September 2026, BEFORE running. Purpose: measure where, if
anywhere, the direct-horizon blocks add value over trivial paths before
building anything. Codex's principle holds throughout: the path models are
separate direct-horizon models anchored on the nowcast at h0; nothing here
feeds back into the release nowcast.

## Object being forecast

At origin t (release-eve clock, CPI known through t-1), the headline
year-on-year rate for target months t+h, h = 0..12. In log terms
y/y(t+h) = sum over the 12 months ending t+h of log(1 + m/m). The months
up to t-1 are known (the BASE part, identical for every method); the
months t..t+h are forecast (the SKILL part). Skill is scored on the
forecast part alone as well as on the year-on-year level.

## The model path (as coded today, no new features)

- h = 0: the nowcast `STRUCT_EVE` (v2.7, documented January entries).
- h = 1..12: the sum of the five direct-horizon blocks and the wedge, the
  recipe of `cz_struct.main`'s `horizon_call`: core ridge trained
  feature(u) -> core(u+h) on the core frame (h <= 3) or the core frame
  plus the slow block M3 / house prices / construction prices (h >= 4);
  food X-13 + ridge at horizon h; administered seasonal median with the
  documented January gate for t+h; alcohol-tobacco same-month mean; fuel
  same-month median of the official fuel m/m (last 8); wedge at t+h;
  weights of the regime of t+h. The h >= 4 slow-block choice extends the
  coded h6/h12 convention to the horizons in between; declared here.

## Benchmarks (all declared now)

- B1 seasonal-naive path: m/m for each future month = mean of the same
  calendar month over the last five released years; h0 also naive.
- B2 nowcast + seasonal naive: h0 from the model, h >= 1 naive. Isolates
  the value of the horizon blocks from the value of the nowcast.
- B3 random walk in year-on-year: y/y(t+h) = last known y/y (t-1).
- B4, information only at h = 12: the CNB financial-market survey's
  one-year-ahead expected y/y (`consensus.inflation_expectations`, market
  survey, 1Y), taken at the survey published before the origin's clock.

## Evaluation

Origins 2019-02..2026-07 (release-eve clock) with realised targets through
2026-07 (so h = 12 has 78 origins, h = 1 has 90). Per horizon: RMSE and MAE
of the y/y level for the model and B1-B3; RMSE of the cumulative m/m
forecast (the skill part) for the same; the share of y/y variance
explained by the base part; ex-January-target and 2024+ splits at h = 3,
6, 12; Diebold-Mariano statistics model vs B1 and vs B2 at h = 3, 6, 12.
A per-block decomposition of the cumulative error at h = 6 and 12.

## Decision rule (frozen)

The model path is "publishable as a product" only if it beats B1 by at
least 10% in y/y RMSE at h = 3, 6 AND 12, and B3 at h = 6 AND 12. If it
beats B2 by less than 5% at every horizon, the horizon blocks add nothing
over the nowcast plus seasonality and the next step is the deterministic
calendars and the futures curve, not more estimation. Nothing is tuned in
this step.

## RESULTS (7 September 2026, single run; log `output/path_run.log`, rows `output/path_experiment.csv`)

Year-on-year RMSE (log points x100, close to pp), release-eve origins
2019-02..2026-07, realised targets through 2026-07:

| h | n | model | nowcast + naive | naive | RW y/y | m/m RMSE model | m/m RMSE naive | base share of y/y variance |
|---|---|---|---|---|---|---|---|---|
| 0 | 90 | 0.41 | 0.41 | 0.84 | 0.90 | 0.41 | 0.85 | 0.89 |
| 1 | 89 | 0.82 | 0.93 | 1.34 | 1.43 | 0.70 | 0.86 | 0.77 |
| 3 | 87 | 1.44 | 1.90 | 2.30 | 2.41 | 0.81 | 0.87 | 0.56 |
| 6 | 84 | 2.44 | 3.26 | 3.67 | 3.78 | 0.87 | 0.88 | 0.28 |
| 9 | 81 | 3.89 | 4.65 | 4.99 | 5.09 | 0.94 | 0.90 | 0.09 |
| 12 | 78 | 5.43 | 5.96 | 5.96 | 6.24 | 0.99 | 0.95 | 0.00 |

Gain over nowcast + naive by horizon (%): 12, 19, 24, 26, 25, 25, 21, 21,
16, 12, 10, 9. Diebold-Mariano model vs naive: −2.4 (h3), −2.5 (h6), −3.1
(h12); vs nowcast + naive: −2.1, −2.5, −3.1. Splits at h = 3 / 6 / 12:
2024+ targets model 0.50 / 0.77 / 1.65 against naive 1.76 / 2.84 / 4.45;
2022-2023 targets model 2.42 / 4.07 / 8.63 against naive 3.73 / 5.87 /
9.33; ex-January targets 1.42 / 2.45 / 5.34 against 2.28 / 3.67 / 5.90.

### Findings

1. The horizon blocks add real value: statistically significant at every
   tested horizon against both naive paths, and large in the 2024-2026
   disinflation, where a five-year seasonal mean still carried the 2022-23
   months and the random walk carried the old level.
2. The value is front-loaded. The model's month-to-month forecasts beat
   the seasonal mean only through h = 6; from h = 7 they are worse (0.96
   against 0.89 at h = 7, 0.99 against 0.95 at h = 12). The twelve-month
   path still wins because its first six months carry the gain.
3. A level bias at long horizons. The model's mean monthly forecast falls
   from 0.34 (h = 1) to 0.20 (h = 12) while the realised mean over these
   years is 0.45-0.47: the direct-h ridges shrink toward a training mean
   that includes the low-inflation 2007-2019 years. Over twelve months that
   is a systematic under-forecast of about 2 to 3 points of y/y in
   high-inflation years, most of the h = 12 error.
4. Base effects: 89% of the y/y variance at h = 0, 56% at h = 3, 28% at
   h = 6, none at h = 12; the tables separate them, so the skill part is
   what the comparisons measure.

### Decision under the rule

"Beats naive by 10% at h = 3, 6 and 12": met at 3 (−38%) and 6 (−33%),
missed at 12 (−8.9%). "Beats RW at 6 and 12": met. Verdict under the
frozen wording: NOT publishable yet, by the h = 12 margin. The DM statistic
at h = 12 is −3.1, so the shortfall is size, not significance; the
findings above say exactly where the size is lost (findings 2 and 3) and
what step 2 must do: keep the direct blocks to h = 6, replace the
month-to-month forecasts beyond that with a seasonal pattern around an
explicitly anchored drift (candidate anchor: the CNB financial-market
survey's one-year expectation, available in real time), and carry the
deterministic calendars and the fuel futures curve. Each is a declared
change with its own rule; none was tried here.

## RESULTS, CORRECTED SCORING (7 September 2026, night; log `output/path_run_v2.log`, rows `output/path_experiment.csv`, table `output/path_experiment_summary.csv`)

The experiment above is unchanged; its first scoring was wrong in two
ways Codex identified (R8): the RMSE dropped missing rows separately per
method, so at h = 12 the model was scored on 66 forecasts and the naive
paths on 78 (the model has no forecast for origins 2019-02..2020-01, where
the food direct-horizon ridge is below its 48-label minimum), and the
"log points x100" were reported as if they were the market's percentage
y/y (they differ by up to 1.4 pp in 2022-23). This section supersedes the
table above. Every method is now scored on the common valid sample per
horizon, in the declared log units AND in exact percent; the h0 column
carries the v2.7.1 nowcast (the h >= 1 blocks price the administered
announcement in the v2.7.1 units).

| h | targets | common | model | nowcast + naive | naive | RW y/y | model pct | naive pct | var. shares base / future / 2cov | m/m RMSE model | naive |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 90 | 90 | 0.418 | 0.418 | 0.837 | 0.899 | 0.470 | 0.925 | 0.89 / 0.04 / 0.07 | 0.421 | 0.854 |
| 1 | 89 | 88 | 0.824 | 0.939 | 1.351 | 1.438 | 0.925 | 1.485 | 0.77 / 0.09 / 0.14 | 0.698 | 0.863 |
| 3 | 87 | 84 | 1.438 | 1.932 | 2.338 | 2.456 | 1.611 | 2.561 | 0.56 / 0.22 / 0.22 | 0.809 | 0.881 |
| 6 | 84 | 78 | 2.457 | 3.382 | 3.800 | 3.924 | 2.720 | 4.143 | 0.29 / 0.46 / 0.25 | 0.867 | 0.909 |
| 9 | 81 | 72 | 3.907 | 4.911 | 5.278 | 5.396 | 4.278 | 5.733 | 0.09 / 0.78 / 0.13 | 0.937 | 0.943 |
| 12 | 78 | 66 | 5.440 | 6.461 | 6.461 | 6.782 | 5.931 | 6.990 | 0.00 / 1.00 / 0.00 | 0.985 | 1.026 |

Gain over the seasonal-naive path: 38.5% / 35.4% / 15.8% at h = 3 / 6 / 12
in log units (37.1 / 34.3 / 15.1 in exact percent). Diebold-Mariano on the
common samples, exact percent: h = 3 -2.33 (HAC lag 2) and -1.94 (lag
12); h = 6 -2.44 / -2.30; h = 12 -3.14 / -3.21. Splits in exact percent at
h = 3 / 6 / 12: 2024+ targets model 0.51 / 0.78 / 1.68 against naive
1.82 / 2.95 / 4.65; 2022-23 targets 2.77 / 4.59 / 9.48 against 4.17 /
6.51 / 10.20; ex-January targets 1.60 / 2.74 / 5.83 against 2.55 / 4.14 /
6.91.

B4, scored as declared: the CNB financial-market survey's one-year
expectation (survey month <= origin) at h = 12 on the same 66 events has
RMSE 6.38 in exact percent, against the model's 5.93, the naive path's
6.99 and the random walk's 7.43; mean error FMIE -3.44, model -3.14.

Per-block cumulative contribution error over t+1..t+h (pp of headline,
mean / RMS, origins with every row valid): h = 6 (n = 78) core -0.42 /
1.27, food -0.04 / 0.71, administered -0.45 / 1.35, alcohol-tobacco
-0.07 / 0.16, fuel -0.02 / 0.43, wedge 0.00 / 0.18, total -0.99 / 2.39;
h = 12 (n = 66) core -1.46 / 2.89, food -0.11 / 1.49, administered -1.18
/ 2.15, alcohol-tobacco -0.09 / 0.20, fuel -0.08 / 0.61, wedge -0.06 /
0.21, total -2.98 / 5.52.

### Decision under the frozen rule (corrected)

"Beats naive by 10% at h = 3, 6 and 12": met (38.5 / 35.4 / 15.8%).
"Beats RW at 6 and 12": met. Verdict: the rule PASSES; the earlier "not
publishable by the h = 12 margin" statement was a scoring artefact and is
withdrawn. Passing the numerical rule certifies neither a live-ready path
product nor the announcement inputs; it says the direct blocks are the
right near-term candidate for step 2.

### Interpretation corrections (Codex R8, accepted)

- The "89% of y/y variance from base effects at h = 0" was
  Var(base)/Var(total); the full decomposition is 0.89 base, 0.04 future,
  0.07 covariance, and the table now carries all three at every horizon.
- On the log scale the known base cancels from the forecast error, so the
  y/y error and the "skill part" error are the same loss; the table keeps
  one of them.
- From h = 11 no known month remains in the trailing-year window and at
  h = 12 the h0 nowcast itself has rolled out: the twelve-month number
  measures t+1..t+12 skill, not next-release skill. The product must show
  this.
- Overlapping targets and reused windows make the DM statistics
  approximate; the lag-12 sensitivity keeps the direction at every
  horizon but the h = 3 statistic falls to -1.94. No unconditional
  "significant everywhere" claim.
- The long-horizon level bias (mean m/m 0.20 at h = 12 against 0.47
  realised; squared mean bias about 28% of the h = 12 MSE) is now
  attributed by the block decomposition: core (-1.46 pp over twelve
  months) and administered (-1.18 pp) carry it, food does not. Whether
  the core part is training-mean shrinkage, missing persistence or
  missing predictors is NOT established; it needs an ablation.
- The six-month boundary was read off this sample; it is a hypothesis for
  step 2, not a validated cutoff (the m/m table itself has the model
  ahead again at h = 8, 10 and 11).

### Step 2 design, revised after this result (to be declared as its own spec before any run)

One index-accounting system (calendar-labelled monthly indices, one
definition of h, as-of basket weights, y/y, quarterly and annual averages
all derived from the same path; scoring of pointwise and cumulative
price-level errors). Three families, few variants: (1) component bridge,
the near-term candidate, the machinery above with the explicit energy and
excise calendars and short-lag fuel; (2) a trend-and-gap state-space
model as the medium-term challenger, a slowly moving underlying rate plus
temporary deviations driven by a small set of activity, labour-cost and
external-price variables, filtered from information available at each
origin (Franta and Sutoris, CNB WP 1/2020, is the architectural motivation,
not evidence of forecast gain), with the FMIE expectation as noisy
information about the trend, a soft constraint on the index path shown
separately, never a pasted drift; (3) a small shrinkage BVAR as the
independent benchmark. Forest challengers come after these three have
been scored. Publish rule as here, on common samples, in exact percent.
