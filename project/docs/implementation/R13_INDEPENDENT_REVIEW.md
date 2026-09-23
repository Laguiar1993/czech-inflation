# R13 independent review

Review started 9 September 2026 against baseline `926e7fa` and R13 declarations.
Reviewer owns this note only; no numerical code, inputs, outputs or commits are
changed. This is a new review of R13, not a re-review of the reviewer's R12 models.

## Status

Closed 9 September 2026 against baseline `926e7fa` and declarations `b84835a`,
`a74a536` and `3559201`. No unresolved actionable correctness findings remain.
This is research validation, not approval to promote an operating model. The early
implementation-stage observations below are followed by the final evidence.

## Early design assessment

- Sequential category raw errors must be actual core minus that date's saved
  out-of-sample raw core forecast. The historical solver must receive the weights
  known at that historical decision; an outer-origin reweighting must never rewrite
  earlier raw errors. The new `category_history` currently calls its provider once
  per eligible origin and saves the historical weight/error identity.
- The unchanged category ridge requires 48 released target labels, with its
  inherited train-only imputation for unavailable lag cells. Frozen rates begin
  February 2015, making February 2019 the first feasible actual category origin.
  A 40-error residual forest therefore has no pre-evaluation category history.
  Full90 zero-correction warmup and active post-warmup comparisons are separate
  estimands; the latter must state which large surprises it excludes.
- BASE matched-history controls are necessary. Both families must retain their
  own error values on exactly the same release-eligible dates. A half-strength
  residual correction is distinct from the older BASE/category midpoint blend.
- The core-path arithmetic cumulative target is coherent with the signed
  reconciliation remainder. It is an arithmetic sum/average, not a compounded
  component price change. Its differenced monthly rates can enter exact headline
  gross-factor compounding. h1 must coincide with monthly-target fits.
- Main aggregate/category and monthly/cumulative comparisons require the declared
  common complete-window label mask. The unemployment addition needs a separate
  exclusion control using exactly the same vintage-eligible dates and current
  observation availability. Own-source lags and labour vintages must respect both
  historical and outer clocks.
- CNB agreement/shared error cannot identify an unforeseen structural shock.
  The declared algebra and same-destination revisions are useful descriptive
  diagnostics, while differing information ages remain explicit. Actual outcomes
  must never decide ex-ante row eligibility; unavailable outcomes can still
  support agreement-only diagnostics.

## Prespecification clarifications sent before empirical fits

1. **Residual validation length:** `TVWQRF.fit_predict` implements
   `min(val_window, max(n//5, 4))`, not always 12 observations. With 40 eligible
   errors it holds out eight; it reaches 12 at 60. Preserve the existing routine
   and parity, clarify the specification as a 12-row cap with that adaptive rule,
   and report actual validation length. This is a declaration clarification,
   not a request to select new forest parameters.
2. **Primary core external count:** the estimator paragraph says three primary
   external predictors but the fixed primary design is FX/import, with labour
   confined to its matched diagnostic. Correct the count to two before fitting.

Both declaration clarifications were resolved in parent commit `a74a536` before
empirical fitting. The nowcast audit now records actual validation rows.

## Behavioural and frozen-source checks completed during implementation

An independent run of the three R13 suites passed 34 behavioural tests. Two
additional tests correctly remained pending: the nowcast empirical-output parity
test and the not-yet-written core-path runner's main-versus-labour roster test.
Those failures did not identify an estimator defect and require rerun after the
respective artifacts exist.

The new core estimator's complete h-window label masks, origin-weight remainder,
shared aggregate/split row intersection and separately matched labour masks are
consistent with the declared comparison. Historical training targets use the
outer-origin basket reconstruction by design; this is distinct from the nowcast
family's actual historical forecasts, which must retain their historical weights.

Two API/data-contract matters were referred to the owner: strict validation of
timezone-aware unemployment publication timestamps before selection (plain
`to_datetime(..., utc=True)` otherwise accepts naive values), and unique category
columns/weight labels. The frozen loader already protects actual category data;
the vintage runner validation was still being completed at this review point.

Independent source-only CNB oracle, without fitting or writing output: 161 bridge
report-quarter rows, 76 complete model/CNB forecast pairs, and 66 scored pairs.
The model-origin/clock mapping is one-to-one, and every report clock is local
Prague midnight. There are no internal missing forecast gaps between available
same-quarter report sequences. Thus the referred generic revision-contract
clarification (do not silently skip an unavailable middle report) does not change
the current frozen numeric results. Neither does separating origin-change from
clock-change labels for this one-clock-per-origin dataset.

## Independent review scope

