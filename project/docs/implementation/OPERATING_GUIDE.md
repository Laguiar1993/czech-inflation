# CZK Cpi Forecasting - Latest models

The independent release nowcast is the operational starting point. The path
models are a separate research product. Both predict consumer inflation; neither
yet provides a validated CZK rates position-sizing rule.

## The short-term forecast

Use `HARD_BASE` as the main point forecast. It combines core, food, alcohol and
tobacco, administered prices, measured fuel and a reconciliation wedge. The core
regression excludes `exp12`, `exp36`, `exp12_x_state`, `household_exp` and `esi`.
Thus neither professional nor household inflation expectations feed the main
forecast. Historical measured prices remain legitimate inputs even when their
statistical source is a survey.

`HARD_HALF` and `HARD_FULL` learn from sequential errors made by that same
independent core regression. They do not inherit the original model's error
history. HALF applies half the learned adjustment; FULL applies all of it.
They are challengers, not different data sources. The main forecast's block
contributions sum to its unrounded headline point.

The optional expectations-conditioned comparison retains the original inputs
and legacy error history explicitly. A current-release consensus number remains
a comparison benchmark, never a regressor in this independent family. ESI was
tested separately and failed its predeclared practical inclusion rule.

## What the experiment established

On the same 90 first-release comparisons, main RMSE is 0.417952, HALF 0.413696,
FULL 0.413931, and consensus 0.381517 percentage points. The new independent
family therefore does not beat consensus over the full sample. From 2024 the
main RMSE is 0.218978 versus 0.240966 for consensus. Removing expectations is
compatible with useful accuracy; it does not establish unconditional superiority.

For 23 actual surprises of at least 0.4 pp, FULL has MAE 0.476061 versus consensus
0.578261, with 9 material wins and 2 material losses at the 0.15 pp threshold.
However, on its 23 alerts where the forecast differs from consensus by at least
0.2 pp, its accumulated absolute-error advantage is **negative**, −1.290482 pp.
We know which historical releases were big only after observing them. The alert
score counts false alarms too; it is not a rates-market P&L calculation.

The paired block bootstrap includes zero for HALF/FULL's overall RMSE difference
from BASE. These are small, exploratory improvements. Repeated previous model
research means none of these historical frames is an untouched test set.

## Reproduce a forecast without a database

Install the dependencies in a virtual environment from `requirements.txt` (or
the supplied `requirements-r9-lock.txt` for the reviewed runtime). The food model
uses the Census X-13 binary; set `CZ_X13_PATH` to the installed executable. If it
fails or is unavailable, food falls back to ridge and the diagnostics show the
method; that fallback will generally produce a different forecast. Exact replay
requires the same binary and numerical-library versions.

From the repo directory:

```powershell
python forecast_independent.py --fixture --target 2026-07 --as-of 2026-08-04T23:59:00+02:00 --include-expectations-comparison --path
```

The command writes a new `output/runs/<timestamp>_<id>/` folder. It contains each
consumed frame, their hashes, the decision clock and the unrounded forecast.
It re-reads the serialized inputs before calculating, so the archive itself is
the input to the reported result. This is a historical fixture demonstration,
not a forecast made before July 2026's outcome was known to this project.

With `--path`, the same archive produces `path.json` and `path.csv`, including
complete quarterly averages. Every path starts with the identical `HARD_BASE`
point. The independent component bridge, forest, BVAR and trend models are shown
as research comparisons. The component bridge excludes expectations at every
horizon; it does not reintroduce them beyond the nowcast month.

Replay that exact folder:

```powershell
python forecast_independent.py --replay output/runs/<timestamp>_<id>
```

Replay rejects changed input files or changed source/static-data files. It does
not silently substitute a refreshed source. Preserve the entire versioned bundle
alongside the archive, including the recorded runtime requirements.
The checks run both before and after calculation, so an intervening source or
data edit prevents publication of a completed receipt.

The delivery includes the verified example
`output/runs/20260909T083745Z_98fbb1c9`. Replay it with:

```powershell
python forecast_independent.py --replay output/runs/20260909T083745Z_98fbb1c9
```

Use the portable ZIP when moving this saved example to another computer: it
preserves the exact archived file bytes. A Git checkout configured to convert
line endings can correctly fail the byte-hash checks. The scientific runtime
and X-13 installation are external requirements; the local economic database
is needed for new live runs, but not for this frozen replay.

## Make a new independent nowcast

