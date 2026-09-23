# R17 verification and reproduction receipt

Date: 14 September 2026. Repo: `C:/Users/luis_/Documents/Codex/2026-09-05/c-users-luis-appdata-local-temp/work/cpi-independent`, branch `codex/independent-cpi-20260909`.

Read [the completed results and assessment](../../R17_RESULTS_2026-09-14.md). Existing unrelated WIP is preserved. No blanket commit or operating-model promotion was made. The original unchecked master/child specification lists remain historical declarations, bound into runs by hashes; this receipt records their completion without rewriting the declarations after fitting.

## Completed evidence

- Component attribution: original R16 support exactly 969 origin/horizon keys; independent ordinary-product joint replacement agrees within 1.2e-13 percentage points. See `attribution_fast_review.json` and `FINAL_REVIEW_RECEIPT.json`.
- Core: 199 filtered historical states, 90 outer origins, four new paths and 180 incremental h0 updates. Fixed R16 recursion max discrepancy 4.45e-16; saved FAST recursion 2.23e-16. Independent own-origin feature/label/clock and h0 coefficient checks agree exactly. See `R17_CORE_ATTRIBUTION_REVIEW.md`.
- Food: 126 own-origin snapshots, six models, all 90 outer origins. Independent checker rebuilt 8,022 fits, 1,512 common training calendars, 163,584 endpoint checks and 252 whole-path penalty selections. Coefficient discrepancy below 1.9e-15. Food receipt: `../research_r17_food/independent_verification.json`.
- Monthly categories: 126 origin snapshots, all five categories, five mapped core candidates. Independent reviewer reconstructed 4,584 first-stage and 5,730 second-stage fits and 1,020,240 publication comparisons; all snapshot seasonality/scales/weights/macros and core forecasts match. See `../research_r17_monthly/independent_verification.json` and `snapshot_lineage_verification.json` there.
- Energy: 34 policy facts, 3,060 origin/fact eligibility rows, 270 quote checks, 27 illustrative bills; no national administered candidate made eligible. All 90 original constant-spot fuel ECM paths reproduce exactly. Independent weekly recurrence errors below 2.2e-14 CZK/litre and monthly fuel errors below 3.8e-14 pp. See `ENERGY_FULL_REVIEW_RECEIPT.json` and `energy_full_verified_review.json`.
- Integration: 30 models, 90 origins, h0–h12. All 180 selector objectives/decisions and fixed/candidate monthly mixtures independently reproduce exactly. 48 early selector defaults are explicitly recorded. Original h0, weights, clocks and untouched blocks match; independent product compounding discrepancy at most 1.32e-13 pp. See `integration_selector_review.json`.
- Evaluation: 412 source/output hashes, 162,000 component rows, 3,960 common score rows, 4,092 CNB pair rows, 10,800 core bands, 5,400 strict-turn rows, 3,472 report omissions and 2,280 large-CNB-departure rows independently checked. Sustained false-alarm counts and bootstrap block eligibility agree. See `integrated_output_review.json`, `diagnostics_output_review.json` and `COMBINATION_FINAL_REVIEW_RECEIPT.json`.
- Original-calendar uncertainty is an additional read-only supplement in `output/research_r17/primary_uncertainty/`. It uses the same tested block-bootstrap function on the frozen 969-key support; the evaluator's broader paired-support uncertainty remains separately available.

No remaining actionable P1/P2 numerical finding was identified by the independent reviewer. This is not a guarantee against every unknown defect or a certificate of historical data vintages.

## Findings and corrections during this batch

Before full core fitting, review clarified that the engine accepts already seasonally adjusted log rates while the runner transforms raw monthly percentages. A nonzero-seasonality/raw-rate fixture covers that boundary. Review also caught stale derived cumulative/annual fields in a smoke native export; they are now cleared and recomputed after component replacement. The complete core output was generated after that fix.

Energy smoke initially failed because `DataFrame.product` resolves to a method; indexing the named column fixed it before the full run. Review required the illustrative previous-bill capacity tariff to be labelled as an assumed carry-forward of the sourced 2024 schedule. This did not change the cap-binding illustrative numbers and was documented before the full run.

