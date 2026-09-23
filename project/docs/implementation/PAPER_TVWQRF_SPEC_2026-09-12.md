# CNB WP 9/2026 TVW-QRF: replication run and path test — specification

**14 September audit amendment (the original declaration and historical results below are retained):** this is an approximate paper comparison, not verified numerical replication. `_TMH` benchmarks have an older information set than the forest; `yoy6` combines forecasts from six origins rather than one path origin. The internal holdout calibration was replaced with saved own-origin forecasts whose targets have matured, and transformations now follow fixed row metadata. New results and acceptance evidence are in `../../IMPLEMENTED_AUDIT_FIXES_2026-09-14.md`. The unchanged historical tables below must not be attributed to the corrected calibration. In particular, the earlier claim that genuine out-of-sample reweighting leaves the results unchanged is not established by the old weighting check and is superseded by the causal replay.

Declared 12 September 2026, before any full run. Results will be appended below
the line at the end; nothing above it changes after the first full run.

## Purpose

The user asked for three things:

- **Replicate the model.** Run the paper's TVW-QRF on the rebuilt 72-predictor Table A6 panel. For LUCI use CNB data, for rows 60–63 use the Bloomberg commodity series, and for rows 65–66 use Bloomberg in place of Refinitiv.
- **Compare with the paper.** Set the results against the published RMSEs.
- **Test it as a path model.** The goal is a good path model, so the same machinery is also scored as a monthly inflation path on the existing path boards.

This is a research lane. The independent nowcast and the path products are not changed.

## Inputs

**Panels.** `tools/paper_replication/build_paper_panel.py` writes both panels to `data/paper_replication/paper_model_panel_20260912/`.

**Where each row comes from:**
- **Official exact series** (`a6_inputs_20260912/exact_inputs_long.csv`): 60 rows.
- **User-selected Bloomberg series:**
  - 60 `CO1` month mean
  - 61 `TTFGDAHD BCFV` month mean
  - 62 `BCOMINSP` month mean
  - 63 `BCOMAGSP` month mean
  - 65 `TTFGCY1` month mean
  - 66 `FSBTY1` month mean
- **Best available candidates:**
  - 13 `CZGRIDX`
  - 17 `LCTQCZI`, quarterly
  - 25 local trade balance
  - 54 `PRIB03M` month-end
- **CNB LUCI (rows 15–16):** used when `official_cnb_luci_20260912/luci_quarterly.csv` exists. A run without them is labelled as such.

**Target.** Headline CPI m/m, not seasonally adjusted (`headline_extended_and_states.csv`), as in Section 4.2 of the paper.

**Paper convention** (reference-month rows):
- Quarterly series are interpolated with Chow–Lin (mean aggregation; indicator: the monthly unemployment rate).
- Every series not already published seasonally adjusted is X-13 adjusted over the sample. If X-13 fails, the raw series is kept and logged.
- Table A6 transforms are applied. Where a log difference is undefined because values are non-positive (rows 22, 25, 64), the first difference is used.
- The fuel first principal component uses the whole sample.
- Rows 65–66 are shifted forward 12 months.
- Gaps are filled by tall-wide factor imputation: 8 factors from the complete columns, fitted values fill the gaps.
- These full-sample steps use data after each origin, as the paper's description implies.

**Real-time convention.** Row `e` holds, for each predictor, the transform of the latest reference month available on the eve of the first CPI release for month `e+1`:
- Declared availability rules and the CPI release calendar set what is available.
- No X-13 is applied.
- Quarterly series enter as the latest published quarter.
- The fuel component is re-estimated at each row.
- Rows 65–66 are shifted by 12.
- Gaps remain and are filled with training means at each origin.

## Model

Section 3 of the paper, implemented in `models/paper_tvwqrf.py`:

- **Forest.** A quantile regression forest (`quantile_forest`) is fitted on all direct pairs (predictors at `s`, m/m inflation at `s+h`, with `s+h` at or before the origin).
- **Weights.** For weight estimation the last 12 pairs are held out. Quantiles from a forest fitted without them give the TVW weights. Each weight vector sums to one, stays within the bounds of eq. 5–7, and is estimated by exponential-kernel least squares with a six-month half-life (eq. 3–4).
- **Point forecasts.** The forest is refitted on all pairs. From it come the QRF median, the QRF mean, and TVW1, TVW2 and TVW3.
- **Hyperparameters.** The paper does not report them. The declared settings are 500 trees, a third of the predictors tried at each split, a minimum leaf of 5, bootstrap rows and seed 42. There is no tuning on the evaluation sample.

