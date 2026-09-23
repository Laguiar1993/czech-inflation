# R34 forecast context sidecar

Implements the accepted `docs/implementation/dashboard_r34/PLAN.md` statistical rules without fetching data, fitting models, rerunning backtests, selecting models, changing h0, or modifying frozen files. The parent supplies the fresh monthly path and core-recipe sensitivities.

## Public interfaces

```python
from tools.forecast_context_r34.analysis import (
    base_effect_ledger, empirical_ranges, seasonal_context,
)
from tools.forecast_context_r34.build import assemble, build

rows = base_effect_ledger(history_mm, forecast_mm)
context = seasonal_context(bundle_directory, successful_record_directory)
artifact = assemble(as_of="2026-09-22T18:30:00Z")
```

`history_mm` and `forecast_mm` are mappings or pandas Series indexed by canonical `YYYY-MM`/monthly Periods. Pair sequences are also accepted so duplicate keys can be rejected. They contain monthly percentage changes, **not levels or gross factors**. History must exclude all months on/after forecast h0; it must contain the complete prior twelve months. Forecast support is contiguous and 1-13 months long, h0 through h12. No gaps are filled. At h12 the dropout is forecast h0, never an observed future print. The initial annual rate is computed from twelve monthly gross factors. Supplying precise headline-index ratios preserves their precision; this function does not substitute a rounded annual starting value.

The ledger is a list of:

```json
{"month":"2026-09","h":0,"mm":0.2,"dropout_mm":-0.6,
 "previous_yy":1.9,"base_effect_pp":0.0,"new_price_pp":0.0,"change_pp":0.0,"yy":0.0}
```

This is a **field-shape illustration**, not numeric forecast output. For each actual output row:

- Remove the old print: `removed = (100 + previous_yy) / (1 + dropout_mm/100) - 100`.
- Add the new print: `yy = (100 + removed) * (1 + mm/100) - 100`.
- `base_effect_pp = removed - previous_yy`; `new_price_pp = yy - removed`.
- Both effects sum to `change_pp = yy - previous_yy`. The allocation depends on this stated removal-then-add order.

`empirical_ranges(errors, *, as_of, release_calendar=None)` accepts records (or a DataFrame) with `origin`, `target`, integer `h`, `forecast`, and `actual`. Target must equal origin+h. Duplicate origin/horizon keys fail even if an offending row would be excluded. Each horizon must represent the fixed model and matching units; do not pass multi-model rows into one horizon. Actual-minus-forecast orientation is retained. The fixed quantiles are .1/.9 with linear interpolation at `(n-1)*p`; no trimming, symmetric-width replacement, rescaling or weighting is applied. Missing/nonfinite errors are counted as excluded.

`release_calendar` maps target months to a detailed-release date, timezone-aware timestamp, or a record containing `detail_release_dt`/`available_at`. Date-only releases become usable after their UTC date completes, a conservative convention. Missing dates become usable at 00:00 UTC on the first day two months after target (after the following month ends). Impossible receipts preceding target-month completion fail. `as_of` must be timezone aware. This gates outcome availability, not historical vintage reconstruction.

`seasonal_context(bundle, record)` accepts filesystem paths, validates the successful archive through the unchanged R33 loader, verifies that the supplied bundle has the exact recorded manifest hash, and uses the unchanged R32 bundle reader. No forecast calculation is called. `seasonal_from_frames(...)` is the pure descriptive-accounting layer used by synthetic tests.

## Dashboard JSON schema: forecast_context_r34/v1

`assemble` returns a JSON-safe dict; `build` writes it as `forecast_context.json` in a **new** repository directory and returns its path. Main fields:

| Field | Contents |
| --- | --- |
| `as_of` | Context outcome cutoff, separate from recorded h0 clock |
| `empirical_ranges.samples.full[str(h)]` | All retained eligible origins at horizon h |
| `empirical_ranges.samples.2024plus[str(h)]` | Origins >= 2024-01 at horizon h |
| `seasonal` | Immutable September h0, descriptive seasonal benchmark and deviations |
| `model_disagreement.samples` | Historical BASE/HALF/FULL max-minus-min spreads by the same two samples |
| `model_disagreement.current` | Recorded current challenger points and spread, explicitly not uncertainty |
| `base_effect_ledger` | Exact ledger rows, or null when the parent has not supplied its path |
| `sources` | Verified file hashes, source/support definitions, retained readiness caveat |

**Sample keys are `full` and `2024plus`**, not `origins_2024plus`. Each error entry includes `status`, `n`, `h`, `lower_offset_pp`, `upper_offset_pp`, `origin_start/end`, `target_start/end`, `units`, `model`, `reason`, and the dated individual `observations` used. There are always entries for h0-h12. Below 20 finite eligible errors, status is `unavailable` and both offsets are null. Add the offsets to a like-unit forecast:

- h0 uses `mm_percentage_points`, around the recorded monthly point.
- h1-h12 use `yy_percentage_points`, around each annual-rate forecast.

Do not draw h0 monthly offsets on the annual-rate path or describe either range as prospective coverage. Current `2024plus` h12 has n=19 and is unavailable.

Each `seasonal.components` row has `component`, `recorded_contribution_pp`, `weight`, `seasonal_mean_mm`, `baseline_contribution_pp`, and `deviation_pp`. The six IDs are core, food, alcohol_tobacco, administered, fuel, wedge. Recorded values are copied unchanged. Baseline plus deviation equals the recorded contribution per row and in total. The `sample` object gives the complete common-support month list, count, dates, window definition, and incomplete observations omitted.

All complete same-calendar-month observations before origin are included, at the **recorded origin weights**, not each historical year's weights. The wedge is constructed consistently as headline minus the five weighted historical components, making the baseline headline-reconcilable. Wedge's `weight=1` means it is already a headline contribution; it is not an additional basket share. On the actual September archive this gives 11 Septembers, 2015-2025. Core seasonal m/m averages -0.4545%; a negative NSA September core print alone does not establish disinflation.

`exact_model_seasonal_terms.status` is `unavailable`: the supplied archive has core predictions/corrections and weights but not fitted seasonal coefficients. No residual correction is relabeled as a seasonal term. `recorded_alternative_points_mm` retains BASE/HALF/FULL as recorded. These alternatives differ by the core residual-correction recipe; their spread is not an empirical error interval or a promotion.

## Sources and caveats

- h0: complete 90-origin `output/bloomberg_lane_20260922_r31c/run_C123.csv`, matched exactly by month and HARD_BASE value to `comparison.csv` for `actual`. Source output hashes are checked against their manifests. All six December `ready=False` rows remain in the fixed scorer's roster and are explicitly listed. The original scorer does not condition on readiness. Full n=90, since-2024 n=31 at the rehearsal cutoff.
- h1-h12: `output/bloomberg_lane_20260922_foodppi/path/path_rows.csv`, exclusively `scored=True`, `actual_previous - yy_lane`. Never substitute R31C path variants, `actual_bbg`, or selectively favourable periods. All origin/horizon pairs are checked for duplicates before selection.
- Outcome clock: `data/release_calendar_cz_cpi.csv` detailed-release dates; conservative fallback as above.
- Seasonal/default record: `output/forecast_updates_r33/runs/20260922T175001527361Z_7c5389d7016a` and the exact `current_bundle_20260922_v2`. The context as-of must not precede recorded completion. September h0 is -0.2042311894134946% m/m.
- Release-eve historical nowcasts differ from a mid-month current nowcast. Overlapping path errors are dependent. Retained/latest-vintage truth and reconstructed inputs do not create an untouched prospective track record. Central historical ranges are not confidence intervals for the mean or calibrated probabilities for this forecast.
- Missing seasonal common support is disclosed, never interpolated. The descriptive benchmark is not a structural or causal model decomposition. The exact model's seasonal attribution was not recovered by refitting.

## Optional ledger in the export

Pass `ledger_input={"history_mm": history_mapping, "forecast_mm": forecast_mapping}` to `assemble`/`build`, or use `--ledger-input FILE.json`. When attached to this record, forecast h0 must match its target and point exactly (tolerance 1e-12). The parent can instead call `base_effect_ledger` directly on its exact headline monthly-history Series and generated path mapping. The default rehearsal leaves ledger null because it does not fabricate a new path.

## Reproduction and verification

```powershell
$env:PYTHONPATH='C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$cpiContextPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiContextPython -B -m unittest tools.forecast_context_r34.test_analysis tools.forecast_context_r34.test_sources -v
& $cpiContextPython -B -m tools.forecast_context_r34.build --output work/forecast_context_r34_rehearsal2 --as-of 2026-09-22T18:30:00Z
```

The 23 tests cover exact recurrence against independent rolling compounding, negative dropout prints, equal incoming/outgoing inflation, h12 roll-off, horizon/gap/duplicate/future-history rejection, signed quantiles, 20-error thresholds, date receipts, future-outcome exclusion, impossible receipt dates, complete source roster preservation, frozen archive/bundle identity, seasonal conservation, unchanged contributions, missing common support, current/historical challenger spread, concrete JSON, optional h0-preserving ledger, create-only output and output hashes. Tests create temporary files only under `work/forecast_context_r34_tests`.

Initial function tests failed before implementation; source/builder tests also failed before those implementations. The real roster exposed and corrected an unsupported readiness assumption, then an impossible-receipt regression failed before its guard was added. Code and input manifests accompany rehearsal artifacts for inspection, with `delivery_seal=false`. No final delivery seal or commit is created by this sidecar work.
