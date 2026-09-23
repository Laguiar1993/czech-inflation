# CZK CPI forecasting — handoff from Claude, rounds R26 to R29B

**Start here. 20 September 2026.** Follows `HANDOFF_TO_CODEX_R25_2026-09-17.md`. The user's objective is unchanged: an independent next-release CPI forecast, a useful monthly path h0–h12, and occasional economically defensible calls that anticipate CNB revisions and are materially closer to the outcome. No CNB forecast or inflation-expectations survey enters the independent forecast.

Branch `codex/independent-cpi-20260909`; every commit since `b462fcd` is mine; the tree is clean. Line-ending rule as before: every new path needs a `-text` rule before its first commit; new directories carry their own `.gitattributes` (`* -text`), `models/`, `tests/` and `data/` carry per-file rules, and root-level results documents are written with CRLF because the root `.gitattributes` is hash-frozen.

Read in this order:

1. `R26_RESULTS_2026-09-18.md` — the benchmark family (the sell-side recipe the user relayed: split, seasonally adjust, AR per block) and the six-condition promotion rule every later round is judged by.
2. `R27_RESULTS_2026-09-20.md` — the one promotion, with the independent review that re-labelled it (`work/research_r27_review/REVIEW.md`).
3. `R28_RESULTS_2026-09-20.md`, `R29_RESULTS_2026-09-20.md` — three clean negatives and one near miss.
4. The five specifications in `docs/implementation/` dated 2026-09-18, each committed before its code, each code commit before its single run.

## Decisions

| Item | Decision |
|---|---|
| Promotion rule | R26's six conditions are the rule: baseline in every era-by-horizon cell; at or below the best feasible benchmark (zero, seasonal-naive, `SA_AR`, `SA_AR_TARGET`); specificity against fixed constants; in phase; bootstrap interval; assembled path. Amendments declared in R27 and R29B for the next specification: the specificity grid must bracket the estimate; intervals need a 1% materiality; a candidate that never leaves a bound is a constant; condition 4's era-mean test applies only when the baseline's mean error exceeds 5% of its RMSE; condition 6 carries a 0.5% per-cell tolerance. None of these was applied retroactively |
| R24 food drift | Re-labelled as a **fixed drift of about 2.6% a year** (R26 condition 3: any constant 2.25–4.25% passes; the estimator is indistinguishable from the best constant) |
| R27 food error correction | **`FOOD_ECM_R27` replaces `FOOD_NORM_SHIFT_R24` as the research roster's food path**, as a fixed rule: subtract 0.25 of the last retail-to-producer gap, decaying at 0.75 a month, over h1–6 (closing 0.62 of the gap). Not an estimator (the clip bound binds at 90 of 90 origins); not error correction with those dynamics (the gap's effect on the baseline error grows to h6 and persists to h12); the producer-price level carries the signal, the farm price is second order; `FOOD_ECM_PPI_R27` is an equivalent alternative |
| R28 administered level | None promoted (regime trade-off). Finding: the block's largest error is the unforecast January 2023 (+30.9%), see below |
| R29 / R29B core phase | None promoted. The EU panel does not separate persistence by upstream phase before 2023. The fixed pair (persistence 1.0 while producer-price momentum is above 2% a year, 0.8 pull toward 2% otherwise) is below FAST's core in all twelve cells and fails conditions 4 and 6 by a hair; shown on the rounds page as research |
| Rounds page | `output/cnb_rounds_v3/cnb_rounds_v3.html` = claude.ai artifact `4Wo4R9YeuJoRXDry2UVgcL` (version 2). Builder `tools/cnb_rounds_v3/build.py`; every number is rebuilt from the exports and checked against the evaluations (all to 1e-9). The v2 tool and output are kept as they were sealed |
| Nowcast BASE, HALF, FULL, Category Raw | Unchanged and untouched |

## Where the roster stands (annual-rate RMSE, 969-key support; matched report-clock CNB pairs from 2024)

| Path | h12 full | h12 from 2024 | vs CNB, 34 pairs | 4Q ahead, 7 |
|---|---:|---:|---:|---:|
| **R27 research path** | **4.769** | **0.659** | **0.405** | **0.537** |
| R24 path (predecessor) | 4.801 | 0.665 | 0.439 | 0.583 |
| FAST | 4.869 | 0.858 | 0.473 | 0.679 |
| R27 + core phase rule (research, not promoted) | 4.740 | 0.602 | 0.398 | 0.516 |
| Current core + R27 food (presentation frame) | 5.273 | 0.499 | 0.327 | 0.375 |
| CNB | | | 0.372 | 0.426 |

Block attribution of the R27 path from 2024 (RMS of the cumulative weighted block error, h1–12, pp of headline): food 0.52 (was 0.73 on FAST), fuel 0.44, core 0.32, administered 0.32 (bias +0.26), wedge 0.19 (bias −0.17). Half of the gap to CNB on the matched pairs has closed since FAST (0.473 → 0.405 against 0.372).