**Benchmarks** (Section 5 of the paper):
- random walk (last observed m/m);
- AR(3) by OLS, iterated (a direct AR(3) is also reported);
- ARIMA(3,1,3), iterated;
- LQR ensemble: 500 median regressions, each on 4 random predictors plus 3 target lags; the point forecast is the mean of the members.

## Evaluation A — comparison with the paper

**Setup.**
- **Convention:** paper, all 72 predictors present (70 if LUCI is not available), full policy.
- **Origins and targets:** data edges run from 2010-12 onward and targets end in 2025-09. Horizons are 3, 6, 9 and 12.
- **Metrics:** RMSE, MAE and bias per model and horizon, reported both on the paper's window and on common targets from 2011-12.
- **Tests:** Diebold–Mariano (Harvey–Leybourne–Newbold correction) of TVW3 against each alternative.
- **Year-on-year:** the Table A4/A5 construction at h=6.

**Outputs.** Every figure is set against the published Tables 1, 2, A4 and A5.

A result counts as reproducing the paper only if TVW3 is within 0.05 RMSE of the published value at every horizon. Otherwise it is reported as a gap, with its likely sources.

## Evaluation B — the path test

**Horizons.** Real-time convention, forecast horizons 1–13 from data edge `e`. These are path horizons 0–12 for path origin `e+1`, on the same decision clock as the existing boards (the eve of the first CPI release).

**Board A (reference): Codex R14B integration.**
- Setup:
  - Origins 2019-02 to 2026-07.
  - h0 is `HARD_BASE` for every model, as on the board; a variant with the model's own h0 is also reported.
  - Year-on-year values are compounded exactly from the realised history.
  - Scored with the board's functions (`add_outcomes_and_compound`, `score_panel`, the circular block bootstrap against `INDEPENDENT_BRIDGE` with block 12, 2000 draws, seed 1409, and CNB report matching).
  - Samples: full, recent targets, recent origins.
- Models compared: `INDEPENDENT_BRIDGE`, `STABLE_PIPELINE_R14B`, `STABLE_LOCAL_CORE_R14B`, `STABLE_LONG_CORE_R14B`, `STABLE_LONG_GAP_R14B`.

**Long span.** Origins 2011-01 to 2026-07, with the model's own h0. The path is scored against the seasonal naive (the mean of the last five same-calendar-month changes, chained) and the year-on-year random walk.

**Board C (continuity).** F1b and F2 from `output/path_step2.csv`, object (b) with h0 set to the print, on common origins.

**Policies.**
- `full`: all 72 predictors, including surveys and expectations. This is the paper model.
- `independent`: hard data only. This is the only version eligible for the independent lane.

## Decision rule (declared before results)

A TVW-QRF path becomes a **path challenger** if, on Board A's full sample, both of the following hold:

1. **Accuracy against the bridge.** Its year-on-year RMSE is below `INDEPENDENT_BRIDGE` at h=6 and h=12. In addition, the bootstrap 95% interval for the MSE difference lies wholly below zero at one or more of h=3, 6 and 12, and no interval lies wholly above zero at any h from 1 to 12.
2. **Recent performance.** On the recent-origins sample, its h=12 RMSE is no more than 10% above the bridge's.

A path that meets the rule is still only a challenger. Replacing a product needs the user's decision and a prospective record. The `full` policy can only challenge the survey-conditioned lines; the `independent` policy is required for the independent lane.

---

## Results

Appended on 12 September 2026. Nothing above the line was changed.

### Notes recorded before the LUCI runs

- **Order of runs.** Three runs were made first without LUCI (`_noluci`) while LUCI was still being located. They are kept as an ablation. The declared Evaluation A and B runs are the `_luci` runs.
- **LUCI source.**
  - Series: CNB ARAD `MLUCLUTXXINDQ` (total, row 15) and `MLUCLUWXXSTDQ` (wages and costs contribution, row 16), snapshot 95 (Monetary Policy Report Summer 2026 baseline, two decimals).
  - Identity check: all six ARAD LUCI series equal the report's chart-data workbook within 0.005, with no period shift.
  - Tidy step: `tools/paper_replication/cnb_luci.py`, which also records hashes and checks.
