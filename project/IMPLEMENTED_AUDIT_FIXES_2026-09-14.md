# Czech CPI — implemented audit corrections, 14 September 2026

The September review's scoped corrections are implemented in this working tree. The basket publication hour was explicitly excluded by the user and has not been changed. Original forecast outputs and the original HTML remain intact. No models were promoted, no coefficients were tuned to improve these comparison numbers, and no commit was made.

Read this after `REVIEW_TO_CLAUDE_2026-09-14.md`. That document records the initial findings; this one records what changed. The working checkout is `work/cpi-independent`, branch `codex/independent-cpi-20260909`, with existing Claude/Codex changes on top of HEAD `709d4b3`. The linked Downloads checkout is not updated by this work. Copying only the old commit will omit these corrections.

## What changed

**Transformations now have a fixed definition.** Previously, a nonpositive value anywhere in a series could make its entire history switch from log differences to arithmetic differences. The metadata now explicitly assigns arithmetic differences to the signed concepts in A6 rows 22, 25 and 64. Other log-differenced series require positive adjacent values; invalid pairs remain missing and are reported. Appending an adverse future observation cannot rewrite earlier transformations. Both LUCI and exact-input realtime panels were rebuilt offline: each has 292 months × 72 variables. Against the old builder in the same runtime, every cell is identical. Against the archived CSVs, only machine-precision fuel-component differences remain, at most 1.78×10⁻¹⁵. This fixes a latent timing defect without manufacturing a historical forecasting gain.

**TVW weights now use forecasts generated at earlier origins.** For edge `e` and horizon `h`, the calibration sample consists of twelve monthly origins `e-h-11` through `e-h`. Their target months end at `e`, so every calibration outcome is known at that edge. Each source distribution comes from a forest and preprocessing fitted with that source origin's information. The forest is fitted once per origin/horizon; its mean and quantiles are unchanged. The old internal holdout is removed from `models/paper_tvwqrf.py`.

`recalibrate_saved()` is the shared engine used by the normal runner and the offline correction tool. New runs generate earlier warmup forecasts. Where twelve consecutive mature forecasts/outcomes are unavailable, the model uses declared fixed feasible weights and records `fixed_insufficient_history`. It does not silently select a different twelve-month sample. Insufficient warmup training is recorded and skipped; a requested forecast with insufficient training still fails. Duplicate horizons are rejected before fitting, and benchmarks use the same requested origin/horizon keys as the forest, including when predictor coverage is truncated.

The weight-only replay reuses archived quantiles because the input transformation correction leaves these realtime panels numerically unchanged. Every non-TVW row, including QRF means and medians and the benchmarks, remains exactly unchanged in memory: 14,118 control rows per run. The archive cannot establish historical vintages; causal weight estimation does not cure revised source inputs.

**Surprise scoring now separates three questions.** A large event means `|actual-consensus| >= 0.4 pp`; an alert means `|forecast-consensus| >= 0.2 pp`. Inclusive boundaries use a small numerical tolerance. Existing magnitude detections are retained, and three event fields are added: same-direction large-event hit, opposite-direction large-event alert, and material large-event hit. Material means the model reduces absolute error against consensus by at least 0.15 pp. Precision divides these hits by *all alerts*, using the all-release frame. A model can give a useful forecast on a non-large event, so a false large-event alarm is not automatically a bad forecast.

| Independent nowcast | All alerts | Magnitude large-event hits | Directional hits | Wrong-way large alerts | Material large-event hits | Material hits / all alerts |
|---|---:|---:|---:|---:|---:|---:|
| HARD_BASE | 20 | 7 | 6 | 1 | 5 | 25.0% |
| HARD_HALF | 22 | 7 | 6 | 1 | 5 | 22.7% |
| HARD_FULL | 23 | 7 | 7 | 0 | 6 | 26.1% |

These are the original 90 first releases, February 2019–July 2026, including 23 large surprises. The scoring fix changes no nowcast. Full looks marginally better on these particular counts, but one additional material hit is too little to establish a reliable advantage. The old score columns reproduce to floating-point noise and the existing selection result is unchanged. The separate conditional big-event frame must not be mistaken for all-release precision.

**Import provenance was repaired through reproduction.** The NFC double-counting correction had changed `data/local_adapter.py`, leaving the historical import manifest stale. The unmodified import preparer reproduced all five output CSVs byte-for-byte. Only then was the current manifest regenerated. The old one is retained as `data/research_r14b/imports/manifest.pre_audit_20260914.json`; `output/audit_fixes_20260914/import_manifest_refresh/refresh_receipt.json` binds the old/new hashes and identical outputs. The loader itself is unchanged and continues to reject mismatched source or output hashes. No compatibility bypass was needed.

**The CNB replay presentation now states what it measures.** It describes simulated historical cutoffs and current-vintage data, keeps month-zero object (a) throughout, leaves unavailable comparable forecasts unscored, checks unique keys and consistent origin clocks, and fails on missing or inconsistent forest reconciliation. Errors are computed before display rounding. The rebuilt page has 19 reports and reconciles all 2,184 scored forest points within 7.11×10⁻¹⁵ pp. Three displayed historical MAEs change by only 0.001 due to rounding order. Its forest curves deliberately retain the original archived forecasts, visibly labeled as such; corrected TVW results are in the separate comparison below. The remote Claude page has not been updated.

