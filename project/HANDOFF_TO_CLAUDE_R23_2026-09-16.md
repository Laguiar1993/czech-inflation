# CZK CPI Forecasting — handoff to Claude

**Start here. Updated 16 September 2026, after R23.** The user wants an independent next-release CPI forecast and a useful monthly inflation path h0–h12. For the path, occasional economically defensible calls that anticipate CNB revisions and materially improve the same-quarter forecast matter; merely differing from CNB or winning a tiny direction comparison does not. Do not put CNB forecasts or inflation-expectations surveys into the independent forecast. Keep optional conditioned comparisons clearly separate.

## Authoritative working copy

```text
C:\Users\luis_\Documents\Codex\2026-09-05\c-users-luis-appdata-local-temp\work\cpi-independent
```

Branch `codex/independent-cpi-20260909`; baseline HEAD `709d4b3449f83c4dbceb353d7d3468d94a62b9aa`. **Substantial work, including R23, is uncommitted. A fresh clone of HEAD will not reproduce this delivery.** Read the live directory, including its `output`, `data`, `tests`, `tools`, `models`, `docs` and review evidence. Preserve the existing working tree. No new commit, reset, merge or broad cleanup was done in R23.

The earlier Downloads `czk-cpi-nowcast_extracted/czk-cpi-nowcast` checkout is not the location of this new round. Root reports R21/R22/R23 and their frozen evidence are the latest entry points; an older `docs/MODELS.md` roster does not cover all subsequent research. Do not silently overwrite the earlier outputs or migrate a legacy engine into the corrected path.

Read in this order:

1. `R23_RESULTS_2026-09-16.md` — model explanation, full/recent scores, CNB lead cases and failures, recommendation.
2. `docs/implementation/R23_COST_GAPS_SPEC_2026-09-16.md` — declared before fitting/scoring; exact estimator, feature and evaluation rules.
3. `work/research_r23_review/REVIEW.md` — independent code/numerical audit and resolved defects.
4. `R22_RESULTS_2026-09-15.md` — why a larger transmission system and its apparent turn gains were not adopted.
5. `R21_RESULTS_2026-09-15.md`, then R20/R19 reports if investigating the operational path or nowcast ledger.

## Current decision and model organization

**R23 is complete as historical research. No candidate is promoted. The nowcast is unchanged.**

| Layer | Keep visible | Interpretation |
|---|---|---|
| Next release | Independent BASE, FULL and HALF | Separate nowcast comparisons; do not infer their quality from path scores |
| Path reference | `STATE_FAST_R15` | Adaptive core trend and mean-reverting cycle |
| Path reference | `STABLE_LOCAL_CORE_R14B` | Current-core reference; relatively good recent accuracy |
| Path reference | `DAMPED_P95_Q001_R16` | Gentle slope reference; useful full/recent compromise |
| Research only | `CORE_FEEDBACK_R21` | Released past core-error correction; small gains, not promoted |
| Closed research batch | R22 joint systems | No promotion; seasonal differences explained most apparent core-turn gains |
| Closed research batch | Seven R23 gap candidates | Common seasonality and quarterly observations; no consistent gain |

Do not confuse nowcast HALF/FULL with `GAP_HALF_R23`: the latter halves the joint **log-core path correction** around FAST. Nor should 'current core' be read as automatic authority to switch the live engine. No all-purpose winner or validated state-dependent selector has been established.

For nowcast background, R21's common 90-release scoreboard had consensus RMSE .3815 versus roughly .414 for FULL/HALF; the 23 large-surprise cases gave FULL 9 material wins and 2 material losses, using .4pp surprise and .15pp error-improvement thresholds. This conditional advantage does not establish profitable all-call trading. R21 reported that October 2022 and January 2023 accounted for 48.49% of FULL squared error, directing attention to energy-policy measurement. These are prior-round results, not a new R23 nowcast audit; inspect that round's tables before using them externally.

## What R23 actually built

Code:

- `data/cost_gaps_r23.py`: source loading, publication masking, five features and provenance.
- `models/cost_gaps_r23.py`: quarterly training, nested selection, constrained/unconstrained fits, band-to-month mapping.
- `tools/research_r23/run.py`: saved-origin replay; verifies FAST state/path equality and preserves noncore accounting.
- `tools/research_r23/lead.py`: immediate-next-CNB report joins, calls, confirmations and first-call episodes.
- `tools/research_r23/evaluate.py`: established scoreboards, fixed-support inference, lead tables and interactive replay.
- `tools/research_r23/charts.py`, `diagnose.py`: post-score display and descriptive exports; not consumed by fitting.
- `tools/research_r23/seal.py`: hashes and verifies delivered evidence and older deliveries.
- `tests/test_cost_gaps_r23.py`: nine tests, including future/unpublished-value poisoning, label maturity, interpolation, signs and CNB joins.

