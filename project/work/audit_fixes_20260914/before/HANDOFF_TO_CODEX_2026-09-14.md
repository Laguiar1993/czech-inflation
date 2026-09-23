# Czech CPI nowcasts and inflation paths — status and review for Codex

Date: 14 September 2026
Prepared by: Claude (Fable 5.1)
Scope: Czech only — the h0 nowcasts, the monthly inflation paths, their evaluation against the CNB, the CNB WP 9/2026 lane, and the Bloomberg data inventory. Poland is a separate project and is not covered here.

## 0. Read this first

**Worktrees.** Two linked worktrees of one repository, both with uncommitted work. Do not reset, clean or stash either.

| Worktree | Branch, HEAD | Uncommitted | Holds |
|---|---|---|---|
| `C:\Users\luis_\Documents\Codex\2026-09-05\c-users-luis-appdata-local-temp\work\cpi-independent` (this checkout) | `codex/independent-cpi-20260909`, `709d4b3` (9 Sep) | 118 paths | Codex R9–R14B lanes (HARD_* nowcast, INDEPENDENT_BRIDGE, R14B challengers), Codex's 10–11 Sep Bloomberg pull, Claude's 12–14 Sep work (below) |
| `C:\Users\luis_\Downloads\czk-cpi-nowcast_extracted\czk-cpi-nowcast` | `codex-p0`, `47c0e6f` (8 Sep) | 29 paths (PATH_SPEC_v5 step-5 files, `models/gap_model.py`; byte-identical to what Codex committed in `8eeda3b`, except `gap_model.py` which predates `3efc718`) | The frozen trio (BASE_RIDGE / PAST_FULL / PAST_HALF), `path_live.py` (F1b engine, F2 trend line, E7 target line), the live logs, RUNBOOK |

`codex-p0` is the merge base of `codex/independent-cpi-20260909` and has no commits of its own.

**What Claude added since your 11 September handoff** (all untracked or new files in this checkout; nothing tracked was edited except the row-38 transform fix in `paper_replication_experiment.py` on 12 Sep, which you had already noted):

| Date | Item | Files |
|---|---|---|
| 12 Sep | Table A6 audit: candidates validated against official ECFIN/Eurostat/CZSO sources; exact and candidate input panels; PPI loader bug found (rows 46–48 read a sub-division row) | `docs/implementation/CNB_WP9_A6_AUDIT_2026-09-12.md`, `tools/paper_replication/`, `data/paper_replication/a6_inputs_20260912/`, `output/cnb_paper_a6_audit_20260912/`, `output/cnb_paper_candidate_validation_20260912/`, tests `test_a6_audit.py`, `test_official_sources.py`, `test_bloomberg_candidate_import.py`, `test_candidate_validation.py`, `test_exact_overrides.py` |
| 12 Sep | LUCI located on CNB ARAD (`MLUCLUTXXINDQ`, `MLUCLUWXXSTDQ`, snapshot 95) | `tools/paper_replication/cnb_luci.py`, `data/paper_replication/official_cnb_luci_20260912/`, `tests/test_cnb_luci.py` |
| 12 Sep | TVW-QRF replication and path test (spec declared before the runs; results appended) | `models/paper_tvwqrf.py`, `paper_tvwqrf_experiment.py`, `paper_tvwqrf_path.py`, `paper_tvwqrf_combination.py`, `docs/implementation/PAPER_TVWQRF_SPEC_2026-09-12.md`, `output/paper_tvwqrf_20260912/`, `tests/test_paper_tvwqrf.py` |
| 12 Sep | Per-horizon evaluation against the CNB's quarterly forecasts | `docs/implementation/CNB_HORIZON_EVALUATION_2026-09-12.md` |
| 12 Sep | Bloomberg probe rounds 1–16 and the strict-equality tool; data-source map | `tools/market_data/probe_bloomberg_candidates.py`, `compare_bloomberg_exactness.py`, `data/market_snapshots/20260912_bloomberg_probe*`, `data/bloomberg_catalog/`, `output/bloomberg_probe_comparison_20260912/`, `docs/implementation/DATA_SOURCES_BLOOMBERG_MAP_2026-09-12.md` |
| 12 Sep | Frozen CNB daily EUR/CZK fixings 2018–2026 (kept when the weekly lane was removed) | `data/cnb_daily_eur_fixings_20260912/` |
| 13 Sep | Per-model Bloomberg input inventory (153 inputs, 61 new strict tests) | `tools/market_data/compare_bloomberg_model_inputs.py`, `output/bloomberg_model_inputs_20260913/` |
| 13 Sep | Weekly h0 nowcast lane built on 12 Sep and removed the next day at the user's request (an archive of the 27 deleted files is outside the repo); nothing else was touched | — |
| 14 Sep | "CNB Rounds Replayed" page builder moved into the repo; rebuilt output is byte-identical to the published artifact | `tools/cnb_rounds/build_cnb_rounds.py`, `tools/cnb_rounds/cnb_rounds_template.html`, `output/cnb_rounds_replayed_20260912/cnb_rounds_replayed.html` |
| 14 Sep | This document and the review in section 5 | `HANDOFF_TO_CODEX_2026-09-14.md` |

