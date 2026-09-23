# R13 independent CPI families and path evaluation

> For agentic workers: use subagent-driven-development for the two independent
> numerical experiments, with parent integration and independent review.

**Goal:** Test the user-approved BASE/Category Raw/Half/Full matrix, a small
component-core path experiment, and separate forecast plausibility from realised
accuracy without declaring unforeseen shocks to be a free exemption.

**Architecture:** Preserve R12 and every operating numerical formula. Add isolated
research modules, fixed-input runners, tests and evidence tables. CNB forecasts
are evaluation benchmarks only. No expectations, release consensus or retailer
data enter new estimators. Each numerical specification is committed before its
first empirical fit. Historical inputs retain their latest-vintage limitations.

**Tech stack:** Existing Python 3.14 scientific lock, frozen R9/R10/R12 inputs,
NumPy/pandas/scikit-learn/quantile_forest, pytest. Original Downloads repo untouched.

## Work packages and acceptance

- [ ] Nowcast: `models/nowcast_family_r13.py`, `nowcast_family_experiment_r13.py`,
  `test_nowcast_family_r13.py`, `R13_NOWCAST_SPEC.md`. Preserve raw forecasts exactly;
  independently generate each family's historical core errors with then-known
  weights and detailed-outcome release gates. Fixed correction strengths 0/.5/1.
  Categories only have adequate raw history from February 2019: do not substitute
  in-sample residuals. Keep existing BASE corrections and matched-history controls.
  Test time gates, future poisoning, own-history identity, raw and half parity,
  and offline refits before presenting scores. Report the correction warmup and
  post-warmup common sample separately, including its big-event count.
- [ ] Core path: `models/core_path_r13.py`, `core_path_experiment_r13.py`,
  `test_core_path_r13.py`, `R13_CORE_PATH_SPEC.md`. Fixed aggregate/category and
  monthly/cumulative comparison, retaining bridge h0 and all other components.
  Specify available cost/labour features, calendar treatment, origin-specific
  reconciliation and complete future-label eligibility before fitting. Report
  failed/short-history origins and horizon-specific common counts. Check h1
  equivalence, accounting, future poisoning and frozen reference replay.
- [ ] Parent diagnostic: `evaluation/path_diagnostics_r13.py`,
  `path_diagnostics_r13.py`, `test_path_diagnostics_r13.py`,
  `R13_PATH_DIAGNOSTIC_SPEC.md`. Use already frozen report/quarter comparisons to
  measure model-CNB disagreement, shared error, relative loss and revisions of
  the same destination quarter. Preserve reference information-age differences.
  This is descriptive analysis, never model selection on retrospectively tagged
  shocks and never a causal claim that common misses were unforeseeable.
- [ ] Independent reviewer checks declarations, fitting clocks and score arithmetic.
  Parent resolves findings, runs the appropriate regression suite, and performs
  deterministic extracted-package replay before reporting completion.
- [ ] Save a consolidated results report and portable successor package. Keep the
  operating roster unchanged unless independently supported evidence and live
  integration warrant a separate decision. No automatic promotion this round.

## Fixed evaluation principles

Nowcast targets are matching first releases and their matching release surveys.
Large surprises remain >=0.4pp and material absolute-error gains/losses >=0.15pp.
Report all-release accuracy and alerts alongside conditional large-event success.
Path losses retain full, recent-origin and recent-target panels at every horizon.
Add complete-path and quarterly losses, not only the final monthly endpoint.
All unknown future shocks remain in unconditional realised-loss tables.

The user's distinction is handled by three separate questions: Was the original
forecast plausible under the information then available? Did its errors resemble
an independent professional benchmark's errors? Did it adapt sensibly when new
information arrived? Agreement with CNB is supporting evidence, not validation
of the model's economic structure. Exact structural shock attribution would
require archived exogenous assumptions and an identified conditional model;
this experiment will not pretend the existing predictive bridge supplies that.