The five features are quarterly ULC relative to core prices less its prior-12-quarter median; negative twelve-month unemployment change; import/core and PPI/core relative levels less prior-36-month medians; and EUR/CZK change since the latest import-price reference month. Core chains are strict and source data are publication-masked before transformation. Quarterly ULC is never interpolated into independent monthly observations. All families share complete-feature quarterly training rows.

There are four quarterly-band targets: realised-minus-original-FAST mean monthly log-core inflation at h1:3,4:6,7:9,10:12. All twelve target prints must have been published before a row becomes eligible. Use last40 eligible quarter-end origins, minimum24; actual outer fits had28–40. Nested validation uses up to8 matured origins, min16 inner training rows, min4 validation origins, inner-origin clocks/scalers and cumulative-error loss at3/6/9/12. Ridge alpha {.1,1,10}; ENET alpha {.01,.1,1}, l1ratio.5. Ties favour stronger shrinkage. Explicit intercept is penalized, not constrained. All parameters and losses are exported.

Seven candidates: intercept-only calibration, positive domestic, positive imported, positive joint, free joint ridge, free joint elastic net, half joint. Positive bounds apply to **band-average coefficients**, not every monthly response: the interpolation has some negative cross-band weights. All four band means are preserved exactly. No clipping or post-score coefficient repair.

## Frozen inputs and evidence

The model does not fetch live sources. Required frozen histories are inside this working copy:

| Location | Purpose |
|---|---|
| `tests/fixtures/cleanup/cnb_core_mm.csv` | CNB monthly core target, Jan2007–Jul2026 |
| `data/paper_replication/a6_inputs_20260912/exact_inputs_long.csv` and `candidate_inputs_long.csv` | Raw sources used by existing adapters; R23 uses A6 series11,17,26,47 |
| `output/independent_path_frozen_inputs.csv` | Monthly EUR/CZK |
| `data/release_calendar_cz_cpi.csv` | Detailed-CPI publication gating |
| `output/research_r15/states.json` | Saved FAST forecasts and origin-specific seasonal states |
| `output/research_r21/path_anchor/native_forecasts.csv` | Four reference paths and frozen headline accounting |
| `data/cnb_mpr_cpi_quarterly.csv` | CNB benchmark vintages, used only for evaluation |
| `output/research_r23/final/manifest.json` | Complete fitting dependencies and output hashes |
| `output/research_r23/final/evaluation/input_manifest.json` | Complete evaluation dependencies and output hashes |

**Canonical results are `output/research_r23/final`, exclusively.** Earlier `full` and `verified` directories predate small provenance corrections and are excluded from the delivery. Their feature values, forecasts and fit records match the final run; do not use their obsolete source manifests. The original R22 canonical directory is `output/research_r22/full`, not its pilot `run`.

Useful R23 fit files: `features.csv`, `feature_provenance.csv`, `feature_clocks.csv`, `band_targets.csv`, `target_available.csv`, `target_audit.csv`, `training.csv`, `inner_validation.csv`, `fits.jsonl`, `coefficient_contributions.csv`, `status.csv`, `native_forecasts.csv`, `forecasts.csv`, `sources.json`.

Useful evaluation files: `primary_rows.csv`, `primary_scoreboard.csv`, `component_scoreboard.csv`, `primary_support_bootstrap.csv`, `leave_one_origin_year_out.csv`, `cnb_summary.csv`, `cnb_leave_one_report_out.csv`, `underlying_core_turn_summary.csv`, `cnb_quarter_projections.csv`, `cnb_lead_pairs.csv`, `cnb_lead_summary.csv`, `cnb_first_call_episodes.csv`, `cnb_lead_coverage.csv`.

Presentation: `output/research_r23/final/evaluation/cnb_rounds_replayed_r23.html`; three PNG/SVG charts in `output/research_r23/charts/`. Post-score case tables and sensitivity summaries are in `output/research_r23/diagnostics/`. The full delivery is sealed by `output/research_r23/DELIVERY_MANIFEST.json`.

## Results that must not be overstated

Joint annual-CPI h12 RMSE: 4.8839 full / .8712 recent; FAST 4.8695 / .8580; gentle slope 4.8101 / .7159; current core 5.3972 / .7077. All models use the same969 primary keys, with75 full and19 recent h12 observations. Full/recent regime differences matter.

At the .30pp report-clock call threshold, joint has21 eligible first-call episodes,19 with actuals,4 material accuracy gains,13 material losses and3 joint successes. FAST has the same4/13 gain/loss record and2 joint successes. Joint's successes are 2022Q3 andQ4 from the same February2022 report, and2025Q2 from August2024. The last example predicted2.2717 versusCNB1.7493; nextCNB2.5670; realised2.3804. FAST already had a useful upward forecast there; a small R23 adjustment crosses the .15pp confirmation boundary. This is not evidence of three independent early turning-point discoveries.