Tracked files modified in the working tree (`git diff --stat`): `.gitattributes`, `README.md`, `data/local_adapter.py`, `docs/implementation/R14_PAPERS_AND_BENCHMARKS.md`, `models/bbim_lite.py` — these are your 9–11 Sep edits, untouched by Claude.

**Published page.** "CNB Rounds Replayed", https://claude.ai/code/artifact/516b30d5-bc5f-4f72-a52b-874b0a36cc27 — one panel per CNB Monetary Policy Report since Winter 2022 (19 reports), each showing the CNB's quarterly forecast (red), our model paths from the latest run before the report (component bridge, the four R14B bridge variants, F1b, F2, the CNB-paper forests with our nowcast at month 0) and realised inflation, with the average absolute quarterly miss per model. The user declined 2018–2021 rounds. Rebuild with `python tools/cnb_rounds/build_cnb_rounds.py` (needs the R14B integration outputs, `output/path_step2.csv`, the forest runs and `data/cnb_mpr_cpi_quarterly.csv`; the August 2026 y/y of 1.9 % is hard-coded from CZSO's 10 Sep release because the frozen inputs end in July). Its "How these panels are built" section documents the pairing rule and the scoring; read it before quoting a panel.

## 1. Map of what exists

**Nowcasts (h0, the next first release).** One model family, two lineages that reconcile:
- `codex-p0`: the frozen trio BASE_RIDGE / PAST_FULL / PAST_HALF (v2.7.1, 7 Sep) with the CNB survey (FMIE), household expectations and ESI in the core frame; live logging via `cz_struct.py --live`; bands V1 flagged uncalibrated.
- this checkout: `forecast_independent.py` HARD_BASE / HARD_HALF / HARD_FULL (no surveys), SENTIMENT_* (adds ESI), LEGACY_* (the trio's frame re-scored). LEGACY_BASE scores 0.420 all / 0.217 since 2024, identical to the trio's release-eve board, so both lineages sit on one scoreboard (`output/independent_nowcast_scores.csv`).

**Paths (h1–h12 monthly, scored as 12-month inflation).**
- this checkout: INDEPENDENT_BRIDGE (reference; h0 = HARD_BASE), R14B challengers STABLE_PIPELINE / STABLE_LOCAL_CORE / STABLE_LONG_CORE / STABLE_LONG_GAP, the direct roster TARGET_ML / TARGET_FX_ML / TARGET_U_FX_ML / BVAR_U_FX / RF_U_FX / NAIVE (`output/independent_path_summary.csv`), FUEL_ECM_R14 as a near-term component challenger.
- `codex-p0`: `path_live.py` product — F1b component engine (publishable under PATH_SPEC_v2), F2 trend-and-gap with FMIE as a measurement (second line), E7 survey-free target-anchored line (flagged), CNB quarterly comparison printed with 0.5 pp flags; step-3/4/5 research (survey-free trend, gap model).
- research: CNB WP 9/2026 TVW-QRF on the 72-variable A6 panel (replicates the paper as a monthly forecaster; not a path challenger).

**Benchmarks.** Bloomberg consensus at h0 (never an input); seasonal-naive path, y/y random walk, FMIE one-year, and the CNB's quarterly report paths (`data/cnb_mpr_cpi_quarterly.csv`, report and cut-off dates) for the paths.

## 2. Nowcasts — where they stand

Release-eve clock, 90 first releases, February 2019 – July 2026, m/m percentage points (`output/independent_nowcast_scores.csv`; frames recomputed on 14 Sep from `output/independent_nowcast_releases.csv`).

| Model | All (90) | 2019–21 (35) | 2022–23 (24) | 2024+ (31) | Flash era 2025+ (19) | Big surprises MAE (23) |
|---|---|---|---|---|---|---|
| HARD_BASE | 0.418 | 0.278 | 0.693 | 0.219 | 0.173 | 0.485 |
| HARD_HALF | 0.414 | 0.280 | 0.682 | 0.220 | 0.166 | 0.479 |
| HARD_FULL | 0.414 | 0.288 | 0.675 | 0.225 | 0.164 | 0.476 |
| LEGACY_BASE (= frozen trio reference) | 0.420 | 0.292 | 0.690 | 0.217 | 0.170 | 0.506 |
| Bloomberg consensus | 0.382 | 0.247 | 0.618 | 0.241 | 0.195 | 0.578 |

Reading:
- The model loses to the consensus over the whole sample because of the 2022–23 energy-policy months (October 2022 missed by +2.57 pp, January 2023 by −1.13 pp; the three shock months are about 83 % of squared error). Since 2024 it beats the consensus in every frame, and in the flash era by 11 %.
- HALF and FULL are indistinguishable from BASE on accuracy; FULL keeps a small edge on big surprises. Surveys add nothing at h0 (HARD ≈ LEGACY).
- Diebold–Mariano against the consensus is not significant in either direction (t +1.3 full sample, −0.8 since 2024).
- **Consensus-shrink evidence (recomputed 14 Sep, script `tools/review/nowcast_vs_consensus_20260914.py` — see section 5).** The model's deviation from the consensus predicts the surprise since 2024 (slope 0.58, t 3.5, R² 0.30) but not over the full sample (0.23, t 1.4). A strictly out-of-sample rule, consensus + b̂ × (model − consensus) with b̂ estimated only on past months from February 2021, scores: HARD_BASE 0.429 vs consensus 0.424 overall, 0.227 vs 0.241 since 2024; HARD_FULL 0.421 vs 0.424 overall, 0.214 vs 0.241 since 2024, big-surprise MAE 0.548 vs 0.600. This is the only h0 construction that is at least level with the consensus overall; it is not in any product and needs a declared spec and a prospective record before use.

**Operator state (`codex-p0` RUNBOOK "September 2026 checklist").** Steps 2 and 3 are not done as of 14 Sep: `data/release_calendar_cz_cpi.csv` has no 2026-09 row (the September call would log with `release_stage = unknown`), and `output/struct_shadow_log.csv` has no rows after the retrospective August calls of 6 Sep (BASE_RIDGE +0.273 / PAST_FULL +0.319 / PAST_HALF +0.296 against the August flash of +0.3, printed 4 Sep — retrospective, not first-release evidence). The independent lane's `independent_nowcast_forecasts.csv` ends at 2026-07. **No prospective row exists yet in either lineage.** The first clean prospective call is the 30 September month-end call and the October-flash eve.

## 3. Paths — where they stand

**Board A** (this checkout, `output/research_r14b/integration/summary.csv`; origins 2019-02 to 2026-07, h0 = HARD_BASE, y/y RMSE on common origins, n = 88/84/81/78/75):

| Path | h1 | h3 | h6 | h9 | h12 | h12, origins 2024+ (19) | h12, targets 2024+ (31) |
|---|---|---|---|---|---|---|---|
| INDEPENDENT_BRIDGE | 0.911 | 1.537 | 2.516 | 3.922 | 5.395 | 1.347 | 1.892 |
| STABLE_PIPELINE_R14B | 0.905 | 1.532 | 2.525 | 3.949 | 5.418 | 1.210 | 1.686 |
| STABLE_LOCAL_CORE_R14B | 0.869 | 1.537 | 2.624 | 4.006 | 5.397 | **0.708** | 2.619 |
| STABLE_LONG_CORE_R14B | 0.868 | 1.505 | 2.513 | 4.031 | 5.478 | 0.906 | 2.208 |
| STABLE_LONG_GAP_R14B | 0.863 | 1.483 | 2.495 | 4.057 | 5.582 | 0.927 | 2.729 |
| TVW3 FULL (CNB paper, with nowcast) | 1.106 | 1.957 | 2.985 | 4.221 | 5.602 | 1.206 | 3.504 |

Bias on the full sample runs from −0.1 (h1) to −1.0/−1.8 (h12) for every line: the paths under-forecast, and the surge years drive it. Your own R14 reading stands: STABLE_LOCAL_CORE is a regime bet (excellent on origins since 2024, weak on targets since 2024 because it carried the 2023 core trend forward); no combined path beats the bridge across regimes.

**Direct roster** (`output/independent_path_summary.csv`, origins 2019+, y/y RMSE h1/h3/h6/h12; bias at h12 in brackets): BVAR_U_FX 0.89 / 1.87 / 3.15 / 6.37 (−3.2); RF_U_FX 0.91 / 1.74 / 2.79 / 5.73 (−1.2); TARGET_ML 0.90 / 1.92 / 3.34 / 6.74 (−1.8); naive 0.99 / 2.09 / 3.61 / 6.72 (−1.4); the stored F1b reference 0.84 / 1.58 / 2.62 / 5.79 (−2.4). Since 2008 (origins to Jan 2019) TARGET_ML beats the naive only at h6–h12 (0.88 / 1.30 vs 0.91 / 1.46). None of these is a product; the bridge family is.

**Against the CNB, by horizon** (`docs/implementation/CNB_HORIZON_EVALUATION_2026-09-12.md`; 18 reports Winter 2022 – Spring 2026, our latest path before each report, quarterly averages of monthly y/y, RMSE all / 2024+):

| Horizon | CNB | Bridge | Bridge · current core |
|---|---|---|---|
| 1Q | 0.95 / 0.28 | 1.54 / 0.30 | 1.50 / 0.21 |
| 2Q | 2.07 / 0.37 | 1.96 / 0.43 | 2.02 / 0.35 |
| 3Q | 2.51 / 0.42 | 2.24 / 0.64 | 2.53 / 0.48 |
| 4Q | 3.24 / 0.43 | 3.47 / 0.93 | 3.15 / 0.55 |

- We saw the 2022 surge earlier than the CNB (Winter 2022 report: bridge 12.1 / 11.1 / 10.1 for 2Q–4Q22 against the CNB's 9.5 / 8.2 / 6.6; actual 15.8 / 17.6 / 15.7). The CNB was closer in 11 of 12 windows from the 2023 reports at 2–4Q (it saw the disinflation). Since 2024 we match the CNB one to two quarters out and it wins at three to four. No difference is significant (|DM t| ≤ 1.13, n = 15–18).
- Information sets are not identical: our path is made 10–17 days before the CNB cut-off for some reports and 10–19 days after it for others (one more CPI print). The table in the doc lists every pairing.
- Formatting rule from the user: compare with the CNB by quarters-ahead on quarterly averages, never against a single monthly print; and only with the path we had already published when the report came out.

**Perfect-component diagnostic at h12** (bridge 5.395): a perfect core block gives 3.31, perfect food 4.30, perfect administered prices 4.87. The level of core beyond six months is the problem, not the components' noise.

**TVW-QRF lane verdict** (`docs/implementation/PAPER_TVWQRF_SPEC_2026-09-12.md`): with the paper's own sources the forest replicates as a monthly forecaster — TVW3 m/m RMSE 0.707 / 0.695 / 0.714 / 0.650 at h3/6/9/12 against the published 0.669 / 0.661 / 0.712 / 0.662, all benchmarks within 0.03 once they use information to t−h — but the TVW weighting gain is a third of the paper's, and as a path it fails the declared rule on every board (loses the 2021–23 surge, m/m bias down). Adding the calendar month (the paper's spec has none) helps every horizon but not enough. Since 2024 the forests with the month are among the best lines (CNB report quarters 0.409 vs CNB 0.372 vs bridge 0.590) — post-hoc, 19–30 origins. User decisions on record: LUCI and the Rushin index stay in the forest even though the CNB re-estimates their histories; "we can't be cheating — the whole goal is to predict going forward, without knowing the data".

**`path_live` product state** (`codex-p0`): last logged origin 2026-09 (8 Sep): F1b Q4-26 2.44, Q1-27 3.02, Q2-27 3.04, Q3-27 3.31 y/y; trend line about 1.8 / 2.3 / 2.5 / 2.7; CNB Summer 2026 2.39 / 2.83 / 2.42 / 2.50. Not re-run after the August flash (+0.3 m/m, 1.9 % y/y).

## 4. Bloomberg inventory (data, brief)

`docs/implementation/DATA_SOURCES_BLOOMBERG_MAP_2026-09-12.md` and `output/bloomberg_model_inputs_20260913/model_input_inventory.csv` list every input of every model with a strict verdict (exact / extremely similar / similar / different) on the model's own transform.
- Exact: CNB core and regulated m/m (`CZCIXM`, `CZCIRM`), `EURCZK CNB Curncy` = the CNB fixing (every day since 2010), published CPI y/y and levels, ECFIN surveys, Eurostat unemployment and PPI, EC Oil Bulletin pump prices, 43 of the 72 A6 rows.
- Extremely similar (one-decimal rounding): CZSO m/m series (the models difference the 2015 = 100 index, Bloomberg publishes one decimal), PRIBOR, repo, M3, Brent, Rushin, import prices.
- Stay CNB/ARAD/CZSO: FMIE, LUCI, CNB forecast paths, both REERs, farm-gate prices, services groups, LFS unemployment vintages.
- Traps recorded: `EURCZKF` is a 6M forward; `CZCIFM` is not the CZSO fuel item; `CPEXCZM` is not CNB core; `czso.wages_headline` differs from `CZNWYOY` by up to 2 pp; Bloomberg holds latest vintages only.

## 5. Review: mistakes, risks, and what checked out

*(Filled in below from the 14 September audits.)*

## 6. Recommended next steps (ranked)

*(Filled in below.)*

## 7. File index

*(Filled in below.)*
