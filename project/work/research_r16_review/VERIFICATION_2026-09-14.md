# R16 verification receipt — 14 September 2026

Repository: `C:/Users/luis_/Documents/Codex/2026-09-05/c-users-luis-appdata-local-temp/work/cpi-independent`, branch `codex/independent-cpi-20260909`. Unrelated existing work is preserved. No commit or operating-model promotion was made for this experiment.

Read the [results and interpretation](../../R16_RESULTS_2026-09-14.md), [prefit design review](DESIGN_REVIEW_2026-09-14.md) and [final evaluator review](EVALUATOR_REVIEW_2026-09-14.md). The five tasks in the frozen R16 declaration are complete; its original unchecked list remains untouched because the declaration is bound into the run by SHA256.

## Execution and dependencies

The full model run completed at `2026-09-14T13:58:09.823610+00:00`. It contains 90 outer origins, 199 saved core-state origins, 247 first-stage signal origins, ten new models and five controls. Forecast origin coverage is February 2019 through July 2026. Earlier signal projections are warmup/training records, not additional scored outer origins.

Full log: `work/research_r16_full.log`; successful two-origin smoke log: `work/research_r16_smoke.log`. The model runner refuses to overwrite an existing output directory. Frozen R15 inputs, control forecasts and source hashes are verified before the new experiment; no live data source is needed.

```powershell
$env:PYTHONPATH='work/audit_fixes_20260914/runtime_deps;../pythonlibs'
$r16Python='C:\Users\luis_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $r16Python path_slope_transmission_r16.py --output output/research_r16_replay --jobs 4
& $r16Python tools/review/evaluate_r16.py --experiment output/research_r16_replay
& $r16Python tools/review/r16_drivers.py --experiment output/research_r16_replay
& $r16Python tools/review/r16_core_attribution.py --experiment output/research_r16_replay
```

The manifest records numpy 2.5.2, pandas 3.0.1, scikit-learn 1.9.0 and scipy 1.18.1. Pure evaluation uses `PYTHONPATH='../pythonlibs'`. Full runner and legacy bridge tests additionally import the recorded DuckDB/dependency directory. The sandbox's read restriction on one installed dependency required an approved escalated offline command; no dependency file, permissions ACL or data source was changed. This verifies the audit runtime, not every possible installation on another computer.

## Fresh tests

**252 tests passed:** 217 numerical/input/runner/driver and related existing path tests; 35 R15/R16 evaluator and post-run attribution tests. R16 supplies 60 tests in the first group and 18 in the second. Two warnings originate in existing X13 bridge fixtures, concerning nonpositive transformation input and residual seasonality; neither is a test failure. The R16 core/signal engine does not call X13.

```powershell
& $r16Python -m pytest tests/test_core_slope_transmission_r16.py tests/test_r16_inputs.py tests/test_r16_runner.py tests/test_r16_drivers.py tests/test_core_trend_residual_r15.py tests/test_r15_inputs.py tests/test_r15_runner.py tests/test_r15_drivers.py test_core_learning_r14.py test_core_path_r13.py test_path_math_r9.py test_path_inputs_r9.py test_path_improvements_r12.py test_path_integration_r14.py test_independent_bridge_r9.py -q -p no:cacheprovider --basetemp work/pytest_r16_parent_final_2
& $r16Python -m pytest tests/test_r16_evaluation.py tests/test_r15_evaluation.py tests/test_r16_core_attribution.py -q -p no:cacheprovider --basetemp work/pytest_r16_eval_attribution_final
```

Logs: `work/research_r16_tests_parent.log` (217 passed, 18.43s) and `work/research_r16_tests_eval_attribution.log` (35 passed, 42.14s). Tests cover matrix powers and a synthetic reversal, label release maturity, future poisoning, train-only scaling/imputation, penalized constants, missing generated forecasts, deterministic selection, same-origin target centering, h0/noncore preservation, original scoring support, CNB clocks and thresholds, future-target revisions, raw/native exports, embedded HTML/JSON parity, and exact core-oracle accounting including error compensation and missing-month rejection.

## Independent numerical audit