Joint's recent first-call record is1 joint success out of8 matured episodes and5 losses. Full headline matched-CNB RMSE can look better than CNB while MAE is worse; omitting a report can reverse the RMSE advantage. The strict underlying-core turn test finds zero correct exact-band turns for all R23 variants. Do not replace these conclusions with cherry-picked replay charts.

CNB lead test: compare same-quarter projections in the immediately next report; target must remain beyond that next report's calendar quarter. Report clock selects the last archived snapshot strictly before the report day; cutoff clock uses the whole stated CNB cutoff day. Calls>=.30pp with .50 sensitivity; confirmation requires same direction and>=.15pp less distance to our original forecast. Eventual material accuracy gain also requires>=.15pp smaller absolute error. Joint success requires both. Keep missing comparisons and unmatured outcomes, and report direction-only agreement separately. Episode deduplication removes consecutive same-sign repeat calls for each target; adjacent quarters and models remain dependent.

## Correctness and reproduction

Review resolved a small-revision direction-label bug, a masked-interior-release provenance exception and overbroad PPI provenance. Forecasts did not change. Independent probes reconstructed all fits, target gates, selected minima, coefficients, monthly contributions, exact noncore/h0 parity and CNB denominator logic. **25 R23/R22/R21 targeted tests passed.** No unresolved implementation blocker was found within this scope; that is not validation of historical source vintages or a live edge.

From the working copy, PowerShell:

```powershell
$env:PYTHONPATH='../pythonlibs'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython -m pytest tests/test_cost_gaps_r23.py tests/test_transmission_r22.py tests/test_released_error_research_r21.py tests/test_policy_anchor_r21.py -q -p no:cacheprovider
& $cpiPython work/research_r23_review/probes.py
& $cpiPython work/research_r23_review/output_checks.py output/research_r23/final
& $cpiPython work/research_r23_review/evaluation_checks.py output/research_r23/final
```

For a new reproduction directory (it must not already exist):

```powershell
& $cpiPython -m tools.research_r23.run --output output/research_r23/claude_replay
& $cpiPython -m tools.research_r23.evaluate --root output/research_r23/claude_replay
```

This reuses the saved earlier-round baselines and target/source snapshots; it is an exact replay of the declared R23 layer, not an end-to-end rebuild of every earlier research round. Verify those dependencies with their manifests before trusting them. The model runtime used Python3.12.14, numpy2.5.2, pandas3.0.1, scipy1.18.1 and scikit-learn1.9.0; verify the delivery manifest for the authoritative recorded versions. The existing sibling `../pythonlibs` is part of this environment. Relocation requires installing dependencies and resolving existing path adapters; don't promise that a clone alone is turnkey. Preserve original manifests and create a separate relocation manifest rather than rewriting historical evidence.

## Questions and next research for Claude

1. **Challenge the information mapping.** Are whole-economy ULC and broad import/PPI relative-price gaps informative about CNB core, or should we build properly weighted domestic services/imported goods measurements first? Specify how excluded/regulated categories are reconciled; don't equate equal-weight proxies with official core subdivisions.
2. **Test faster learning without label leakage.** R23's common twelve-month maturity delays even h1–3 learning. Declare a band-specific release-maturity variant with partial pooling across bands, then nested chronological selection. Compare on the frozen origin/horizon support and keep this R23 baseline intact. It has not yet been run.
3. **Separate wages from productivity if the data support it.** Confirm release timing, revisions and definition before building a mixed-frequency state-space measurement layer. No fake monthly interpolation or repeated quarterly observations counted as independent labour data.
4. **Audit why CNB disagreements fail.** Use all calls, not just successful ones. Separate core pressure, noncore/energy policy, mechanical annual base effects and later unexpected news using predeclared rules. Do not remove wars/shocks from the scoreboard after seeing errors.
5. **Improve the alert test without optimizing three hits.** Joint success is intentionally strict and sensitive to overshoots; retain continuous revision-distance and absolute-error gains alongside thresholds. Cluster by report/event and target overlap. Freeze a prospective disagreement ledger before the next report; record abstentions and false calls. A selective overlay must be learned only from matured historical calls and validated chronologically, not hand-picked from these cases.
6. **Prioritize nowcast measurement independently.** Energy-policy start/expiry and tariff exposure, genuine input vintages and timely food observations remain more compelling than a large nowcast hyperparameter search. R23 does not settle those workstreams.

The next research should aim for a few better-founded, timely disagreement calls, not force resemblance to the CNB line. Preserve the independent economic forecast, use CNB as an external benchmark, and explain uncertainty and scenarios. There is still no untouched holdout, prospective nowcast/path record, calibrated rates position-sizing rule or proof of consistent superiority.
