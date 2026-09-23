# Predeclared: calibrated uncertainty bands for the frozen trio

Declared 7 September 2026, night, BEFORE running. One run, frozen rules.
Purpose: the operating models (BASE_RIDGE, PAST_FULL, PAST_HALF) have no
calibrated interval; the only bands in the repository describe the legacy
residual forest. Position size should follow the conditional reliability
of the point forecast, not the point alone. Nothing here touches any point
forecast; the trio stays frozen.

## Object

For each model m and each backtest origin t, an interval for the first
release of the month, built ONLY from the model's own past release-eve
errors e_u = forecast_u - print_u for origins u < t whose first release
was public at t's release-eve clock (all of them, by construction of the
clock), with the origin's own clock as the as-of. Bands are quantiles of
the error distribution added to the point forecast: lo_q = f_t - Q(1 - q),
hi_q = f_t - Q(q) for the central 50 / 80 / 90 percent intervals (the sign
convention of v2.0: an upward-biased model gets a band shifted DOWN).

## Variants (all declared now; nothing added after the run)

- V0 unconditional: expanding empirical quantiles of all past errors,
  minimum 24 errors, else no band.
- V1 January split: separate pools for January and non-January targets;
  the January pool needs at least 5 errors, else it falls back to the
  non-January pool scaled by the ratio of the two pools' root mean square
  errors when at least 3 January errors exist, else to V0.
- V2 state split: pools by the core block's state dummy (trailing
  twelve-month inflation above 4% at t-1, the same line as the model) and
  January, four cells, minimum 8 per cell with fallback to V1.
- V3 scaled-t: a Student-t with 5 degrees of freedom centred on the
  expanding mean error, scale from the expanding root mean square error of
  the pool of V1 (so the January cell gets its own scale); the same
  fallbacks.
- V4 recency-weighted V1: the V1 pools with exponentially decaying
  weights, half-life 36 months, weighted quantiles.

## Evaluation (90 origins, release-eve clock, first-release actuals; the
first 24 origins can carry no V0 band and are reported as coverage of the
bands that exist)

Per model and variant: empirical coverage of the 50 / 80 / 90 intervals
on all origins, ex-January, 2024+, and the 23 big-surprise months; mean
width of the 80 interval; the probability integral transform histogram in
ten bins with a Kolmogorov-Smirnov statistic against uniform; the
continuous ranked probability score from the empirical error distribution
(all months) and the threshold-weighted version (Gneiting and Ranjan)
concentrating on |print - survey| >= 0.4; a reliability table of the
model-versus-survey deviation: for deviation buckets |f - survey| in
[0, 0.1), [0.1, 0.2), [0.2, 0.4), >= 0.4, the share of months where the
model was closer to the print than the survey, with counts.

## Selection rule (frozen)

For each model separately: keep the variants whose 80 and 90 coverage on
all origins AND on 2024+ lie within 5 points of nominal; among them the
one with the lowest CRPS; ties broken toward the simpler variant (V0 <
V1 < V3 < V4 < V2). If no variant satisfies the coverage condition for a
model, the model gets V1 with the note "uncalibrated" and its bands are
published as such. The chosen variant per model is wired into the live
row as `h0_<model>_lo80 / hi80 / lo90 / hi90` and `band_variant_<model>`,
computed at the call's own clock from the same error file the scoreboard
uses (`data/exact_historical_core_errors.csv` is NOT that file; the
release-eve headline errors are taken from `output/cz_struct_backtest.csv`
first releases, extended live by the prospective rows as they are graded).

## What this does not do

It does not calibrate January energy events (two observations); January
bands will be wide or explicitly marked. It does not produce a decision
rule; the reliability table is information for sizing, and any sizing
rule is a separate declared product. No parameter of any variant is
tuned after seeing results; failing variants stay in the output.

## RESULTS (7 September 2026, single run; log `output/bands_trio_run.log`; rows `output/bands_trio.csv`; `output/bands_trio_summary.csv`, `output/bands_trio_selection.csv`)

66 origins carry bands (the first 24 have no pool). Coverage of the 80 /
90 intervals, all origins / ex-January / 2024+ / big-surprise months,
mean 80-width, PIT Kolmogorov-Smirnov, CRPS:

| model | variant | 80 | 90 | exJan 80 / 90 | 2024+ 80 / 90 | big 80 / 90 | width80 | KS | CRPS |
|---|---|---|---|---|---|---|---|---|---|
| BASE_RIDGE | V0 | 0.80 | 0.85 | 0.82 / 0.85 | 0.97 / 1.00 | 0.60 / 0.75 | 0.84 | 0.12 | 0.225 |
| BASE_RIDGE | V1 | 0.77 | 0.83 | 0.77 / 0.84 | 0.97 / 1.00 | 0.55 / 0.70 | 0.80 | 0.11 | 0.228 |
| BASE_RIDGE | V2 | 0.80 | 0.85 | 0.80 / 0.85 | 0.94 / 0.97 | 0.65 / 0.80 | 0.85 | 0.13 | 0.233 |
| BASE_RIDGE | V3 | 0.79 | 0.83 | 0.79 / 0.84 | 1.00 / 1.00 | 0.60 / 0.70 | 0.93 | 0.10 | 0.232 |
| BASE_RIDGE | V4 | 0.79 | 0.86 | 0.79 / 0.87 | 0.97 / 1.00 | 0.60 / 0.75 | 0.81 | 0.09 | 0.228 |
| PAST_FULL | V0 | 0.77 | 0.83 | 0.79 / 0.85 | 0.97 / 0.97 | 0.55 / 0.70 | 0.88 | 0.07 | 0.236 |
| PAST_FULL | V1 | 0.77 | 0.82 | 0.79 / 0.82 | 0.97 / 1.00 | 0.55 / 0.70 | 0.82 | 0.11 | 0.240 |
| PAST_HALF | V0 | 0.79 | 0.85 | 0.80 / 0.85 | 0.97 / 1.00 | 0.60 / 0.75 | 0.88 | 0.10 | 0.226 |
| PAST_HALF | V1 | 0.76 | 0.83 | 0.75 / 0.84 | 0.97 / 1.00 | 0.55 / 0.70 | 0.79 | 0.09 | 0.231 |

(V2-V4 of the challengers are in the summary file; the pattern is the
same.) Selection under the frozen rule: NO variant keeps the 80 and 90
coverage within 5 points on all origins AND on 2024+; every model
receives V1 with the status "uncalibrated" and the bands are published as
such. Diagnosis, not a fix: the 90 band under-covers overall (0.82-0.86)
because the 2022-23 errors exceeded anything in the pools that preceded
them, and every variant over-covers 2024+ (0.94-1.00) because those same
errors then dominate the pools; neither the January split nor the 4% state
split nor a 36-month half-life separates the two regimes. A pool keyed to
a volatility regime is the obvious candidate and is NOT run here; it would
be a new declared variant.

Reliability of the model-versus-survey deviation (release eve, 90
origins): bucket of |forecast - survey| in pp, count, share of months the
model was closer to the print than the survey, mean gain |s| - |e|:

| model | [0, 0.1) | [0.1, 0.2) | [0.2, 0.4) | >= 0.4 |
|---|---|---|---|---|
| BASE_RIDGE | n=45, 0.42, -0.002 | n=26, 0.54, +0.002 | n=11, 0.36, -0.072 | n=8, 0.38, -0.083 |
| PAST_FULL | n=36, 0.36, -0.011 | n=22, 0.36, -0.058 | n=22, 0.64, +0.077 | n=10, 0.30, -0.241 |
| PAST_HALF | n=44, 0.43, -0.010 | n=22, 0.55, +0.001 | n=16, 0.44, -0.017 | n=8, 0.50, -0.114 |

Reading for sizing: a large ex-ante disagreement with the survey is not a
reliable signal on its own; when any of the three sits 0.4 pp or more from
the survey it has been closer to the print in 3 to 5 of 8-10 cases and
loses on average. PAST_FULL's useful zone is the 0.2-0.4 bucket (64%
closer, +0.08 pp, 22 months). This is the ex-ante view; the big-surprise
scoreboard conditions on the realised surprise and is a different
statement. Both hold on the same 90 months.

Wiring: the live row carries `h0_<model>_lo80 / hi80 / lo90 / hi90`,
`band_variant` = V1 and `band_status` = uncalibrated, computed at the
call's clock from the first-release errors whose release date precedes
the clock. Nothing in the points changed.