- **Last observed quarter.**
  - Quarters after 2026Q1 are CNB forecasts and are dropped.
  - In the Summer 2026 report the forecast shading of Chart 2.9 (LUCI) and Chart 2.10 (wages) starts at 2026Q2.
  - Availability rule: a quarter becomes available on the date of the report two quarters later. Report dates come from `data/cnb_mpr_cpi_quarterly.csv`; before those dates, the rule is the 15th of the report month.
  - Values are the current vintage, as for every other input.
- **LUCI transformation.** It is not X-13 adjusted again: CNB WP 7/2024 (p. 4) states that all LUCI inputs are seasonally adjusted. In the paper convention LUCI is interpolated with Chow–Lin.
- **LUCI contains survey data.**
  - CNB WP 7/2024 Table 1 (p. 8) lists 28 LUCI inputs. Three of them are European Commission balances for shortage of labour limiting production, in industry, services and building.
  - Source file: `https://www.cnb.cz/export/sites/cnb/en/economic-research/.galleries/research_publications/cnb_wp/cnbwp_2024_07.pdf`, SHA-256 `137ba853bc3e9da96b6a50ce00f9eaafd865b3423e80fcd16ba9800505e15e28`.
  - The user decided on 12 September that LUCI is used in the `independent` policy as well. That run is therefore not strictly survey-free; the strictly survey-free result is `realtime_independent_noluci`.
- **Panels.**
  - `data/paper_replication/paper_model_panel_20260912_luci/` holds all 72 rows.
  - In the real-time panel the other 70 columns are identical to the no-LUCI panel.
  - In the paper-convention panel, only factor-imputed cells differ, because the two complete LUCI columns enter the imputation factors.

### Exploratory checks (declared before running; they cannot make a challenger)

The no-LUCI paths lost to `INDEPENDENT_BRIDGE` on Board A at every horizon. The losses were concentrated in targets from 2021–2023, while on recent origins the TVW-QRF paths were below the bridge at h9–h12. Two checks follow. Neither is covered by the decision rule above, and acting on either would need a separately declared test and a prospective record.

- **E1 — equal-weight combination.** For each origin and horizon, average the monthly forecasts of `INDEPENDENT_BRIDGE` and TVW3 (`_luci` runs, full and independent policies) 50/50. Use h0 = `HARD_BASE`. Score on Board A with the same functions, bootstrap and checks.
- **E2 — calendar month.** Rerun the same real-time TVW-QRF with the month of the data edge as one extra feature. Within a horizon-specific forest this identifies the target month; everything else is unchanged. Use the full and independent policies with LUCI and score on all boards.

### Evaluation A — comparison with the paper

**Run.** `output/paper_tvwqrf_20260912/paper_full_luci`: paper convention, all 72 predictors, full policy, with the LQR ensemble.

**m/m RMSE on the paper window.** Targets run to 2025-09, starting from 2011-03, 2011-06, 2011-09 and 2011-12; n = 175/172/169/166. Each cell is ours / published.

| Model | h3 | h6 | h9 | h12 |
|---|---|---|---|---|
| QRF median | 0.724 / 0.731 | 0.708 / 0.708 | 0.729 / 0.748 | 0.660 / 0.707 |
| QRF mean | 0.706 / 0.713 | 0.712 / 0.723 | 0.715 / 0.737 | 0.670 / 0.700 |
| TVW1 | 0.706 / 0.694 | 0.707 / 0.688 | 0.718 / 0.732 | 0.663 / 0.687 |
| TVW2 | 0.716 / 0.701 | 0.706 / 0.693 | 0.720 / 0.738 | 0.663 / 0.690 |
| **TVW3** | **0.704 / 0.669** | **0.705 / 0.661** | **0.713 / 0.712** | **0.667 / 0.662** |
| LQR ensemble | 0.726 / 0.739 | 0.725 / 0.748 | 0.749 / 0.765 | 0.636 / 0.659 |
| Random walk | 0.985 / 0.896 | 0.888 / 0.715 | 0.979 / 1.005 | 0.708 / 0.874 |
| AR(3) | 0.733 / 0.710 | 0.723 / 0.740 | 0.738 / 0.753 | 0.746 / 0.765 |
| ARIMA(3,1,3) | 0.744 / 0.716 | 0.712 / 0.736 | 0.728 / 0.787 | 0.748 / 0.772 |

**Declared criterion: met.** TVW3 differs from the published values by +0.035, +0.044, +0.001 and +0.005, all within 0.05. The random walk is the exception, and the gaps have a structure:

- **TVW3's advantage is smaller than published.**
  - At h6 TVW3 is 0.705 against 0.708 for the QRF median; the paper has 0.661 against 0.708.
  - Relative to AR(3), our TVW3 is 0.962/0.975/0.966/0.894; the paper's is 0.942/0.893/0.946/0.865.
  - Diebold–Mariano (HLN), one-sided p-values that TVW3 beats the benchmark:
    - AR(3): 0.273/0.166/0.209/0.000
    - ARIMA: 0.104/0.400/0.261/0.021
    - QRF median: 0.208/0.447/0.239/0.619
    - QRF mean: 0.436/0.100/0.438/0.425
- **Random walk.** Our last-value random walk gives 0.985/0.888/0.979/0.708. No single lag of our target reproduces the published 0.896/0.715/1.005/0.874, so the paper's random walk is defined differently.
- **Bias (forecast minus actual).** TVW3 is −0.04 to −0.07 pp a month; the QRF median is −0.10 to −0.13.
- **Weights.** The mean TVW3 weights at h3 are 0.05/0.23/0.39/0.26/0.07. The weight on the 0.9 quantile rises to 0.10 at h12. Weights often sit on a bound.
- **Tables A4/A5 (y/y at h6, n = 167).** TVW3 ranks first, as in the paper. Ours / published:

  | Model | y/y RMSE |
  |---|---|
  | TVW3 | 2.189 / 1.973 |
  | TVW1 | 2.234 / 2.089 |
  | QRF mean | 2.248 / 2.224 |
  | TVW2 | 2.254 / 2.173 |
  | QRF median | 2.319 / 2.304 |
  | AR(3) | 2.516 / 2.449 |
  | ARIMA | 2.618 / 2.944 |
  | LQR | 2.620 / 2.567 |
  | Random walk | 2.675 / 2.653 |
- **LUCI ablation.** Without LUCI, TVW3 is 0.703/0.710/0.716/0.660, and its y/y at h6 is 2.244.
- **Likely sources of the remaining gap (not tested):**
  - current rather than original vintages;
  - candidate inputs for rows 13, 25, 54, 60–63 and 65–66;
  - factor imputation instead of Chen–Labonne;
  - forest hyperparameters the paper does not report;
  - X-13 failures on rows 8, 48, 49 and 55.

### Evaluation B — path test

**Run.** `output/paper_tvwqrf_20260912/path_scores_luci`, scoring `realtime_full_luci` (FULL) and `realtime_independent_luci` (INDEP, which includes LUCI).

**Board A, y/y RMSE.** Common sample of origins 2019-02 to 2026-07, with h0 = `HARD_BASE`; n = 88/84/81/78/75.

| Model | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|
| INDEPENDENT_BRIDGE | 0.911 | 1.537 | 2.516 | 3.922 | 5.395 |
| STABLE_LONG_GAP_R14B | 0.863 | 1.483 | 2.495 | 4.057 | 5.582 |
| TVW3 FULL | 1.106 | 1.957 | 2.985 | 4.221 | 5.602 |
| QRF mean FULL | 1.084 | 1.924 | 2.964 | 4.204 | 5.526 |
| TVW3 INDEP | 1.098 | 1.973 | 2.974 | 4.326 | 5.678 |
| QRF mean INDEP | 1.089 | 1.966 | 3.014 | 4.356 | 5.660 |

**Decision: no challenger.** TVW3, the QRF median and the QRF mean, under both policies, all fail four of the five checks:

- their RMSE is not below the bridge at h6 or h12;
- no bootstrap interval lies wholly below zero;
- intervals lie wholly above zero at h1–h6.

The one check they pass is the recent-origins h12 check.

Bootstrap MSE differences against the bridge, full sample:

| Model | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|
| TVW3 FULL | 0.39 [0.09, 0.80] | 1.46 [0.09, 3.36] | 2.58 [0.21, 5.45] | 2.44 [−1.22, 7.82] | 2.28 [−3.50, 11.17] |
| TVW3 INDEP | 0.38 [0.09, 0.77] | 1.53 [0.18, 3.37] | 2.51 [0.02, 5.52] | 3.33 [−1.22, 10.52] | 3.14 [−3.76, 14.14] |

With the model's own h0 the paths are worse; TVW3 FULL is 1.426 at h1.

**Where the losses are.** y/y RMSE at h1/3/6/9/12 on subsamples:

- **Recent origins (2024-01 on; n = 30/28/25/22/19).**

  | Model | h1 | h3 | h6 | h9 | h12 |
  |---|---|---|---|---|---|
  | Bridge | 0.371 | 0.569 | 0.678 | 1.005 | 1.347 |
  | STABLE_LOCAL_CORE_R14B | 0.323 | 0.472 | 0.467 | 0.557 | 0.708 |
  | QRF mean FULL | 0.433 | 0.484 | 0.574 | 0.582 | 0.812 |
  | QRF median INDEP | 0.441 | 0.539 | 0.684 | 0.582 | 0.718 |
  | TVW3 FULL | 0.465 | 0.544 | 0.781 | 0.883 | 1.206 |
- **Recent targets (2024-01 on; n = 31).**

  | Model | h1 | h3 | h6 | h9 | h12 |
  |---|---|---|---|---|---|
  | Bridge | 0.365 | 0.547 | 0.748 | 1.182 | 1.892 |
  | TVW3 FULL | 0.491 | 0.575 | 0.831 | 1.365 | 3.504 |

  The TVW3 FULL bias at h12 is +0.91: forecasts made in 2023 stayed high.
- **CNB report quarters (y/y RMSE, all quarters ahead).**
  - All 18 reports: CNB 2.295, bridge 2.362, QRF mean FULL 3.064, TVW3 FULL 3.086.
  - Reports from 2024: CNB 0.372, STABLE_LOCAL_CORE_R14B 0.402, QRF mean FULL 0.462, bridge 0.590, TVW3 FULL 0.818.

**Long span.** Origins from 2011-01, the model's own h0; n = 186 at h1 and 175 at h12.

| Sample | Model | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|---|
| All | TVW3 FULL | 1.043 | 1.606 | 2.271 | 3.024 | 3.799 |
| All | QRF mean FULL | 1.030 | 1.580 | 2.248 | 3.016 | 3.750 |
| All | Seasonal naive | 1.067 | 1.795 | 2.804 | 3.753 | 4.422 |
| All | y/y random walk | 1.132 | 1.890 | 2.902 | 3.849 | 4.664 |
| Targets 2011–2019 | Naive | 0.411 | 0.626 | 0.879 | 1.108 | 1.313 |
| Targets 2011–2019 | TVW3 FULL | 0.480 | 0.752 | 0.976 | 1.166 | 1.307 |
| Targets 2020–2023 | Naive | 1.804 | 3.060 | 4.730 | 6.292 | 7.341 |
| Targets 2020–2023 | TVW3 FULL | 1.848 | 2.870 | 4.097 | 5.452 | 6.423 |
| Targets 2024 on | Naive | 1.100 | 1.815 | 2.952 | 3.956 | 4.648 |
| Targets 2024 on | TVW3 FULL | 0.663 | 0.794 | 1.000 | 1.466 | 3.504 |

The forests' advantage over the naive comes entirely from 2020 onward. In 2011–2019 they are worse than the naive up to h9.

**Board C.** Object (b), h0 = the print, common origins with `path_step2.csv`; n = 88 at h1 and 66 at h12.

| Sample | Model | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|---|
| All | F1b | 0.772 | 1.556 | 2.572 | 4.054 | 5.788 |
| All | TVW3 FULL | 1.011 | 1.961 | 3.004 | 4.317 | 5.963 |
| All | QRF mean FULL | 0.987 | 1.923 | 2.973 | 4.287 | 5.875 |
| All | Naive | 0.937 | 2.095 | 3.652 | 5.278 | 6.990 |
| Origins 2024 on | F1b | 0.320 | 0.503 | 0.618 | 0.882 | 1.200 |
| Origins 2024 on | F2 | 0.313 | 0.503 | 0.514 | 0.507 | 0.508 |
| Origins 2024 on | QRF mean FULL | 0.407 | 0.463 | 0.509 | 0.563 | 0.812 |

**LUCI ablation on Board A.**
- TVW3 FULL without LUCI: 1.075/1.907/2.940/4.201/5.630.
- TVW3 INDEP without LUCI, the strictly survey-free run: 1.110/1.974/2.955/4.317/5.730.

**Scorer note.** Bootstrap intervals for a series identical to the bridge are of order 1e-16, from floating-point noise in recompounding. This cannot affect any comparison above.

### E1 — equal-weight combination (exploratory)

**Run.** `output/paper_tvwqrf_20260912/e1_combination_luci`. As a check of the combination scorer, a bridge weight of 1 reproduces the bridge exactly.

