# R18 measured pressure, exposure and forecast reliability implementation plan

> For agentic workers: use subagent-driven-development for independent data/energy/food tasks and explicit parent numerical review. The user approved the six-part proposal with "lets do it"; proceed through implementation and evaluation without another permission round.

**Goal:** test whether broader category information, identified energy exposure, an independent food h0 update and sequential forecast-error distributions improve the existing nowcast/path framework.

**Architecture:** preserve the isolated checkout and every R15-R17 forecast/input manifest. New child modules emit native h0-h12 forecasts or explicitly unscored scenarios; the common evaluator recomposes monthly rates on the original calendar. Point forecasts remain independent of consensus/expectations. Consensus enters only a separately identified evaluation/alert layer.

**Tech stack:** bundled Python, numpy/pandas/scipy/sklearn, existing source and native-output contracts, official CZSO/ERU sources, existing CNB replay.

## Fixed common rules

- Ninety primary monthly origins Feb2019-Jul2026; existing 969 original R16 scored origin/horizon keys. Full/recent and target-era sensitivities retain original meanings. A new source does not silently shorten the primary scoreboard: unavailable or early states use explicit unchanged-control fallback.
- First-release nowcast is regular CPI before the flash regime and flash afterward. Detailed CPI labels have their own later availability. No future current-month category values enter a pre-release forecast.
- Core category inputs are statistical measurements with historical-definition limitations, not an exact tax-adjusted CNB-core partition. Freeze the source-defined category roster before fitting.
- Source dates, own-origin transformations, forecasts, matured labels and fallback reasons are saved. Historical availability remains reconstructed; a prefit declaration does not create an untouched holdout after extensive earlier model research.
- Formal declarations are written before full fits; negative outcomes are results. No model promoted on an inspected period's best number. No automatic change to operating models.
- Primary next-release material gain/loss is 0.15pp and big surprise 0.4pp; every alert and false alarm scored. Path comparisons include component errors, CNB two clocks, report omission sensitivity and exact/sustained turns.

## Task A - broaden monthly category measurements

Files: `tools/research_r18/category_inputs.py`, `tests/test_r18_category_inputs.py`, `data/research_r18/categories/`, `work/research_r18_categories/`.

- [ ] Extract nonoverlapping, documented goods/housing/services groups from the previously saved full CZSO CEN0101E CSV. Retain rejected mixed groups and reasons.
- [ ] Save official raw sources, monthly levels, metadata, detail-publication availability, historical basket information and SHA256 provenance.
- [ ] Verify target geography, household population, NSA index units, duplicates, contiguous months, base consistency and available_from gates before model fitting.

## Task B - multivariate persistent price pressure

Files: `models/category_trend_r18.py`, `category_trend_experiment_r18.py`, `tests/test_category_trend_r18.py`, child `R18_CATEGORY_SPEC_2026-09-15.md`, `output/research_r18_category/`.

- [ ] Declare a small common-persistent / common-temporary / sector-persistent Gaussian state model with core plus the eligible category measurements. Two fixed response speeds; robust training-only observation scales, origin-fitted seasonality and explicit minimum history.
- [ ] Test a common persistent synthetic shock against an isolated category shock, future poisoning, release gaps, covariance validity, missing inputs, and two transitions from last observed t-1 to h1.
- [ ] Save all own-origin states and paths, then test a strongly regularised direct correction using the existing six hard domestic/imported signals and category breadth. Adjacent-horizon coefficients share a smoothness penalty; only matured labels enter each horizon.
- [ ] Compare standalone core and recomposed headline on the original dates, with early unchanged FAST defaults shown explicitly.

## Task C - independent food h0 update

Files: `models/food_h0_r18.py`, `food_h0_experiment_r18.py`, `tests/test_food_h0_r18.py`, child spec, `output/research_r18_food/`.

- [ ] Verify archived independent food h0, source clocks and state-only food h0; retain only exact lineage.
- [ ] Predeclare short/long decay profiles, constrained regularised coefficients, unchanged-control default and chronological selection using matured saved forecasts.
- [ ] Test coefficient units, timing, preservation of headline h0, and standalone/aggregate accounting before the full run.

## Task D - household exposure and policy scenarios

Files: `models/energy_exposure_r18.py`, `tools/research_r18/energy_exposure.py`, `tests/test_energy_exposure_r18.py`, child spec, `data/research_r18/energy/`, `work/research_r18_energy/`.

- [ ] Investigate official contract/reset cohort data and expenditure denominators; retain public-source evidence and unsuccessful searches.
- [ ] Implement exposure-weighted bill paths with explicit baseline identity, mass accounting, start/expiry and source eligibility. Do not infer shares from realised CPI.
- [ ] If national exposure remains unidentified, deliver working assumption-conditioned scenarios and exact source gaps, with no national historical score invented.

## Task E - nowcast distributions and alert reliability

Files: `models/nowcast_reliability_r18.py`, `nowcast_reliability_experiment_r18.py`, `tests/test_nowcast_reliability_r18.py`, child spec, `output/research_r18_nowcast/`.

- [ ] Freeze the four independent point series. Compare simple pooled errors, sequential volatility scaling and a small disagreement-conditioned error pool.
- [ ] Test future poisoning, first-release maturity, normalized weights/quantiles/CRPS, and material-gain probability with extreme overshoots.
- [ ] Evaluate 80/90 interval coverage/width, probability scores and all alerts on identical eligible dates. Probability gates are exploratory, never declared calibrated from training or model agreement alone.

## Task F - integration, uncertainty, revision and prospective recording

Files: `tools/research_r18/evaluate.py`, `tools/research_r18/forecast_archive.py`, tests, `output/research_r18/`, final `R18_RESULTS_2026-09-15.md`.

- [ ] Reuse reviewed scoring/compounding to compare all new candidates with frozen FAST/current/gentle and unchanged nowcasts; retain every source clock and coverage key.
- [ ] Extend explicit dated energy scenarios without treating scenario bands as probability intervals. Empirical path-error distributions use only fully matured joint historical paths and preserve cross-horizon dependence; insufficient samples remain unavailable.
- [ ] Report component forecast revisions and preserve a hash-bound append-only forecast archive interface. A historical replay is labelled replay, not a prospective call.
- [ ] Independent code/spec review, source-to-score numerical replay, targeted and existing regression tests, previous manifest verification, updated CNB charts and a clear decision for every hypothesis.

Execution begins with A/D/C in parallel while the parent implements E and B's fixed model contract. Parent integration waits for verified child output manifests. The approved work is complete when all hypotheses are measured or a demonstrated source gap is represented by a working explicit fallback/scenario, with results and remaining limitations documented.
