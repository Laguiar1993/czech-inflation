# R23B independent review

17 September 2026. Reviewed against `docs/implementation/R23B_MEASUREMENT_REPAIR_SPEC_2026-09-17.md`: the R23B code, tests, `output/research_r23b/final` and `R23B_RESULTS_2026-09-17.md`. Nothing in the tree was edited; every file of this review is in this folder. Each `[FAIL]` line in a probe output is one of the findings below; every other check passed.

## Assessment

The implementation matches the frozen specification, has no look-ahead, and every fit, path, score, gate and lead-test count I rebuilt with my own code reproduces to rounding, so "six candidates, none promoted, lane closed" stands and no blocker was found. What needs correcting is on the reporting side: one factually wrong sentence in the results document (line 68), a repair that is described as removing the delayed-echo intercept when a mean component with the same −0.57 anti-phase signature survives inside the uncentred features, and a test suite that guards look-ahead well but leaves the do-no-harm gate, the estimator's objective and several diagnostics rules unpinned.

## Findings

Severity: blocker / should-fix / minor / note. "Number" means a number in a delivered output file or in the results document.

### Blockers

None.

### Should-fix

**1. Results document line 68 is factually wrong: "all from two 2022 reports".**
Evidence: `probe_H_results_document.out.txt`, own rebuild from `data/cnb_mpr_cpi_quarterly.csv`, `evaluation/cnb_clocks.csv` and the frozen headline series (no delivered lead file used): random walk joint successes `{'2022-02-10': 4, '2024-08-08': 2}`; constant 2% `{'2023-08-10': 2, '2025-08-14': 1}`. Two reports, yes; but one is August 2024, and none of the constant-2% successes is from 2022. The August 2024 report is also the source of the joint candidate's third success (2025Q2; joint: `2022-02-10: 2, 2024-08-08: 1`), so the naive random walk scores twice on the very report that lifts the joint candidate from two to three. That supports the paragraph's conclusion better than the sentence as written.
Changes a number: no. The table on lines 61–66 is right (all 224 rows of `cnb_lead_summary.csv` reproduce, probe E7). The sentence must be corrected.

**2. "No intercept" left a pseudo-intercept; the delayed echo is reduced, not gone.**
Spec line 29 declares every feature "defined so that zero means neutral" and line 51 concludes "the delayed-echo intercept is gone". The estimator scales by RMS without centring (`models/cost_pressure_r23b.py:35-36`), so a feature with a non-zero mean carries a level term. Evidence, `probe_G2_edges_sensitivities.out.txt` section (c) and `probe_G2_pseudo_intercept.csv`:
- Share of the training second moment that is the feature's mean (mean² / mean of squares), band 1, by origin year: `ulc_sameq` 0.61–0.66 for 2019–2022 origins (the feature is positive at 82% of quarter-ends, mean +1.68 against sd 3.82), `tightening` 0.22–0.50, `import_gap` 0.43–0.56 for 2024–2026 origins. The momentum features and `fx_news` are clean (at most 0.13).
- Split of the applied h6 correction into coefficient × training mean ("level part") and coefficient × deviation: correlation with the correction FAST needed is −0.57 / +0.47 (labour cost), −0.59 / +0.33 (joint), −0.48 / +0.26 (signed), −0.37 / +0.29 (domestic), −0.35 / +0.21 (levels). R23's intercept scored −0.58. Mean absolute size of the level part is 0.09 log points against 0.31 for the deviation part (labour cost).
- Cost: on the 81-origin support the labour-cost candidate's h6 core RMSE is 1.629 delivered, 1.603 with the deviation part alone, 1.810 with the level part alone (FAST 1.758).
- It does not rescue anything: from 2024 the deviation part alone gives 0.522 against FAST 0.394 (level part alone 0.405). The 2024+ failure comes from the time-varying labour-cost signal, which is what results line 53 argues. The decision is unaffected.
Changes a number: no. It changes the reading of results line 15 and line 49 ("its correction is now in phase with need"): true of the total (+0.42) and of the deviation part, not of the level part. The results document should state the split. This is a decomposition of the delivered correction, not a proposal to refit.

