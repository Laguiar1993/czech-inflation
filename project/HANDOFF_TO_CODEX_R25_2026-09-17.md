# CZK CPI forecasting — handoff from Claude

**Start here. 17 September 2026, after the R23 review and rounds R23B, R24 and R25.** The user's objective is unchanged: an independent next-release CPI forecast, a useful monthly path h0–h12, and occasional economically defensible calls that anticipate CNB revisions and are materially closer to the outcome. No CNB forecast or inflation-expectations survey enters the independent forecast. Conditioned comparisons stay clearly separate.

## State of the working copy

```text
C:\Users\luis_\Documents\Codex\2026-09-05\c-users-luis-appdata-local-temp\work\cpi-independent
```

Branch `codex/independent-cpi-20260909`. **The tree is now committed.** `ea547dc` is a checkpoint of everything that was uncommitted after R23, byte for byte as found; every later commit is mine. Pytest temporary directories were left out.

**Line endings matter here.** `core.autocrlf` is true and the manifests hash working-tree bytes, so a file without a `-text` rule comes back with different bytes after any checkout. `.gitattributes` now has an explicit `-text` rule for every path committed since R14B. Add a rule for every new path before its first commit, and check that the staged blob equals the working file.

Read in this order:

1. `REVIEW_TO_CODEX_R23_2026-09-17.md` — the review of your R23 delivery.
2. `R24_RESULTS_2026-09-17.md` — the one positive result.
3. `R23B_RESULTS_2026-09-17.md`, `R25_RESULTS_2026-09-17.md` — two clean negatives.
4. `CNB_TRACKER_RESULTS_2026-09-17.md` — CNB tables, block attribution of gaps, the ledger, and a revision tracker that is not established.
5. The four specifications in `docs/implementation/` dated 2026-09-17. Each was committed before its code, and each code commit precedes its single run.

## Decisions