- New tests, including 48-label and 40-error boundaries; first/detail release
  equality and missing-clock rejection; future-label/source/vintage poisoning.
- Exact raw category and published BASE/correction parity over all 90 origins.
- Independent own-error, historical-weight, matched-calendar and half/full
  arithmetic oracles, with complete training/publication audit-table checks.
- Core target/remainder reconstruction and destination-month/source-month tests;
  no future target used in any fit, and no dropped cumulative intermediate step.
- Independent products for every annual path and sums for component cumulative
  targets; full/recent-origin/recent-target common panels and coverage accounting.
- Independent loss/threshold/attribution/leave-one-out calculations and paired
  uncertainty replay, including active-correction warmup dates and event counts.
- Same-quarter CNB revisions and shared-error algebra, with missing coverage,
  stale model-origin flags and information-age differences preserved.
- Source and deterministic payload hashes, and fresh offline refits/replays
  after implementation is stable. Open logs are not deterministic payloads.

## Final findings and closure

The reviewer changed this note only. Independent oracles ran in memory against
frozen artifacts; no numerical code, input, output or commit was changed.

### Setup findings resolved

The nowcast's first empirical attempt stopped at its clock assertion before
correction fits or scoring. Saved raw forecasts use release-eve 23:59; the legacy
BASE error helper uses 09:00. Declaration `3559201` preserves the legacy helper
and reconstructs both new matched BASE and category histories at 23:59. The
legacy-versus-matched contrast explicitly allows both clock and history-length
effects. Empirically, the BASE raw errors differ by exactly zero on all 90
overlapping dates. This was a setup correction, not a results-driven model choice.

The core runner now applies strict vintage validation. The pure selector also
rejects naive labour timestamps and series/adjustment disagreement; category and
weight labels must be unique. The h0 setup comparison was corrected for the
pre-existing bridge/HARD_BASE CSV reading difference of at most 2.22e-16. Candidate
h0 remains exactly equal to the original bridge; separately stored HARD_BASE is
compared at 1e-12. A 1e-8 change fails the regression test.

CNB revisions now retain adjacent source reports, including unavailable pairs,
with an explicit revision-availability flag. Origin changes use origin labels,
and conflicting clocks for a single origin fail. These generic fixes do not change
the frozen source's numbers because it has no internal forecast-availability gaps
and a one-to-one origin/clock mapping.

### Verification evidence

The final independent run of `test_nowcast_family_r13.py`,
`test_core_path_r13.py`, `test_path_diagnostics_r13.py` and
`test_core_path_attribution_r13.py`, with pytest's cache disabled, completed with
**47 tests passed in 11.11 seconds**. The two early pending-artifact tests also
pass. Future label/source/vintage poisoning, release boundaries, historical weight
isolation, warmups, missing cumulative steps, target calendars, constant-column
scaling, matching and ex-post arithmetic are covered.

Independent SHA-256 checks matched all declared dependencies and deterministic
payloads: nowcast **78 inputs / 19 outputs**, core path **74 / 14**, CNB diagnostic
**6 / 4**, and post-fit attribution **8 / 2**. These per-manifest counts overlap.
Live logs are excluded. Owners additionally completed fresh network/database-
blocked refits with all 19 nowcast and 14 core payloads byte-identical, plus
diagnostic replays. The independent checks below do not rely solely on those
same-code refits.

**Nowcast.** All 90 raw category and legacy BASE/half/full parity checks pass.
The category history has 48 explicit insufficient-history attempts and 90 actual
sequential forecasts. Independently reconstructed category and matched BASE
actual-core-minus-own-raw errors; verified basket publication dates, all 540 raw
fit bounds/publication clocks and 270 correction eligibility calendars, actual
validation lengths, omitted expectation columns, matching and half/full arithmetic.
Independently recalculated all **216 score rows**, including threshold/event
counts, from the original survey rather than saved flags; all **234 bootstrap
rows**, **1,170 pairwise leave-one-out rows** and **1,170 attribution identities**
agree.

Both matched corrections first activate in **June 2022**: 50 of 90 dates,
including 13 of 23 large events. Ten large events precede activation. Category raw
full-sample RMSE is 0.408947pp versus BASE 0.417952pp; category half/full give
0.409436/0.410977pp. On 2024+ dates, raw is 0.197798pp versus
0.200580/0.204653pp with corrections. All three category strengths have large-event
direction 13/23 versus BASE 17/23. Small conditional large-event MAE gains do not
establish general direction or event-identification improvements. Evaluation-only
consensus has lower full-sample RMSE than these families.

