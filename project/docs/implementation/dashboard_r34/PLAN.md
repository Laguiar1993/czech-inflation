# R34 current inflation path and forecast interpretation

Approved by the user on 22 September 2026: rerun the current path, explain the seasonal drivers of September, separate base effects from new inflation, and add evidence-based uncertainty. This implements the four priorities already presented and accepted; it does not select a new model.

## Goal and architecture

Calculate the accepted FAST + R24 food drift + R27 food error-correction monthly path at a September 2026 origin, anchored to the recorded independent September HARD_BASE nowcast. Add a current-path view alongside the immutable historical CNB rounds replay. Build separate modules for current input preparation, path execution, explanation/uncertainty and the dashboard. Python/pandas models remain unchanged; the deliverable is an offline HTML/CSS/JavaScript page.

## Model and information rules

- Keep every R33 and earlier file unchanged. Add tools/current_path_r34, tools/forecast_context_r34, tools/inflation_dashboard_r34 and new output directories, each with its own * -text attributes. Never overwrite a run, captured source or manifest.
- Verify the R33 prospective nowcast archive and current bundle. Its h0 and six contributions remain exactly as recorded; expose its decision time separately from the new path run time.
- Recompute core, administered, fuel, alcohol, wedge and weights through the existing models.current_path entry point. Apply the unchanged R24 drift and R27 FOOD_ECM_R27 correction to future food months. No CNB forecasts or expectations enter the forecast.
- Extend accepted R31B path inputs with Bloomberg food CPI index, food PPI monthly observations and gross pump prices. Use the same farm-price construction as the accepted food system; source newer official observations if available. Preserve old training rows. Mark newly captured observations available no earlier than retrieval completion. Missing input is never silently interpolated or declared current.
- Use ratios of the headline CPI index for known months in the annual compounding window; report index precision and reconcile to the published rounded annual rate. No future realised monthly print may enter a forecast.
- All required months through August must be present in headline/core/regulated/alcohol/food. Upstream inputs use their own publication/availability clocks and expose their last usable month. Record any legitimate publication lag.
- Prospectively archive h0-h12, all contributions/weights, component values, origin, decision time, source hashes and diagnostics. Assert finite values, complete horizon, exact contribution sums and independent annual-rate compounding.
- Preserve historical CNB rounds at their original clocks. A current model versus latest CNB comparison explicitly uses different publication dates, and compares complete quarterly mean annual inflation only.

## Interpretation and uncertainty

- September explanation: show the recorded component contributions against a pre-origin, same-calendar-month historical seasonal benchmark at current weights. Where exact model seasonal terms are available expose them; distinguish the descriptive benchmark from an exact model attribution. Display sample dates/count and remaining deviation. Do not call a negative unadjusted September print disinflation without its seasonal context.
- Base-effect ledger: for each forecast month use y_new = (100+y_previous)*(1+m_new/100)/(1+m_12months_ago/100)-100. Decompose the change exactly in the fixed order: first remove the old monthly print, then apply the new monthly print. State this allocation convention and show new/base/total plus the corresponding rates. Do not approximate arithmetic contributions with log points.
- Uncertainty: use fixed central 80% historical error ranges (10th/90th percentiles of actual minus forecast), separately for full support and origins since 2024. Use R31C HARD_BASE for h0 and accepted R31B path rows on primary support for h1-h12. Require at least 20 finite errors per horizon/sample; otherwise show unavailable. Display n, dates, historical clock mismatch (release-eve versus current mid-month) and overlapping-path dependence. These are empirical historical-error ranges, not calibrated prospective probabilities or confidence intervals for the mean.
- Core-recipe alternatives may be shown as model sensitivity with the same food adjustment and inputs. Their spread is not a confidence band or a new promotion.

## Files and execution plan

1. tools/current_path_r34/inputs.py, test_inputs.py, capture_config.json: verify frozen bundles and captures; prepare food_levels.csv, food_available.csv, pump_weekly.csv, headline_history.csv and provenance/manifest in a new directory. Return pandas monthly frames with ordered unique indexes. Regression tests reject missing/nonpositive/rebased-conflicting levels, future availability and overwritten outputs; preserve all baseline food rows.
2. tools/current_path_r34/run.py, test_run.py: load the validated h0 archive and prepared path inputs; run the unchanged base engine; replace future food with R24/R27; recompute annual rates on exact-index history; archive results and diagnostics. Reproduce a July-origin accepted path on matching inputs before the single final September run. Test h0 preservation, no-future-data use, exact aggregation and month-to-month annual recurrence.
3. tools/forecast_context_r34/analysis.py, test_analysis.py: implement empirical_ranges(errors), seasonal_context(bundle,record), base_effect_ledger(history,forecast) and immutable build exports. Test signed error orientation, sample filtering, quantile coverage requirements, no duplicate keys/future outcomes, exact base/new sum, negative old prints and twelve-month roll-off. Input/implementation interfaces may be refined without changing these declared statistical rules.
4. tools/inflation_dashboard_r34/build.py, app.js, style.css, template.html, browser_check.cjs: extend the sealed R33 page additively. Default to the fresh path; retain July archive as a dated comparator and historical CNB replay unchanged. Add seasonal explanation, base/new table, historical error display and a source freshness summary. Scenario controls must compound from the fresh path and keep neutral equality. Remove inherited claims that the current path is still archived.
5. Rehearse on work/ scratch outputs, independently review the numerical/provenance boundaries, fix material findings with regressions, then commit code before the single canonical current-path run and dashboard export. Verify every new manifest and the preserved R33 manifest. Exercise desktop/mobile, all CNB selectors, scenarios, uncertainty sample selection and offline operation. Commit outputs and replace the identified local preview server only after verification.

## Reproduction environment

Use C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe with PYTHONPATH=C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs, PYTHONDONTWRITEBYTECODE=1 and PYTHONIOENCODING=utf-8. Bloomberg capture uses C:/Users/luis_/anaconda3/python.exe with its Library/bin prepended to the process PATH. Source capture is read-only. No database writes, model selection, parameter tuning, public publication or live trading action is authorized by this implementation.

## Acceptance

A reader can see the same day's recorded September nowcast and a newly estimated September-origin h0-h12 path, understand the seasonal and base-effect arithmetic, inspect historical error sizes and model sensitivities, and compare complete quarters with the latest CNB path without confusing that comparison with the historical replay. Data holes and clock differences are visible. All quantities reconcile and old snapshots remain reproducible.