| Item | Decision |
|---|---|
| R23 delivery | Reproduces byte for byte; no look-ahead. No promotion stands. The diagnosis changes: NSA labour costs (44% of the feature's variance seasonal), sign bounds binding in 82–98% of fits, and a penalized intercept whose correction correlated −0.58 with need |
| R23B cost-pressure corrections | Six candidates, none promoted. **Lane closed.** The repaired labour-cost signal is in phase with need on the full sample (+0.42 at h6) and fails from 2024 |
| R24 food drift | **`FOOD_NORM_SHIFT_R24` replaces the baseline food path in the research roster.** Read it as a stable food drift of about 2.6% a year, in one cycle; the estimator is not separately validated |
| R25 panel-estimated mean reversion of core | Four candidates, none promoted. A regime trade-off, as R21's anchors were |
| CNB revision tracker | Not established: no regression beats the zero-revision benchmark under both schemes |
| Nowcast BASE, HALF, FULL | Unchanged and untouched |
| Path references | FAST, current core, gentle slope, now each also shown with the R24 food drift |

## The one thing that worked, and why

Block attribution shows where the path error sits. For origins from 2024 (RMS of the cumulative weighted block error over h1–12, percentage points of headline): food 0.73, fuel 0.44, administered 0.32, core 0.32. Three rounds had worked on core. The food system's forecasts decay to calendar-month means of its training window, so they carry the window's average drift: 4.4 to 5.4% a year once the window contains 2022. Replacing only that drift with a long-history median (2.5 to 2.8% a year) lowers food-block RMSE in all twelve era-by-horizon cells and takes assembled headline h12 RMSE from 4.869 to 4.801 on the full sample and from 0.858 to 0.665 from 2024. The full-sample h12 interval excludes zero under every bootstrap variant the reviewer tried, and the gain survives leaving out any origin year.

The independent review limits the claim, and the results document adopts every point: a plain constant of 2.6% scores the same; every constant from 1.75 to 4.75 would have passed my promotion rule; the start year of the median is a tuning constant; the gain is a level shift, with the forecast-outcome correlation from 2024 unchanged at −0.59; 2023 and 2021 origins carry 75% of the full-sample gain.

## What is new in the tree

| Location | Purpose |
|---|---|
| `tools/path_diagnostics/` | Standard diagnostics for every path round: input gates, circular block bootstrap, block error tables, block benchmarks against zero change and seasonal-naive, lead-test base rates with report clusters, a dominant-block label on scored calls. `standard.py` runs the fixed R17 stack plus all of these. **Its modules are hash-frozen inputs of three evaluations: add new files, do not edit these** |
| `data/cost_pressure_r23b.py`, `models/cost_pressure_r23b.py`, `tools/research_r23b/` | R23B |
| `models/food_drift_r24.py`, `tools/research_r24/` | R24 |
| `data/hicp_panel_r25.py`, `data/research_r25/`, `models/panel_persistence_r25.py`, `tools/research_r25/` | R25 and the frozen EU HICP-core panel (26 member states, no Czechia) |
| `data/cnb_mpr_tables_20260917/` | All 19 CNB report spreadsheets with hashes; every row parsed; bold means CNB forecast. Parsed CPI equals `data/cnb_mpr_cpi_quarterly.csv` exactly |
| `tools/cnb_tracker/` | Table parser, block attribution of model-minus-CNB gaps, the revision tracker |
| `tools/current_path_r24/extend.py` | Adds the three paths with the R24 food drift to a recorded current-path run without touching it. Exact parity with the research output on the July 2026 fixture |
| `tools/recording/cnb_ledger.py` | Append-only, hash-chained ledger of disagreements with CNB, with abstentions and a named driver; `resolve` writes outcomes to a separate file |
| `output/research_r23b/final`, `output/research_r24/final`, `output/research_r25/final` | Canonical runs and evaluations |
| `output/claude_delivery_20260917/DELIVERY_MANIFEST.json` | Seals this delivery and verifies R18–R23 unchanged |
| `work/research_r23b_review/`, `work/research_r24_review/` | Independent reviews with probes. `work/research_r25_review/` holds only my own reconstruction checks |

93 tests pass: 68 new in seven files, plus your 25 targeted tests. Two independent reviews ran mutation probes and 24 mutants survived my first suites. Tests were added, and re-running both reviewers' mutant lists now kills all 45 (`work/claude_mutation_recheck_20260917/recheck.py`). Every surviving behaviour had been correct on the delivered data.

## Results that must not be overstated

- **R24 is historical evidence on a studied sample.** I had seen the 2024+ food bias before declaring it. What it shows is narrower than my specification's wording; see above.
- **The lead test measures the regime.** Passed through the same rules, a constant 2% forecast scores 6 gains, 12 losses and 3 joint successes on 19 matured first calls, exactly the record of the best model, and carrying the last annual rate forward scores 6 successes. FAST's 19 episodes come from 13 reports. Since 2023 the three-to-four-quarter gap against CNB correlates −0.32 with CNB's eventual error.
- **In 2024–25 our whole systematic gap against CNB three to four quarters ahead was food** (+0.5pp), the block R24 repaired. In 2022–23 it was core against administered prices.
- **The tracker's directional numbers are tiny-sample.** When the independent gap and the tracker agreed in sign, the direction was right in 7 of 9 material cases. That is a lead, not a result.
- R25's combination of panel core and R24 food has the lowest h12 headline error of any path from 2024 (0.593). It fails the full sample badly. Do not select it on that panel.

## Operator steps for the first prospective record

Nothing prospective exists yet. `output/cnb_ledger_replay_demo/` is a replay on the July fixture and says so in every row.

**One decision is needed before step 1.** The live runner reads `data/release_calendar_cz_cpi.csv`, which ends at the August 2026 target, and refuses a target without a sourced row. That same file is hashed by the R18, R21, R22 and R23 delivery manifests and by the R23, R23B, R24 and R25 run manifests. Adding the September row will make every one of those verifications fail at HEAD, although each still verifies at the commit where it was sealed. Either give the live runner its own calendar file and keep the research calendar frozen (a small change to the R20 runner, which the R20 manifest seals), or make the verifiers accept an append-only extension of the calendar. I did not choose for you and I did not touch the file.

1. Refresh the inputs and add sourced first-release rows for September 2026 onward to `data/release_calendar_cz_cpi.csv`. Prepare and seal a path input bundle (`tools.current_path.seal_inputs`).
2. `python -m tools.current_path.run --live --target 2026-09 --path-inputs <bundle>` before the October flash.
3. `python -m tools.current_path_r24.extend --run <that run> --output <new directory>`.
4. `python -m tools.recording.cnb_ledger record --run <that run> --path <new directory>/path_r24.csv --tables data/cnb_mpr_tables_20260917 --ledger output/cnb_ledger`. Do this before the Autumn 2026 CNB report; take its date from cnb.cz.
5. After that report: `python -m tools.cnb_tracker.fetch_tables --output data/cnb_mpr_tables_<date>` (the registry `data/cnb_mpr_cpi_quarterly.csv` needs the new report first), then `cnb_ledger resolve`.

## Research I would do next, in order

1. **Food, h1–6.** R24 fixed the level, not the dynamics. An error-correction term between retail, producer and farm price levels has the right in-sample sign at h3 and h6 (−0.43 and −0.33) and needs level states inside the stability and ragged-edge machinery. Declare it separately, score the block first.
2. **A promotion rule with power.** The R24 reviewer showed mine could not distinguish an estimator from a constant. Require a candidate to beat the best simple alternative of its own kind (for a drift: the best constant), and state era-balanced conditions.
3. **Administered prices.** Split regulated energy, where the regulator's November decisions are known in advance, from the rest. From 2024 a zero-change forecast beats the constant baseline (1.15 against 1.85).
4. **Core: which phase are we in.** R21, R23B and R25 all show that a symmetric pull toward a norm hurts while inflation builds and helps while it unwinds. The missing information is upstream pressure building or fading. R23B found producer-price momentum to be the one imported-cost measure with a stable sign. Extending the frozen panel with producer and import prices by country would let that be estimated outside the Czech sample.
5. **Tracker with calibrated elasticities.** Replace the estimated coefficients, which the 2022 pairs contaminate, with pass-through elasticities from CNB's own published sensitivity scenarios. Open and cite those documents first.
6. **A post-release snapshot clock** for fair comparison at CNB's cutoff, where CNB currently has one more CPI print than our snapshot in all 19 rounds.

## Rules I followed, and ask you to keep

- Specification committed before code; code committed before its single run; evaluation rehearsed on a scratch copy so the canonical directory is written once.
- Never edit a hash-frozen file: run inputs listed in any `manifest.json`, the evaluators in `tools/review/`, `tools/research_r23/lead.py`, the modules of `tools/path_diagnostics/`, the frozen specifications. Errata go in the results document.
- Gates and audits are read before scores. Expectations are written down in advance; two of mine were wrong (R24's effect on 2021 origins, R25's horizon profile) and the results say so.
- Block first, then the assembled path. A headline gain with a worse block is error cancellation.
- Every figure in a results document is reproduced by a probe or an exported file.

## Reproduce

```powershell
$env:PYTHONPATH='../pythonlibs'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython -m pytest tests/test_path_diagnostics.py tests/test_cost_pressure_r23b.py tests/test_r23b_review_mutants.py tests/test_food_drift_r24.py tests/test_panel_persistence_r25.py tests/test_cnb_tracker.py tests/test_cnb_ledger.py tests/test_cost_gaps_r23.py tests/test_transmission_r22.py tests/test_released_error_research_r21.py tests/test_policy_anchor_r21.py -q -p no:cacheprovider
& $cpiPython -m tools.claude_20260917.seal
```

The seal verifies R18–R23, the three run manifests and their evaluation manifests, then hashes this delivery. Each round's own results document gives its run and evaluate commands; every runner requires a new output directory. Runtime: Python 3.12.14 with the sibling `../pythonlibs`. `requests` is not installed there, so the new network tools use `urllib`.

There is still no untouched holdout, no prospective record, no calibrated position-sizing rule and no proof of consistent superiority over consensus or CNB.
