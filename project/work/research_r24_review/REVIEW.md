# Independent review of R24 (food-price drift), 17 September 2026

Reviewer: Claude (independent of the R24 author session). Read-only on everything outside this directory. Every number below comes from a probe in this directory whose captured output sits beside it.

## Overall assessment

The implementation is clean. I found no look-ahead, no departure from the frozen specification, and every reported number reproduces from my own code to 1e-15. Claims (a), (b) and (c) are all correct as arithmetic and as the rule is written.

What is overstated is the interpretation. `mu_long` is a constant in practice (2.51 to 2.82 log points a year, sd 0.07, across 90 origins), and **any constant drift between 1.75 and 4.75 a year passes all four promotion conditions**. The experiment therefore shows that a food drift near 2.5 a year would have beaten the window mean over this one cycle. It does not show that the robust long-history estimator works, which is how the R25 specification already cites it. The gains are concentrated in the 2021 to 2023 origins. The 2024+ bias of +0.19 is the average of two offsetting sub-periods (-3.2 and +2.7), and two legs of the rule were foreseeable from numbers printed in the specification before declaration.

No blocker. Four should-fix items: three concern what the results document must say, one concerns the tests.

## Verdicts

| Claim | Verdict | Qualification |
|---|---|---|
| (a) NORM_SHIFT improves food-block RMSE at h3/h6/h12 in every era | **Correct.** All 12 cells reproduced (max diff 1.8e-15); candidate below baseline in each, -1.4% to -18.3%. Full h12 7.357 vs 7.842; 2024+ h12 3.373 vs 4.129; bias +0.187 vs +2.305. | The 2019-21 cells are -2.4 to -2.6%. At h12 the era-level loss difference has an interval including zero for 2022-23 [-31.9, +2.1] and for 2024+ [-16.7, +5.6]. In 2024+ the candidate is worse at 8 of 19 origins (finding 2). |
| (b) Headline h12 4.801 vs 4.869 (n=75); 2024+ 0.665 vs 0.858 (n=19); interval [-1.20, -0.25]; survives leave-one-year-out | **Correct.** 4.8008 vs 4.8695; 0.6646 vs 0.8580; stored interval [-1.1986, -0.2520]; leave-one-year-out deltas -0.0426 (omit 2023) to -0.1093 (omit 2021), reproduced to 9e-16. "Interval excludes zero" is robust to block length, scheme and seed (D(iv) below). | The loss difference has lag-1 autocorrelation 0.78, so about six independent blocks. A t-test on non-overlapping block means gives -1.82 to -3.90 depending on alignment; 8 of 12 alignments fall short of the 5% critical value. No interval exists for 2024+ under the project's own rule (n=19 < 24). |
| (c) All four conditions hold for NORM_SHIFT, ROBUST_WINDOW, NORM_REFIT; order selects NORM_SHIFT | **Correct as written.** ZERO_DRIFT fails all four. | The rule has little power: constants 1.75 to 4.75 a year all pass (finding 1). |

## Findings

### 1. Should-fix (reporting). The promotion rule does not distinguish `mu_long` from a plain constant, and two of its legs were foreseeable before the fit

Evidence, `out_F2_rule_vs_constant.txt` (post-hoc sensitivity, not for selection). Replacing `mu_long` by a constant `c` in `s_c + c/12 + d_h`:

| c, log points a year | food h12 full | food h12 2024+ | bias 2024+ | headline h12 full | headline h12 2024+ | all four |
|---|---:|---:|---:|---:|---:|---|
| baseline (window mean) | 7.842 | 4.129 | +2.305 | 4.869 | 0.858 | |
| `mu_long` (declared) | 7.357 | 3.373 | +0.187 | 4.801 | 0.665 | pass |
| 1.50 | 7.751 | 3.540 | -1.001 | 4.883 | 0.642 | fail (c3) |
| 1.75 | 7.648 | 3.478 | -0.751 | 4.864 | 0.641 | pass |
| 2.50 | 7.382 | 3.396 | -0.001 | 4.809 | 0.659 | pass |
| 4.00 | 7.063 | 3.712 | +1.499 | 4.708 | 0.769 | pass |
| 4.75 | 7.019 | 4.073 | +2.249 | 4.663 | 0.852 | pass |
| 5.00 | 7.022 | 4.216 | +2.499 | 4.649 | 0.883 | fail |

