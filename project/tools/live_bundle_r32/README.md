# Independent Bloomberg bundle adapter (R32)

Standalone h0 entry point for the approved R31C default. All work is additive;
`forecast_independent.py`, `cz_struct.py`, models, frozen bundles and release
calendars are unchanged. No dashboard integration, source refresh, path extension,
research retuning, seal script or commit is performed here.

## Use

Run from the repository root in PowerShell:

```powershell
$env:PYTHONPATH='C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs'
$env:PYTHONDONTWRITEBYTECODE='1'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython -m tools.live_bundle_r32 inspect --bundle data/bloomberg_inputs_20260922_foodppi --target 2026-09 --as-of 2026-09-22T12:00:00+02:00
& $cpiPython -m tools.live_bundle_r32 readiness --bundle data/bloomberg_inputs_20260922_foodppi --target 2026-07 --as-of 2026-08-04T23:59:00+02:00
& $cpiPython -m tools.live_bundle_r32 run --bundle data/bloomberg_inputs_20260922_foodppi --target 2026-09 --as-of 2026-09-22T12:00:00+02:00
```

`inspect` and `readiness` are aliases. Every command requires an explicit `YYYY-MM`
target and timezone-aware decision timestamp. Timestamps are converted to Prague
wall time for the unchanged model. UTC and fixed offsets work across DST.

JSON goes to stdout; model chatter goes to stderr. Exit 0 means inspection is ready
for calculation, or a run produced a validated result. Exit 2 means blocked or
invalid inputs. Inspection never emits forecast points. A successful run exposes
`forecast.points_mm_pct.HARD_BASE/HARD_HALF/HARD_FULL`, with HARD_BASE primary.
`ready_for_calculation` is a preflight flag; `forecast_available` and
`ready_for_first_release` remain false until an actual calculation succeeds.

Optional `--output output/live_bundle_r32/<new-name>.json` writes a new report,
refusing to overwrite existing files. It is restricted to this new output subtree.
The supplied September clock is an explicit inspection example, not an implicit
"now" or a contemporaneously archived forecast. Commands do not make network calls.

## Input contract and R31C

`MANIFEST.json` must contain `files: {relative_path: sha256}`. Every listed file is
verified before any frame is parsed; required but unlisted files are rejected.
Paths cannot escape their root, including through symlinks. Parsing uses the
verified bytes. Hashes attest integrity relative to the supplied manifest, not an
external digital signature.

The seven monthly CSVs under `nowcast/` use the existing R31 bundle schema:
`target_headline_cpi_mm.csv`, `component_food_fuel_mm.csv`, `cnb_core_mm.csv`,
`cnb_regulated_mm.csv`, `alcohol_tobacco.csv`, `core_features.csv`, and
`food_block_features.csv`. Their first column is the monthly index. `reg` and
`regulated` are accepted for the one-column regulated series. Required HARD and
food features must exist, with unique chronological rows and numeric values.
Missing values are permitted for publication gating and checked for staleness.
No new feature rows or extrapolated monthly observations are created.

R31C is always applied:

- Drop `services_l1` from the entire core frame, including sequential error fits.
  Unexpected services interactions are rejected.
- Replace every populated historical fuel-component cell with
  `100*(CP7FCZ[t]/CP7FCZ[t-1]-1)`. Both consecutive index months must exist;
  missing months cannot become a two-month change or a CZSO fallback.
- Read `nowcast/fuel_weekly_variant_b.csv` and verify every populated petrol/diesel
  value against `ECOBETCZ Index`/`ECOBOTCZ Index`, divided by 1000 into CZK/l.
  Bloomberg dates map to ISO-week Monday, as in R31. No CZSO substitution is allowed.
  The model retains its Monday + 7 calendar days publication rule.

For the existing R31B bundle, the hash-listed `provenance.json` pins external
`data/market_snapshots/.../history_long.csv` files relative to the repository root.
Only these listed snapshots are read and hash-checked, in the original sorted
snapshot order. No directory glob can silently pick up a newer pull.

