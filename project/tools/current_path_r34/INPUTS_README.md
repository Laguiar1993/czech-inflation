# R34 observed path inputs

Implemented in `inputs.py`; no forecast, model fit, database write or frozen-file modification is performed.

## Ready input snapshot

Use `output/current_path_r34_inputs/prepared_20260922_v2` for the September 2026 origin. V1 remains immutable as an initial integration artifact: its variable fractional-second formatting is incompatible with the parent's default pandas date inference. V2 changes timestamp serialization to uniform six-digit fractional seconds; observations and availability instants are unchanged.

- Actual V2 preparation: `2026-09-22T19:03:59.756037+00:00`.
- Global source availability: `2026-09-22T18:45:34.705323+00:00`.
- Bloomberg capture completion: `2026-09-22T18:43:35.812155+00:00`.
- Official CZSO farm capture completion: `2026-09-22T18:45:34.705323+00:00`.
- Food CPI, food PPI and four-product farm levels: January 2015–August 2026, 140 months.
- All 139 accepted training rows through July 2026 are numerically unchanged.
- Gross pump prices: 3 January 2005–14 September 2026, 1,088 Monday observations; the last observed week is usable after 21 September.
- Headline m/m history: February 1991–August 2026, 427 months. Exact captured-level ratios replace February 2015–August 2026; older accepted history is retained.
- Headline levels: January 2015–August 2026. August level 102.6 versus August 2025 level 100.7 yields 1.8867924528301883% y/y; July-to-August yields 0.2932551319648091% m/m. These reconcile to published 1.9% and 0.3%, respectively.

Both `inputs.load_prepared` and the parent's unchanged `run.load_inputs` loaded V2 successfully. The parent additionally gates the actual preparation timestamp; choose a new recording clock after the preparation time. No final path, dashboard or delivery seal was created by this sidecar. No commits were made.

## Integration API

```python
from tools.current_path_r34.inputs import prepare, load_prepared

result = prepare(
    base_bundle, current_bundle, bloomberg_capture, new_output_directory,
    origin='2026-09', as_of='2026-09-22T19:10:00+00:00',
    farm_raw='output/current_path_r34_inputs/farm_capture_20260922/CEN0203B.csv',
)
frames = load_prepared(new_output_directory, as_of=decision_clock)
```

The example clock must be replaced with an actual, aware clock no later than the current time. Both functions return a dictionary containing `food_levels`, `food_available`, `pump_weekly`, `headline_history`, `headline_levels`, `provenance`, and `output` (a pathlib Path). Monthly indexes are sorted, unique pandas PeriodIndex objects. Returned food frames use the model's exact column order `agri4, food_ppi, food`. Availability frames hold UTC timestamps. CSV column order follows the export contract below.

`prepare` accepts source paths relative to the caller's working directory or absolute paths. It refuses any existing output directory, validates before creating the output, and writes a manifest only after all output files are complete. An incomplete directory is never accepted as a prepared snapshot. `load_prepared` validates output and source manifests, original raw farm bytes/metadata, every source clock, and numerical frame contracts on each read. It does not require that retrieval time equal the h0 decision time; these are independently recorded inputs for the later path.

## Export contract

| File | Columns / meaning |
| --- | --- |
| `food_levels.csv` | `period,food,food_ppi,agri4`; 100 log-level points normalized to zero in January 2015. |
| `food_available.csv` | Same columns; UTC ISO timestamps with uniform six fractional digits. Missing upstream observations have blank value and blank timestamp, never interpolated values. |
| `pump_weekly.csv` | `date,gross_petrol95,gross_diesel`; Monday labels, CZK/l. No net/tax columns. |
| `headline_history.csv` | `period,headline_mm`; exact available index ratios where both adjacent levels exist, otherwise preserved older history. |
| `headline_levels.csv` | `period,headline_level`; unmodified captured CZCPI levels for precision/reconciliation. |
| `provenance.json` | Origin/target, requested clock, actual preparation timestamp, global availability, per-source hashes/clocks, definitions, coverage, baseline overlap checks, readiness, headline precision reconciliation. |
| `MANIFEST.json` | `files` maps relative file names to SHA-256 hashes; includes all five CSVs, provenance and local `.gitattributes`. |

All exports use explicit UTF-8. Local `.gitattributes` specifies `* -text` to prevent checkout newline conversion from invalidating hashes.

## Source definitions and historical preservation

Food: `100*log(CZCPF / CZCPF[2015-01])`, matching the accepted Bloomberg path. The fresh capture has exactly zero discrepancy over every accepted month. A conflicting overlap fails instead of silently replacing or splicing revised training values. Uniform source-index rebasing is acceptable only if every normalized overlap value remains identical within 1e-9 log points.

Food PPI: unchanged `tools.bloomberg_lane.food_ppi_variant.cumulated_level`, i.e. cumulative `100*log1p(CZPPA10M/100)` rebased to January 2015. The preparer additionally rejects missing months and nonpositive gross ratios before calling that helper. Actual overlap differs by at most 1.4210854715202004e-14 because of floating-point summation; original training values are retained exactly.