- `mu_long` over the 90 origins: min 2.512, max 2.824, mean 2.656, sd 0.066 (`out_F_robustness.txt` section 4). A constant 2.6 gives food h12 7.352 and headline h12 4.802, identical to `mu_long` to the second decimal.
- The full-sample headline h12 RMSE falls monotonically with any higher constant up to at least 8 a year (4.513). That leg of condition 3 rewards repairing the 2021 under-prediction, not drift accuracy.
- For a constant shift the 2024+ leg of condition 1 and condition 4 are one condition: they hold for any drift between 0.20 and 4.81 a year. The specification printed the 2024+ bias (+2.31, line 15) and the window drift (4.9% a year, line 17) before declaration. The bias-zeroing drift is 2.50; `mu_long` at those origins averaged 2.69. From the specification's table alone the predicted 2024+ RMSE is 3.43; realised 3.37. The specification discloses this exposure (line 23), so this is not concealment, but the results document must not present those two legs as a test.
- The start year of the "norm" is a tuning constant (`out_B3_long_history.txt` section 5): at origin 2019-02 the median is 2.25 from 1998, 2.56 from 1996, 3.58 from 2010. Specification line 43 ("needs no tuning constant") is overstated. Every one of these passes the rule.

Changes a number: no. Changes a claim: yes. `R25_PANEL_PERSISTENCE_SPEC_2026-09-17.md` line 9 says "R24 showed that replacing a recent-window quantity by a robust long-history norm works for food". What was shown is that a drift of roughly 2 to 4.5 a year beats the window mean in this cycle.

### 2. Should-fix (reporting). The 2024+ food result is two offsetting sub-periods; the near-zero bias is an average, not an unbiased forecast

Evidence, `out_B4_base_year_and_era_detail.txt`, food block h12, error = forecast minus actual, log points:

| Origins | n | baseline mean error | candidate mean error | candidate better at |
|---|---:|---:|---:|---:|
| 2024-01 to 2024-08 | 8 | -1.19 | -3.20 | 0 of 8 |
| 2024-09 to 2025-07 | 11 | +4.85 | +2.65 | 11 of 11 |
| all from 2024 | 19 | +2.305 | +0.187 | 11 of 19 |

- At the first eight origins food rose faster than even the baseline's 4.9% drift, and the candidate under-predicts by 1.8 to 4.4 log points. The three origins 2025-05 to 2025-07 carry 79% of the era's net gain.
- Forecast-outcome correlation at 2024+ h12 is -0.585 for the candidate and -0.575 for the baseline (`food_block_scores.csv`). The dynamics are not improved, as designed; the gain is a level shift.
- The specification's narrative (line 17: "kept projecting +4.4 to +5.2% a year through 2025 while food prices fell") fits only the origins from 2024-09.

Changes a number: no. Changes a claim: "bias +0.19 vs +2.31" must be reported with this split.

### 3. Should-fix (reporting). The full-sample headline gain is concentrated, and in 2019-21 it is a by-product of the surge

Evidence, `out_F_robustness.txt` sections 1 to 3, `out_F_per_origin_h12.csv` (NORM_SHIFT, h12, n=75, sum of loss differences -49.83):

- Improved at 58 of 75 origins. Top 5 origins carry 36.1% of the total (2023-02, 2023-03, 2023-01, 2023-04, 2021-07), top 10 53.6%, top 20 77.3%.
- By origin year: 2023 44.4%, 2021 31.3%, 2022 9.5%, 2025 9.3%, 2020 2.3%, 2024 2.0%, 2019 1.3%. By era: 2019-21 34.8%, 2022-23 53.9%, 2024+ 11.2%. Era RMSE change: -0.6%, -4.1%, -22.5%.
- In 2019-21 the candidate raises the path (delta > 0 at 27 of 32 origins, mean +0.041 pp on the annual rate), because the 2015-19 window mean (1.7 to 2.4) was below `mu_long` (2.5 to 2.7). The gain is `2 x e_FAST x delta` with `e_FAST` near -10 pp at 2021 origins. At the twelve pre-surge origins 2019-05 to 2020-04 it is 7 of 12 improved, sum -0.6: a coin flip. At 2021-05 to 2021-12 it is 8 of 8, sum -10.0.
- This contradicts the specification's stated expectation (line 21: "worsen origins in 2021-22"). All 12 origins of 2021 improved because the candidate drift was higher there, not lower. The declared trade-off appears only at 2022-03 to 2022-05 (three of the five largest deteriorations).
- Decomposition: sum of `2 x e_FAST x delta` = -56.31, sum of `delta^2` = +6.48; correlation(delta, e_FAST) = -0.673.