- All 43 input/source and 16 output hashes verify in the R16 model manifest; frozen R15 model inputs/outputs also verify.
- All 5,160 ridge configuration selections and training calendars and all 90 whole-path slope selections reproduce independently. Maximum selection-loss discrepancy is 1.67e−16.
- All 796 slope paths reproduce with independent covariance recursion/matrix powers, maximum 8.89e−16. Twenty independent scikit-learn refits span both stages and all four bands, maximum 7.11e−15.
- All 11,700 new native rows preserve h0, noncore values/contributions and weights. Native/exported headline monthly predictions match exactly; same-origin annual compounding is unchanged.
- Earlier smoke states, first-stage projections, candidate records and core paths remain unchanged in the full run.
- All 21,300 evaluator scoreboard rows independently reproduce exactly; every R15 primary support set and all five control scores are unchanged.
- CNB snapshot selection, quarter means, paired scores, every-report omissions, first-stage annual-signal outcomes and core-turn classifications independently reproduce. All 15,987 raw matched-target revisions verify, including 990 without a realised annual outcome; all-model-common summaries retain 1,035 pairs per model.
- All 64 evaluator inputs and 44 exported artifact hashes verify. Embedded HTML DATA equals the UTF-8 replay JSON; all 7,980 monthly chart points and displayed scores reconcile to saved forecasts.
- All 1,440 end-to-end source-contribution decompositions verify independently, with maximum 4.44e−16 versus saved corrections.

Raw evidence: `research_r16/summary.json`, `evaluation/audit_summary.json`, `evaluation/driver_audit_summary.json` and the associated independent reference CSVs. An initial suspected label-encoding defect was a reviewer default-encoding read error; explicit UTF-8 reads withdrew that finding. No artifact correction was required.

## Post-run component attribution

The diagnostic in `tools/review/r16_core_attribution.py` replaces h1..h core contributions with realised core, holding all other blocks, weights, h0 and known headline history fixed. It is strictly hindsight accounting and never enters model selection. Its nine output files and ten input/source hashes verify; the numerical model/evaluator outputs remain unchanged.

The independent reviewer recomputed 2,907 FAST/gentle/aggressive rows across all horizons by multiplying monthly gross inflation factors from the raw component contributions. Every original common headline date was retained, including the identical 75 h12 dates; maximum exported-value discrepancy is 2.00e−13. The retained remainder is identical across models and the h0-in-window flags are correct. Evidence is in [the attribution audit](attribution/audit_summary.json) and `attribution/h12_independent_scoreboard.csv`.

This confirms an economically material qualification: full h12 own-core errors worsen for both .95 variants while their annual-headline errors improve through a more favourable cross moment with retained-block errors. The gentle variant reduces positive error alignment; the aggressive variant's aggregate cross term becomes negative. All such terms use annual-log units and uncentered moments, not ordinary annual-rate errors or covariances.

## Artifact behavior and limits

```powershell
& 'C:\Users\luis_\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' work/research_r16_review/check_replay_behavior.cjs output/research_r16/evaluation/cnb_rounds_replayed_r16.html
```

The embedded script runs against a small DOM contract in Node. Checks pass for both clocks, all 19 rounds per clock, individual-round selection, all fifteen models, checkbox off/on, reset, tooltip entry/exit, finite SVG geometry, score restoration and absence of external script/font resources. The final HTML SHA256 is `0dd96bdcdb4e9da38c8a79ecfcf4422919d00cf715fe141652d7c3f60372b59c`.

See `replay_behavior_receipt.json`. This is program/data/SVG verification, **not browser layout or pixel inspection**. Earlier browser file access was restricted and was not bypassed. The artifact retains the original local CNB-round template.

The final local integrity command verifies both R15 and R16 model/evaluator manifests, R16 interpretation/attribution files, report links and the replay receipt:

```powershell
& $r16Python work/research_r16_review/verify_final_integrity.py
```

Its receipt is `final_integrity.json`. No frozen R15 source, input, output or evaluator artifact changed during R16. Documentation updates are confined to the new report/verification material and the latest entries in README/model map.

## Interpretation boundary

Forecast formulas, candidate grids, targets and selection rules were fixed before the full run. Post-run accounting diagnostics do not alter forecasts or select new parameters. Current-vintage histories with reconstructed availability and repeated research on the same period do not become an untouched holdout or a live-vintage record because mechanical validation is chronological. Improved headline RMSE alone does not establish improved core dynamics, advance-turn skill, calibrated probabilities or a rates-trading edge.