A portable refreshed bundle can instead include hash-listed
`market/history_long.csv` with `ticker,observation_date,value`. It needs positive,
finite CP7FCZ and EC pump levels covering the frames. Dates are naive midnight
observation dates. The file may also include `EURCZK CNB Curncy` fixings. Upstream
monthly frame preparation is still required: this adapter does not rebuild the
old fixture-based bundle or infer absent features from newer raw snapshots.

## Clock, FX and calendar

For a current-month target, Bloomberg daily EUR/CZK fixings strictly before the
Prague call date form the MTD mean. The previous month's daily mean is rounded to
three decimals, matching the R31 monthly convention. The resulting m/m and state
interaction pass through `gated_mtd_fx`, the existing calculate seam. The call-day
fixing is excluded even after its usual publication time. Historical complete-month
feature values stay unchanged. A seven-calendar-day freshness/coverage guard checks
both months' starting coverage, latest fixings and maximum interior gaps; this is
an explicit conservative guard, not a Czech holiday calendar. After the first seven days, unavailable MTD FX blocks readiness.

The frozen `data/release_calendar_cz_cpi.csv` keeps its original date-at-09:00-Prague
semantics. Optional `--live-calendar <file.csv>` accepts these columns:

```csv
target_month,first_release_dt,detail_release_dt,available_from,source
```

Populate rows only with verified release metadata. All three timestamp fields
must have explicit timezones; `source` is mandatory and should identify the
release-page URL or other evidence. Rows are eligible only after `available_from`.
The file may append targets strictly after the frozen calendar's final target;
it cannot replace, backfill or correct any frozen target. Conflicting frozen
calendar history therefore remains a separate unresolved issue. No release date
examples are fabricated here.

The merged calendar is supplied to `cz_struct._CAL` only during the model call and
restored in `finally`; neither calendar file nor `_CAL_PATH` is changed. Run the
standalone CLI in its own process. Concurrent use of the frozen model's global
caches by unrelated callers in the same interpreter is unsupported.

Readiness checks target/previous release metadata, the first-release boundary,
released component edges through target minus one, minimum history, feature rows,
due versus unpublished inputs, every due weekly pump observation and usable MTD FX.
The publication rules mirror the frozen model and retain its latest-vintage
limitation. They do not certify a historical data vintage.

## Dependencies and current production limitation

Inspection imports only the standard library, NumPy and pandas (with Prague
timezone data). Model packages are discovered without importing `cz_struct` or any
model loader. `run` requires actual NumPy, pandas, SciPy, scikit-learn, statsmodels,
quantile-forest, duckdb and requests in the same interpreter, plus X13. Set
`CZ_X13_PATH` if its default `~/x13as/x13as/x13as.exe` is wrong. Discovery is a
preflight check; `run` also imports the actual packages to detect DLL/transitive
failures. No dummy modules, fake imports or automatic package installation exist.
X13/forest fallback results are blocked instead of advertised as production points.

The shared bundled runtime still lacks duckdb and requests, but the authorized
isolated setup now supplies **duckdb 1.5.5** and **requests 2.34.2**, including their
real dependencies, from `C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime`. The
bundled Python is 3.12.14 and X13 is present. Neither the shared runtime nor
`../pythonlibs` was modified. Both module import paths were verified under the
isolated directory. The directory is temporary and must be recreated if removed.

Installation used bundled pip with `--no-cache-dir --no-compile --target` and an
installation report. To reproduce the resolved versions:

```powershell
& $cpiPython -m pip --disable-pip-version-check install --no-cache-dir --no-compile --target 'C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime' duckdb==1.5.5 requests==2.34.2 charset-normalizer==3.5.1 idna==3.20 urllib3==2.8.0 certifi==2026.7.22
$env:PYTHONPATH='C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs'
$env:PYTHONDONTWRITEBYTECODE='1'
```

