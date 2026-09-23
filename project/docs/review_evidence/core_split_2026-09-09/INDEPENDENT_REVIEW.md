# Independent R10 code and econometric review

Reviewed the uncommitted R10 additions on R9 HEAD `3efc7182e253c295d461976bbef349b53cb18c8a`, against `docs/implementation/CORE_SPLIT_PLAN_2026-09-09.md`. This was a read-only repository review. Review-time results precede any subsequent fixes.

## Initial findings — both resolved before the first scored run

1. **[P2] Put the broad split and aggregate control on the same training calendar.** `models/core_split.py:130-136` fits the goods/services changes on every finite broad observation, but the residual and `BROAD_AGG_CONTROL` require the core 12-month difference. In the actual first scored origin, February 2019, goods and services have 144 training observations beginning February 2007, while the residual and aggregate control have 133 beginning January 2008. Therefore a comparison with this aggregate control combines disaggregation/dynamics effects with an extra eleven training observations. Restrict all broad target fits to the finite intersection of core delta and both broad deltas, or add and explicitly report a broad control using a common training window. The source histories and main baseline do not need to change.

2. **[P2] Verify the delivered outputs as well as the regenerated outputs.** `core_split_experiment.py:180-194` checks frozen inputs, then compares a fresh run's hashes with the manifest. It never hashes the saved `OUTPUT/core_split_*.csv` files or `core_split_gates.json`. An isolated temporary-directory probe placed corrupted saved forecast and gates files next to a valid manifest, mocked only the rerun to reproduce the expected hashes, and `verify()` still printed that the CSVs and gates were byte-identical. Hash the currently saved outputs and gates against the manifest before rerunning, and add a corruption regression test. As written, replay reproducibility is checked, but the integrity of the files the user is reading is not.

## Follow-up disposition

Both patches were independently re-read and the focused model/replay suite was rerun: **9 passed in 1.64 seconds**.

- **Finding 1 resolved.** `models/core_split.py:129-137` now constructs the joint finite broad/core/residual calendar and applies it to the goods, services, reconciliation and aggregate-control target labels. All four models therefore fit the same labelled training rows. Keeping their own historical lag values as regressors is appropriate: those values were available, and the intentional difference in component dynamics remains. `test_broad_split_and_aggregate_control_share_training_label_calendar` verifies equal sample counts and boundaries.
- **Finding 2 resolved.** `core_split_experiment.py:186-189` now checks that every manifest-listed saved CSV and the gates file exist and match the frozen hashes before attempting replay. The parameterized regression test rejects separate forecast-CSV and gates corruption cases.

**No remaining numerical correctness issue was identified in the reviewed patches or model/evaluation logic.** This code-review clearance is subject to successful completion of the first 90-origin run and its actual offline replay; no concurrent full runner was launched by the reviewer.

## Verification and positive findings

- Existing model/input tests: **54 passed**. Existing scoring tests: **32 passed**. Tests used Python 3.14, `-B`, and pytest's cache provider disabled.
- The annual conversion is correct: the change in log annual gross inflation equals current log monthly inflation minus the same-month-prior-year log monthly inflation. Adding the known prior-year monthly log change and applying `expm1` recovers monthly percentage inflation. The synthetic identity test passes to numerical precision.
- The broad projection uses only the sixty calendar months `origin-60` through `origin-1`, requires at least 48 finite jointly available labels, enforces a coefficient in `[0,1]`, and forms the full historical reconciliation series with that origin's coefficient.
- The five categories and remainder have exact algebraic accounting under the declared approximate origin coefficients. Origin weights are frozen across the full historical remainder before fitting. The targeted shared-design ridge forecast equals its common-calendar aggregate control to numerical precision.
- Poisoning all independent-feature and food-feature rows strictly after the February 2019 origin with `1e12` changed every real-data forecast by exactly zero. Existing tests also pass future outcome and survey-expectation poisoning and unavailable previous-target checks.
- Source taxonomy explicitly handles current holidays code `098` versus historical basket `09.6`, includes the catering/accommodation scope limitations, retains the approved basket-midnight convention, and labels basket coefficients as base expenditure projections rather than official current contributions.
- Current evaluator arithmetic, finite/common coverage, event thresholds, fixed practical gates, and paired deterministic bootstrap passed the tests and review. The evaluator explicitly labels bootstrap blocks as consecutive eligible releases, which can span missing calendar months. Surprise direction is separately reported; `false_alarm` specifically means an alert when absolute realised surprise is below the large-surprise threshold, not every wrong-direction alert.
- Survey values enter only the evaluator after predictions. The reviewed source/calendar conventions remain current-vintage pseudo-out-of-sample assumptions, as disclosed; this review does not convert them into archived real-time observation vintages.

Both initial findings were resolved before the first scored run, so no result-guided model change was introduced by these fixes.

## Final saved-results and report check

The full 90-origin output was subsequently reviewed against `docs/CORE_SERVICES_REVIEW_2026-09-09.md`. No forecast runner was launched by the reviewer. All sixteen saved forecast columns are finite for the same ninety origins. Saved R9 BASE/HALF/FULL columns match their independent R9 reference columns exactly, with maximum absolute difference zero.

Independent calculations from saved forecasts and first-release outcomes confirm:

| Quantity | R9 BASE | TARGET_OWN |
|---|---:|---:|
| All headline RMSE | 0.4179515474 | 0.4089469925 |
| All headline MAE | 0.2625157342 | 0.2565045687 |
| 2024+ headline RMSE | 0.2189777613 | 0.1977976020 |
| All core RMSE | 0.2997166456 | 0.2464553932 |
| All core MAE | 0.2408643019 | 0.1828690633 |
| Large-surprise MAE | 0.484583 | 0.511988 |
| Correct side on large surprises | 17 of 23 | 13 of 23 |
| Headline RMSE excluding October 2022 | 0.3197867131 | 0.3235523883 |
| Headline RMSE excluding all 2022 | 0.2898963979 | 0.2775740888 |

Every rounded main results-table number matches the saved score tables. The report's 31 recent observations, 19 flash observations, 23 large surprises, 21 TARGET_OWN alerts, nine alerted large surprises, twelve false alarms and 0.165441 total alert gain also match. Only TARGET_OWN passes the saved practical gate. The reported six-month-block full-period interval `[-0.027395, 0.009334]`, recent three-month interval spanning zero, July category monitor, and category-versus-seasonal comparisons were checked against the saved tables.

The new `component_evidence` arithmetic correctly separates weighted core squared-error improvement from the cross term with unchanged non-core/reconciliation error. Across the exported attribution table, the maximum algebraic identity residual is **9.99e-16**. Comparing attribution directly with differences in squared errors from the separately saved headline forecasts yields a maximum difference of **2.22e-15**. `diagnostic_tables` performs these calculations only after forecasting and introduces no model selection or prediction change.

No numerical inconsistency or unsupported promotion claim was found. The report appropriately retains TARGET_OWN as a research accuracy challenger, preserves the main model, discloses the adverse large-surprise results and influential October 2022 observation, and distinguishes reconstructed history from a prospective test.

One minor wording clarification was sent to the author: the seasonal category benchmark uses **up to five previous same-calendar-month observations**; the earliest twelve scored origins have four. The July 2026 monitor genuinely uses five previous Julys. This does not alter any numerical result.

Final actual offline replay and package integrity are being verified separately by the main agent and should be recorded in its delivery receipt. The reviewer did not duplicate that full run or the reported 326-test repository suite.
