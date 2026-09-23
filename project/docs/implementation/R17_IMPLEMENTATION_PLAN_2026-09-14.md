# R17 component forecasting and coherent path implementation plan

> For agentic workers: use subagent-driven-development, with an independent specification/numerical review before final claims. The user approved all proposed work with "Do it all"; routine implementation and research choices proceed without another permission round.

**Goal:** implement and measure the approved component, core-state, monthly-transmission, energy-scenario and chronological-combination improvements, preserving the independent release nowcast and all earlier experiments.

**Architecture:** new isolated R17 modules and outputs replace one block at a time in the frozen R15 FAST component system. Fixed current-core, FAST, pipeline and gentle R16 slope controls retain their exact forecasts. Candidate inputs, equations and grids are declared before each full fit. Current-vintage/reconstructed availability is disclosed; historical policy knowledge and household exposure are never inferred from realised CPI.

**Tech stack:** local Python/numpy/pandas/scipy/sklearn, existing frozen inputs and numerical scoring contracts; original self-contained CNB replay template. Existing isolated checkout is retained. No mass cleanup, old-file rewrites or blanket commit of unrelated WIP.

## Contracts applying to every task

- The 90 monthly outer origins remain February2019–July2026, h0..12. HARD_BASE h0 and all untouched component values/contributions/weights are bit-identical. New unavailable information is recorded rather than reconstructed from future outcomes.
- All final headline annual paths compound their own origin's monthly rates. Every forecast identifies its source clock and target month. Older h0/core estimates used in training are saved own-origin estimates; no reconstructed residual may use a later model fit.
- All R15/R16 source/input/output hashes continue to verify. Research source and parameter declarations, fits, candidates, outcomes and evaluation receipts are separate.
- Primary control-calendar scores use the original R16 common support, with failures explicitly visible. Also report each genuinely finite common comparison, dates lost, and paired baselines. No model wins by silently shrinking the sample.
- Full history, origins2024+, targets2024+, h1..12, monthly/cumulative component and annual headline scores; unchanged CNB report/cutoff clocks and material absolute-error threshold0.15pp. Twelve-calendar-origin block uncertainty and every-report omission sensitivity; no removal of war episodes from main scores.
- No survey, expectations or confidence series is added to main forecasts. Futures are origin-known scenario inputs, not observed future prices or a complete delivery curve.

## Task 1 — locate remaining component errors and usable inputs

Create `tools/review/r17_component_attribution.py`, `tests/test_r17_component_attribution.py`, outputs `output/research_r17/attribution/`. Use R16 FAST monthly forecasts and R14B actual component targets. For each block b and each origin, form `oracle_mm = forecast_mm + weight_b*(actual_b-forecast_b)` (wedge already in headline units). Recompound all12 target-window months, retaining h0 and known history. Score on original annual-headline dates, and require every replacement month; show missing component outcomes separately. Keep joint-replacement effects and cross terms separate from single-block effects.

- [ ] Test a two-block fixture where replacing one block worsens headline accuracy because errors offset; test missing-month propagation, h0 retention, annual-window indexing and changing origin weights.
- [ ] Replay FAST/full/recent and compare against preserved current-core evidence; quantify each block's bias, cumulative error and actual event contributions.
- [ ] Audit food source/release panels, monthly category definitions, h0 core outputs and frozen Bloomberg metadata. Produce file/column/units/availability map before model fitting.
- [ ] Source auditor writes `work/research_r17_policy/` official-source evidence and candidate policy/exposure rows. Existing `models/energy_ledger.py` stays immutable.

## Task 2 — asymmetric food cost transmission

Create `models/food_transmission_r17.py`, `food_transmission_experiment_r17.py`, `tests/test_food_transmission_r17.py`, and a separate frozen child specification under `docs/implementation/`. Use existing agri4/foodPPI/food levels and endpoint-gated monthly log changes; do not backfill with unknown future levels.

Compare a small own-food model, a symmetric upstream-cost model, and an asymmetric model that separates positive and negative cost changes. Smooth lag summaries cover months1..3 and4..6, with penalties shrinking upstream effects toward zero. Include explicit persistence and fixed half-correction controls. Each historical predictor and seasonal baseline is frozen at its own origin; response bands/months must all have matured before fitting. No unrestricted level-VAR extrapolation. Child spec fixes exact baselines, ridge penalties, warmup and missing-data rules before full execution.

- [ ] Tests before implementation: positive/negative lag decomposition, required endpoint release gates, future poisoning, train-only scaling/seasonality, contiguous lags, horizon maturity, declared fallback visibility and exact monthly compounding.
- [ ] Run smoke and independent checks; freeze source/hash declaration; fit all outer origins; export standalone food and FAST-with-food paths plus training/selection logs.

## Task 3 — core adaptation and independent h0 information

Create `models/core_adaptation_r17.py`, `core_adaptation_experiment_r17.py`, `tests/test_core_adaptation_r17.py`, child spec. Use saved R15 origin-specific seasonality and released monthly core history. Test a low-dimensional persistent-trend/temporary-shock filter whose trend responsiveness depends only on past standardized innovations; isolated jumps and repeated same-direction surprises have different effects. Fixed FAST remains the direct comparator.

