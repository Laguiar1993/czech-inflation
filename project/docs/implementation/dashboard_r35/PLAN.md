# R35 category momentum overview implementation plan

**Goal:** Put current category price momentum, its direction and its weighted importance at the centre of the inflation dashboard, preserving the R34 forecasts and historical CNB replay.

**Architecture:** Add independent modules for observed category inputs, X-13 adjustment, momentum accounting and a compact dashboard. Only new R35 paths are written. Current-vintage descriptive analysis is separate from the already recorded forecast and never feeds or retrospectively revises it.

**Tech stack:** Python/pandas/numpy, installed Census X-13 executable, portable HTML/CSS/JavaScript, Playwright Chrome verification.

Approved design: user said “OK LETS DO IT” after the proposal for a category momentum table, 3m/6m annualised rates, acceleration, 12-month heatmap, weighted drivers and click-through charts, with secondary narrative moved away from the overview. Execution and routine implementation choices are authorized.

## Fixed measurement rules

- Refresh the official CZSO CEN0101E national all-household index levels and verify all 37 existing category mappings. Capture raw bytes, retrieval time, source URL and hashes; require January 2015 through August 2026 without missing months or duplicates. Report any revisions to the existing July snapshot; do not rewrite it. Source code and weights remain the verified frozen R18 definitions.
- Keep the accepted eight-block partition, splitting actual and imputed rent into separate rows (nine non-overlapping categories). Category labels must preserve scope: transport includes fuel, parts and repairs; other services contains mixed groups; the goods block is a proxy rather than exact CNB core membership. All 37 groups remain selectable within their parent category. Do not falsely label vehicle operation as fuel alone.
- Seasonally adjust each of the 37 positive monthly index series with the installed X-13, a fixed declared log specification, automated ARIMA and AO/LS/TC outlier detection. Easter regressors may be used only for predeclared travel-sensitive groups, with the choice and diagnostics archived. Adjustment failure means unavailable, never silent fallback to raw or median-adjusted data. Retain original price shocks in the seasonally adjusted series. Archive executable hash, specs, output, warnings and adjustment diagnostics. A simple multiplicative seasonal synthetic series must validate removal of seasonality and preservation of trend.
- Exact group annualised rates: M3(t)=100*((SA(t)/SA(t-3))**4-1); M6(t)=100*((SA(t)/SA(t-6))**2-1). This means the compounded change over three/six months, not a three-month-average-on-three-month-average rate. Acceleration=M3(t)-M3(t-3), using a common adjustment vintage. Latest NSA y/y remains context.
- Aggregate each block by chaining the monthly percentage changes of its constituent adjusted indices with normalized fixed 2026 weights. Apply the same procedure to NSA indices for descriptive block y/y. Group weights partition the 1000-permille basket. These are analytical fixed-weight aggregates, not official chain-weighted CPI aggregates.
- Weighted driver accounting must reconcile exactly to the analytical basket's momentum change. Use log annualised rates for the additive contribution decomposition: weight * 400*log(SA(t)/SA(t-3)) minus the corresponding preceding-three-month log rate. Label contributions as annualised log percentage points. Show exact arithmetic M3 separately and do not pretend weighted arithmetic rates add exactly. Use the nine blocks' geometric aggregation of group gross changes for this additive basket summary, clearly labeled analytical weighted momentum; do not conflate it with the official headline.
- To avoid conflicting aggregation definitions, the displayed block M3/M6 will likewise use the weighted geometric monthly index (weighted log changes); NSA block y/y on the same synthetic fixed-weight index. Official headline y/y and recorded forecasts stay distinct in the top strip.
- Direction labels use a fixed descriptive deadband of ±0.25 arithmetic percentage points in acceleration: picking up, little change, cooling. Negative M3 means falling prices; a negative acceleration with positive M3 means prices rising more slowly. Labels are not significance tests.
- Publish adjustment diagnostics and a truncated-sample endpoint check (fit through July versus fit through August and compare overlapping July M3). A difference above 0.5 pp is a visible revision-sensitivity flag, not a confidence interval. Historical heatmaps use the current adjusted vintage and are labelled revised history, never historical real-time calls. Do not base a new model promotion on these diagnostics.
- Weighted breadth is now the share of covered basket weight with acceleration above +0.25 pp, alongside cooling/broadly unchanged shares and missing coverage. Do not reuse the old y/y-based accelerating-share label. Denominator and complete-coverage requirement are explicit.

## File responsibilities and steps

