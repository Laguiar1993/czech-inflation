# R18 quantile correction and final parity receipt

This note supersedes the quantile conclusion in the original `FINDINGS.md` and
`arithmetic_audit.json`. Those files remain preserved. My first independent audit
used ordinary floating cumulative sums for its quantile oracle and therefore
repeated the implementation's exact-mass-boundary error. It verified numerical
agreement with that behavior, rather than the intended empirical inverse CDF.
The original law, probability, CRPS and all-alert conclusions remain unchanged.

The corrected audit uses exact rational arithmetic for the published weights and
exact decimal probability fractions. Equal-weight quantiles reduce to integer
nearest rank, without floating `ceil` adjustments. All **3,960 requested quantiles**
in `output/research_r18_nowcast_verified` match: 1,320 pooled and 2,640 unequal-weight
quantiles. Every support has at most 60 observations; all tested integer-rank
boundaries within that supported range pass. Results and changed cells are retained
in `verified_quantile_receipt.json`, `verified_quantile_changes.csv`,
`verified_coverage_changes.csv` and `verified_score_changes.csv`.

Relative to the preserved original run, **280 quantile cells changed across 156
POOLED rows**: 156 medians, 120 lower 80% endpoints and four upper 80% endpoints.
Each model has 39 changed medians, 30 changed lower endpoints and one changed upper
endpoint. The largest individual shift is 0.115973 percentage points. No 90% band
endpoint or coverage flag changes. SCALE and STATE quantiles do not change.

Two 80% coverage flags change from false to true: CATEGORY_RAW/POOLED for May and
December 2024. Its full-sample 80% coverage rises from 49/66 (74.24%) to 51/66
(77.27%). Twenty-eight summary cells change, solely coverage80 and width80 across
the prescribed overlapping report frames. These are numerical corrections, not
a refit or a new parameter selection.

The original and verified `laws.json`, `alerts.csv`, `coverage.csv` (eligibility
status) and `error_history.csv` are byte-identical. All non-quantile prediction
columns, including frozen points, probabilities, CRPS, gains and alert flags,
match exactly. Original/verified source manifests verify 63/64 input hashes and
seven output hashes each.

The subsequent `output/research_r18_nowcast_final` run adds the positive-tail p=1
endpoint correction. Its predictions, scores, alerts, coverage-status records,
error histories and laws are **byte-identical to the verified run**, including
all requested quantiles. Its manifest and all 64 input/seven output hashes pass.
The exact manifest digest and parity results are in
`final_quantile_parity_receipt.json`; this receipt applies to those frozen bytes.

The helper's supported model contract is at most 60 observations. Exploratory
larger-support results are outside the R18 model paths and have no bearing on
these receipts. No source or engine was changed by this audit, and no further
generic quantile-library development was performed.