Is the 2019-21 gain real? As arithmetic, yes (era interval [-1.11, -0.05], 25 of 32 improved). As evidence about the drift, no: it is one sustained shock rewarding a small upward nudge, consistently signed and therefore easy for a block bootstrap to call significant.

Changes a number: no. Changes a claim: "survives leaving out any single origin year" is true and should be accompanied by the concentration table.

### 4. Should-fix (tests). The suite does not pin the specification's definitions; five of eight mutants survive

Evidence, `out_G_test_strength.txt` (in-memory mutants of `models/food_drift_r24.py`; no file edited). 17 tests pass in 1.57 s (`out_G_pytest.txt`).

| Mutant | Caught by tests | `run.py:47` assertion |
|---|---|---|
| Horizon off-by-one, `[0:12]` instead of `[1:13]` (`food_drift_r24.py:99`, `:102`) | **no** | passes |
| `mu_robust` ignores the training window (`:95`) | **no** | passes |
| Refit moves the food centre the wrong way (`:73`) | **no** | passes |
| `LONG_START` 2005 instead of 1996 (`:17`) | **no** | passes |
| `mu_window` taken over all three series (`:94`) | **no** | passes |
| Publication stamps ignored (`:44`) | yes | passes |
| Simple-rate conversion dropped (`:106`) | yes | passes |
| Median replaced by mean (`:50`) | yes | passes |

- Cause: `tests/test_food_drift_r24.py:70-73` compares candidates with constants taken from the same `drifts` dict, so any definition is self-consistent. Line 69 only checks an ordering at one origin. Lines 60-61 only check that a shifted refit differs, not its direction.
- `tools/research_r24/run.py:47` asserts on `baseline_path`, which is the frozen model's own dict, not on the `[1:13]` slice of `forecast_food_rates` from which every candidate is built. It cannot catch a horizon shift.
- The fallback branches (`insufficient_history`, `missing_drift_estimate`) are untested. They behave as the specification says (`out_H_misc.txt` section 2).
- The frozen outputs are right on all five points: independently recomputed in `out_B1_own_drifts.txt` (drifts, 90 origins, 8e-17), `out_AC_compliance_baseline.txt` (stored baseline log rates map exactly onto R21 `value_food` at the same h, max gap 0.0) and `out_A2_refit_scale.txt` (new food centre averages exactly `mu_long`).

Changes a number: no. Matters because the module is already reused (`tools/current_path_r24/extend.py`, R25 candidate `CORE_PANEL_SHRINK_FOODNORM_R25`).

### 5. Minor. Undeclared parameter `MIN_WINDOWS = 12`

`food_drift_r24.py:18`, `:50`. Not in the specification. Never binds: fewest windows used 31 (`mu_robust`) and 266 (`mu_long`). No number changes.

### 6. Minor. "From January 1996" is ambiguous and the code's reading lowers `mu_long`

`food_drift_r24.py:17`, `:44` start the monthly rates at 1996-01, so the first twelve-month change ends 1996-12. From a file that begins 1995-01 the natural reading is that the first change is January 1996. That reading gives a higher `mu_long`: +0.10 at 2019-02, +0.05 at 2022-06, +0.26 at 2024-06 (2.94 vs 2.68), +0.14 at 2026-07 (`out_B3_long_history.txt` section 4). Both readings sit inside the passing band. No claim changes.

### 7. Minor. Block and headline tables are on different supports

Food-block h12: 78 origins (35 in 2019-21). Headline h12: 75 (32), because the fixed 969-key support omits 2019-02 to 2019-04. On all 78 matured origins the headline h12 is 4.7094 vs 4.7775 (`out_E_promotion.txt`). Conclusion unchanged.

### 8. Note. The full-sample bias gets worse

Food h12 bias -1.17 to -2.14; headline h12 bias -1.64 to -1.83; the 2022-23 food bias flips from +0.85 to -0.98 (`out_H_misc.txt` section 7). Condition 4 looks only at 2024+. The numbers are in `food_block_scores.csv`, so nothing is hidden.

### 9. Note. Long CZSO file: no leak; rounding and representation are immaterial; the vintage is unverifiable offline

