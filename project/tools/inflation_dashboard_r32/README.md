# Czech Inflation dashboard — R32

A portable, offline preview of the approved integrated page. Open the generated
`output/inflation_dashboard_r32/index.html` directly in Chrome, or serve that
directory on localhost. The HTML embeds its data, styles and scripts. No account,
CDN, network request or installation is needed to view it on the other computer.

## Views

- Overview: dated narrative; headline/core/services/goods; contribution levels and
  1m/3m changes; weighted breadth; seasonally normalised momentum; base effects;
  food and industrial price pipeline.
- Forecasts & CNB: original R31B July-origin path versus that path updated with
  realised months; quarterly CNB segments; last three recorded prints; monthly
  base-effect ledger; 19 CNB report rounds on report/cutoff clocks, model toggles,
  quarterly outcomes and MAE, diagnostic component charts.
- Data & reliability: R31C BASE/HALF/FULL versus consensus on three samples; R31B
  path scores; source vintages; refresh checklist and explicit limitations.

## Build and verify

From the repository root, using Python 3.10+ (standard library only for this builder):

```powershell
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$env:PYTHONDONTWRITEBYTECODE='1'
& $cpiPython -m unittest tools.inflation_dashboard_r32.test_data -v
node --check tools/inflation_dashboard_r32/app.js
& $cpiPython -m tools.inflation_dashboard_r32.build --output output/inflation_dashboard_r32
```

Choose a new output directory for another snapshot. The builder refuses overwrite.
It verifies consumed frozen exports against their own original manifests before
reading them, then records input, code and output SHA-256 hashes in the new manifest.
The nine semantic tests check integrity, contribution reconciliation, missing
observations, quarter completeness, weighted breadth and the accepted model lane.

A browser interaction check uses installed Chrome through Playwright:

```powershell
& $cpiPython -m http.server 8767 --bind 127.0.0.1 --directory output/inflation_dashboard_r32
# In a separate terminal:
node tools/inflation_dashboard_r32/browser_check.cjs http://127.0.0.1:8767 work/inflation_dashboard_r32_browser_check
```

Set CPI_PLAYWRIGHT to the Playwright package directory if using a different machine.
Tests exercise the actual desktop (1440x1100) and mobile (390x844) page, report/clock
selectors, model switches, path vintages, contribution changes and score samples.
Screenshot files are development evidence, separate from the immutable snapshot.

## Meaning and limitations

This is an integrated **dated preview**, not a live data service. Current sources
are the frozen 22 September monitor and R31 lane exports; detailed CPI is through
July, headline through the August flash, and the model origin is July. Opening or
rebuilding the page does not refresh Bloomberg, download CZSO files or fit models.

- No current September nowcast is shown; empty values are deliberate.
- The original archive is the R31B path. The M1 updated path substitutes observed
  months but does not re-estimate future monthly forecasts.
- CNB replay retains the frozen 20 September roster and older R27 lane. These are
  reconstructed historical forecasts, not a prospective live record.
- Red CNB segments are quarterly averages. No monthly interpolation is presented.
- Missing/incomplete quarters have no outcome or score.
- Contributions use fixed 2026 weights plus a displayed reconciliation residual.
  Full-precision weights are used for breadth, avoiding the rounded source table.
- Breadth means weighted share whose y/y increased over three months. Momentum
  uses calendar medians, not X-13. Pipeline correlations are descriptive.
- Base-effect bridge columns are m/m-point arithmetic, not exact y/y contributions.
  Implied y/y retains the source's compounded annual rates.
- No confidence band, probability of surprise or position-sizing recommendation.
- Wages/services and demand/credit analysis are labelled as future modules.

## Production path

The additive entry point in `tools/live_bundle_r32/` validates hash-listed bundle
frames, enforces R31C inputs, supports a separate sourced calendar and Bloomberg MTD
FX, and calls the existing model explicitly. Its README and saved readiness reports
list the current blockers. It calculates h0 only; it does not rebuild upstream
monthly frames or extend the full model path. No old loader, frozen data, calendar,
research code or artifact is overwritten.

To make this preview live on the Bloomberg computer, the remaining integration is:
refresh raw data and construct current bundle feature rows; run the adapter and
the path with a sourced release calendar; regenerate dated monitor exports; ingest
the successful outputs into the page. A historical replay must not populate the
live card. Source freshness and decision timestamps must remain explicit.