Set `CZ_CPI_DB` to the local `czechia.duckdb` database and `CZ_X13_PATH` to the
binary. Refresh upstream data with the existing source-specific ingestion
workflow. The new entry point is a forecast runner, not a universal database
refresh tool.

```powershell
python forecast_independent.py --live --target 2026-09
```

The live mode uses the capture clock and rejects a manually backdated `--as-of`.
Monthly features and food inputs are masked to the same clock. For an incomplete
FX month, it uses the already-declared month-to-date rule, excluding all call-day
fixings. The exact gated FX input is stored separately so replay retains it.

Inspect `ready_for_first_release`, `before_first_release`, `detailed_CPI_edge_gap`,
`component_history_edges`, `missing_inputs`, food/fuel diagnostics and residual-forest status. A point can still be
computed with imputation; that alone does not make it a clean first-release
forecast. In particular, after a flash but before detailed CPI is available,
the next month's component history can be incomplete. A known flash headline
does not supply the missing core and food breakdowns.

The archive records retrieval/capture and completion times. It does not turn old
latest-vintage observations into historical releases. Genuine prospective
evidence begins when a complete forecast archive is written before the outcome.
`prospective_eligible` requires a live capture, clean input readiness and completion
before the first release. Historical fixture runs can never qualify. Receipts
hash the results as well as the snapshots. Replay rejects nonfinite or missing
points instead of declaring them equal by accident.

## What was repaired

An incomplete prospective energy announcement can no longer fall through into
the old reconstructed block-unit mapping. Quarterly comparison now includes
known months and suppresses incomplete final quarters. Path state transitions,
known lag propagation, BVAR horizons and measurement-unit invariance were fixed;
failed optimizations and nonfinite forecasts carry explicit diagnostics.

The unemployment archive contains 103 publication vintages, January 2018–July
2026. Each path origin selects the complete history then published. Earlier
origins are not certified by that archive. Imports remain latest-vintage, and
FX timing retains a month-close assumption. See `VINTAGE_FINDINGS.md`.

## What remains research

The new energy ledger treats monetary credits, VAT, caps and expiry consistently.
It replaces the explicitly embedded baseline energy contribution to avoid double
counting. Its scenario ranges are wide because customer/product exposure and CPI
allocation are not identified. They are assumption envelopes, not probability
intervals or ready-to-use point forecasts.

The old `path_live.py` and step-two to step-five backtests remain historical
research interfaces. Some wrappers discard known future lag rows and new failure
diagnostics. Their old scoreboards must not be labelled results of the repaired
models. The old model-consistent gap variant also has an unresolved flat versus
geometric terminal-condition specification. Use the new independent path
experiment for corrected comparisons and keep this variant demoted.

No nowcast or path interval is certified as calibrated. Original nominal 90%
bands undercovered in the audited first-release sample. Probability calibration,
alert selection, and rates-market response require separate prospective work.

## Parameter optimization

Coefficients are already estimated from available history. Ridge strength,
forest complexity, validation length and several path assumptions are separate
settings. A nested tuning experiment must choose those settings from earlier
forecast errors before evaluating the next release. Random train/test splits
are unsuitable for this task.

The first new grid tested 12 ridge/window settings and ran 2,244 sequential fits.
Nested selection worsened overall headline RMSE from 0.417952 to 0.419449 and MAE
from 0.262516 to 0.270661. It improved the 2024+ RMSE but worsened the flash frame.
Therefore the fixed default stays. Full details and every chosen setting are in
`TUNING.md` and `output/core_tuning_*`. Forest tuning is recorded separately.

The nested forest search selected one of four forests and a zero/half/full
correction using earlier errors. It produced 0.413013 overall headline RMSE,
about 1.18% better than BASE, and 0.262233 MAE. Its 2024+ RMSE worsened slightly
while the flash-era RMSE improved. Conditional big-surprise MAE was 0.474699, but
the selected alerts still lost 0.697695 pp of aggregate absolute-error advantage
against consensus. The tuned rule remains research; it has not earned a new
default or a trade signal. See `FOREST_TUNING.md` for every setting and selection.

New simple sequential 90% error bands covered 87.9% of 66 eligible BASE and HALF
outcomes, and 86.4% for FULL. These use only previously published first-release
errors, with at least 24 warm observations and at most 60. They are empirical
diagnostics, not guaranteed or prospectively calibrated probability intervals.

Useful computation should test stable economic alternatives and validate
uncertainty. It cannot manufacture more independent inflation crises or remove
missing historical vintages. A broad historical search would need a correspondingly
more demanding prospective validation period.
