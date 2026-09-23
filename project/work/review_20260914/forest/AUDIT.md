# Forest audit, 14 September 2026

Read-only audit of the new CNB-paper forest lane. Main worktree files were not modified. All scripts and evidence are in this directory. Source references below are relative to `../cpi-independent` unless stated otherwise.

## Findings and their limits

### 1. TVW validation forecasts are not causal at the simulated validation origins

`models/paper_tvwqrf.py:107–118` fits a forest on all but the last 12 direct pairs and predicts those last 12 rows. There is no horizon argument or embargo. At outer edge December 2023, the held-out forest trains target labels through December 2022, regardless of horizon. Its first validation feature origins are October 2022 / July 2022 / April 2022 / January 2022 at h3/6/9/12. Thus 2/5/8/11 training labels are still unknown at the first simulated validation origin. At model h13 (path h12), the first validation origin is December 2021 and 12 unavailable labels enter.

Executable counterexample: on the actual realtime LUCI panel, h12 and outer edge December 2023, changing only held-out-forest training labels dated after January 2022 changes January 2022 validation quantiles (maximum change 9.396 pp for a deliberately large +10 pp perturbation). Dates and both quantile vectors are in `audit_evidence.json`.

**Limit:** this is a weight-calibration defect, not future-label leakage across the outer forecast origin. All those labels are known by December 2023. Outer scores remain scores of a deployable historical rule conditional on the panel's vintage conventions; do not describe the whole OOS backtest as invalid solely for this reason. The current engine also matches the saved exact run's engine SHA-256.

Correct causal calibration is available without changing the final forest: save each prior origin's quantiles generated using labels `s+h <= v`; when outcomes mature, fit weights from the latest 12 such forecasts with `v+h <= current_edge`. Rebuild preprocessing at each validation origin. A cheaper fixed validation forest requires its last training label to be at or before the first validation feature origin, plus preprocessing fit solely on that training slice.

`causal_reweight.py` applies the saved-origin approach. For the exact paper panel, it can only start once 12 saved, matured forecasts exist, so comparisons below use exactly the same eligible origins, not the full published sample:

| Exact paper run | h3 | h6 | h9 | h12 |
|---|---:|---:|---:|---:|
| n | 161 | 155 | 149 | 143 |
| Original TVW3 RMSE | 0.716841 | 0.711370 | 0.740015 | 0.686812 |
| Causal TVW3 RMSE | 0.727978 | 0.709429 | 0.739869 | 0.686219 |

There is a modest mixed effect, not a universal optimistic bias. The paper panel retains its declared full-sample preprocessing in this diagnostic.

On all Board A common origins, using the causal weights in the realtime FULL path and retaining HARD_BASE at h0:

| Path y/y RMSE | h1 | h3 | h6 | h9 | h12 |
|---|---:|---:|---:|---:|---:|
| Original FULL | 1.105994 | 1.956544 | 2.985443 | 4.221433 | 5.602016 |
| Causal FULL | 1.119867 | 2.013505 | 2.981307 | 4.159908 | 5.514871 |
| Causal FULL + month | 1.078145 | 1.954848 | 2.858818 | 4.100679 | 5.431277 |
| Bridge | 0.910737 | 1.537322 | 2.516379 | 3.921607 | 5.394839 |
| n | 88 | 84 | 81 | 78 | 75 |

Neither corrected path beats the bridge at h6 and h12, so neither can pass the declared rule. No bootstrap rerun is needed to establish that necessary-condition failure.

### 2. The realtime imputer is fit before the internal holdout split

`paper_tvwqrf_experiment.py:108–111` prepares all outer training arrays before calling `fit_forecast`. `models/paper_big.py:362–367` estimates means on every eligible outer training row. Consequently, the last 12 validation feature rows contribute to imputed values in the earlier held-out-forest training rows, even at h1 where the label embargo issue disappears.

Counterexample in `audit_evidence.json`: changing only the 12 held-out feature rows from 1 to 100 changes an earlier imputed training feature from 1 to 11.513274. This does not use data after the outer origin, but it undermines the claimed held-out validation procedure. The causal saved-origin diagnostic above also avoids this internal preprocessing contamination.

### 3. The paper benchmark matching uses a different information cutoff from the forests

`paper_tvwqrf_experiment.py:96–105` uses direct forest labels through `t` and predictor row `X_t`. Its `_TMH` benchmarks at `:141–157` instead truncate outcome history at `t-h`, forecasting `t+h` over **2h** steps. The RW is therefore `pi_(t-h)`, while the h-aligned RW at `:158–160` is `pi_t`. This is material: RW h6 is 0.887813 when h-aligned versus 0.696487 with the extra lag; h12 is 0.707858 versus 0.845171.

The specification explicitly records selecting this alternative alignment because its RMSEs match, while retaining the forest alignment because the h6 median matches (`docs/implementation/PAPER_TVWQRF_SPEC_2026-09-12.md:382–386`). It correctly concedes at `:413` that h-aligned benchmarks remain the fair forest comparison. Treat the `_TMH` values as a diagnostic numerical match, not evidence of a common-information forecasting comparison.

