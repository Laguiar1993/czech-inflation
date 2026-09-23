# R20 shared path independent review

Date: 2026-09-15. Scope: `models/current_path.py` and `tools/current_path/audit_parity.py`, against `docs/implementation/R20_CURRENT_PATH_PLAN_2026-09-15.md`. The live runner was outside this review. No implementation or frozen source file was edited by the reviewer.

## Assessment

Ready for the next R20 integration checks within this scope. One material audit defect was reproduced and corrected by the parent; its two regression cases now pass. No unresolved material path-formula or timing defect was found. This review does not certify prospective source freshness or live issuance.

## Resolved finding

**P2 — Annual reference coverage was not checked.** `tools/current_path/audit_parity.py:35` joined annual references using an inner merge. Before the fix, deleting one annual `(origin, model, h)` reference, or deleting every annual row, silently removed those comparisons while producing a successful summary with `rows=39`, `max_abs=0`, `finite_mask_mismatches=0`, and `failed_checks=0`. This could falsely certify the plan's required thirteen-horizon YoY parity.

Evidence: both parameterizations of `test_review_parity_rejects_incomplete_annual_reference` in `tests/test_r20_path_review.py` failed before the correction because the audit did not raise. The parent added the required 39-row check immediately after the annual join at line 36, with existing one-to-one validation. Both cases pass after that correction. The arithmetic implementation was unchanged.

## Formula and timing checks

- FAST directly uses R15's `fast` state forecast and transforms log percentage points with `100*expm1(v/100)`. h1 is two transitions beyond the last observation at t-1.
- Current core uses R14's twelve-month log-rate mean plus the destination month's origin-frozen seasonal term. Its existing import/FX availability requirements are retained; a missing local state yields unavailable local paths rather than substituting another model.
- Gentle slope uses the R15 seasonal adjustment with R16's fixed `p95_q001` state path and the same log-to-simple transformation.
- Stable food uses the unchanged `FOOD_STABLE_PIPELINE_R14B` function and its endpoint availability gates. Constant pump averages weekly gross levels by product and month, then blends product relative changes using the released petrol share. The +7-day pump release rule matches the original constant-pump recipe.
- Administered prices, alcohol, released basket weights, and the wedge match the bridge function's formulas and argument timing. Contribution recombination preserves all six blocks, with the wedge already in headline contribution units.
- Annual accounting uses only headline months strictly before the origin and the supplied independent h0 thereafter. It compounds each exact twelve-month calendar window. Future headline/core/component/feature values, future food levels, unreleased food endpoint values, and unreleased pump rows were poisoned simultaneously; the complete output table remained exactly identical.
- Relevant missing core and duplicate monthly component keys fail closed. Existing focused tests additionally verify duplicate pump dates, timezone-aware clocks, pump release dates, and unreleased last-core rejection.

Original sources inspected: `models/core_trend_residual_r15.py`, `models/core_learning_r14.py`, `models/core_slope_transmission_r16.py`, `models/food_stable_r14b.py`, `models/food_path_r14.py`, `models/fuel_path_r14.py`, `independent_bridge_experiment.py`, `models/path_inputs.py`, the relevant publication and component functions in `core_split_experiment.py` and `cz_struct.py`, and R15/R16 path assembly and R14B integration reference code.

## Verification evidence

Added eight independent test cases in `tests/test_r20_path_review.py`. Six exercise the real first fixture origin, including exact saved component/weight/contribution parity for all three models, all-horizon accounting, future-value invariance, h0 contributions, missing core, and duplicate components. Two isolate malformed annual reference coverage in the actual audit CLI function.

Final command (offline, existing dependency runtime; elevated read access was necessary for restricted dependency files):

```powershell
$env:PYTHONPATH='work/audit_fixes_20260914/runtime_deps;../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m pytest tests/test_r20_path_review.py tests/test_current_path.py -q -p no:cacheprovider --basetemp work/research_r20_review/pytest_verified
```

Result: **14 passed in 2.64s**, exit code 0. Earlier red evidence was **2 failed, 6 passed**: both missing-annual-reference cases failed before the parent fix. An initial test harness attempt also required creating the custom temporary directory's parent; that environment setup error was not a product defect.

The parent's complete 90-origin replay was not duplicated. Its written artifacts in `output/research_r20/parity_v1` were independently inspected with pandas: 3,510 rows; 90 origins; exactly the three declared model IDs; horizons 0 through 12; zero duplicate origin/model/horizon keys; 5,130 field checks including 270 annual checks; maximum absolute difference `5.329070518200751e-15`; zero finite-mask mismatches. The shared path's first origin was independently recomputed and compared against all saved native component fields in the added tests.

## Reviewed file identities

| File | SHA-256 |
|---|---|
| `models/current_path.py` | `b741b15e6a09e9c29b72fbf59f71137103e2db49f3f008ec214c8133a97fdc97` |
| `tools/current_path/audit_parity.py` after coverage fix | `402a78af647ad9158590dbae44c22fdbd4d226d94079abbaa7e48e2f90cf14d2` |
| `tests/test_r20_path_review.py` | `c9a245e724ac903ad968b46294df0725a1985d085c05f6709ac34bc2dfc02585` |
| R20 plan | `9a196415bec7482a7f10ed9095541ba9b186683efbef864ca9b3617913835fc4` |