The first full evaluator stopped at a numeric-type check: an untyped empty core-prediction frame caused the native-only joined forecast column to have object dtype. The evaluator now creates a typed empty frame; a dedicated regression test passes. The two incomplete exports are preserved under `output/research_r17/path/failed_evaluation_dtype/`. No model forecasts or selection decisions were changed. The successful final evaluation has its own complete manifest.

A reviewer initially suspected reversed capture-ratio sign. Source inspection and literal examples proved the stored field is `actual−CNB`, so the existing division was correct. The finding was withdrawn and recorded; no harmful sign change was made. CNB 5, actual 3, model 4 produces capture +0.5; exact forecast gives +1; model 0 gives +2.5 overshoot; model 6 gives −0.5 wrong direction. Absolute-error scoring penalizes harmful overshoots.

Negative full-sample findings did not trigger feature/penalty retuning. Food and category mechanisms, h0 propagation, combinations and selectors remain unpromoted. Policy-source gaps are explicitly ineligible or scenario assumptions.

## Fresh tests

**347 passed:** 69 new/related fuel checks and 278 prior numerical/accounting/regression checks. Logs are `tests_new_final.log` and `tests_regression.log`. Two warnings come from existing X13 bridge fixtures (nonpositive synthetic series / residual seasonality), not test failures. R17 core and category filtering does not run a new X13 fit.

```powershell
$env:PYTHONPATH='../pythonlibs'
$r17Python='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$r17Tests=Get-ChildItem tests -Filter '*r17*.py' | ForEach-Object { $_.FullName }
& $r17Python -m pytest @r17Tests test_fuel_path_r14.py -q -p no:cacheprovider --basetemp work/pytest_r17_new_recheck
```

Legacy regression tests also use `work/audit_fixes_20260914/runtime_deps` on PYTHONPATH. The sandbox previously denied reading one installed dependency folder, so the offline legacy regression command used an approved escalation. No ACL or dependency files were changed. That is an environment detail, not a failed model test.

## Offline reproduction

Run from the repo root. Each output directory must be new. Existing canonical output paths are immutable evidence. These commands recompute each child into fresh directories for comparison:

```powershell
& $r17Python core_adaptation_experiment_r17.py --output output/r17_core_replay
& $r17Python food_transmission_experiment_r17.py --output output/r17_food_replay
& $r17Python monthly_transmission_experiment_r17.py --output output/r17_monthly_replay
& $r17Python energy_path_experiment_r17.py --output output/r17_energy_replay
& $r17Python path_component_experiment_r17.py --output output/r17_path_replay
& $r17Python tools/review/evaluate_r17.py --experiment output/r17_path_replay
```

The integration command deliberately reads the canonical hash-verified child archives rather than silently substituting a fresh run. Compare child replay predictions to their canonical copies first. On another computer, retain the whole repo-relative input/output/manifest tree and install the recorded dependencies; the paths above identify this audit's runtime, not a portable Python installation promise. New-data operation requires a separately versioned origin/input archive and a new experiment declaration.

## Replay artifact

The final HTML is `output/research_r17/path/evaluation/cnb_rounds_replayed_r17.html`; SHA-256 `0d39d0fdab01c7f250f71d9a0aee9d423ee7112f0f4ce08d7244a1d4e7dc6425`.

```powershell
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' work/research_r16_review/check_replay_behavior.cjs output/research_r17/path/evaluation/cnb_rounds_replayed_r17.html
```

The original renderer's DOM-contract check passes all 19 rounds on both clocks, individual round selection, all models, checkbox off/on, reset, tooltips, finite SVG geometry, fixed-score restoration and no remote resources. Receipt: `replay_behavior_receipt.json`. These are data/program/SVG checks, not browser pixel inspection; the earlier local-file access restriction was not bypassed.

The completion check in `verify_r17_final.py` verifies every final model/evaluator/attribution/uncertainty manifest, R15/R16 preservation, local report links, test summaries and the artifact hash. Its result is `final_integrity.json`.

## Interpretation limits

All scores are simulated historical results with frozen current-vintage inputs and reconstructed release availability. Multiple experiments use the same sample. Overlapping horizons and repeated quarterly targets are dependent. The experiments do not supply an untouched holdout, actual historical vintages, calibrated probabilities, live trading returns or reliable advance core-turn skill. h0 is unchanged; no next-release survey-beating claim follows from the path comparison.