### 1. Observed input preparation — tools/momentum_r35/inputs.py and test_inputs.py

- [ ] Write failure-first fixtures for missing/duplicate/nonpositive values, wrong population/geography/type, changed schema, source-hash mismatch and future capture clock.
- [ ] Fetch the exact official dataset to output/momentum_r35_inputs/capture_20260922, preserving original bytes or a deterministic gzip copy plus raw SHA256 and headers.
- [ ] Reuse the unchanged R18 extract_levels parser only where the fresh schema is identical. Produce monthly_levels.csv, series_metadata.csv, weights.csv and provenance/manifest in a new prepared directory; load_prepared(path, as_of) verifies them and all source evidence.
- [ ] Verify 37 complete series, weight sum 1000, matching mapped series, current coverage and an explicit overlap revision audit. No model calls or frozen-file writes.

### 2. Seasonal adjustment — tools/momentum_r35/seasonal.py and test_seasonal.py

- [ ] Implement adjust_series(series, name, output_dir) -> (positive aligned SA Series, diagnostics dict), writing create-only X-13 evidence. Record fixed settings and binary hash. Keep process working files isolated under the chosen output directory.
- [ ] Test exact rate preservation on smooth trends, seasonal removal on a synthetic seasonal trend, rejection of gaps/nonpositive/short series, subprocess errors and malformed/nonfinite/misaligned output.
- [ ] Fit full and through-July samples for the 37 categories on rehearsal inputs. Archive endpoint differences and residual-seasonality warnings; flag rather than conceal unstable travel components.

### 3. Momentum accounting — tools/momentum_r35/analysis.py, build.py and test_analysis.py

- [ ] Implement exact M3/M6/yoy, adjacent-three-month acceleration, geometric fixed-weight blocks, deadband direction, coverage-aware breadth and additive weighted log contributions.
- [ ] Tests: constant growth gives the same M3/M6; annualisation compounds rather than sums; a one-off shock rolls out after three months; latest/previous windows do not overlap; scale invariance; weights conserve; missing groups cannot disappear from denominator; driver contributions add exactly; current-vintage dates/quality propagate.
- [ ] Rehearse under work/, then export one canonical analysis after code commit. Output full group/block histories, latest rows, 12-month heatmap, weighted drivers and adjustment diagnostics. Verify source and code hashes before/after calculation.

### 4. Compact overview — tools/inflation_dashboard_r35/{build.py,template.html,app.js,style.css,browser_check.cjs}

- [ ] Start from sealed R34 data. Verify its manifest and retain current_path, live forecast, forecast_context and historical replay unchanged. Only analysis/overview is replaced.
- [ ] Top strip: official headline and month, September nowcast with clock, current path end-year and CNB gap. Main table: category, M3, M6, acceleration, y/y and 12-month sparkline; clear latest data month.
- [ ] Category selector opens its y/y/M3/M6 history, constituent group selector and adjustment status. Provide keyboard and mobile controls. No misleading empty charts while panels are hidden.
- [ ] Below: compact 12-month heatmap with a shared color scale/legend, exact-value hover and keyboard labels; top three positive/negative weighted drivers; accessible direction text rather than color alone. No universal 2% benchmark for every category.
- [ ] Move legacy overview narrative, pipeline, long seasonal/error/accounting tables and scenarios into existing forecast/data/detail views. Keep the current path chart and CNB rounds replay easy to reach. Do not delete archived research content.
- [ ] Chrome checks: point and forecast equality, category/group selection, table sorting, heatmap tooltips, current versus replay navigation, old scenarios, responsive widths and no JS errors. Verify exact displayed arithmetic and contribution reconciliation.

### 5. Review, freeze and delivery

- [ ] Independently review numerical/SA provenance and UI interpretation; resolve material issues with focused regressions.
- [ ] Commit implementation and observed source captures before the single canonical analysis and dashboard build. Use local * -text attributes and verify staged byte hashes. Do not change root attributes, old model code or frozen calendars.
- [ ] Verify new output manifests and the preserved R34 delivery. Record actual diagnostics and limits in a concise delivery note. Commit outputs; replace only the identified local port-8766 server after checking its command line. Open the verified R35 page.

## Runtime and scope

Bundled Python: C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe; PYTHONPATH=C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs. Set PYTHONDONTWRITEBYTECODE=1 and PYTHONIOENCODING=utf-8. X-13 default C:/Users/luis_/x13as/x13as/x13as.exe. No forecast rerun, model change, database write, trading or public hosting. The offline HTML remains portable.