**Core path.** All **12,870 forecast rows** preserve 90 origins, h0..12 and eleven
models with unique keys and target = origin + h. Independent direct annual gross-
factor products agree within **1.31e-13pp**; original monthly/annual outcomes agree
exactly. All **7,020 native candidate rows** preserve original non-core
contributions, destination weights and h0 exactly; failed components remain missing.

All **17,280 fit audit rows** obey complete h-window label eligibility, target
<= origin-1 and detailed publication <= decision time. Primary models share their
training calendars at each origin/horizon; the labour pair shares its separately
restricted calendar. There are 13,152 estimated and 4,128 explicit insufficient-
history block fits, with no bridge fallback. Independently selected all **235
external source rows and labour vintages**, verifying source months, fixture-row
mapping, publication rules, chosen timestamps and provenance hashes. Calendar
arithmetic precedes timezone localization.

Independently rebuilt **292 estimated matrix fits** at eight fixed review origins
(2019-02, 2020-03, 2021-03, 2022-06, 2024-01, 2025-01, 2026-01, 2026-07), at
h1/h6/h12. The oracle rebuilt origin-weight remainders, complete training masks,
own lags, destination-month dummies, external variables, monthly/arithmetic-mean
labels, train-only scaling and mean-loss ridge matrices. Predictions match exactly;
insufficient-history cases at those dates were separately checked. Independently
recalculated **1,620 headline score rows**, **396 uncertainty rows**, **7,560 core
outcome sums/products and contribution recombinations**, and **288 core score
rows**. h1 monthly/cumulative equality and signed-remainder arithmetic pass.

The primary h12 full comparison has 54 common origins; the separate labour
comparison has 30. Primary recent-target/recent-origin counts are 31/19. Every
failed warmup forecast remains in the coverage ledger, with own/pairwise scores
available; labour does not shrink the main comparison. None of the four main
variants beats the original bridge at h12 in all three declared samples. Split
monthly full annual RMSE is 6.494246pp versus bridge 6.174949pp; recent-origin
RMSE is 1.909105pp versus 1.347309pp. This headline result alone does not imply
that every new core equation is worse, because fixed other-component errors can
offset core errors.

**Post-fit annual attribution.** This is explicitly post-fit descriptive
accounting, not a prespecified fitted experiment. Actual future core enters a
separate evaluation module; neither fitting runner imports it. Original h0,
non-core contributions and destination weights stay fixed. Independently rebuilt
all **6,480 replacement/attribution rows** with direct annual products (maximum
difference **8.35e-14pp**) and all **216 summaries**. Split monthly full h12
headline MSE gain **-4.045246pp²** equals annual core-error gain **+4.926592pp²**
plus changed cross term **-8.971838pp²**. Annual core-error RMSE falls from
3.682377pp to 2.938249pp on that sample. Recent-origin headline/core/cross-term
gains are -1.829442/-0.277567/-1.551875pp². Full-sample headline deterioration
partly removes offsetting component errors; recent core improvement does not
persist. This accounting does not identify economic causes.

**CNB.** Independently reconstructed **70 summary rows** and **133 consecutive
same-quarter revision rows**. There are 161 source report-quarter rows, 76 complete
forecast pairs and 66 scored pairs, covering only 18 unique target quarters.
Model information age has median 8.000694 days and maximum 30.042361 days.

For 2022-issued forecasts, model/CNB RMSE is **4.202369/4.615255pp**; for
2023-issued forecasts it is **2.149574/0.375163pp**. Each issued-year panel has
16 scored rows over seven target quarters. All-report RMSE is
2.362397/2.295453pp; recent-report RMSE is 0.590400/0.371789pp. There are 16
same-direction misses of at least 0.5pp by both, including eleven in the
2022-issued panel and three in 2023. Error identities, outcome versus forecast
eligibility, information ages and revision flags agree with independent oracles.

Shared errors can reflect common shocks, missing information, assumptions or
misspecified persistence. The evidence cannot identify which shocks were
unforeseen. The 2023-issued relative error also does not support a blanket claim
that the model's large misses were unavoidable for informed forecasters. Repeated
target quarters and different information sets preclude interpreting the rows as
independent or treating the comparison as a causal test.

### Limits and disposition

No promotion is supported. These are repeatedly inspected research samples.
Most CPI/import/FX histories are latest stored vintages with reconstructed
availability; archived labour releases are the explicit exception. The legacy
residual feature-history convention remains, rather than a genuine vintage panel.
Bootstrap intervals are descriptive and not selection-adjusted. The short active-
correction and long-horizon common samples require prospective evidence before
operational change. All actionable findings raised here are resolved; final
numerical artifacts agree with the independent checks above.
