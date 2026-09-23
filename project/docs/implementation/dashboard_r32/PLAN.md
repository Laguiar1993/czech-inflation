# R32 integrated inflation dashboard — implementation plan

Approved design: user accepted the combined overview, forecasts/CNB replay, and data/reliability page on 22 September 2026. Build locally for viewing in Chrome and portability to a Bloomberg computer.

Goal: explain the inflation situation in one minute, retain the historical CNB comparison, and make data/model vintages unmistakable.

Architecture: additive Python builder under tools/inflation_dashboard_r32 consumes existing frozen M1/R31C/R31B/replay exports and writes a standalone offline HTML page plus JSON and an input/output manifest. No frozen code, calendars or evidence are edited. Independent production bundle adapter under tools/live_bundle_r32; existing production entry points stay intact until a validated replacement is usable. New directories use local .gitattributes with * -text. No new forecasting model or retuned research result.

## 1. Data and financial meaning

- [ ] Add semantic tests under tools/inflation_dashboard_r32/test_data.py for contribution change accounting including the residual, calendar-quarter averaging, unavailable live forecast, and no fictitious realised outcomes.
- [ ] Build display data from output/inflation_monitor_20260922/monitor_data.json and contributions.csv, output/cnb_rounds_v3/replay_data.json, R31C scores/comparison, and R31B path score/summary files. Check finite values, input dates, common supports, and reconcile headline contributions.
- [ ] Preserve original/rebased/fresh distinctions. The M1 ledger is a July-origin path updated with realised months. Historical replay is a reconstructed backtest with the older roster, not a contemporaneously recorded prospective forecast. New CNB view labels report and origin separately.
- [ ] Momentum is seasonally normalised using calendar medians, not X-13. Base bridges use approximate m/m arithmetic labels; annual paths use the existing compounded values. Breadth is weighted share of the 37 groups whose y/y increased over three months, not a forecast.

## 2. Interactive page

- [ ] Overview: dated narrative, headline/core/services/goods cards, contribution level/change selector (1m/3m), trend chart, breadth, momentum, pipeline and upcoming data requirements.
- [ ] Forecasts: unavailable-live state, recorded last prints, archived monthly path and quarterly CNB comparison, historical report/cutoff selector and model switches. The CNB series remains quarterly. No interpolated quarterly values claimed as monthly forecasts.
- [ ] Data/reliability: sample-aware BASE/HALF/FULL/consensus scorecard, path scorecard, source freshness, manual pulls, definitions and portable refresh instructions. Export data and print supported; useful at mobile widths.
- [ ] Self-contained assets: no CDN, font or network dependency. Keep original rounds artifact intact.

## 3. Production bundle adapter (independent side task)

- [ ] Inspect forecast_independent.calculate and cz_struct loader seams. Add a new explicit bundle entry point with hash checks, R31C changes, timezone-aware decision clock and a separate live calendar input, never editing the frozen calendar.
- [ ] Add targeted tests for corrupt hashes, R31C feature removal, missing/stale coverage and clock handling. Avoid import stubs in production if real dependencies are available; fail clearly if not.
- [ ] Use available evidence to check parity on recorded dates. Never invent a current nowcast when latest necessary observations/release dates are absent. Emit a machine-readable readiness report and document exact remaining refresh requirements.

## 4. Delivery and checks

- [ ] Commit implementation before the canonical build. Development preview builds and tests are engineering checks, not a new research experiment.
- [ ] Build to a new output/inflation_dashboard_r32 directory, verify all input/output hashes, run focused tests and JavaScript syntax checks.
- [ ] Open in browser, exercise selectors, verify layout and no uncaught JS failures. Independent review of data interpretation and code risks. Fix findings before final build.
- [ ] Record tested commands and limitations in README, commit only this work, open the finished page for the user.