- Only months 1995-02 to 2015-01 come from the CZSO file; the last is stamped 2015-02-10, four years before the first clock. Poisoning all 131 division-01 base-index values from 2015-02 leaves the spliced history identical (`out_B2_poison.txt`).
- The CZSO series and the model series agree to 1.1e-13 on the 131-month overlap, so both are the same one-decimal index.
- Rounding Monte Carlo: sd 0.02 a year. The same median from CZSO's independently rounded year-on-year index differs by -0.09 (2019-02) to +0.01 (2026-07).
- Base is 2015 = 100 (2015 mean 99.98; `bazobdobiod` 2015-01-01). The 2019 real-time vintage is not in the repository, so identity with it is not verified. CZSO does not revise the CPI as a matter of practice; that is the reviewer's domain knowledge, not something checked here.
- The pre-2015 publication rule (10th of the following month, 09:00 Prague) is never decisive for any origin.

### 10. Note. `ROBUST_WINDOW` is at least as good on three of the rule's six numbers

Food 2024+ h12 3.063 vs 3.373; headline full 4.7962 vs 4.8008; headline 2024+ 0.6608 vs 0.6646. It needs no extra data source. The declared order still selects NORM_SHIFT, and the differences are far inside noise. Against it: `mu_robust` rises to 4.03 in 2023-24 and stands at 3.67 in 2026 as the surge fills the window.

### 11. Note. Context for the size of the gain

The existing control `DAMPED_P95_Q001_R16` has full-sample h12 4.8101, the same size of gain as the food candidate (4.8008). Against CNB on reports from 2024 the candidate's MAE is 0.308 (cutoff clock) and 0.321 (report clock) vs CNB 0.287 (`out_context_cnb_summary.txt`).

### 12. Note. Process

Specification committed 08:20:43, code 08:24:16, outputs written 08:24:23 to 08:24:27, freeze commit 08:27:33. The specification is unchanged since a10939f; the R24 code is unchanged since b74136d. A search for `mu_long`, `FOOD_NORM_SHIFT` and `food_drift_r24` found no artefact predating the declaration. This ordering is consistent with declaration before the run; commit times cannot prove that no uncommitted exploratory fit happened. The R25 specification (12:13) builds on `FOOD_NORM_SHIFT_R24` before this review was delivered.

### 13. Note. Harmless dtype change

In the R24 native file the controls' all-NaN `food_model_status` column is string-typed; in the R21 file it is float. Every other shared column is identical (`out_AC_compliance_baseline.txt`, `out_C_status_dtype.txt`).

## D(iv). Bootstrap sensitivity, NORM_SHIFT, full-sample h12 squared-loss difference vs FAST (mean -0.6644, n=75)

| Scheme | Block | 95% interval | Excludes zero |
|---|---:|---|---|
| Stored (circular, seed 1509, 2,000 draws) | 12 | [-1.199, -0.252] | yes |
| Own circular, 20,000 draws, seed 24091717 | 6 | [-1.144, -0.272] | yes |
| Own circular | 12 | [-1.188, -0.240] | yes |
| Own circular | 18 | [-1.121, -0.268] | yes |
| Own circular | 24 | [-1.086, -0.267] | yes |
| Own moving block | 12 | [-1.250, -0.259] | yes |
| Own stationary, 5,000 draws | 6 / 12 / 18 | [-1.131, -0.276] / [-1.122, -0.271] / [-1.094, -0.283] | yes |
| Declared scheme over 200 seeds | 12 | upper bound -0.265 to -0.213 | yes, every seed |
| Diebold-Mariano, Newey-West lags 11 / 17 / 23 | | t = -2.69 / -3.04 / -3.30 | |
| Non-overlapping 12-origin block means, 12 alignments | 12 | t = -1.82 to -3.90, 5 or 6 blocks | 4 of 12 alignments at 5% |

Plainly: "the interval excludes zero" is robust to block length 6, 18 and 24, to a stationary and a moving-block scheme, and to the seed. All six non-overlapping block means at offset 0 are negative (-0.05, -0.56, -0.74, -1.80, -0.57, -0.26). The caveat is sample size, not method: one inflation cycle, about six independent blocks.

## Verified and found correct

