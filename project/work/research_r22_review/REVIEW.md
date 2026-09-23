# R22 independent review — 15 September 2026

## Assessment

**Ready as a historical research experiment. No correctness blocker found.** This assessment does not promote a candidate to an operating model or identify a causal transmission mechanism.

Reviewed `docs/implementation/R22_TRANSMISSION_SPEC_2026-09-15.md`, `data/research_transmission_r22.py`, `models/transmission_r22.py`, `tests/test_transmission_r22.py`, `tools/research_r22/run.py`, `tools/research_r22/evaluate.py`, relevant shared conditioning/accounting/evaluation code, and `output/research_r22/full`. No model or production source was edited by this review.

## Findings

No critical or important correctness issue was found.

**Minor: source frequency and sample bounds are not explicit metadata fields.** `data/research_transmission_r22.py:44`, `:52`, `:61`, `:65`, and `:69` construct metadata with source/units and selected transform details but omit the per-source frequency and sample limits promised in the spec. They can be inferred by joining frozen sources, the monthly panel and `ulc_source_quarter.csv`. Explicit `source_frequency`, source first/last reference period and transformed first/last finite month fields would make the standalone export easier to audit. This does not change fitted values or scores.

The five committed tests pass but provide narrow coverage of conditioning and accounting. The independent probes in this directory supply numerical checks of those behaviors for this delivery; useful cases could later be retained in the normal test suite.

## Evidence

- `pytest tests/test_transmission_r22.py -q --basetemp work/research_r22_review/pytest -p no:cacheprovider`: **5 passed**.
- `audit.py`: first, 31st, 61st and final real origins passed exact hidden/future-input poison invariance across five linear/elastic-net families; date matching; independent h1–h12 matrix recursion; exact permitted macro h0 observations; and stable companion radii. Artificially delaying the older quarterly endpoint correctly delayed all three ULC reference months. Missing endpoints failed closed.
- `artifact_audit.py`: every manifest input/output hash in `output/research_r22/full` verified. All seven candidates retained **90 × 13** rows with identical FAST h0, non-core components and weights. All future headline monthly rates equal FAST plus weighted core substitution. All 90 saved fitted paths match the native forecast rows.
- Every saved linear state perturbation was reproduced independently from the coefficient powers; maximum difference **2.95e-15** cumulative log points. First and last full origin fits, including RF and elastic net paths/responses, reproduced exactly.
- All **630** origin/candidate status records are estimated; training spans **40–96** monthly rows. Each of the 11 models/controls has **969** primary headline keys with finite forecast and outcome.
- Generated driver values are finite. The unemployment level stays between approximately **0.252 and 3.959**. Monthly core log forecasts stay between approximately **-0.962 and 1.926**.

The obsolete `output/research_r22/run` directory initially failed a source-hash check after the runner was edited. The current `output/research_r22/full` directory passes; the obsolete output is outside this assessment.

## Timing and interpretation

- A quarterly ULC annual-growth observation occupies its quarter-end reference month and the following two months, always with the maximum publication date of both year-on-year endpoints. This is a declared step proxy, not interpolated monthly measured costs. No future quarter enters that construction.
- Parameter fitting uses only reference months before the origin and data released by the original clock. Seasonality, centering and scale use the masked origin history; all families share complete response/lag dates.
- Filtering advances from the common anchor through internal month t, conditions only permitted known observations, and then advances once more for h1=t+1. HARD_BASE h0 never enters as an observed core measurement.
- RF filtering uses the linear Gaussian approximation; the bounded residual forest starts only in subsequent recursion, as declared. Linear stability diagnostics should not be presented as identifying economic shocks or validating causality.
- The earliest fit has **14 distinct ULC quarters**, despite 40 monthly response rows; later 96-row windows contain 32 distinct source quarters. Exact repeated quarterly-proxy observations and their resulting diagnostics must retain this finite-information caveat.
- ULC, unemployment, FX and Brent responses are changes from perturbing a filtered state with no refit. Their signs describe the estimated predictive association, including possible confounding and policy response. They are not structural impulse responses.
- Current-vintage history, reconstructed publication dates, short quarterly effective history, seven examined candidates and no untouched holdout remain substantive research limitations. Intraday release hours were not treated as blockers, in accordance with the user's instruction.

Machine-readable evidence is saved in `audit_results.json` and `artifact_audit_results.json` alongside the two reproducible audit scripts.

## Addendum: post-score seasonal mechanism diagnostic

