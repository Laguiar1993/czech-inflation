# Independent R17 core and component-attribution review

Date: 2026-09-14. Read-only review; all reviewer writes are under work/research_r17_review. Numerical implementations and existing results were not edited by this reviewer.

**Status: pass for the reviewed Task1 attribution and Task3 core implementation/full run. No unresolved P0/P1 finding.** This is a correctness/source-lineage review, not evidence that R17 forecasts outperform controls.

## Findings and resolution

1. **API/specification ambiguity, resolved before full fit.** R16's slope_state accepts already seasonally adjusted log monthly rates. The early R17 prose could be read as a raw-input filter while the parity test supplied the same adjusted series to both engines. The parent explicitly assigned raw-to-log conversion and saved-seasonal subtraction to r17_common.adjusted_core, clarified the specification, and added a nonzero-seasonality/20% raw-rate fixture. The review separately transformed synthetic raw rates with 8%-12% shocks and nonzero seasonality. Fixed R17/R16 path disagreement was at most 4.44e-16.

2. **P2 stale native cumulative forecast, resolved before full fit.** Initial smoke native_forecasts.csv copied R15 cumulative_log_forecast after replacing core. For 2019-03 CORE_ROBUST_R17 h9 it held 1.172350 while the correctly recompounded forecast file held 1.578690. The parent changed replace_block to clear derived annual/cumulative forecast fields for h>0 and added a regression fixture. Full-run native exports contain no stale derived forecast values. The earlier smoke's source hash naturally differs after this correction; it is not the certified full-run artifact.

## Core engine checks

- Saved FAST state fields mu, cycle and covariance match R15; F=diag(1,.8), H=(1,1), Q=diag(.20,.20), R=1. Its adapter matches every h1..12 forecast at all 199 saved origins, maximum 2.22e-16.
- The three-state fixed limit matches R16 p95_q001 with the same adjusted input series. Joseph covariance updating is numerically consistent with the existing covariance recursion.
- Independent matrix-power checks confirm t+h uses F^(h+1) from the filtered t-1 state. In particular h1 takes two transitions. Destination seasonality is added once.
- For fixed, robust and news modes, 108 innovations were independently checked against a scale built from preceding innovations only. Prefix traces remain identical when later observations are appended. Repeated-news selection uses the saved prior two standardized innovations and the current one as specified.
- h0 conditioning independently matches baseline_path_h + H F^h w delta with w=P0 H/(H P0 H); H w=1. Maximum synthetic discrepancy is 8.89e-16. Covariance remains explicitly a pre-update state covariance, not posterior uncertainty.
- The h0 coefficient formula, clipping, shrinkage, 60-row window and chronology were independently recomputed, including poisoning current/future/unreleased response rows.

## Full core-run evidence

Reviewed output: output/research_r17_core.

| Check | Result |
|---|---:|
| Input/output hash checks | 73 valid |
| Outer forecast origins | 90 |
| Own-origin state snapshots | 199 |
| FAST/NEWS h0 history rows | 180 |
| Recorded h0 updates | 180 |
| Saved-h0, actual and p0 raw/log lineage discrepancy | 0 |
| Independent beta discrepancy | 0 |
| Independent delta discrepancy | 0 |
| Maximum selected coefficient history | 60 rows |
| h0 and untouched component values/contributions/weights | exact |
| Core replacement monthly arithmetic discrepancy | 0 |
| Annual direct-product compounding discrepancy | 8.89e-14 pp |
| Cumulative log compounding discrepancy | 0 |
| Stale native derived columns | none |

The review recalculated every h0 row from the archived policy=hard core forecast, the output's corresponding own-origin state h0_log and the raw actual core series. Every training-origin list and detailed-release list matches the independently selected rows strictly before the current month and published by its clock. The runner never substitutes a later-fit state into older h0 errors. Transforming historical outcomes before their availability screening is safe here because only the screened rows enter the coefficient; the review checked the actual row lists and poisoning invariance.

The native files preserve the original HARD_BASE headline h0, all noncore blocks, weights and decision clocks exactly. New raw core rates equal 100*expm1(core_log/100). The headline update is exactly the frozen core weight times the raw core forecast difference; annual outcomes are compounded from each individual origin's own monthly path.

## Component and joint-oracle evidence

Reviewed output: output/research_r17/attribution.

- All source/output hashes in its manifest verify.
- The primary calendar equals the original 15-model R16 finite annual-headline intersection: 969 origin/horizon rows.
- Both retained models and all seven single/joint oracle blocks are present at every primary key. Missing component outcomes remain unavailable rather than producing partial replacement.
- Joint noncore and all-component paths were independently calculated from frozen monthly weights and ordinary 12-month product relatives, without calling the implementation's annual helpers.
- Maximum annual-forecast disagreement is 1.16e-13 pp, joint-oracle disagreement 9.33e-14 pp and actual disagreement 6.44e-14 pp.
- The squared-error identity agrees to 5.69e-14. The offset fixture correctly shows that a single-block oracle can worsen a forecast. h0 remains at its original value; h12 excludes it through ordinary window indexing.

Interpretation remains limited to conditional accounting. These are ordinary annual-CPI percentage-point oracles with frozen origin weights and unchanged reconciliation wedge, not R16 annual-log attribution or exact official chain-linked contributions. Single-block gains are nonadditive. Compare oracle scores on the same validity scope; fewer valid component outcomes are disclosed.

## Verification receipt

18 focused tests passed after the export correction: tests/test_r17_component_attribution.py, test_path_attribution_r14.py, tests/test_core_adaptation_r17.py and tests/test_r17_common.py. Tests ran with cache writing disabled and the temporary directory confined to this review folder.

Independent receipts:
- attribution_fast_review.json
- core_engine_review.json
- core_runner_research_r17_core_review.json
- final_core_attribution_tests.log

The three independent_*.py scripts reproduce the extra review calculations without editing original data or model outputs. core_runner review expects the exact saved run's source hashes, so later changes to shared numerical helpers require a newly declared/reviewed run rather than treating the old receipt as current evidence.

