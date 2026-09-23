# Category core remainder experiment — R11

Approved scope: Luis accepted the proposed follow-up on 9 September 2026:
keep the five category equations and restore independent economic information
to the remaining-core equation; investigate the non-core errors exposed by R10.
The design and implementation workflow apply within that approval. No additional
permission or change to the operating model is required.

**Goal:** establish whether the information lost when replacing aggregate core
with category own-dynamics explains its weaker upward-surprise forecasts.

**Architecture:** add a separate pure forecaster and experiment runner. Preserve
all R9/R10 code, data, manifests and scored outputs. Reuse R10 publication masks,
origin weights, training calendar, fixed ridge alpha 3 and minimum 48 observations.
No new data, survey input, model selection, penalty tuning or live integration.
Execution uses test-first development and an independent review.

## Design fixed before generating R11 forecasts

All five category equations are unchanged TARGET_OWN equations (own lags 1/2/12
and month dummies). The historical remaining contribution is constructed with
the forecast origin's fixed weights, exactly as in R10. It includes the remaining
core, tax/classification mismatch and aggregation reconciliation; it is not a
literal goods index.

Two specified replacements for that remaining equation:

1. **TARGET_BASE_REMAINDER (primary):** use the existing independent aggregate
   feature frame after removing expectations, ESI and the mislabelled services
   proxy. Thus FX, imports, inflation state and interactions, aggregate core
   lags 1/2/12 and month indicators predict the remaining contribution. This
   tests restoration of the established aggregate information set.
2. **TARGET_MACRO_REMAINDER (diagnostic):** retain remaining-contribution lags
   1/2/12 and month indicators, adding FX, imports, inflation state, FX-state and
   imports-state interactions. This is exactly the existing R10 TARGET_CHANNEL
   remainder with the five categories returned to TARGET_OWN. It isolates
   macro information without also changing category channels or own dynamics.

Both receive the same fixed 50/50 blend with R9 BASE used in R10. The two
unblended variants are declared together; we will report all four, not search
further after observing scores. R9 BASE/HALF/FULL and R10 TARGET_OWN, its half
blend and TARGET_CHANNEL are references. No fitted R9 error correction is
transplanted onto the new estimator.

All forecasts use the existing 90 first-release eve clocks, February 2019 to
July 2026. Forecast completion precedes reading survey outcomes. Detailed core
is only an auxiliary scoring target. Historical availability remains reconstructed
from publication rules and latest-vintage histories, not recorded vintages.

Report headline MAE/RMSE/bias, ordinary/ex-January/recent/flash periods, all 23
large surprises, upward/downward surprise subsets, material wins/losses (0.15pp),
alerts (0.2pp) including false calls, and paired block-bootstrap uncertainty.
Large surprise remains |print-consensus| >=0.4pp. Keep every-origin deletion
diagnostics. Count alerts on all eligible releases, never interpret conditional
big-event precision as live precision. No automatic promotion from this reused
historical sample. Keep current BASE as the operating reference.

Non-core audit: reconstruct each forecast-origin contribution and its error
against the corresponding realized component, with a separate realized
reconciliation against the first print. Check exact sum against R9 headline
error, use release-eve weights, quantify accidental offsets, and distinguish
code errors from forecast failures. This diagnosis does not change non-core
forecasts or use realized errors to construct a scored forecast.

## Implementation plan

Tech stack: existing Python 3.14 / pandas / NumPy / scikit-learn, no added packages.
Use the existing isolated codex branch; execute the tightly coupled model and
runner tasks locally while an independent audit handles non-core evidence.

- [ ] Add `test_core_remainder_r11.py`: fail before implementation; check exact
  five-leg invariance, agreement of the macro remainder with R10 TARGET_CHANNEL,
  distinct primary and diagnostic feature sets, origin-weight reconstruction,
  future/expectations poisoning, missing previous targets and publication gating.
- [ ] Add `models/core_remainder.py`: import the frozen R10 helpers, fit the five
  category equations once, fit the two remainder equations on the same eligible
  label calendar, return forecasts/fit metadata/contributions and own-dynamics
  replay. No edits to `models/core_split.py`.
- [ ] Add `core_remainder_experiment.py`: verify R10 input/output hashes, mask
  original features at each saved clock, regenerate and check TARGET_OWN,
  freeze unchanged non-core contributions, then score. Save R11-only outputs
  under `output/core_remainder/`; record all dependencies and output hashes.
- [ ] Add scoring checks for up/down and alerts frames, original-output integrity
  and an offline exact rerun. Verify contribution and error identities before
  inspecting rankings. Use existing scoring conventions without modifying them.
- [ ] Integrate the independent non-core diagnosis with exact identities and
  source hashes. Review its weight clock and distinction between forecast wedge
  and realized reconciliation. Record any code defect separately from misses.
- [ ] Review code against this specification, run relevant regression tests and
  frozen R10/R11 verification. Write a report with every declared variant,
  uncertainties, operating recommendation and follow-up priorities. Save a
  portable addendum containing code, required frozen data, results and run steps.

Design self-review: no undeclared optimization, no survey predictors, no changes
to the five category equations, no future-label correction, no automatic model
replacement. Historical weights are origin-specific base projections, not exact
price-updated official contributions. The old frozen experiment remains runnable.