## Two findings that are not modelling

1. **January 2023 administered prices.** The announcement ledger's `sourced_retrospective` row for January 2023 has `available_from` 2023-01-11 (the December index release it prices off). The December-2022 path origin's clock is 2023-01-10 22:59, so the gate never fires and every origin forecasts +0.9% for a month that printed +30.9%. The primary documents cited in that row (decree 298/2022 of 5 October 2022, the MPO release of 23 June 2022, ERU decision 13/2022 of 14 November 2022) predate the November- and December-2022 origins' clocks. A row available from 14 November 2022, priced off the October index, would let those two origins carry the reversal. This is the nowcast lane's hand-maintained data (R12/v2.7 lineage) and the user's decision; the 2022–23 administered and headline scores of every round would change with it.
2. **The release-calendar conflict** flagged on 17 September is still open; the first live run still needs it.

## What is new in the tree

| Location | Purpose |
|---|---|
| `models/benchmarks_r26.py`, `tools/research_r26/evaluate.py`, `output/research_r26/final` | Benchmark family, constant ceiling, rule mechanics |
| `models/food_ecm_r27.py`, `tools/research_r27/`, `output/research_r27/final`, `work/research_r27_review/`, `work/research_r27_review_recheck/` | R27, its review (10 probes, 16 mutants) and the recheck |
| `models/administered_level_r28.py`, `tools/research_r28/`, `output/research_r28/final` | R28 |
| `data/ppi_panel_r29.py`, `data/research_r29/ppi_panel_20260918/`, `models/core_phase_r29.py`, `models/core_phase_r29b.py`, `tools/research_r29/`, `tools/research_r29b/`, `output/research_r29/final`, `output/research_r29b/final` | R29 and R29B, with the frozen Eurostat producer-price panel (26 member states, 1975–2026) |
| `tools/cnb_rounds_v2/`, `output/cnb_rounds_v2/`, `tools/cnb_rounds_v3/`, `output/cnb_rounds_v3/` | The rounds page, two editions |
| `tools/claude_20260920/seal.py` → `output/claude_delivery_20260920/DELIVERY_MANIFEST.json` | Seals this delivery and verifies R18–R23 and the 17 September delivery unchanged |

101 tests pass (33 new). Runs on the R27 frame: R28, R29 and R29B were run after R27's promotion (`--frame-run output/research_r27/final --frame-model FOOD_ECM_R27`); their block verdicts do not depend on the frame.

## Research I would do next, in order

1. **The persistent form of the food gap** (declared, not searched): the R27 reviewer showed the baseline's food error loads −1.9 on the gap at h6 and −3.7 at h12 while the promoted rule applies 0.62 over h1–6 and nothing after. A candidate that applies the gap through h12 with a declared shape, judged by the amended rule, is the obvious next block gain. Everything the reviewer found was seen on outcomes, so the shape must be declared before the run and the interval materiality applied.
2. **The core phase rule, prospectively.** Its evidence is one Czech cycle and a panel gate that fails. It goes into the ledger as a labelled research line from the next CNB round; nothing else can settle it.
3. **The January 2023 ledger row** (the user's decision), then a re-run of the administered block under the amended rule.
4. **The prospective record**, which every round since R17 has been waiting for; the Autumn 2026 report date comes from cnb.cz.
5. Fuel is done (the pass-through model is worth 2% over the sample and nothing since 2024; a futures-curve line is a separate conditioned series). Alcohol and tobacco is done.

## Rules I followed, and ask you to keep

Specification committed before code; code committed before its single run; evaluation rehearsed on a scratch copy; never edit a hash-frozen file (the list has grown: everything hashed by any manifest under `output/`, including `tools/cnb_rounds_v2/*` and the `tools/path_diagnostics/` modules); errata go into results documents; an independent adversarial review before any promotion, with mutation probes, and its findings adopted in the results document; expectations written before running and scored after.

## Reproduce

```powershell
$env:PYTHONPATH='../pythonlibs'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython -m pytest tests/test_benchmarks_r26.py tests/test_food_ecm_r27.py tests/test_food_ecm_r27_review.py tests/test_administered_level_r28.py tests/test_core_phase_r29.py tests/test_core_phase_r29b.py -q -p no:cacheprovider
& $cpiPython work/research_r27_review_recheck/recheck.py
& $cpiPython -m tools.claude_20260920.seal
```

Do not re-run `tools.claude_20260917.seal`: it rewrites its own manifest with a new timestamp (I did once and restored the file from git).

There is still no untouched holdout, no prospective record, no calibrated position-sizing rule and no proof of consistent superiority over consensus or CNB.