- **A, specification compliance.** Shift formulas exact (max deviation 4.4e-16). `value_food = 100 x expm1(log rate)` exactly. Only `value_food`, `contribution_food`, `mm_forecast` and the derived or status columns change. h0 identical on every column. Change in `mm_forecast` equals `weight_food` times change in `value_food` to 2.5e-16. Six contributions sum to `mm_forecast` to 8.9e-16. All 360 status rows `estimated`, no fallback used. `mu_window` is the mean of the twelve food calendar means (it differs from the plain window mean by up to 0.32 a year, as the specification defines it). Refit: identical training dates, identical scale (difference 0.0), farm and producer centres unchanged, new food centre averages `mu_long` to 6e-17, contraction never binds (largest spectral radius 0.8212). Refit and shift paths differ by 0.027 log points on average over h1 to h12, so the refit converges to the declared centre.
- **B, look-ahead.** Own recomputation from the CSVs at all 90 origins: largest difference 8.3e-17 for each of the three drifts; training windows identical; the latest published food month is t-1 at every origin. Poison tests at all 90 origins, bit-identical in every case: poisoned levels (P1), poisoned long rates (P2), poisoned CZSO file (P3), truncated inputs (T). A clean call equals the frozen `fits.jsonl` at 90 of 90.
- **C, baseline.** Reproduction equals `value_food` of `STATE_FAST_R15` in the R21 file with a largest gap of 0.0 over 90 x 12 cells. `models/food_stable_r14b.py` and `models/food_path_r14.py` have no diff against HEAD, were last touched in ea547dc, and their hashes equal those recorded by 27 older manifests (R14, R14B, R17, R18, R22). R24 run manifest (70 inputs, 6 outputs) and evaluation manifest (91 inputs, 45 outputs) are all unchanged.
- **D, scores.** Food block 60 cells, largest difference 1.8e-15, identical n. Headline 112 cells, 8.9e-16. `yy_exante` recompounded independently from the native monthly paths: 5.3e-15. Primary key set identical to the 969-key file; no non-finite values. Leave-one-year-out 9.0e-16.
- **E.** Four conditions evaluated from my own scores; same result as claimed.
- **H.** Horizon index: rates for the same target month from adjacent origins differ by 0.138 on average, against 0.563 for adjacent target months; `target == origin + h` on every row; the exact match in C pins the slice. Era masks identical to mine and they partition the sample (35 / 24 / 31). Clocks given as UTC, Prague-aware or naive Prague time give the same `mu_long`; the comparison is `<=` at the stamp. Food-block n identical (87 / 84 / 78), so no NaN dropped silently. Fixed support applied identically to every model.

## Probe files (all in `work/research_r24_review/`)

`probe_common.py` (own loaders and estimators; imports no model code), `probe_AC_compliance_baseline.py`, `probe_A2_refit_scale.py`, `probe_B1_own_drifts.py`, `probe_B2_poison.py`, `probe_B3_long_history.py`, `probe_C_hashes.py`, `probe_D_scores.py`, `probe_E_promotion.py`, `probe_F_robustness.py`, `probe_F2_rule_vs_constant.py`, `probe_G_test_strength.py`, `probe_H_misc.py`.

Outputs: `out_AC_compliance_baseline.txt`, `out_A2_refit_scale.txt`, `out_B1_own_drifts.{txt,csv}`, `out_B2_poison.{txt,csv}`, `out_B3_long_history.txt`, `out_B4_base_year_and_era_detail.txt`, `out_C_git_readonly.txt`, `out_C_hashes.txt`, `out_C_status_dtype.txt`, `out_D_scores.txt`, `out_D_food_block_own.csv`, `out_D_food_block_pairs.csv`, `out_D_headline_own.csv`, `out_D_bootstrap_own.csv`, `out_E_promotion.{txt,csv}`, `out_F_robustness.txt`, `out_F_per_origin_h12.csv`, `out_F_constant_drift_grid.csv`, `out_F2_rule_vs_constant.{txt,csv}`, `out_G_pytest.txt`, `out_G_test_strength.{txt,csv}`, `out_H_misc.txt`, `out_context_cnb_summary.txt`, `out_context_block_error_table.txt`.

Run order: `probe_D_scores.py` before `probe_E_promotion.py`, `probe_F_robustness.py` and `probe_H_misc.py`, which read its CSVs. `probe_B2_poison.py` takes a scratch directory as its argument for the poisoned CZSO copy, which it deletes.

Limits of this review: era intervals quoted for n < 24 are indicative only, since the project's own rule gives no interval there. The constant-drift tables are post-hoc and must not be used to pick a drift.