**3. Tests guard look-ahead but leave declared behaviour unpinned (19 of 37 mutants survive).**
Evidence: `probe_F_mutation.out.txt` (in-memory mutants of the delivered modules run against the delivered tests; no file modified). Killed, so genuinely tested: every publication mask (ULC, PPI, imports), both label-maturity rules removed together, inner folds built at the outer origin and clock, the R23 single maturity rule, the 40-row cap, the `<=` tie, centring, far-band corrections, band sum instead of mean, six-release maturity, non-circular blocks, the block rule, the random-walk clock. Survivors that matter:
- Do-no-harm ignored when the path is built (`models/cost_pressure_r23b.py:106`). `tests/test_cost_pressure_r23b.py:157-160` computes its expectation with the same rule and the fixture never produces an unapplied band. Line 125 of the same file is a tautology (`alpha is None or score < zero_loss` holds by construction).
- Earliest instead of latest eight folds (`:68`), tie among penalties to the weaker one (`:82`), inner minimum 16 → 4 (`:65`), fold minimum 4 → 1 (`:69`).
- Standard-deviation scaling instead of RMS (`:35`) and a penalty not scaled by n (`:38`): the declared objective is pinned by no test.
- `tools/path_diagnostics/attribution.py:82-83` (months before the origin count as zero) and `:87-88` (h0 dropped at h12): both rules named in the docstring are untested. `:113-114` dominant block in the direction of the error: the only assertion is membership of the set of all parts (`tests/test_path_diagnostics.py:100`), which is vacuous.
- `tools/path_diagnostics/lead_baselines.py:26`: a base rate that treats the origin month as known history passes; both test quarters lie wholly in the future.
- `tools/path_diagnostics/gates.py:55`: correlation over active rows only passes.
- Median → mean of the three earlier ULC quarters (`data/cost_pressure_r23b.py:56`): the synthetic series makes them equal.
- No test imports `tools/research_r23b/evaluate.py` (feature gates, coefficient gates, needed-against-applied, same-support scoreboard, leave-one-year-out), and nothing in code or tests asserts that h0, noncore values and weights are preserved (`run.py:79` asserts FAST path equality only; spec implementation step 3 asks for both).
Survivors that are equivalent in practice, not weaknesses: month-maturity and release-maturity are each implied by the other because every clock lies between the releases of t−1 and t (probe A1); the same holds for the two seasonal-naive guards and the unfinished-quarter ULC reference.
Changes a number: no. Every surviving behaviour was checked on the delivered data and is correct (probes A2, C, E). It matters because `tools/path_diagnostics` is declared the standard for later rounds.

### Minor

**4. Binding-share gate is tighter than the bounded solver.** `gates.binding_share` uses 1e-10 (`tools/path_diagnostics/gates.py:33-36`); `lsq_linear(..., tol=1e-12)` is an interior method (`models/cost_pressure_r23b.py:40-44`) and leaves 1.24e-10 and 2.23e-10 on coefficients that the exact active-set solution (NNLS) sets to zero. `probe_A2_estimation.out.txt`: exact zeros 369, counted 363; missed `ulc_sameq` band 1 at 2021-01..03 and `tightening` band 2 at 2022-07..09.
Changes a number: yes, two cells of `evaluation/gate_coefficient_signs.csv` for `PRESS_SIGNED_R23B`: band 1 `ulc_sameq` 3.3% → 6.7%, band 2 `tightening` 61.1% → 64.4%. Neither is quoted in the results document (line 31 quotes koruna news and import momentum, which are unaffected). Selection is unaffected: my NNLS rebuild picks the same penalty and the same applied flag in all 180 signed cells.

**5. `ppi_mom` does not fail closed on an interior publication hole.** Spec lines 33–34: "all six must be published and finite"; the code reads only the two end levels (`data/cost_pressure_r23b.py:71-73`). `probe_G2`: with the publication date of month t−4 removed, `ppi_mom` stays −8.353451; `import_mom` correctly turns missing.
Changes a number: no. The delivered PPI source has no missing or non-monotone publication date.

