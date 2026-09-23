# Independent R23 review — 16 September 2026

**Assessment: ready for historical research delivery; no unresolved correctness blocker found within this review scope.** This is not approval to promote a live model. I reviewed the working-tree R23 additions against `docs/implementation/R23_COST_GAPS_SPEC_2026-09-16.md`, with repository HEAD `709d4b3449f83c4dbceb353d7d3468d94a62b9aa`. The canonical numeric artifacts reviewed are exclusively `output/research_r23/final`; earlier `full` and `verified` directories are superseded.

The review covered `data/cost_gaps_r23.py`, `models/cost_gaps_r23.py`, `tools/research_r23/run.py`, `tools/research_r23/lead.py`, `tools/research_r23/evaluate.py`, the targeted tests, and the relevant existing accounting/CNB-evaluation helpers. I made no production-model or source-data edits. Review probes live beside this report.

## Findings resolved during review

1. **CNB direction agreement incorrectly required a material revision.** A same-direction +0.10pp CNB revision was classified as disagreement. The direction flag now measures sign separately; confirmation still requires at least 0.15pp less distance to the frozen model forecast. Small revisions and overshoots are tested independently.
2. **Masked interior releases could abort feature creation.** A delayed unpublished observation was correctly masked, but provenance still treated its future date as used and raised an exception. Missing required history now emits missing-feature status and permits the declared FAST fallback.
3. **PPI provenance included irrelevant history.** Published PPI levels use the current plus preceding 36 months, but their audit included every earlier PPI release. An irrelevant delayed old release could therefore cause an exception. Provenance now uses the 37-month PPI window; the import chain and core level correctly retain their required prefixes. The fixture now gives each source its own publication-date Series, preventing a source-specific test from accidentally corrupting core dates too.

All three fixes have fresh regression/probe evidence. No economic specification, candidate set, threshold, or regularization grid was changed in response to forecast results.

## Verification evidence

- **Targeted suite:** 9 tests passed independently after the fixes.
- **Features:** all 199 archived R15 origins constructed without failure; 185 had all five features, from March 2011 through July 2026. The first 14 fail closed for insufficient history. The audit uses source publication masks before transforms, quarterly ULC without interpolation, strict monthly chains, complete consecutive gap windows, and exact unemployment/FX endpoints.
- **Targets and selection:** all twelve target observations and publication dates are required. Training origins are quarter ends, their full twelve-month target ends strictly before the decision origin, and all target releases precede its clock. Outer fits use 24–40 rows; inner folds use their own clocks/scalers and fully matured labels. The saved selections match the minimum declared cumulative-loss score and stronger-regularization tie rule.
- **Interpolation:** 100 independent random four-band vectors retained all four three-month means and cumulative corrections at h3/6/9/12 within numerical precision. Constant band inputs remain constant.
- **Final fits and accounting:** all 90 origins, 11 models and 13 horizons are present (12,870 native rows). Every R23 path preserves h0, all noncore values/contributions and all weights exactly. Saved coefficients reconstruct their band contributions and predictions, then reconstruct the exported monthly log-core corrections. Positive-family predictor coefficients meet the bounds; the half path is exactly half the joint correction.
- **Fixed support and integrity:** all 206 entries across the final run/evaluation manifests matched their SHA-256 digests. Each of the 11 models retains the original 969 primary origin/horizon keys.
- **CNB lead tables:** 7,084 rows equal the entire model-projection table times both predeclared thresholds, including unavailable forecasts and unmatured outcomes. All 176 summary rows and 1,360 first-episode export rows reconcile independently. Checks cover the immediate next report, identical target quarter strictly beyond that next report's calendar quarter, sign agreement, distance confirmation, material eventual gain/loss, missing-pair coverage, and episode resets.

## Interpretation boundaries

The **1,360 exported episode rows are not 1,360 independent successful calls**. They span eleven models, both clocks and both thresholds, and include episodes without an eligible next-report comparison. Use `revision_eligible` for revision evidence and `mature_calls` for eventual accuracy. `unconfirmed_calls` is measured among revision-eligible calls; `calls_without_eligible_revision` separately reports calls that cannot be evaluated. `all_calls` retains both. Episodes keep the first call of a same-direction consecutive-report streak for each model, clock, threshold and target quarter. A non-call, absent report observation or sign change resets the streak. Adjacent target quarters, thresholds, clocks and model variants can still share the same underlying inflation event.

The lead exercise compares **quarterly headline-inflation forecasts** with later CNB headline-forecast revisions. It does not model CNB core inflation turning points, identify what news CNB learned, establish causal anticipation, or establish a rates-trading strategy. CNB revision confirmation and eventual model accuracy remain separate outcomes. The independent models contain no CNB forecast as an input or selector.

Nonnegative restrictions apply to the **four band-average predictor coefficients**. The interpolation has some negative cross-band weights (minimum approximately -0.19453), so it does not promise a nonnegative response in every individual month. Contributions are predictive accounting, not identified economic shocks.

The research retains current-vintage source histories, reconstructed availability assumptions, overlapping forecast errors, limited effective quarterly observations and accumulated research-selection exposure. This review checked implementation against the frozen files and specification; it did not validate genuine historical source vintages, external release calendars, visual rendering, or live out-of-sample superiority. Prior R15–R16 source/output digests and other inputs carried into the canonical manifests were checked; this is not an independent pre/post snapshot of every R17–R22 file.

## Reproduce

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH='../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m pytest tests/test_cost_gaps_r23.py -q -p no:cacheprovider
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r23_review/probes.py
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r23_review/output_checks.py output/research_r23/final
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r23_review/evaluation_checks.py output/research_r23/final
```
