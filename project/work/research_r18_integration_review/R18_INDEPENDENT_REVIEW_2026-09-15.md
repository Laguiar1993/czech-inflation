# R18 independent integration and joint uncertainty review

Reviewed deliverables: `output/research_r18/path_v2/` and **`output/research_r18/uncertainty_final/`**. Independent arithmetic scripts import no project scoring or model helpers. Separate adversarial tests call the model with hand-constructed inputs. No production files were changed by this reviewer.

**Final result: no unresolved material implementation findings in the reviewed deliverables.** The probability-calibration limitation remains substantial and is not an implementation failure.

## Findings resolved during review

1. The first R18 HTML version replacement would rename the embedded `FUEL_ANNUAL_R17` identifier to `FUEL_ANNUAL_R18`. The parent narrowed visible version replacement; final HTML preserves original identifiers. Embedded data equals `replay_data.json`, plus the template's checked `reports` alias for the report clock.
2. Initial uncertainty scores lacked intended and missing-distribution counts. Verified output now includes every intended origin/horizon/model row in `scored_calendar.csv`, and `n_intended`, `n_estimated`, `n_missing_distributions`, `n_noncommon_distributions`, and `n_common` in all 264 score rows, including zero-support rows.
3. The original empirical quantile helper moved exact cumulative-weight boundaries to the next atom because of floating-point accumulation. Examples: equal weights over 30 atoms gave atom15 rather than14 for p=.5; over60 atoms, p=.1 gave6 rather than5. The verified helper and newly generated uncertainty outputs pass exact inverse-CDF checks. Original files remain preserved and superseded outputs must not be presented as final verified bands.

The final follow-up also preserves the p=1 endpoint for a tiny positive-mass upper atom. It restricts the uncertainty scoring ledger to the original969 keys, removing33 warmup keys per model from intended/missing counts. Independent parity checks confirm byte-identical interval rows, pool vectors and origin availability, with every score column except intended/missing counts bit-exact. The former `uncertainty_verified` output is superseded by `uncertainty_final`.

The first partial `path/` folder failed before evaluation and is not the audited deliverable. Its inherited bridge missing rows were subsequently retained, with explicit unavailable revisions in `path_v2`.

## Point paths and score contracts

- Exact roster: 11 models, 90 origins February2019–July2026, h0..12, 1,170 rows each. Keys and targets, not only aggregate counts, are checked.
- Frozen bridge, FAST, current core, gentle slope and annual-fuel controls have zero difference in monthly values, contributions, weights, clocks and annual paths. Candidate headline h0 is exact. Category candidates alter future core only; food candidates alter future food only. Protected component/weight fields are exact; additive reconstruction differs only by floating-point arithmetic, below9e-16.
- Direct products of same-origin monthly relatives independently reproduce annual CPI within1.32e-13 percentage points. Cumulative-log forecasts match exactly. The integration performs no new model fit.
- Original969 scoring keys per model are retained. Counts h1..12: 88,86,84,83,82,81,80,79,78,77,76,75. All3,300 primary headline/core score rows were recomputed, including intended counts and missing forecasts.
- All59,400 raw component outcome rows and660 selected full/recent component score rows were checked against native components and the frozen component targets.
- All1,584 CNB model/comparator pairs,480 summary rows and38 selected clocks were recomputed. Both clocks retain66 complete report-quarter pairs. Report selection uses the last snapshot strictly before report-day midnight Prague; cutoff selection includes the full cutoff day. Quarterly predictions average three annual rates, using history before that snapshot's origin and its own future path thereafter.
- The10,769 monthly revision rows include7 inherited unavailable cases. Finite component deltas sum to monthly forecast changes within1.08e-15. In10,737 rows the annual-rate revision differs from the component sum: annual revision is a separate compound-path result, not an additive contribution attribution.
- R18 visible methods,11-model roster, default choices and fuel ID were checked. Legacy CSS variable names are internal and do not change visible methodology.

Training ledgers also pass chronology checks: 68,400 food training rows use fully matured12-month paths and both released monthly endpoints; 36,288 category-signal fitting rows have past targets and releases before the saved decision clock. This verifies recorded release chronology. It does **not** turn revised/current-vintage histories or retrospective category recoding into genuine historical vintages.

## Joint uncertainty

Independently reproduced990 model/origin pools and405,210 saved log-error coordinates (maximum difference2.22e-14). All pools use at most the latest60 complete own-model h0..12 vectors, final target strictly before the current origin, and every release available by its saved clock. No later labels enter the vector pool. Minimum24 gives399 unavailable and591 estimated model/origin cases; the first available origin is February2022.

All7,092 interval rows,264 score rows and10,659 final calendar rows (969 per model) were checked. Direct monthly-relative products preserve each vector's dependence, include its own h0 error and correctly roll h0 out of the annual window at h12. Frozen points remain unchanged. Exact empirical inverse-CDF endpoints, coverage and CRPS independently reconcile.

These are experimental historical error bands. Overlapping vectors are dependent; crisis episodes recur in many vectors; 24–60 atoms make the tails coarse; outcomes are revised continuous CPI, not first releases. No shock probabilities or national household-energy probability bands are identified.

For example, FAST's full-sample h12 nominal90% interval covers26/39 outcomes (66.7%), with mean width15.94pp. Its recent-origin h12 interval covers19/19 but has mean width16.81pp. The contrast argues against an operational calibration claim; high recent coverage by itself is insufficient.

## Verification evidence

Reproducible entry points in this directory:

- `audit_integration.py` → `integration_verification.json` and `independent_primary_scores.csv`.
- `audit_uncertainty.py` → `uncertainty_final_verification.json`; earlier verified-output checks remain separately preserved.
- `audit_final_parity.py` → `final_parity_verification.json`: byte/exact parity checks above; all478 path input hashes and3 outputs,487 evaluation inputs and33 outputs,66 final uncertainty inputs and6 outputs match.
- `tests/test_r18_integration_audit.py`: **11 passed in0.71s**, including future-label mutation, single missing/unreleased h0 invalidating an entire vector, latest60 membership, joint-vector identity, direct annual products, current/future-history rejection, duplicate/target rejection, four exact quantile boundaries and the positive-mass extreme quantiles.

Run from repository root with `PYTHONPATH=.;../pythonlibs` and bundled Python. Commands:

```text
python work/research_r18_integration_review/audit_integration.py
python work/research_r18_integration_review/audit_uncertainty.py
python work/research_r18_integration_review/audit_final_parity.py
python -m pytest tests/test_r18_integration_audit.py -q -p no:cacheprovider
```
