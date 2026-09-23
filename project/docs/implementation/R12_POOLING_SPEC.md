# R12 category pooling — fixed specification before forecasting

Implement `models/core_pooling_r12.py`, `core_pooling_experiment_r12.py`,
`test_core_pooling_r12.py`; save only under `output/research_r12/pooling/`.

This tests sharing persistence across six statistical blocks, not a new set of
survey/macroeconomic regressors. It is separate from the unsuccessful R11 macro
remainder experiment. Source and publication rules are exactly those of R10.

## Targets and information

At each of the 90 R9 release-eve origins, retain only published target observations
strictly before month t. Project the five R10 service category monthly changes
with the basket weights available at that origin. Construct the historical
remainder using those same fixed-origin weights. Divide that contribution by
`core_weight - sum(category_weights)` to express it as a comparable monthly rate.
This positive residual weight is a statistical scaling, not an official index.
The original contribution identity must hold to 1e-12 at all retained months.

Each equation sees its own monthly lags 1, 2, 12; lag 1 of published aggregate
core; and February–December indicators. There are no expectations, sentiment,
release surveys, contemporaneous CPI outcomes, wages or new external series.
The lagged aggregate core is the shared price-pressure signal in this first
pooling experiment. Feature construction follows origin masking of raw targets.

All six equations use the same finite-target calendar, expanding, minimum 48
published observations. Require the immediately previous target to be available.
Impute missing predictor observations using that equation's training means only;
an entirely missing feature is replaced with zero and reported. Predictor means
and sample standard deviations, and target mean/sample standard deviation, are
estimated only on this training sample. Constant columns/targets use scale one.

## Exactly three declared variants

1. `POOL_SEPARATE`: a control, separate ridge alpha 3 for the same six equations
   and added aggregate-core lag. This isolates the changed features/scaling from
   the actual pooling. It must match the existing ridge helper on the same data.
2. `POOL_12`: a common coefficient for each of the four standardised dynamic
   predictors, plus category-specific deviations. Sum of the six standardised
   squared-error losses, ridge penalty 3 on common coefficients, 12 on deviations,
   3 on each category's eleven seasonal coefficients.
3. `POOL_48`: identical except deviation penalty 48. This provides the declared
   stronger-sharing sensitivity; it is not selected based on historical results.

Each equation is centred separately, so its unpenalised intercept is recovered
through its training mean. Calendar coefficients remain category-specific. Solve
the finite positive-penalty normal equations deterministically. No tuning, state
switch, correction transplant, ensemble blend or outcome-dependent selection.

Recover rates from target standardisation, multiply by the five category weights
and residual weight, then divide their sum by core weight to recover core m/m.
Use the frozen R9 non-core contribution to construct each headline forecast.
Keep BASE, HALF, FULL, TARGET_OWN as references. Before scoring replay TARGET_OWN
and verify all 90 core forecasts against R10 to 1e-12.

## Tests and evaluation

Test before implementation: future and unpublished target poisoning invariance;
fail closed on missing previous publication; origin-weight identity and rejection
of nonpositive residual weight; exact separate-ridge control; same training clocks
across equations; category permutation invariance; strong-pooling coefficient
convergence; contribution identity; no changes to frozen source files.

Use the R11 assessment/attribution helpers unchanged, retaining all/recent/flash/
ex-January and signed large-event frames, alert frames, paired block bootstrap and
leave-one-origin-out diagnostics. Fit all forecasts before parsing the survey.
Save forecasts, training metadata, contributions, standardised dynamic
coefficients, checks, scores, release rows, uncertainty and dependency hashes.
Provide offline `--verify` with identical numeric outputs. This reused historical
sample supports a research verdict only, with prospective validation still needed.