**Full sample.** The combinations fail the declared checks, and the bootstrap marks the loss at h1 as significant (0.10 [0.01, 0.24]).

| Model | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|
| 50/50 with TVW3 FULL | 0.963 | 1.691 | 2.661 | 3.980 | 5.405 |
| 50/50 with TVW3 INDEP | 0.958 | 1.697 | 2.660 | 4.021 | 5.429 |

**Recent origins.**
- The FULL combination scores 0.385/0.508/0.622/0.789/1.043, against the bridge's 0.371/0.569/0.678/1.005/1.347.
- It is significantly better than the bridge at h9 (−0.39 [−0.53, −0.24]) and h12 (−0.73 [−1.18, −0.25]).
- `STABLE_LONG_GAP_R14B` is lower still (0.340/0.514/0.548/0.757/0.927).

**Elsewhere it does worse.**
- Recent targets at h12: 2.518, against the bridge's 1.892.
- CNB report quarters: 2.630 against the bridge's 2.362 over all reports, and 0.633 against 0.590 over reports from 2024.

### E2 — calendar month (exploratory)

**Runs.** `realtime_full_luci_month` and `realtime_independent_luci_month` add one feature, the month of the data edge, to the LUCI runs. They are scored in `path_scores_luci_month`.

**Monthly accuracy.** The month lowers m/m RMSE at every horizon under both policies, by 0.004–0.069.

| m/m RMSE, TVW3 | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|
| FULL, with month | 0.591 | 0.684 | 0.665 | 0.693 | 0.624 |
| FULL, without month | 0.640 | 0.706 | 0.692 | 0.703 | 0.652 |
| INDEP, with month | 0.575 | 0.663 | 0.657 | 0.700 | 0.624 |
| INDEP, without month | 0.639 | 0.694 | 0.682 | 0.709 | 0.646 |

**Board A, full sample (y/y RMSE).** The paths improve but remain behind the bridge.

| Model | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|
| TVW3 FULL + month | 1.055 | 1.897 | 2.874 | 4.162 | 5.520 |
| TVW3 INDEP + month | 1.036 | 1.884 | 2.904 | 4.286 | 5.656 |
| QRF mean FULL + month | 1.041 | 1.879 | 2.912 | 4.217 | 5.583 |
| Bridge | 0.911 | 1.537 | 2.516 | 3.922 | 5.395 |

Every variant still fails the checks.
- Bootstrap losses remain at h1 (TVW3 FULL 0.28 [0.02, 0.65]).
- For the independent policy they also remain at h3 (TVW3 INDEP 1.18 [0.04, 2.71]).

**Recent origins (2024-01 on), y/y RMSE.**

| Model | h1 | h3 | h6 | h9 | h12 |
|---|---|---|---|---|---|
| QRF mean FULL + month | 0.382 | 0.405 | 0.470 | 0.474 | 0.844 |
| QRF median INDEP + month | 0.388 | 0.440 | 0.537 | 0.539 | 0.716 |
| STABLE_LOCAL_CORE_R14B | 0.323 | 0.472 | 0.467 | 0.557 | 0.708 |
| Bridge | 0.371 | 0.569 | 0.678 | 1.005 | 1.347 |

**CNB report quarters.**
- Reports from 2024: QRF mean FULL + month 0.409, CNB 0.372, STABLE_LOCAL_CORE_R14B 0.402, bridge 0.590.
- All reports: 2.990, against the bridge's 2.362 and the CNB's 2.295.

**Long span.** Own h0, 2011–2026.
- TVW3 FULL + month scores 0.965/1.535/2.156/2.971/3.756, against the naive's 1.067/1.795/2.804/3.753/4.422.
- For targets in 2011–2019, the QRF mean FULL + month (0.395/0.640/0.819/1.076/1.281) is now close to the naive (0.411/0.626/0.879/1.108/1.313).

**Board C.**
- TVW3 FULL + month scores 0.950/1.890/2.874/4.244/5.874, against F1b's 0.772/1.556/2.572/4.054/5.788.
- For origins from 2024, the QRF mean FULL + month scores 0.353/0.382/0.432/0.501/0.844, against F1b's 0.320/0.503/0.618/0.882/1.200 and F2's 0.313/0.503/0.514/0.507/0.508.

### Reading

**Replication.** The paper's model replicates as a monthly forecaster. TVW3 is within 0.05 of every published RMSE, and it ranks first on y/y at h6.