Reviewed `tools/research_r22/diagnostics.py`, its five saved outputs under `output/research_r22/diagnostics`, and the two added tests in `tests/test_transmission_r22.py`. **No correctness defect found.** This is an explanatory sensitivity analysis after scoring, not a new forecast candidate, refit or basis for promotion.

The algebra is correct. If the original forecast log rate is `p`, the R22 seasonal estimate is `s22` and the saved R15 seasonal estimate is `s15`, the temporary forecast is `p - s22 + s15`. The existing evaluator then subtracts `s15`, leaving exactly `p - s22`. Thus the diagnostic removes the explicit R22 seasonal addition from its projected pressure path while preserving the original R15-adjusted actual event labels. It does not change model parameters, original forecasts or headline scores. Omitting HALF is reasonable because its arithmetic mixture of simple percent changes does not have an exact additive mixture of log seasonal components.

Independent `seasonality_audit.py` checks passed:

- All **1,800** diagnostic origin/model/interior-band rows were independently reconstructed from the original forecasts and saved seasonal estimates. Maximum round-trip algebra difference is **5.56e-16** log points.
- Actual event labels and eligibility remain identical to the original evaluation. The four controls retain their original predicted labels. All models in the diagnostic retain the same **159 eligible origin/bands and 77 actual turns**.
- Full-sample exact hits change from **14 to 0** for JOINT_LINEAR, **15 to 1** for JOINT_RF, and **13 to 9** for JOINT_ENET. The latter generates **57 calls, including 48 false calls**. The linear diagnostic generates no strict interior-turn calls; RF generates one.
- Every sustained-movement summary, including its sample filters, counts, hits and false calls, was independently reproduced.
- Full-run and evaluation output hashes still match their saved manifests. The diagnostic does not alter those artifacts.
- All 12 metadata-addendum entries match the frozen source frequency, source sample bounds/counts and transformed sample bounds/counts. This resolves the earlier minor metadata finding without changing the original export.
- The R22 test module now passes **7 tests**. The new tests meaningfully verify exact known macro h0 state conditioning followed by one-step h1 advancement, and the maximum quarterly endpoint publication date plus missing-endpoint failure behavior.

Interpretation should remain narrow: the original exact-turn score is sensitive to the difference between the two seasonal estimators, and the smooth joint linear pressure path supplies none of those strict interior turns after its own season is removed. This supports withdrawing an economic turning-skill interpretation of the original hit count. It does **not** establish which seasonal estimate is correct, prove those nominal-path turns are spurious, or create a newly comparable accuracy score: predictions now use R22 season removal while actual events remain defined by R15 season removal. The RF result and ENET false calls also do not warrant forecast promotion.

Reproducible evidence for this addendum is saved in `seasonality_audit.py` and `seasonality_audit_results.json`.

## Final delivery addendum: ex-post error accounting and results report

Reviewed `tools/research_r22/error_attribution.py`, its saved diagnostics and `R22_RESULTS_2026-09-15.md`. **No material correctness defect or interpretive misstatement found.** The accounting exercise is consistently identified as ex-post and unavailable for forecasting; no candidate is promoted.

`error_accounting_audit.py` independently builds the annual actual-core oracle from frozen historical headline rates, unchanged h0, and each future FAST monthly rate plus its basket-weighted realised-core substitution. It agrees with every exported oracle value within **3.56e-15**. Every exported MSE term and zero-price-change benchmark comparison reproduces on the stated support.

On the same **75 primary h12 keys**, the common remaining-error MSE is **11.939747**. FAST has core-difference MSE **6.249902**, cross term **5.522110** and total **23.711760**. RF has **5.423990**, **8.713886** and total **26.077623**, respectively. Thus the smaller RF core difference reinforces the remaining annual-rate errors more strongly in this sample. The report correctly distinguishes this exact nonlinear annual-rate accounting from an official additive CPI contribution and distinguishes the **78-observation component sample** from the **75-observation primary headline sample**.

The price benchmark correctly sets monthly log changes to zero, corresponding to a constant level, and scores it on the identical keys as each driver forecast. The reported Brent, FX and imports comparisons, and ULC/FX/Brent negative-response counts, agree with the exported diagnostics. The report preserves the seasonal-estimator interpretation caveat and makes the post-score nature of both exercises clear.

One immaterial rounding note was sent to the author: the recent component cumulative-core RMSE values **0.586465** and **1.144495** round to **0.586** and **1.144** at three decimals; the reviewed draft had 0.587 and 1.145. The R22 plus related R21 test command in the report was independently run and passed **16 tests**.

Machine-readable accounting evidence is saved in `error_accounting_audit_results.json`. This completes the independent review; no forecast, fit or evaluation source/output was edited by the reviewer.