Farm: reuse the exact `PRODUCTS` declared by `tools.r14_food.prepare_inputs` (wheat, milk, pigs and chickens), select national monthly rows from CZSO CEN0203B, and calculate the equal mean of each product's `100*log(price / Jan2015 price)`. All four positive prices are required; regional rows, duplicate product-months and partial means are rejected. This is distinct from the seven-product nowcast basket. Fresh official August prices are wheat 4557, milk 9724, pigs 35489 and chickens 30425 in the original physical-price units. The resulting August agri4 value is preserved in the CSV; fresh historical overlap is exactly zero.

The fresh official dataset is archived from https://data.csu.gov.cz/opendata/sady/CEN0203B/distribuce/csv with response headers, start/end retrieval times and hashes. It contains August, so September's path uses a fully observed August farm row. The inherited 26th-of-next-month farm clock is a model convention, not a verified publication timestamp. Actual newly retrieved official observations become available only at retrieval completion. Existing historical model clocks remain unchanged as instants. If no new farm file is supplied, the hash-verified R33 raw file is used; a trailing gap stays missing and is explicitly labelled under the accepted model lag convention, failing once overdue. No missing farm values are filled.

An explicit `farm_raw` must have adjacent `<filename>.metadata.json` containing `source`, `sha256`, timezone-aware `retrieved_at`, and `completed_at`. The supplied archive also includes its own manifest.

Gross pumps: use only the already verified R33 portable market's ECOBETCZ/ECOBOTCZ observations, divided by 1000 from CZK/1000 litres. Source dates map to ISO-week Monday and agree with R33's weekly gross frame. A week is not used before Monday+7 days; unpaired, nonpositive or conflicting prices fail. Removing unused net columns avoids the accepted model discarding fresh gross prices because older net prices are absent.

Consumer readiness independently requires twelve complete months through August in the current bundle's headline, core, regulated, alcohol and food/fuel frames. Current bundle capture/manual availability is rechecked against the requested as-of. Its R33 h0 and the frozen frames are never changed.

Headline exactness means exact arithmetic on the captured index, which itself is rounded to one decimal. It does not claim to recover unrounded official CPI. Provenance includes the resulting annual difference (-0.013207547169811651 percentage points in August), the interval induced by half-unit index rounding, the replaced history span, and the published annual comparator. The known-history values are for compounding the path; they do not revise the independently archived h0.

## Capture and preparation commands

From the repository root, Bloomberg capture uses Anaconda with its DLL path. The existing capture tool performs read-only BDP/BDH requests and archives all raw and normalized source hashes. Every capture/output path must be new.

```powershell
$env:PATH='C:/Users/luis_/anaconda3;C:/Users/luis_/anaconda3/Library/bin;C:/Users/luis_/anaconda3/Scripts;'+$env:PATH
$env:PYTHONPATH=''
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
& 'C:/Users/luis_/anaconda3/python.exe' -B -m tools.market_data.probe_bloomberg_candidates `
  --config tools/current_path_r34/capture_config.json --end-date 2026-09-21 `
  --output output/current_path_r34_inputs/NEW_CAPTURE
```

The shipped capture `bloomberg_capture_20260922` completed successfully in seconds with five tickers, 140 observations each, and no Bloomberg errors. The official farm archive is `farm_capture_20260922`. No browser or message/trading action is necessary.

```powershell
$env:PYTHONPATH='C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$decision=[DateTimeOffset]::UtcNow.ToString('o')
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B -m tools.current_path_r34.inputs `
  --base-bundle data/bloomberg_inputs_20260922_foodppi `
  --current-bundle output/forecast_updates_r33/current_bundle_20260922_v2 `
  --capture output/current_path_r34_inputs/bloomberg_capture_20260922 `
  --farm-raw output/current_path_r34_inputs/farm_capture_20260922/CEN0203B.csv `
  --origin 2026-09 --as-of $decision `
  --output output/current_path_r34_inputs/NEW_PREPARED
```

## Verification

Run `python -B -m unittest tools.current_path_r34.test_inputs -v` under the bundled environment above. All 26 tests pass. The first suite run failed before implementation. A separate regression reproduced pandas dropping mixed-precision current timestamps, failed before the serialization fix, then passed with all other tests.

Tests cover missing consumer months/January anchors, duplicate capture and farm rows, nonpositive levels/PPI ratios/pumps, conflicting food and PPI overlap, raw-versus-normalized disagreement, source/output tampering, naive/future/earlier clocks including current manual and official farm capture clocks, incomplete farm baskets, historical row preservation, legitimate ragged-edge handling, exact annual compounding from headline ratios, gross prices surviving stale net columns, and immutable outputs.

Actual V2 passed both loaders, verified every referenced source manifest, and rejected the real earlier source clock `2026-09-22T18:45:34+00:00`. The parent owns forecast execution, historical parity, final review, commits and delivery sealing.