**6. Results document, four table cells are 0.001 too high (double rounding).** Line 40 headline h6 2024+ 0.680 (0.679466), line 41 headline h6 full 2.280 (2.279482), line 43 core h6 full 1.692 (1.691491), line 44 core h6 2024+ 0.509 (0.508458). `probe_H`. No comparison changes.

**7. Results line 49, bootstrap sentence needs its metric.** "Intervals for the 2024+ loss difference exclude zero on the wrong side at h3 and h6" holds for headline (h3 +0.004 to +0.087, h6 +0.050 to +0.301) and for core at h6 (+0.007 to +0.216); for core at h3 the interval is −0.006 to +0.042. The sentence sits in a bullet about core. `probe_H`.

**8. "A dominant-block label on every call" (spec line 80, results line 72) overstates.** `tools/research_r23b/evaluate.py:122-125` labels only first calls that are revision-eligible and matured: 703 of 1,612 model calls (1,275 first calls). `probe_H`. No number changes.

**9. Results line 16: "no correction is learned from labels more than a year old" is false as written.** Training label origins are 4 to 126 months before the decision origin and 93% are older than 12 months. What holds: the newest label is 4–9 months old (R23: 13–15), and h7–12 gets no learned correction. `probe_H`, `probe_B` (newest label's last target 0–2 months before t−1 in both bands).

**10. Needed-against-applied uses a different support from the score tables.** `evaluate.py:53-62,73-74` takes all matured origins (87/84/78 at h3/h6/h12); the tables use 84/81/75. On the primary support the h6 correlations move by at most 0.002 and no sign changes (`probe_G2` (d)). The results document should name the support.

**11. `eligible()` depends silently on row order.** `models/cost_pressure_r23b.py:57` slices `[-40:]`; a shuffled feature frame returns a different set (26 of 40 rows differ) without error (`probe_G2` (b)). `tools/research_r23b/run.py:61-62` refuses unsorted features, so the delivered run is safe; the function is not.

**12. Missing current features are all-or-nothing.** `models/cost_pressure_r23b.py:94-95`: a missing `import_gap`, used by one candidate, sends all six to FAST (`probe_G2` (g)); spec line 70 reads per candidate and band. Never triggered: 540 of 540 origin-model rows are `estimated`, no band fell back.

### Notes

**13. The monthly map moves months outside the band it is given (per spec line 70).** c2 = 1 alone gives −0.17, −0.17, +0.33 in h1–3 and +0.32, −0.19, −0.12, −0.05, +0.02, +0.02 in h7–12. 86 origin-model cells carry a non-zero h1–3 monthly correction although validation refused band 1; the largest h7–12 monthly value is 0.103 log points. The cumulative effect is exactly zero at h3, h6, h9 and h12 (probe C), so the reported h3/h6/h12 figures are unaffected; h1–2, h4–5, h7–8 and h10–11 scores are.

**14. The do-no-harm test is weak as declared.** The weakest penalty, the lower edge of the grid, is chosen in 473 of 682 applied cells; 156 applied cells beat no correction in at most 4 of their 8 folds; 61 applied cells gain less than 1% in validation. Frozen by the specification; worth stating next to "applied at 50–79% of origins" (results line 29).

**15. Coefficient gates pool applied fits with unapplied diagnostic fits at the fixed α = 3** (`models/cost_pressure_r23b.py:26,104`; `evaluate.py:42-50`). Among applied fits only, the joint candidate's wrong-sign shares are koruna news 100% / 85%, import momentum 70% / 100%, tightening 25% / 80%, labour cost and producer momentum 0%. Same reading as results line 31.

**16. Bootstrap.** The index rule gives uniform inclusion, also when n is not a multiple of the block (0.4% maximum deviation at 400,000 draws); at the delivered 2,000 draws the realised inclusion still varies by up to 7.8% between origins, which is Monte Carlo noise. The unchanged R17 stack still writes the old truncated moving-block file (`headline_paired_block_bootstrap.csv`) beside the new one; the results document cites only the circular one.

**17. Block table semantics.** `block_error_table.csv` is the cumulative price-level error with h0 included at every H, H = 12 too; the module docstring motivates it by the annual-rate error. The sum of monthly errors understates that error in the high-inflation years (FAST h12 RMS 4.43 against 4.78, correlation 0.9997). `quarter_attribution` treats h12 correctly.

**18. Pre-declaration checks out.** Specification blob in commit `669f56a` (08:01:38) = file on disk = hash pinned in the fit manifest. Code commit `7ff8c9e` (08:10:48) precedes the run directory (08:10:49) by one second; the code is unchanged since (empty `git diff`), and one run directory exists. Results line 76 ("an independent reviewer reconstructed the fits and scores; see the linked review for its findings and their disposition") was written at 08:46 and committed at 12:13, before this review existed. The first half is now true; a disposition cannot exist yet.

**19. Out of scope.** `tools/path_diagnostics/standard.py` (08:23) is newer than the run and was not reviewed. PREV_CNB and CNB_MOMENTUM have no value at the first report because the CNB file starts there.

## Verified and found correct

A. Specification compliance (`probe_A1`, `probe_A2`)
- `ulc_sameq`, `import_mom`, `ppi_mom` rebuilt from the frozen sources with own code on all 199 origins: maximum difference 6e-14; reference quarter and month equal the saved provenance; reference = latest published quarter ending by t−1, exactly q, q−4, q−8, q−12, median of the three earlier ones, all four published with complete core months.
- Exactly six published monthly changes; core change over the same months; reference month = latest published import (or PPI) month at most t−1; `import_mom` and `import_gap` share one reference month.
- `tightening`, `fx_news`, `import_gap`, `ppi_gap` and all 199 clocks are bit-identical to the sealed R23 final files; `data/cost_gaps_r23.py`, `models/cost_gaps_r23.py`, `r17_common.py`, the three evaluators and `lead.py` are byte-identical to what R23 used; all 164 files of the R23 delivery manifest are unchanged.
- Targets: band mean of realised log core less the saved FAST log rate over h1–3 and h4–6, difference 0; label release = last of the 3 or 6 releases; missing when incomplete.
- Estimator re-implemented from the text (ridge by augmented least squares, bounded variant by NNLS) for all 1,080 origin-model-band cells: training rows (latest 40 band-matured, released, seven-feature-complete quarter-ends, minimum 24; 30 to 40 rows), fold sets (latest 8, at least 16 inner rows at the fold's own clock, inner cap 40; 8 folds in every cell), scores to 5e-10, no-correction loss exactly, penalty choice, tie rule, strict do-no-harm inequality and status in every cell; unrestricted coefficients and predictions to 5e-16, bounded to 3e-9; paths to 4e-10. No exact tie and no score equal to the no-correction loss occurs.
- No intercept, RMS scaling without centring, objective scaled by n, grid {0.3, 1, 3, 10, 30}, common rows across candidates, `monthly_correction([c1, c2, 0, 0])`. No fallback was triggered.

B. Look-ahead (`probe_B`)
- Features bit-identical under 1e12 poison of every unpublished or future cell (core after t−1 or unreleased, FX after t, all four A6 series) on all 199 origins, 2019-02, 2021-06, 2023-01 and 2026-07 printed; the poison is live (196 of 196 origins contaminate when origin and clock move three months forward).
- Every clock lies at or after the release of t−1 and before the release of t; evaluated-origin clocks equal the saved FAST state clocks to the second.
- `training.csv`: 6,919 rows, last target = s + 3·band ≤ t−1, release ≤ clock and equal to the calendar release, quarter-ends only, 24–40 rows. `inner_validation.csv`: 43,200 rows, validation origins are outer rows, matured at the outer clock, inner labels ≤ v−1 and released by v's own clock, validation labels released after v's clock.
- The delivered `run_origin` re-run with every unmatured label at 1e8 and every later feature row at 1e12 equals `fits.jsonl` exactly at six origins; per-fold poison beyond each fold's own clock leaves all 960 checked fold losses unchanged.

C. Reconstruction from saved outputs, 90 origins × 6 candidates (`probe_C`)
- coefficient × (current feature / saved scale) = contribution = prediction (6e-17); `coefficient_contributions.csv` and `status.csv` mirror `fits.jsonl`; saved scores = mean of the fold losses; zero loss = mean squared validation label; chosen penalty = argmin with the declared tie rule, applied only if strictly below; unapplied bands enter as exactly 0; paths = `monthly_correction([c1, c2, 0, 0])`; band means exact.
- Exported core = 100·expm1((FAST log rate + path)/100) exactly; h0 rows, every noncore value and contribution, every weight and every outcome column identical to FAST; control rows identical to the R21 native file; `mm_forecast` = FAST + weight × core change; annual rates = twelve-month compounding of known history, FAST h0 and the path.
- 11,700 native and forecast rows (10 models × 90 × 13); 969 primary keys per model, identical to the R17 support, all finite; cumulative log core less FAST = 3·c1 at h3 and 3·(c1 + c2) at h6, h9, h12 to 3e-15.

D. Scores (`probe_D`, `probe_E2`)
- Outcomes rebuilt from the frozen headline and core series; 120 cells (2 metrics × h3/h6/h12 × 2 samples × 10 models) of n, RMSE, MAE and bias equal `same_support_scoreboard.csv` to 9e-16; needed-against-applied equals `needed_vs_applied.csv` to 4e-16 for 7 models, 3 horizons, 2 samples; 138 leave-one-year-out cells, 96 block-error cells and 36 block-benchmark cells reproduce.

E. Diagnostics (`probe_E`)
- Seasonal share = R² of a period-of-year dummy regression, 14 cells; the gate returns 0.438 on the sealed R23 `ulc_gap`, so it has power on the defect it was written for; coefficient gates reproduce.
- Bootstrap: block rule, uniform inclusion, contiguity and reversed-order refusal, the delivered table's rule by n, mean loss differences, intervals within 6% of an own-seed replication, no point estimate outside its interval.
- `monthly_block_errors`: block error = weight × (forecast − realised), parts sum to total, h0 its own bucket, cumulation from h0 with missing months propagating. `quarter_attribution`: four cases on real data. `seasonal_naive_path`: own rebuild and poison at four origins.
- Lead test: CONST_2 and RW_YY quarter values on all 322 report-clock pairs and their summary rows on all 15 columns; then all 224 rows of `cnb_lead_summary.csv` (14 models × 2 clocks × 2 thresholds × 2 samples × 2 scopes) with own call, eligibility, episode and outcome rules; base rates use only annual rates published at the snapshot clock.

Integrity (`probe_G1`): 67 fit-input, 14 fit-output, 95 evaluation-input and 47 evaluation-output hashes match; no reviewed code file is newer than the first output.

Results document (`probe_H`): gate table lines 23–29 and 31, the counts on line 35, 38 of 42 score cells, line 47, the 4% and 7% and the correlations on line 49, lines 50–51, the lead table, "19 from 13 reports, losses from 9, gains from 3", and "20 new, 29 tests" are all right. Commits `669f56a` and `7ff8c9e` on line 5 exist with the stated contents and order.

Tests (`F_pytest_output.txt`): 29 passed.

## Files

`_common.py`; `probe_A1_features_targets.py`; `probe_A2_estimation.py`; `probe_B_lookahead.py`; `probe_C_reconstruction.py`; `probe_D_scores.py` (writes `probe_D_scores.recomputed.csv`, `probe_D_needed_applied.recomputed.csv`); `probe_E_diagnostics.py`; `probe_E2_tables.py`; `probe_F_mutation.py`; `probe_G1_integrity.py`; `probe_G2_edges_sensitivities.py` (writes `probe_G2_pseudo_intercept.csv`); `probe_H_results_document.py`; one `.out.txt` beside each probe; `F_pytest_output.txt`.

Run from the repository root (the relative `PYTHONPATH` breaks elsewhere):

```bash
export PYTHONPATH=../pythonlibs PYTHONDONTWRITEBYTECODE=1
PY="C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
"$PY" work/research_r23b_review/probe_A1_features_targets.py    # same for the others; A2 takes about 90 s, F about 60 s
```

Probes write only into this folder. `probe_H` reads `probe_D_scores.recomputed.csv`, so run D first.
