# R15 verification receipt — 14 September 2026

Repository: `C:/Users/luis_/Documents/Codex/2026-09-05/c-users-luis-appdata-local-temp/work/cpi-independent`, branch `codex/independent-cpi-20260909`. Existing unrelated WIP was retained. No commit or live model promotion was made for R15.

The five implementation tasks in the immutable R15 prefit declaration are completed. The declaration itself is intentionally not edited after its hash was recorded. See [results and interpretation](../../R15_RESULTS_2026-09-14.md), [engine review](DESIGN_REVIEW_2026-09-14.md) and [evaluator review](EVALUATOR_REVIEW_2026-09-14.md).

## Execution

The full model run completed at `2026-09-14T11:34:00.587773+00:00`, with 199 historical states, 90 outer origins, 11 new candidates and 3 controls. Its log is `work/research_r15_full.log`. The final evaluator output has its own completion/hash record in `output/research_r15/evaluation/input_manifest.json`. The numerical output directory is `output/research_r15`; earlier failed/successful smoke directories were preserved separately.

Used runtime:

```powershell
$env:PYTHONPATH='work/audit_fixes_20260914/runtime_deps;../pythonlibs'
$r15Python='C:\Users\luis_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $r15Python path_trend_residual_r15.py --output output/research_r15_replay --jobs 4
& $r15Python tools/review/evaluate_r15.py --experiment output/research_r15_replay
& $r15Python tools/review/r15_drivers.py --experiment output/research_r15_replay
```

The model command requires a new output directory and refuses to overwrite existing experiment outputs. Frozen inputs and local dependencies suffice; it performs no Bloomberg/public-data download. Exact active numerical versions are recorded in the experiment manifest: numpy 2.5.2, pandas 3.0.1, scikit-learn 1.9.0, scipy 1.18.1. This is a verified audit runtime, not a certification of arbitrary Python installations on another computer.

## Fresh test results

**174 tests passed:** 157 estimator/input/runner/driver and related existing path tests, plus 17 evaluator tests. Of these, 62 are R15 tests. The two emitted warnings are X13 warnings in existing bridge fixtures (nonpositive transformation and residual seasonality); neither is an R15 test failure. The R15 engine does not call X13.

```powershell
& $r15Python -m pytest tests/test_core_trend_residual_r15.py tests/test_r15_inputs.py tests/test_r15_runner.py tests/test_r15_drivers.py test_core_learning_r14.py test_core_path_r13.py test_path_math_r9.py test_path_inputs_r9.py test_path_improvements_r12.py test_path_integration_r14.py test_independent_bridge_r9.py -q -p no:cacheprovider --basetemp work/pytest_r15_parent_final
& $r15Python -m pytest tests/test_r15_evaluation.py -q -p no:cacheprovider --basetemp work/pytest_r15_eval_final
```

Logs: `work/research_r15_tests_parent.log` (157 passed, 18.13s) and `work/research_r15_tests_eval.log` (17 passed, 10.13s). Tests cover future-data poisoning, fully released labels, horizon indexing, training-only scaling, zero residual shrinkage, ties, numerical compounding, unchanged h0/noncore, missing forecasts, CNB clocks, equal-support scoring, threshold arithmetic and future-target revision support.

## Independent numerical audit

- All 26 model input/code hashes and 12 generated output hashes reconciled with the prefit declaration and final manifest.
- All 2,160 selection decisions independently reproduced, including common validation calendars, release gates, configuration and loss. Maximum loss difference was zero.
- Nine direct learner refits across 2022, 2024 and 2026 matched within 6.66e−16 monthly log percentage points. Scalar-filter replays matched within 2.22e−16.
- All 12,870 new native rows preserve noncore values/contributions and weights. The h0 forecast is unchanged. All 16,380 annual-path rows re-compounded within 1.31e−13pp.
- All 111 earlier smoke states and 264 core predictions are exactly unchanged in the full run.
- All 38 CNB clock choices, 1,980 paired CNB/model score rows, 5,040 core-band values and 2,520 core-turn records reconciled independently.
- The evaluator initially gated stability summaries on realised outcomes. Its reviewer found the error and it was corrected: 924 valid future-target rows were restored, with 1,035 common revision pairs per model. Forecasts and accuracy/turn results were unaffected.
- Final evaluator manifest verifies 12 input hashes, 33 output hashes and evaluator source hash. HTML embedded data matches the UTF-8 replay JSON and underlying forecasts/scores.
- All 1,440 elastic-net driver decompositions sum back to the learned correction; maximum error 8.88e−16.

## Artifact checks and their limits

`check_replay_behavior.cjs` executes the actual embedded JavaScript against a small DOM contract in Node. It exercises both clocks, all 19 rounds per clock, individual-round selection, showing all models, checkbox off/on, reset and tooltip entry/exit. It verifies finite SVG geometry and score restoration, and checks that scripts/fonts require no external resources.

```powershell
& 'C:\Users\luis_\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' work/research_r15_design/check_replay_behavior.cjs output/research_r15/evaluation/cnb_rounds_replayed_r15.html
```

The final artifact SHA256 and checks are in `replay_behavior_receipt.json`. This is a JavaScript/data/SVG check, **not browser layout or pixel inspection**. Earlier local-browser access was restricted; it was not bypassed. The original local CNB-round template supplies the layout, with only the documented selector/data additions.

## Evidence boundaries

The forecast formulas and parameters were frozen before the full run. The new leave-one-report-out CNB concentration table is a post-run descriptive robustness check across every scored report and every candidate; it does not change model selection, weights or the main sample. The simple fixed-state model's inability to generate an internal underlying-core reversal is explicitly reported, not concealed behind annual-inflation direction scores.

All results are historical reconstructions from current-vintage inputs and assumed/reconstructed publication availability. The final frozen origin is July 2026. Neither nested validation nor numerical parity creates an untouched holdout, a live forecast record, calibrated uncertainty or a tested trade signal.
