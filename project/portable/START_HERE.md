# Czech inflation: start on the other computer

This is the complete tracked research project: models, historical input snapshots, evaluations, recorded forecasts, the CNB-round replay, and the exact R35 dashboard. The model code and historical results are unchanged. The outer GitHub repository contains this original project under `project/`.

## 1. Open exactly the delivered page

Clone the **private** repository while signed into the same GitHub account:

```powershell
git -c core.longpaths=true clone https://github.com/Laguiar1993/czech-inflation.git
cd czech-inflation
.\open-dashboard.cmd
```

The launcher opens the self-contained September 22 R35 page in your default browser. You can also open `project/output/inflation_dashboard_r35/index.html` directly in Chrome. No Bloomberg connection or Python installation is needed just to view it. This is a dated snapshot: category data through August 2026 and a September-origin forecast path. Opening it does not refresh data.

## 2. Install the model environment

Use Windows x64 and an installed **CPython 3.12 x64** interpreter. All commands below run inside `project/`. Replace the Python path with the actual installed executable (find available interpreters with `py -0p` if the Python launcher is installed).

```powershell
cd project
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\portable\setup.ps1 -PythonExe 'C:\Path\To\Python312\python.exe' -WithBloomberg
& .\.venv\Scripts\python.exe -E -s -B -m portable restore
& .\.venv\Scripts\python.exe -E -s -B -m portable doctor
& .\.venv\Scripts\python.exe -E -s -B -m portable verify --models
```

Setup installs a checkout-local `.venv`, with the tested numerical dependencies. `restore` expands two large research CSVs and the legacy database byte-for-byte; it refuses to overwrite changed files. The exact X-13 executable used by this delivery is included. `verify --models` checks frozen records and recalculates the saved nowcast and 39 path rows offline. It does not publish a new forecast.

Sign into Bloomberg Terminal on this computer, then:

```powershell
& .\.venv\Scripts\python.exe -E -s -B -m portable doctor --bloomberg
```

A connected terminal is necessary for fresh Bloomberg pulls, not for the saved dashboard or offline forecasts. Source entitlements and ticker coverage are checked separately by capture/readiness. If Bloomberg uses a separate supported Python environment, use `capture-bloomberg --python FULL_PATH`; keep the model environment pinned. See [ENVIRONMENT.md](ENVIRONMENT.md) for setup, repair and dependency details.

To serve the same page at localhost:

```powershell
& .\.venv\Scripts\python.exe -E -s -B -m portable serve --open
```

Keep that terminal running. If port 8766 is occupied, add `--port 8767`.

## 3. Operate a new nowcast and inflation path

[MANUAL_INPUTS.md](MANUAL_INPUTS.md) is the operator reference: exact Bloomberg tickers, official download URLs, file layouts, units, release clocks and examples. Start with its checklist. Use a **new directory for every capture, prepared bundle and run**. A downloaded historical series is a current vintage, not historical real-time evidence.

The following is a command sequence, not a scheduled job. Replace every `NEW_*` name, `YYYY-MM`, and `YYYY-MM-DD` before running. Use the real current decision month and completed observation date. Manual core/regulated rows are only needed if Bloomberg lacks a released observation.

```powershell
# This alias lasts only for this PowerShell session.
function cpi { & .\.venv\Scripts\python.exe -E -s -B -m portable @args; if ($LASTEXITCODE -ne 0) { throw 'CPI command failed; inspect its output before continuing.' } }

cpi capture-bloomberg --lane nowcast --output output/manual_inputs/NEW_BBG_NOWCAST --end-date YYYY-MM-DD
cpi capture-bloomberg --lane path --output output/manual_inputs/NEW_BBG_PATH --end-date YYYY-MM-DD
cpi capture-public --kind farm --output output/manual_inputs/NEW_FARM

# Create the sourced release-calendar CSV described in MANUAL_INPUTS section 4.
# If necessary, create core/regulated supplement rows using section 3.
cpi prepare-nowcast --snapshot output/manual_inputs/NEW_BBG_NOWCAST --farm-raw output/manual_inputs/NEW_FARM/CEN0203B.csv --target YYYY-MM --output output/forecast_updates_r33/NEW_BUNDLE
# Add --manual-inputs output/manual_inputs/NEW_CNB/manual_inputs.csv if required.

cpi readiness --bundle output/forecast_updates_r33/NEW_BUNDLE --target YYYY-MM --calendar output/manual_inputs/NEW_CALENDAR/live_calendar.csv
cpi nowcast --bundle output/forecast_updates_r33/NEW_BUNDLE --target YYYY-MM --calendar output/manual_inputs/NEW_CALENDAR/live_calendar.csv
```

