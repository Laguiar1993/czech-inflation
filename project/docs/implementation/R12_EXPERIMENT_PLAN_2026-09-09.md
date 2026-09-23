# CPI improvements R12 — implementation and experiment plan

> For agentic workers: use subagent-driven-development for the independent energy
> and path tasks, with parent integration and independent correctness review.

**Goal:** test the user's approved improvements to independent Czech CPI release
nowcasts and the inflation path; exclude online retailer price collection.

**Architecture:** preserve the frozen R9/R10/R11 models, inputs and results.
Create separate research modules, runners, tests and output folders. Forecast
construction must complete before reading evaluation outcomes or release surveys.
Use existing data first; newly verified primary-source evidence may populate an
energy ledger only with explicit publication and treatment-knowledge dates.

**Tech stack:** existing Python / NumPy / pandas / scikit-learn; frozen local data.
Baseline commit c1dacdf4ec946bd5d59d0d7f96876ad9efd1f0a3. Work in the already
isolated codex checkout; do not change the original Downloads repository.

## Approved design and constraints

Luis approved the preceding six-part proposal on 9 September 2026 and explicitly
excluded online food retailer collection. This carries authorization to specify,
implement and evaluate the bounded experiments below without another approval.
Existing operating formulas and model selection remain unchanged during research.

Three independent tasks:

1. Energy/admin: extend event accounting to any effective month, enforce both
   publication and CPI-treatment clocks plus input/weight availability, preserve
   start/expiry links and levels-first arithmetic. Compare only evidentially
   supported adjustments with the baseline. Missing exposure or paid-price data
   must remain scenario assumptions; no realised shock can become a predictor.
   Separate strict eligible output from reconstructed scenario output. Explicitly
   address replacement versus incremental seasonal contributions.
2. Food/path: separate calendar seasonality from a time-varying food trend using
   only released observations; compare one parsimonious trend model and one
   independently lagged cost-pressure extension against the existing bridge.
   Test direct cumulative log-change targets as a separate path experiment,
   preserving coherent monthly/annual compounding and delayed-label eligibility.
   Write exact parameter/feature/target choices into a companion specification
   before fitting; report every declared variant, with no post-result search.
3. Category core: test partial pooling across the five service groups and the
   remaining contribution. Shared dynamics and shrinkage allow small categories
   to borrow information while retaining their own seasonal effects. Use the
   R10 origin masks, weights and independent data only. Declare two pooling
   strengths before fitting; retain both. Reuse unchanged non-core forecasts.

The later structured nonlinear/quantile-weighting proposal is assessed against
these results and existing forest comparisons. Do not conduct an unbounded model
tournament or tune correction weights on the 23 known large surprises. Separate
future experiments clearly from implementations completed in this round.

## Tasks and acceptance checks

- [ ] Freeze the detailed energy, food/path and pooling specifications and all
  numeric choices in git before the first forecast fit for that task.
- [ ] Write tests first for as-of masking, future-data poisoning, unknown dates,
  start/expiry arithmetic, category aggregation, trend seasonal centring and
  cumulative-target endpoint alignment as applicable; observe expected failures.
- [ ] Implement isolated pure estimators and runners; all new outputs live below
  `output/research_r12/`. No edits to frozen baseline output files.
- [ ] Reproduce the relevant original forecasts before comparison. Record source
  hashes, effective training endpoints, parameters, failures and fallback counts.
- [ ] Nowcast: same 90 first-release clocks, baseline/category/HALF/FULL references,
  all/recent/ex-January/flash frames, large absolute surprise >=0.4pp, material
  absolute-error improvement/loss >=0.15pp and all alerts >=0.2pp. Report direction,
  upward/downward events, bias, MAE/RMSE and paired block uncertainty.
- [ ] Path: same baseline origins and available outcomes, exact annual targets,
  horizon-specific common samples, recent-origin AND recent-target panels; include
  last-released YoY carried forward and existing forest/BVAR references. Separate
  monthly-target and cumulative-path performance. Never discard difficult periods
  based on results. CNB report comparisons only when publication clocks align.
- [ ] Review specification compliance, then independently audit code, clocks,
  arithmetic and scoring. Run relevant existing and new tests and replay outputs.
- [ ] Write a concise decision report, updated research roster and reproducible
  portable handoff under the workspace outputs directory. State what improved,
  what failed and where source evidence prevents a defensible scored test.

## Interpretation rule

This is repeatedly inspected pseudo-out-of-sample history, not a new untouched
holdout. A favourable result earns a prospective challenger, not a guaranteed
survey-beating claim. No fitted distribution is implicitly a trading rule. Keep
expectations and current release consensus outside the main independent inputs.

Self-review: work is separated by file ownership, forecasts precede scoring,
timing is part of the estimator, and every result must retain its declared frame.