`output/live_bundle_r32/dependency_install_20260922.json` records wheel URLs,
hashes and the complete resolved installation. The adapter itself still performs
no automatic installation.

The supplied bundle at the September 22 inspection clock additionally needs:

- August headline, food, core, regulated, alcohol and fuel-component history.
- Refreshed September core/food feature rows: import prices, core lags and state,
  food lags, the released farm-price lag and food PPI. `agri_l0` is correctly
  classified as NOT_DUE at the specified September 22 clock.
- EC pump observations dated August 31, September 7 and September 14.
- Fresher EUR/CZK fixings (the pinned snapshots stop September 11).
- Sourced September CPI first/detailed release dates in the separate live calendar.

Farm prices, announcement history, basket weights and other existing static model
inputs retain their original source requirements. This adapter does not extend
stale forecasts, fetch announcements or claim a current nowcast.

## Validation and evidence

```powershell
& $cpiPython -m pytest tools/live_bundle_r32/test_adapter.py -q -rs -p no:cacheprovider
```

Tests were written and observed failing before their implementation. They exercise
hash corruption/omissions/path escapes, R31C coverage, schemas, current-month FX,
release boundaries, DST, frozen-calendar preservation, JSON CLI behavior and lazy
real-dependency checks. Tests create temporary files only in the new tools subtree.

Verified on 22 September 2026 with the isolated real-dependency setup:
**35 passed, 0 skipped, 0 failed in 12.07 seconds** after the P2 current-month FX
coverage fix. The test command included `--tb=short`; all other arguments are shown
above. Both new regressions (missing starting coverage and an interior gap despite
a fresh final fixing) failed before the fix and pass afterward. Current-month
coverage now uses the same seven-calendar-day start and maximum-gap limits as the
previous month, before constructing `gated_mtd_fx`. Recorded July numerical parity
still passes with the isolated real dependencies. Existing saved reports are
unchanged and retain their original verification counts.

The archived July 2026 clock (`2026-08-04T23:59:00+02:00`) passes data readiness.
The bundle and all snapshot hashes match the archived R31C manifest, and every
archived R31C output is hash-verified. Numerical parity now passes for all three
HARD forecasts and every contribution against `run_C123.csv`, at absolute tolerance
1e-10. The separate fresh recorded-July CLI run exited 0 with `status: calculated`,
food method `x13`, and no HARD residual-forest fallback:

| Forecast | m/m percent |
|---|---:|
| HARD_BASE | 0.4734274935716145 |
| HARD_HALF | 0.5450927541467958 |
| HARD_FULL | 0.6167580147219772 |

The fresh run's maximum absolute forecast difference is
0 pp; its maximum absolute contribution
difference is 8.3266726846886741e-17 pp. This is a
recorded-clock engineering replay, not a current or prospective forecast.

```powershell
& $cpiPython -m tools.live_bundle_r32 run --bundle data/bloomberg_inputs_20260922_foodppi --target 2026-07 --as-of 2026-08-04T23:59:00+02:00 --output output/live_bundle_r32/run_recorded_202607_real_dependencies.json
```

The output filename is already occupied; choose another new filename to repeat the
command. `verification_real_dependencies_20260922.json` records precise differences,
real import locations and hashes proving the prior inspections, frozen calendar,
`forecast_independent.py` and `cz_struct.py` remained unchanged.

Saved machine-readable inspections are in `output/live_bundle_r32/`:
`readiness_20260922.json` and `readiness_recorded_202607.json`. Both have
`forecast_available: false` and were deliberately preserved, including their
original missing-dependency findings. `run_recorded_202607_blocked.json` was also
preserved. The new successful recorded replay is
`run_recorded_202607_real_dependencies.json`; it does not remedy the missing current
inputs listed above. No current forecast was created. Nothing has been committed;
integration belongs to the parent task.