**As a path model it fails on the full boards**, with or without LUCI, the month, or averaging with the bridge. Three reasons:
- **Surge.** It loses heavily in the 2021–2023 surge, where tree ensembles cannot forecast monthly changes larger than they have seen.
- **Bias.** Its m/m forecasts are biased down, and that bias compounds along the path.
- **Weighting.** The TVW weighting does not help on the paths; the plain QRF mean is at least as good.

**Seasonality.** The paper's specification carries no calendar information, although its target is not seasonally adjusted. Adding the month (E2) improves every monthly horizon and every board, but not enough: on Board A it is 1.055 at h1 against the bridge's 0.911.

**Since 2024 the picture differs.** Forests with the month are among the best paths:
- recent CNB report quarters: 0.409, against the CNB's 0.372;
- recent origins at h3 and h9: below every R14B line;
- recent origins at h6 and h12: close to the best, `STABLE_LOCAL_CORE_R14B`.

This is post-hoc and rests on 19–30 origins. Combining with the bridge (E1) likewise helps only on recent origins.

**Next step.** A declared test of a regime-robust use, for example a forest on a de-seasonalised, core-only target inside the bridge, plus a prospective record, is the route to a path challenger. Re-tuning the paper's specification on these boards is not.

### Exact-input replication (declared 12 September 2026, before the run)

**Why this run.** The user asked whether our results and variables match the paper's. Three checks prompted a rerun.

- **Sources.** Table A6's note lists "Eurostat, ARAD CNB, CZSO, Refinitiv". ARAD holds series whose labels match Table A6 rows, and several of our inputs were stand-ins or had truncated histories.
- **Weighting step.** Re-estimating the TVW weights on genuine out-of-sample validation windows, from the quantiles saved in `paper_full_luci`, leaves TVW3 unchanged at 0.715/0.701/0.715/0.667. The shortfall against the paper is therefore in the forest's quantiles, not in the weighting.
- **Benchmarks.** The paper's random walk, AR(3) and ARIMA RMSEs are reproduced when a benchmark's information ends h months before the edge.
  - Random walk at lag 2h: 0.881/0.696/0.979/0.845, against the published 0.896/0.715/1.005/0.874.
  - ARIMA: 0.706/0.736/0.766/0.762, against 0.716/0.736/0.787/0.772.
  - Our QRF median already matches the paper at h6 (0.708), so the forests' alignment is kept as it is.

**Inputs.** The panel is `data/paper_replication/paper_model_panel_20260912_exact/`. It is built with `--overrides data/paper_replication/a6_exact_overrides_20260912/overrides_long.csv`, written by `tools/paper_replication/build_exact_overrides.py`, which records download hashes and identity checks.

| Row | Now | Before | Check |
|---|---|---|---|
| 13 building permits | CZSO Table 6 monthly count | Bloomberg `CZGRIDX` | identical in all 295 months |
| 17 nominal unit labour costs | ARAD y/y, SA, from 2002Q1 | Bloomberg level index | a stationary rate fits transform 0 |
| 25 trade balance FOB/FOB | ARAD `SVEVZM4`, from 1993 | local series from 2005 | different series (correlation 0.95) |
| 26 import prices | ARAD m/m, from 2000 | CZSO `CEN0303`, from 2008 | identical from 2008 |
| 43 agricultural PPI y/y | ARAD, from 1996 | CZSO, from 2011 | MAE 0.14 |
| 52 agricultural PPI incl. fish | CZSO, rebuilt before 2010 from ARAD y/y | CZSO from 2010 | rebuild test MAE 0.05 pp |
| 54 PRIBOR 3M, end of month | ARAD `SFTP04M2106` | Bloomberg month-end | MAE 0.0003 |
| 58–59 client loans | ARAD, from 1993 | same codes from 2005 | identical |
| 60 Brent | ARAD | Bloomberg CO1 monthly mean | MAE 0.002 USD |
| 61–63 gas, metals, food | ARAD | Bloomberg | log-change correlation 0.91 / 0.98 / 0.92 |

Imputed predictor-months fall from 1,024 to 554. What remains:
- Rushin, 74 months, which the paper also imputes.
- Rows 50–51, 93 months each: no source before 2010 was found. ARAD's livestock and crop y/y series are different aggregates.
- Rows 65–66, 143 and 146 months: Bloomberg in place of Refinitiv, per the user's decision.

