# R14 inflation path improvement implementation plan

> For agentic workers: apply subagent-driven-development, keep ownership separate,
> run meaningful timing/arithmetic tests and independent review before completion.

**Goal:** improve the independent1--12month Czech CPI path with explicit cost
transmission and adaptive core forecasts, and measure whether it improves against
realised inflation and contemporaneous professional benchmarks.

**Architecture:** independent food, fuel and core estimators replace only their
future contributions in the unchanged component bridge. One evaluation layer
recombines prespecified alternatives and compares them on common historical dates.
Original nowcast, surveyed variables policy, source repo and R9--R13 outputs stay
unchanged. Main forecast excludes surveys/expectations; no futures or retailer data.

**Stack:** Python3.14, numpy/pandas/scipy/sklearn, immutable local data, source hashes.

## Experiments frozen before results

The exact input definitions, clocks, formulas, parameters and tests are in
R14_CORE_DESIGN.md, R14_FOOD_DESIGN.md and R14_FUEL_DESIGN.md. Root and independent
reviewer considered level/cost approaches, fixed regressions and adaptive learning.
The selected bounded tests are quarterly-band level/gap core, a domestic log-level
food pipeline, and weekly oil-to-pump error correction with constant observable
oil/FX scenario. No claim a public paper's results transfer to these stricter tests.

Fixed combined roster, declared without results:

1. PIPELINE_FOOD_FUEL_R14: FOOD_DOMESTIC_PIPELINE_R14+FUEL_ECM_R14, original core.
2. PIPELINE_GAP_RIDGE_R14: same food/fuel+CORE_GAP_RIDGE_R14.
3. PIPELINE_GAP_RF_R14: same food/fuel+CORE_GAP_RF_R14.

These are tests of theoretical mechanisms, not an ex-post winning-component
cross-product. Unavailable components imply unavailable combined forecasts.
If the fuel model invokes its prespecified constant-pump fallback, record it on
the combined row. Other component values, weights, wedge and h0 are unchanged.
No extra blend/penalty/window chosen after viewing these scores.

## Sequence and ownership

- [ ] Freeze and commit declarations before model fits. Primary source downloads
 and input coverage inspection are allowed first, because no forecast score enters
 the choice. Parent writes core; agents own food, fuel and benchmark/data review.
- [ ] Each owner writes synthetic behaviour tests first, observes intended red,
 implements pure estimators and frozen offline runner, then runs focused tests.
- [ ] Fit full intended90origin sample once under declarations, preserving missing
 forecasts. Store native forecasts before joins to evaluation outcomes.
- [ ] Independently test source extraction and future poisoning, publication
 eligibility, training-only transforms, exact target/reconstruction equations,
 fixed-component preservation and selected numerical fits. Fix real errors with
 an explicit evidence trail; do not tune economic choices against the scores.
- [ ] Parent recombines three declared paths in path_integration_r14.py and writes
 output/research_r14/integration/. Run test_path_integration_r14.py first with known
 contributions, missing components, forecast clocks and exact annual products.
- [ ] Score common/paired/own panels, all h1..12, full and recent target/origin
 windows; headline and component errors, bias, coverage and paired circular
 block12/2000/seed1409 uncertainty. All horizons overlap; no independent-row claim.
- [ ] Rebuild CNB issue-vintage quarterly comparisons with existing dated report
 table, show publication-to-model age and unique target counts. Audit FMIE actual
 horizons/date metadata before any survey comparison; no fabricated6month series.
- [ ] Rerun appropriate inherited tests, re-fit new estimators offline, compare
 deterministic payloads, review assumptions and report successes/failures honestly.
- [ ] Deliver a portable code/data archive, concise results and revised model
 recommendation, preserving all previous research. No production promotion based
 solely on repeated historical testing; state remaining live-input/uncertainty work.

User explicitly asked to source data and try improvements now, so this implements
the authorized research without an additional design approval interruption.