The paper comparison is also qualified: `_TMH` uses information through `t-h`, while the forest uses `t`. Approximate numerical agreement is not proof of the authors' generating specification. The `yoy6` output mixes six origins and does not measure one origin's six-month path. The separate path scorer constructs paths from one origin correctly. The 83% shock-SSE statement was corrected: 57.3% for the three largest Base errors, or 50.2% for the January-2022/October-2022/January-2023 policy trio.

## What happened to path accuracy

Year-on-year CPI RMSE, percentage points, on exactly matched support with the independent component bridge. These are full-sample results, not selected recent windows. `h` below is the path horizon after the nowcast month; the direct forest horizon is `h+1`.

| Path horizon | Observations | Bridge | TVW3 FULL before | FULL corrected | FULL + month before | FULL + month corrected |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 88 | 0.911 | 1.106 | 1.120 | 1.055 | 1.078 |
| 3 | 84 | 1.537 | 1.957 | 2.014 | 1.897 | 1.955 |
| 6 | 81 | 2.516 | 2.985 | 2.981 | 2.874 | 2.859 |
| 9 | 78 | 3.922 | 4.221 | 4.160 | 4.162 | 4.101 |
| 12 | 75 | 5.395 | 5.602 | 5.515 | 5.520 | 5.431 |

The causal correction slightly worsens short horizons and modestly improves longer ones. It does not rescue the TVW path's promotion case: both versions remain worse than the bridge at these horizons. The unchanged QRF mean remains a separate, useful research candidate. `FULL` includes expectation variables, so it must not be described as an independent forecast.

The initial diagnostic folder `causal_tvw/` reports own coverage only. Use `causal_tvw_common/` as the authoritative comparison: it explicitly reports both `own_paired` and `paired_with_bridge` support, as well as full, recent-origin and recent-target windows. Do not compare an own-window number with a common-window benchmark.

## Verification and handoff files

- `models/paper_tvwqrf.py`, `paper_tvwqrf_experiment.py`: causal calibration and integrated runner.
- `tools/paper_replication/build_paper_panel.py`: fixed transformations.
- `independent_nowcast_experiment.py`, `tools/review/nowcast_vs_consensus_20260914.py`: scoring definitions and saved-forecast rescoring.
- `tools/cnb_rounds/build_cnb_rounds.py`, `tools/cnb_rounds/cnb_rounds_template.html`: corrected historical presentation.
- `tools/review/recalibrate_tvw_20260914.py`: reproducible weight-only replay; pass a new `--output` directory.
- `output/audit_fixes_20260914/`: corrected nowcast scores, transform comparisons, causal path comparisons, actual runner smoke, import replay, and `artifact/cnb_rounds_replayed.html`.
- `work/audit_fixes_20260914/`: before copies, red/green regression logs, independent review evidence and verification receipt.

Fresh parent verification: **224 tests passed** across the affected path/import and forest/scoring suites (132 + 92). Both originally blocked checks now pass: the import fingerprint check and the DuckDB-dependent rejected-resume test. A separate actual 30-tree runner smoke with h1/h3/h13 confirms twelve mature calibration forecasts at the first scored origin, warmup exclusion from scoring, and equal benchmark/model coverage. Independent review also exercised duplicate horizons, shortened predictor history, gaps in historical targets, invalid quantile histories and future-input mutations. The final implementation has no outstanding finding from that scoped review.

Runtime: bundled Python 3.12, existing workspace numerical libraries, plus audit-local DuckDB/requests dependencies. Exact package versions and hashes are in the output manifests. This is not a claim that the original pinned Python 3.14 environment or every historical 500-tree run was reproduced. Before copying to another computer, use the project's dependency specification and run these checks there as well.

## Assessment and next research step

Keep HARD_BASE as the independent operating reference and HARD_HALF/HARD_FULL on the same challenger board. The small differences do not justify switching after every historical comparison. Keep the component bridge and current-core variant for path diagnosis; retain QRF mean plus month as a research comparison. Keep expectation-inclusive forecasts visibly separate. Do not promote TVW3 on the basis of a visually attractive recent CNB panel.

The next substantive path experiment should forecast an economically interpretable core trend plus a mean-reverting residual, with domestic services and imported-goods cost signals tested separately. Compare a small linear/state-space version with a forest for the residual, using nested chronological selection and one fixed origin/horizon scoreboard. A forest trained on inflation levels cannot readily extrapolate beyond the inflation seen in its leaves; adding more trees will not solve that weakness. Policy measurement/start-expiry accounting and recorded input vintages remain more pressing for the next-release product than broad hyperparameter searching.

Those are proposed research steps, not newly tested models in this correction batch. The scoped fixes strengthen correctness; they do not supply an untouched holdout, a prospective nowcast record, a calibrated trading strategy, or proof that the models consistently beat consensus/CNB. Existing reconstructed availability and revised-history limitations remain. Other legacy TVW implementations outside this paper runner were not migrated in this batch and should not silently replace the corrected engine.
