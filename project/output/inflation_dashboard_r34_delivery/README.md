# R34 delivery — 22 September 2026

The September nowcast and September-origin h0–h12 path are now separately recorded. Open `output/inflation_dashboard_r34/index.html` in Chrome, or the local preview at http://127.0.0.1:8766/?snapshot=r34-final. The HTML is self-contained and portable; it does not refresh Bloomberg automatically.

| Quantity | Current forecast |
| --- | ---: |
| September nowcast, m/m | -0.204231% |
| September implied y/y | 2.288171% |
| December 2026 y/y | 2.937783% |
| 2026 Q4 quarterly mean y/y | 2.613847% |
| CNB August-report 2026 Q4 mean | 2.388718% |
| Q4 model minus CNB | +0.225129 pp |
| September 2027 y/y (h12) | 3.179564% |

The recorded HARD_BASE h0 and its six contributions are unchanged from 17:50:01 UTC. The path decision was 19:23:51 UTC, with calculation complete at 19:23:52 UTC. Both precede the October 6 first release. The model was rerun with observed consumer prices, food PPI and the exact four-product farm basket through August. Bloomberg remains the default; August core/regulated observations use the already verified CNB ARAD supplement, and farm prices use an official CZSO capture. Old model training rows were preserved.

## What the new explanations show

The September call is 0.041 pp above the historical September mean of -0.245% m/m. Core's -0.270 pp contribution is close to its -0.262 pp seasonal benchmark. Food is 0.123 pp below its benchmark, while fuel is 0.218 pp above. This is a descriptive same-month comparison over 11 Septembers, not the fitted model's seasonal decomposition or causal attribution.

From August to December, the projected annual rate increases by 1.051 pp: 0.716 pp from removing outgoing monthly prints and 0.335 pp from incoming prints. The removal-then-add ledger reconciles exactly. Incoming inflation contains normal seasonality. Headline compounding is exact on captured one-decimal CPI levels; it does not recover unrounded official indexes.

Historical error ranges use fixed 10th/90th percentiles of actual minus forecast, with at least 20 released outcomes. The recent September m/m range is approximately -0.50% to +0.03%, n=31. Recent h12 has n=19, so the page shows unavailable. The full sample remains selectable. These ranges are not calibrated prospective probabilities: the historical nowcasts used later release-eve information, and overlapping path errors are dependent. Alternative core paths and BASE/HALF/FULL disagreement are labeled separately.

The CNB rounds replay and July-origin archive are unchanged. Current-quarter comparisons label the August CNB information date and retain an unexplained accounting residual. The 37-group monitor and its farm/PPI cards remain July; fresh forecast inputs are listed separately. No model is promoted by this update.

The overview legend now says “Non-tradable prices*”, with the exclusion of regulated prices and the distinction from CZSO services explained underneath and in its tooltip. First-round tax effects remain in those ARAD series.

## Verification and handoff

Implementation checkpoint: a2ef02d, after approved plan a9e304d. The single canonical run is `output/current_path_r34/final`; the dashboard is `output/inflation_dashboard_r34`. All 70 targeted tests passed; the runner's four independent review findings have regressions and are resolved. The final offline Chrome check passed at desktop and mobile widths with no page errors. Python and browser scenario arithmetic agree exactly. Matching-input July reproduction differs by at most 2.22e-16; annual rates match exactly. See `july_parity.json` for the limited, synthetic h0 allocation used only for that historical parity test.

`verification.json` records the manifest audit: 579 hash entries across the new canonical forecast/dashboard, captures, prepared inputs and preserved R33/R32 artifacts. `verify.py` repeats the read-only numerical and source audit under the runtime documented in `tools/inflation_dashboard_r34/README.md`. Do not edit or overwrite anything pinned by the forecast, dashboard or delivery manifests. Start the next change in a new module/version and use a new run directory.

Next practical work is the repeatable operator refresh on the Bloomberg computer and the missing August 37-group analysis file, followed by wages/demand context and the January energy announcement ledger. The existing model remains the baseline while those analysis modules develop.
