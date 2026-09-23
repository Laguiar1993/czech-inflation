# R18 category runner correction — 15 September 2026

The original R18 category experiment and all its sources/manifests remain
unchanged. An independent review verified its fitted equations and saved point
forecasts, and found two unused source-gap fallback defects plus an ambiguous
history-count field. The original 90 origins had complete category inputs and
all first-stage filters were fitted, so these defects did not affect their
numerical predictions. The parent authorized a separate verified runner/output.

`category_trend_experiment_r18_verified.py` changes only these contracts:

- Catch source availability/calendar failures inside an origin helper and emit
  all twelve exact unchanged FAST core monthly values with a recorded reason.
  The original runner's source gate was outside its fallback handler.
- Preserve fallback core m/m values directly. The original log/exp conversion
  could change an unchanged control by up to 4.44e-16 pp. A zero signal correction
  also preserves its parent's exact monthly values, including a FAST fallback.
- `status.csv:n_history` now records the actual fitted sample (maximum 96 for
  first-stage filters; zero when no fit occurred). `n_available_history` separately
  records available candidate history. The original status table reported the
  untrimmed history in 82 first-stage rows from March 2023 onward, reaching 137
  rather than 96 in July 2026. Saved state n_history was already correct.

The engine, specification, category roster, inputs, clocks, seasonal calculation,
state variances, transition coefficients, predictor definitions, signal ridge and
smoothness penalties, maturity rules, sample and model names are unchanged. The
18 national categories plus separate CNB core remain proxy measurements; no
official core partition or true historical vintage is claimed.

Before implementation, two tests in tests/test_r18_category_audit.py failed for
the missing verified runner. They exercise the real origin helper with missing
availability, a nonfinite released measurement, exact monthly fallback and
history longer than 96 months. Existing poisoning/clock/math tests remain.

The new output directory is `output/research_r18_category_verified`. Its runner
verifies the original experiment's entire input/output manifest before reading,
hashes the original runner/manifest, new runner, correction note and both test
files, then writes a declaration before fitting. It refuses existing output
directories. The new manifest rechecks all old hashes and includes the
`original_point_parity.json` receipt. That receipt requires every numeric column
of state/core predictions, generated labels, signal features, scalar forecasts
and native paths to match the original experiment bit-for-bit; metadata-only
state/history/lineage additions are allowed. No historical result is overwritten.