Read the nowcast result. Continue only after a successful prospective run; copy its exact new `runs/...` directory into `--nowcast-run` below. A blocked run is not a forecast. The BASE model is the production point; HALF/FULL are separate variants. The path must inherit this recorded h0 and its components.

```powershell
cpi prepare-path --current-bundle output/forecast_updates_r33/NEW_BUNDLE --capture output/manual_inputs/NEW_BBG_PATH --farm-raw output/manual_inputs/NEW_FARM/CEN0203B.csv --origin YYYY-MM --output output/current_path_r34_inputs/NEW_PREPARED
cpi run-path --bundle output/forecast_updates_r33/NEW_BUNDLE --inputs output/current_path_r34_inputs/NEW_PREPARED --nowcast-run output/forecast_updates_r33/portable/runs/EXACT_SUCCESSFUL_RUN --output output/current_path_r34/NEW_RUN
```

For new approved energy announcements, supply the same `--announcements PATH` to readiness, nowcast and run-path, as described in the manual guide. The wrapper archives this input with h0. Do not put an announcement into an observed CPI series.

New output directories contain the record, manifests, forecasts and diagnostics. **These commands do not rebuild the sealed R35 HTML.** The dashboard builders and all source data are included, but publishing a later dashboard requires a new dated build and validation connecting the new forecast and analysis records. Do not relabel the September snapshot as current after refreshing data. This boundary preserves what was actually forecast at each date.

## 4. Refresh the category momentum analysis

This lane is separate from independent model inputs. After detailed CPI, obtain the CZSO category panel and run:

```powershell
cpi capture-public --kind categories --output output/manual_inputs/NEW_CATEGORIES
cpi prepare-momentum --capture output/manual_inputs/NEW_CATEGORIES --through YYYY-MM --output output/momentum_r35_inputs/NEW_PREPARED
cpi momentum --prepared output/momentum_r35_inputs/NEW_PREPARED --output output/momentum_r35/NEW_ANALYSIS
```

The model, nowcast and analysis clocks may differ; retain them separately. Basket revisions and source-history conflicts stop preparation for a reviewed integration. Never bypass that by changing frozen hashes. CNB forecasts/consensus remain benchmarks, never inputs to the independent forecast.

## 5. What is included and how to work safely

- `models/`, `data/`, `tools/`, tests, implementation specs and result notes contain the full research program, including rejected alternatives and historical evaluations.
- `output/inflation_dashboard_r35/` is the delivered page; the replay and model roster are preserved in it.
- `portable/SOURCE_TREE.json` pins every source project file to the source commit and its exact SHA-256. `portable verify` also checks the R35/R34 records.
- `portable/packed/` holds lossless large-file archives. The legacy DuckDB is for older database-backed workflows; current production uses explicit Bloomberg bundles.
- The private GitHub release includes a `.bundle` of the original Git history. Download it if you need original branches/commits. `git bundle verify PATH` checks it; `git clone PATH history-checkout` restores it separately. The main repository starts from this portable snapshot so GitHub accepts its large historical assets.
- `.venv`, caches and unpacked archives stay local. Credentials and Bloomberg Terminal installation are not copied. The repository is private; keep it private.

After editing code or collecting new data, commit deliberately selected new files and push; on the other computer pull before working. Never edit historical hash-frozen sources, specs, inputs or outputs. Add a new version when changing a model. Do not rerun old sealing scripts. Huge new artifacts need compressed storage or a release asset, following the same verified restoration pattern.

For ongoing work, read the latest model register and R35/R34 result notes, then [MANUAL_INPUTS.md](MANUAL_INPUTS.md). Older handoffs describe earlier rosters; they remain evidence, not a replacement for the current production instructions.