The paper text at `../cnbwp_2026_09.txt:338–349` defines the forecast of `pi_(t+h)` conditional on `X_t`; `:595–599` describes the RW as the last observed value. However, `:453–462` also says QRF training/information runs through `t-h`. That prose is ambiguous about feature versus label dates. Without author code, the correct conclusion is **the exact timing protocol is not established**, not a definitive allegation that the paper authors implemented it incorrectly. The forest implementation's own direct-horizon cutoff is sensible.

The saved exact TVW3 RMSEs rescore to 0.706783 / 0.694749 / 0.713808 / 0.649849 (n175/172/169/166), so the declared four-cell ±0.05 criterion does pass. That is weaker than replication of the method or its claimed advantage. The weighting-gain criterion fails, as the specification already says. Its final statement at `:458` that the plain forest, LQR and all benchmarks are within about 0.03 overstates even the table: QRF median at h12 differs by -0.053718, mean by -0.040308.

### 4. The realtime transform has a latent future-dependence bug

`tools/paper_replication/build_paper_panel.py:217–220` selects log versus simple differences by checking whether **any value in the complete supplied history** is nonpositive. `:376–378` does this before filtering by release availability. A later nonpositive value therefore changes all prior transformed rows.

Counterexample: adding a nonpositive April 2012 value to an otherwise positive row61 series changes the May 2007 realtime feature from 0.00623055 to 1.0. Only the later raw observation changed. A stable, declared row-specific transform policy would avoid this failure; simply rerunning this global rule as data arrive makes earlier backtests mutable.

**Limit:** this is a demonstrable prefix-invariance failure, not proof that the supplied evaluated 2011+ forecasts were materially contaminated. In the current raw candidate panel the only nonpositive T2 series outside the fuel component are row22 (first negative October 1993) and row25 (April 2005), both before the first evaluated origin. The other T2 histories currently remain positive.

## Explicit conventions, not newly discovered bugs

- Paper preprocessing really is full-sample: X13 (`build_paper_panel.py:193–207`), fuel PCA (`:224–231`, `:283–286`), Chow-Lin (`:171–189`, `:289`), and factor imputation (`:235–254`, `:307`). These can use later observations and are explicitly disclosed in the spec at lines35–43 and builder docstring lines7–14. This panel is unsuitable as evidence of strictly real-time ability. Paper prose describes the transforms but does not establish whether every preprocessing step was full-sample or recursive.
- Realtime avoids rerunning X13, uses published-quarter availability, fits fuel PCA on visible rows, and estimates outer imputation means only on eligible training rows. This is still a current-vintage panel with assumed release dates; absence of local X13 does not recover historical vintages of already-SA/revised source series. `build_a6_audit.py:13–16` explicitly says none of the inputs is an original real-time publication vintage.
- No accidental full-policy admission into the independent run found. `feature_columns/policy_columns` (`paper_tvwqrf_experiment.py:62–75`) filter Table A6 kinds. LUCI rows15/16 are classified hard, but the user's explicit exception is documented at `PAPER_TVWQRF_SPEC_2026-09-12.md:133–137`: three underlying LUCI inputs are EC surveys; the independent LUCI run is not strictly survey-free. The no-LUCI independent run is the stated survey-free ablation.
- The purported h6 YoY construction (`paper_tvwqrf_experiment.py:196–215`) compounds six h6 forecasts made at **six different origins**. For December 2023 YoY, the July–December forecasts come from January–June 2023. It is causal by June, but it is not a single June-origin h1–h6 path. Do not cite its 2.083 RMSE as evidence for a same-origin six-month path. The path scorer itself correctly uses same-origin direct horizon forecasts.
- No horizon mapping or Board A clock bug found: source horizon k becomes path h=k-1 and origin e+1 (`paper_tvwqrf_path.py:53–62`), and all saved panel eves equal Board A as-of dates. Board A and combination keep HARD_BASE at h0. Missing monthly forecasts stay missing rather than silently becoming zero.

## Verification

55 existing tests passed: `tests/test_paper_tvwqrf.py`, `test_candidate_validation.py`, `test_bloomberg_candidate_import.py` (35); `test_paper_big.py`, `test_exact_overrides.py`, `test_a6_audit.py` (20). They do not enforce causal internal validation timing. Outer future-target/panel-row perturbations leave prepared realtime h12 arrays unchanged. Exact run forecasts were rescored independently. Existing path scores are reproduced on the same 88/84/81/78/75 origins by the causal-reweight diagnostic before replacing weights.

Runtime: bundled Python3.12 with existing `work/pythonlibs` first on sys.path (numpy2.5.2, pandas3.0.1, quantile-forest1.4.2). This differs from the saved run's package versions, so this audit does not claim to reproduce every original forest fit bit for bit. Arithmetic rescoring is exact to reported precision.
