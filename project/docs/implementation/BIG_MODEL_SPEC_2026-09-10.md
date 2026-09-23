# Big Czech CPI challenger (Bloomberg-independent)

This document defines the large research panel added on 10 September 2026.
It is a challenger to the operating independent nowcast, not a replacement for
`forecast_independent.py` or the frozen CZ-STRUCT roster.

## What the model is for

The aim is to test whether a broad set of official Czech, European and CNB
variables improves direct forecasts of monthly Czech headline CPI m/m at
one, three, six, nine and twelve months ahead.  The target is the realised
headline m/m rate.  Each horizon is fitted directly (`X_t -> CPI_{t+h}`), so
the model does not need forecasts of every covariate.

The comparison has three input policies:

* **independent**: hard data only.  It removes professional and household
  inflation expectations and all confidence/sentiment balances.
* **sentiment**: hard data plus ESI and confidence balances, still without
  inflation expectations.
* **full**: the complete local panel, including the two FMIE CPI expectation
  series.  This is a diagnostic information line, not the independent forecast.

The main result to carry forward is therefore the independent policy.  Survey
columns are never used by it, and are not used to tune it.

## Estimators

`TVW_QRF` is the existing CNB-WP-9-inspired quantile-forest point estimator,
with a twelve-observation validation window and the existing quantile-weight
constraints when the `quantile-forest` package is installed.  `BBIM` is the
blockwise depth-three boosting challenger from the Bank of England paper.
Both include three lagged headline m/m values and a month-of-year indicator.
The economic blocks are trend, domestic supply, global supply, demand, FX and
other.  Monotonic restrictions are left at zero in the generic wrapper until a
Czech sign specification is independently validated; imposing a sign merely
because it is intuitive would turn a predictive experiment into an assumption.

If `quantile-forest` is unavailable, the runner uses an explicitly labelled
sklearn random-forest tree-quantile approximation.  This keeps an offline smoke
run reproducible; it is not described as an exact TVW-QRF replication.  If a
model has too little history or an estimator fails, the wrapper returns the
last-observation forecast with a recorded fallback status.

## Official non-Bloomberg panel

The runner is `big_model_experiment.py`.  It first calls the canonical
`backtest_h0_hybrid.build_panel()` (which may refresh public official sources)
and records that choice in `manifest.json`; if its optional dependency or live
source is unavailable, it uses the explicitly labelled local DuckDB/CSV
fallback.  It never calls Bloomberg.  The current frozen run has 41 columns
before policy filtering, 35 in the hard-data
independent policy, 39 in the sentiment policy and 41 in the full policy.  The
counts are recorded in `output/big_model_all_20260910d/manifest.json`; they may
change when a source is refreshed or a short series is omitted.  The columns
are:

* Czech PPI by agriculture, industry, manufacturing, utilities, water,
  construction and services (`*_ppi_yoy`); these are year-on-year percentage
  changes from CZSO's same-period-year-ago index, not m/m rates.  The local
  adapter places reference-month values one month forward for the CZSO release
  lag.  The research-panel boundary renames the legacy adapter's `*_ppi_mm`
  columns so the transform is explicit.
* EUR/CZK and USD/CZK monthly changes; Czech industrial production, retail,
  construction and unemployment (`*_yoy`); CZSO activity is placed two months
  forward, as documented in `data/local_adapter.py`.
* CNB 3-month PRIBOR, 10-year Czech government yield and CPI/PPI real-effective
  exchange-rate changes.
* Household and NFC loan growth, trade balance, CPI breadth, weighted-median
  CPI, services CPI, the seven-item Czech farmgate basket, HPI and construction
  price growth, M3 growth and a quarterly Eurostat labour-cost index (LCI)
  growth measure.  The LCI is released three months after quarter-end and is
  held constant between releases.  CPI-derived breadth, median and services are
  placed one month forward so an unreleased current CPI cannot enter an origin.
* CZSO total import-price m/m growth, shifted one month after its reference
  month; and German HICP processed food, unprocessed food, energy, services and
  industrial goods excluding energy from the local ECB mirror, shifted one
  month.  The German food total is an explicitly labelled unweighted proxy
  because the mirror does not provide a matching CP01 weight in this snapshot.
* ESI and the three Czech confidence balances.  ESI is placed one month
  forward for the broad sentiment comparison.
* The 12- and 36-month FMIE CPI y/y means.  Their database labels are survey
  months rather than exact publication timestamps, so the full policy places
  them one month forward and keeps them out of the independent policy.

Short one-off analytical series are omitted when they have fewer than 24 finite
observations.  A monthly wage/ULC series, the exact CNB Rushin index, global
commodity indexes, building-permit counts and market inflation swaps are not
fabricated: they are listed as missing paper variables in the manifest and
remain future data work.

## Timing and evaluation

At target month `T` and horizon `h`, the origin is `T-h`.  The model receives
only rows at or before that origin.  The pure preparation layer then:

1. rejects non-monthly, duplicate or gapped panels;
2. selects a column only when its latest finite value is no more than two
   months stale at the origin;
3. computes missing-value means on training rows only; and
4. fills the origin row from those training means.

The output stores the selected columns, training count, estimator engine,
fallback reason and policy for every release.  `summary.csv` reports RMSE, MAE, bias and the share
of m/m signs called correctly.  That sign score is a general-direction
diagnostic; it is not the project's separate material surprise-capture score.

The runner accepts any positive horizon list.  The paper checkpoints are h=1,
3, 6, 9 and 12; use `--horizons 1 2 3 4 5 6 7 8 9 10 11 12 --policies
independent` to create the monthly grid used by the path work.

The first run should be a small smoke run, for example:

```powershell
python big_model_experiment.py --output-dir output/big_model_smoke `
  --oos-start 2023-01 --max-origins 6 --horizons 1 3 `
  --trees 20 --rounds 5
```

The paper-like comparison uses the full requested window and fixed settings;
the output manifest records the settings and hashes:

```powershell
python big_model_experiment.py --output-dir output/big_model `
  --oos-start 2019-01 --horizons 1 3 6 9 12 `
  --trees 200 --rounds 100
```

The files under `output/big_model/` are `forecasts.csv`, `summary.csv`,
`features.csv`, `input_snapshot.csv`, `feature_availability.csv` and
`manifest.json`.  The two snapshot files preserve the exact local panel used
by that run; the runner still rebuilds from current official sources on the
next invocation.  A research run must be compared with RW,
AR3 and the existing independent nowcast on identical target months.  It must
also be checked on recent-surprise windows and on an untouched prospective
shadow period before any policy is promoted.

## Current interpretation

The six-origin pilot is a wiring check, not evidence of superiority.  In that
small 2023--2026 tail the independent TVW-QRF happened to beat AR3 at h=1,
while the full TVW-QRF happened to be best at h=3; six observations cannot
support a model choice.  The full policy's occasional gain is not evidence that
surveys belong in the independent forecast.  The full comparison exists so we
can quantify the information value of expectations and sentiment separately.

The large panel should be treated as a disciplined screening device.  If it
does not beat the frozen hard-data nowcast on a common, predeclared window, the
answer is to reduce the panel or improve the data clocks, not to search more
hyperparameters.  If it does beat it, the gain still needs a material-surprise
score, a release-clock audit and a prospective live record.
