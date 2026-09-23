# R13 path plausibility and shared-error diagnostic specification

Declared before generating new diagnostic tables. No estimator is fitted here.
Source: frozen `output/research_r12/path/cnb_quarters.csv` and its verified
manifest, plus `data/cnb_mpr_cpi_quarterly.csv`. Only complete finite rows for
INDEPENDENT_BRIDGE are used for the primary evidence. Missing rows are counted.
Every report/quarter key must be unique, outcomes and CNB values finite, and
the saved model clock strictly earlier than the report-publication clock.
Report matching is publication-based; the CNB internal cutoff can differ.

## Row arithmetic

Errors use forecast minus outcome. Let m=model, c=CNB and y=realised.
`model_error=m-y`, `cnb_error=c-y`, `disagreement=m-c`.
Assert `model_error == cnb_error + disagreement` and
`model_error**2 == cnb_error**2 + disagreement**2 +
2*cnb_error*disagreement` to numerical tolerance. Neither right-hand component
is a causal attribution to shocks or misspecification.

Store absolute-error gain vs CNB, squared-error gain, both errors' sign agreement,
and calendar information age `(report_clock-model_clock)` in days. A descriptive
large shared miss means same nonzero error sign and both absolute errors >=0.5pp;
close agreement means absolute model-CNB difference <=0.25pp. Keep continuous
differences as the main measure; thresholds are illustrative, not a promotion
or trading rule. No actual data determine whether a row was ex-ante eligible.

## Summaries and revisions

Report all reports and reports from 2024; horizons all and 1/2/3/4 quarters;
report-year and target-year panels. Show pairs, unique target quarters, model
origins, model/CNB RMSE/MAE/bias, disagreement RMSE/MAE, mean squared-error
identity terms, material shared-miss counts and information-age distribution.
No shock years are excluded from headline tables. Small and overlapping samples
are descriptive; do not manufacture independent significance from repeated
forecasts of the same quarter.

For consecutive reports forecasting the same destination quarter, calculate
model and CNB forecast revisions, their directions and absolute-error changes.
Keep model-origin-change flags; a repeated archived model origin is not an
updated forecast. Revisions after an event are not proof of a causal response
to that event. This evaluates adaptation descriptively without knowing agents'
expectations or decomposed assumption vintages.

## Meaningful tests and implementation steps

- [ ] Create tests before code. A synthetic model=3,CNB=2,actual=5 must give
  errors -2/-3, disagreement 1, and squared error 4=9+1-6.
- [ ] Reject duplicate report/quarter rows, missing or naive clocks, nonfinite
  forecasts/outcomes, and model clock at/after report publication. Preserve
  incomplete source rows in a coverage table rather than silently count them.
- [ ] A fixed destination example across two dated reports must calculate
  revisions using the same quarter, never compare adjacent target quarters.
- [ ] Rows with unavailable realised outcomes remain in agreement-only coverage,
  but cannot receive error or adaptation-to-outcome scores.
- [ ] Implement pure `prepare_rows`, `summarise`, `revision_rows` functions in
  evaluation/path_diagnostics_r13.py, and a runner with --verify that rebuilds
  deterministic CSVs from frozen source, checks hashes and equality.
- [ ] Verify synthetic tests; run descriptive evidence; inspect highest errors
  and disagreement, preserving every pair. Add sources in the explanatory note.

## Research interpretation

CNB's own review of 2022 forecasts separates external, fiscal and administered
assumption errors from model behaviour. Its 2024-forecast review likewise asks
whether misses originated in model structure or assumptions. These motivate a
future archived conditional-scenario design; they do not identify shocks in our
simple error difference. A future perfect-foresight-assumptions rerun must be
labelled diagnostic and can never enter the historical forecast scoreboard.

Sources (accessed 9 September 2026):
https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/boxes-and-articles/Assessment-of-the-fulfilment-of-the-2022-forecasts
https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/boxes-and-articles/Assessment-of-the-fulfilment-of-the-2024-forecasts/