Add a separate h0-information variant only after identifying saved HARD_BASE core estimates and their own historical errors. Update the path using the incremental h0 forecast signal, treating its error as uncertain and accounting for shared information; never treat h0 as a realised core observation. If an exact saved h0 component history is absent, reconstruct the independent origin forecasts using existing frozen original inputs/code and verify their headline/component parity before use. Every update and historical measurement-error estimate is exported.

- [ ] Tests: isolated-vs-persistent synthetic innovations, no future influence, nonnegative covariance, fixed-filter limiting case, same-origin horizon step count, h0-error maturity, shared-information update, and h0 headline unchanged.
- [ ] Freeze a small candidate grid before full fitting. Evaluate standalone core and annual headline, including R16-style core-replacement attribution.

## Task 4 — monthly price-signal transmission

Create `models/monthly_transmission_r17.py`, `monthly_transmission_experiment_r17.py`, `tests/test_monthly_transmission_r17.py`, child spec. Use verified monthly category levels, their historical weights and an explicit reconciliation remainder where needed; broad annual goods/services are not silently relabelled as monthly core components. Work with released monthly log inflation and simple/shared lag coefficients rather than fitting every small category independently without shrinkage.

Candidate groups distinguish domestic labour/demand pressure from imported prices/FX/energy. First-stage forecasts must beat their own persistence/AR comparisons on the same dates to support a mechanism claim. Any second stage trains on the actually saved first-stage forecasts at historical origins, never realised future signals. Preserve and compare the prior failed R13/R16 approaches. Source/definition gaps become explicit exclusions or scenario-only inputs.

- [ ] Test category/remainder arithmetic across basket changes, publication gates, generated-forecast lineage, train-only shared scaling and exact unit conversions.
- [ ] Run fixed domestic/imported/both groups with small prespecified regularization, forecast h1..12 monthly and score components before headline integration.

## Task 5 — regulated bills and market-conditioned energy paths

Create `models/energy_path_r17.py`, `energy_path_experiment_r17.py`, `tests/test_energy_path_r17.py`, child spec, new source tables. Reuse the already tested Bill/PolicyEvent mechanics without changing their meaning. A policy changes a persistent expenditure level over its known start/expiry interval; known expiry may affect a future forecast, unknown expiry may not. Never add POZE separately to a regulated-bill change already containing POZE. VAT, fixed charges, commodity caps and network charges retain distinct units and exposure definitions.

Rows require published monetary quantities, dates, applicable household products and exposure support. If CPI treatment or exposure is unresolved, output bounded assumption-labelled scenarios and a fail-closed eligibility ledger; do not award them an invented historical score. Source-supported changes are scored against the unchanged administered block. Historical source evidence is kept separate from prospective-entry records.

For fuel, compare constant pump/constant spot assumptions with a declared scenario interpolating from the latest origin-known spot to the user's one-year Bloomberg series. The latter is a chosen interpolation, not a recovered monthly delivery curve. Forward observations use the corrected current-available alignment; stale/missing data has an explicit reason. Feed the scenario through the existing separately estimated petrol/diesel transmission; use fixed dated weights and exact relatives. Gas commodity scenarios remain separate from household tariff timing unless contract exposure mapping is supported.

- [ ] Test start/expiry inverse-level arithmetic, missing knowledge dates, no POZE double counting, cap/network separation, VAT once, origin exposure gates, spot/forward timestamps, h12 endpoint and no realised future market input.
- [ ] Run all supported histories; save unscoreable scenarios with reasons, so limitations are visible rather than disappearing through fallback.

## Task 6 — combinations, selection, turns and replay

Create `path_component_experiment_r17.py`, `tools/review/evaluate_r17.py`, corresponding tests and a frozen combination specification. Compare every single-block change with FAST, then fixed combinations and a strongly constrained combination chosen only from matured own-origin headline path losses. The loss averages squared annual-CPI errors over h1..12; only fully published outcomes enter selection. Fixed controls and equal-weight comparisons remain visible. A common configuration/weight applies to a whole path to avoid artificial horizon-by-horizon switching.

Retain exact R16 core-turn diagnostics. Add prespecified sustained acceleration/deceleration: at least0.5pp annualized change from the first to third core band and no opposite material adjacent move across those bands; score direction/hit/false-alarm counts on common support. This is an additional diagnostic, not a replacement for the failed exact-turn metric. Report forecast revisions and explanatory component changes; CNB proximity does not select parameters.

- [ ] Tests: no late labels in combination weights, deterministic equal-weight/default rules, coherent monthly recombination, declared sample support, sustained-turn boundaries/false alarms, both CNB clocks and HTML/JSON parity.
- [ ] Independent specification/code/numerical review; reproduce source-to-fit lineage, weighted accounting and primary score rows.
- [ ] Fresh consolidated tests and hashes; create `R17_RESULTS_2026-09-14.md`, update README/model map, self-contained CNB replay and a concise user assessment. Distinguish measured improvement, unchanged controls, negative findings and remaining source limitations.

The child specifications make each numerical task reviewable before its full fit; recording a task's failed hypothesis is completion of research, not grounds to silently tune and rerun it. The master scope is fulfilled only after each approved area has been implemented/tested or its specific unavailable source requirement has been investigated and made explicit in a working fail-closed/scenario path.
