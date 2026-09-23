# R34 current path dashboard

A self-contained, offline Chrome page extending the immutable R33 dashboard. The accepted model is unchanged: FAST core, R24 food drift and the R27 error-correction food path on the accepted R31B inputs. HARD_BASE remains the nowcast default. This is a current-data execution and interpretation update, not an accuracy promotion.

## Delivered views

- The current September-origin h0–h12 forecast and its decision time; h0 preserves the separately recorded same-day September nowcast and all six contributions.
- Complete quarterly averages versus the 13 August CNB forecast, with approximate component gaps and an explicit reconciliation residual. No CNB forecast enters model estimation.
- A descriptive September seasonal benchmark at recorded weights: 11 complete Septembers, 2015–2025. This is not the fitted model's seasonal decomposition.
- Exact base/new-price contributions to annual-inflation changes, in removal-then-add order, compounded on captured one-decimal headline index ratios.
- Fixed 10th/90th percentiles of historical actual-minus-forecast errors, with full/recent samples and a minimum of 20 observations. h0 is m/m; h1–h12 are y/y. No calibrated probability claim. Recent h12 has only 19 errors and is unavailable.
- Alternative core recipes as sensitivities, and recorded BASE/HALF/FULL nowcast disagreement separately.
- The unchanged historical CNB rounds replay and July-origin path archive. The detailed 37-group monitor and its farm/PPI cards remain dated July; their sources are explicitly separate from the newer forecast inputs.

The overview legend uses `Non-tradable prices*`; its footnote and tooltip retain the source definition excluding regulated prices. This isolates a useful domestic-price measure without renaming it as broad CZSO services. First-round tax effects remain in these ARAD series.

## Reproduce without overwriting an archive

Run from the repository root, using a new output name every time. Run inputs first as documented in `../current_path_r34/INPUTS_README.md`. A new prospective run must use the actual clock before the target's first release; historical runs must be explicitly rehearsals.

```powershell
$env:PYTHONPATH='C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$python='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $python -B -m tools.current_path_r34.run --bundle output/forecast_updates_r33/current_bundle_20260922_v2 --path-inputs output/current_path_r34_inputs/prepared_20260922_v2 --nowcast-run output/forecast_updates_r33/runs/20260922T175001527361Z_7c5389d7016a --output output/current_path_r34/NEW_RUN
& $python -B -m tools.inflation_dashboard_r34.build --path-run output/current_path_r34/NEW_RUN --output output/NEW_DASHBOARD
```

Append `--rehearsal` to both commands for development outputs. Only the canonical run follows the committed implementation. Path loading verifies source/code/output hashes, clocks, unchanged h0 evidence, source freshness and independent annual compounding. The dashboard verifies the path and inherited source manifests before embedding any data.

For presentation on another computer, copy `output/inflation_dashboard_r34/index.html` and open it in Chrome: all data, CSS and JavaScript are embedded; the page makes no live pull. For new forecasts on the Bloomberg computer, prepare new inputs there with its local paths and actual retrieval clocks. Archived preparation provenance retains the source computer's absolute paths and must not be edited to relocate it. This is not yet a one-click cross-computer installer.

## Checks

```powershell
& $python -B -m unittest tools.current_path_r34.test_inputs tools.current_path_r34.test_run tools.current_path_r34.test_review tools.forecast_context_r34.test_analysis tools.forecast_context_r34.test_sources tools.inflation_dashboard_r34.test_build -q
node tools/inflation_dashboard_r34/browser_check.cjs http://127.0.0.1:8766 work/NEW_BROWSER_CHECK
```

The 70 unit tests cover source contracts and clocks, stale inputs, h0 preservation, exact arithmetic, error samples and validator mutations. Browser checks cover desktop/mobile, all main controls, CNB report/cutoff selection, current-path accounting, empirical-error samples and scenario compounding. Matched-input July parity was checked independently before the September run: maximum absolute difference 2.220446049250313e-16; annual rates and non-food contributions matched exactly. Original h0 component splits were unavailable in that fixture, so the parity check used an explicitly synthetic h0 allocation solely to preserve the same point; it is not a recorded forecast.

See `tools/current_path_r34/RUN_REVIEW.md` for the four independently found runner issues and their regression-verified resolution. Verification reports after the final export belong in a separate delivery directory; do not edit code or files pinned by an existing manifest.