**Run.** `output/paper_tvwqrf_20260912/paper_full_exact`: paper convention, full policy, the LQR ensemble and the `_TMH` benchmarks (information to t−h). Everything else is identical to Evaluation A: forest settings, seed, weight schemes and validation.

**Reading, fixed in advance.**
- **Reproduction criterion (unchanged).** TVW3 must be within 0.05 of the published RMSE at every horizon.
- **Weighting gain (added).** The paper's TVW3 gain over the QRF median is 0.062/0.047/0.036/0.045 at h3/6/9/12. The run reproduces that gain if its own gain is at least half the paper's at both h3 and h6.
- **Benchmarks.** The `_TMH` benchmarks are compared with Table 2. The h-aligned benchmarks remain the fair comparison for the forests.

### Exact-input replication — results

**Run.** `output/paper_tvwqrf_20260912/paper_full_exact`: 682 tasks, 9.5 minutes.

**m/m RMSE on the paper window.** Each cell is ours / published.

| Model | h3 | h6 | h9 | h12 |
|---|---|---|---|---|
| QRF median | 0.723 / 0.731 | 0.707 / 0.708 | 0.733 / 0.748 | 0.653 / 0.707 |
| QRF mean | 0.706 / 0.713 | 0.695 / 0.723 | 0.718 / 0.737 | 0.660 / 0.700 |
| TVW1 | 0.713 / 0.694 | 0.696 / 0.688 | 0.725 / 0.732 | 0.653 / 0.687 |
| TVW2 | 0.719 / 0.701 | 0.698 / 0.693 | 0.727 / 0.738 | 0.651 / 0.690 |
| **TVW3** | **0.707 / 0.669** | **0.695 / 0.661** | **0.714 / 0.712** | **0.650 / 0.662** |
| LQR ensemble | 0.726 / 0.739 | 0.726 / 0.748 | 0.749 / 0.765 | 0.635 / 0.659 |
| Random walk, information to t−h | 0.881 / 0.896 | 0.696 / 0.715 | 0.979 / 1.005 | 0.845 / 0.874 |
| AR(3), information to t−h | 0.717 / 0.710 | 0.735 / 0.740 | 0.743 / 0.753 | 0.749 / 0.765 |
| ARIMA(3,1,3), information to t−h | 0.706 / 0.716 | 0.736 / 0.736 | 0.766 / 0.787 | 0.762 / 0.772 |

**Checks.**
- **Reproduction criterion: met.** TVW3 differs from the published values by +0.038, +0.034, +0.002 and −0.012.
- **Weighting-gain check: not met.**
  - TVW3's gain over the QRF median is 0.017/0.012/0.019/0.003, against the paper's 0.062/0.047/0.036/0.045.
  - Diebold–Mariano one-sided p-values that TVW3 beats the median are 0.24/0.25/0.16/0.42.
- **Benchmarks.** With information to t−h, every Table 2 benchmark is within 0.03 of its published value. The QRF median matches the paper at h3 (−0.008) and h6 (−0.001).

**Against the previous run** (Bloomberg commodities, truncated histories):
- TVW3 improves at h6 (0.705 → 0.695) and h12 (0.667 → 0.650).
- The QRF mean improves at h6 (0.712 → 0.695).

**y/y RMSE at h6 (Tables A4/A5).** TVW3 ranks first, as in the paper. Ours / published:

| Model | y/y RMSE |
|---|---|
| TVW3 | 2.083 / 1.973 (previously 2.189) |
| QRF mean | 2.132 / 2.224 |
| TVW1 | 2.169 / 2.089 |
| TVW2 | 2.241 / 2.173 |
| QRF median | 2.371 / 2.304 |
| AR(3), information to t−h | 2.626 / 2.449 |
| LQR | 2.636 / 2.567 |
| Random walk, information to t−h | 2.679 / 2.653 |
| ARIMA, information to t−h | 2.931 / 2.944 |

**Reading.** With the paper's own sources, the data side is reproduced: the plain forest, the LQR ensemble and all benchmarks land within about 0.03 of the published tables, once the benchmarks use information to t−h. What remains is the size of the TVW improvement, which is about a third of the paper's.

Candidate causes not yet tested:
- the forest hyperparameters and quantile estimator, which the paper does not report;
- X-13 applied to series already published seasonally adjusted (the paper adjusts every series);
- Chen–Labonne imputation for the rows still imputed (Rushin, rows 50–51 and 65–66);
- Refinitiv's futures.
