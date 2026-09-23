# R28 specification: the level of the administered-price block

18 September 2026, Claude. Declared before any code or data work on outcomes; committed before the code, the code before the single run. Judged by the R26 promotion rule.

## Why

R26 put numbers on the administered block: from 2024 zero change beats FAST's block by 21% at h3 and 38% at h12 (1.15 against 1.85 log points), FAST's block bias is +1.5 log points a year, and that bias is the +0.26 pp headline bias in the block attribution. FAST's administered path is a sticky seasonal pattern: the median of the same calendar month over the last ten published years, with an announcement gate that overrides January when a sourced regulated-energy announcement implies a move of at least 8% (it fired for January 2022 and January 2023). Outside January the pattern carries +0.05 to +0.20 a month, about +1 log point a year, from the 2015–2021 regime of small regular increases; in 2025 and 2026 the block has printed close to zero outside January and −0.9 in January 2026. In 2022–23 the same pattern, with the gate, was the only thing that caught the energy repricing, and zero change was the worst member of the family there (18.2 against 16.9 at h12). The round asks one question: which level should the block revert to outside announced events, and can that be answered without trading 2022–23 for 2024–26.

## Candidates

All act on the FAST frame's administered block for h1–12 and keep the announcement gate exactly as it is (a January override, when it fires, is kept in every candidate; nothing here touches the ledger or the nowcast). h0, every other block, the wedge and the weights are untouched.

| Candidate | Non-January months | January (when the gate does not fire) |
|---|---|---|
| `ADMIN_ZERO_R28` | 0 | 0 |
| `ADMIN_JAN_ONLY_R28` | 0 | FAST's ten-year January median, as now |
| `ADMIN_RECENT_R28` | median of the same calendar month over the latest three published years | same, three years |
| `ADMIN_HALF_R28` | half of FAST's pattern | half of FAST's January median |

`ADMIN_ZERO_R28` is the R26 benchmark member run as a candidate so that the rule can reject it formally on 2022–23. The others keep the January repricing, which is where the regulated items move, and change only the level assumed for the other eleven months.

## Gates, read before any score

- The realised non-January administered rate by year (mean and sum) against FAST's pattern, so the bias is seen as a regime, not a number.
- Which Januaries the announcement gate fires on at each origin (it must be 2022 and 2023 only, as in FAST; if any candidate changes that, the run is wrong).
- Needed-against-applied correlation and sign agreement of each candidate's change against FAST at h6 and h12, full sample and from 2024.

## Promotion rule

The R26 rule against FAST's administered block, with the assembled condition (6) evaluated on the research roster path at the time of the run (named in the run manifest; the R24 path, or the R27 path if it has been promoted). Condition 3 (specificity) applies to `ADMIN_HALF_R28` against the grid of fixed shrinkage factors {0, 0.25, 0.5, 0.75} of FAST's pattern; `ADMIN_JAN_ONLY_R28` is a fixed rule and has no estimator. Condition 5 (interval) at h12 on the full sample. Condition 4 uses the R26 amendment for level-type candidates: sign agreement of at least one half and the era means' signs agreeing at h6 and h12, full sample and from 2024.

## What is run

- `models/administered_level_r28.py`: the candidate paths at an origin from FAST's own block path (the January override is read off the FAST path: a January monthly rate above 5 percent is a fired gate and is kept as it is; the pattern's own January is 0.6 to 1.5).
- `tools/research_r28/run.py`: the 90 origins on the frozen R24 run's FAST frame; `native_forecasts.csv`, `forecasts.csv`, `admin_audit.csv`, `manifest.json`.
- `tools/research_r28/evaluate.py`: the standard evaluation, the R26 family scores for the administered block, the six conditions.
- `tests/test_administered_level_r28.py`: the gate detection, the January handling, h0 untouched, the three-year median with publication gating, the half pattern.

## Expectations, written before running

- `ADMIN_ZERO_R28` fails condition 1 on the 2022–23 cells and passes everything from 2024. It is the clean negative that shows why the level is the question and not the block.
- `ADMIN_JAN_ONLY_R28` passes condition 1 in every cell: within 2% of FAST in 2019–21 and 2022–23 (the non-January pattern is small there against the errors of those years) and 15–30% better from 2024 at h12. It is the candidate I expect to be promoted.
- `ADMIN_RECENT_R28` is worse than FAST in 2024–25 origins (its three-year window holds 2022–23) and better from 2026; it fails condition 1.
- `ADMIN_HALF_R28` sits between FAST and `ADMIN_JAN_ONLY_R28` everywhere and is not distinguishable from the fixed 0.5 factor; if it passes, the promoted object is the fixed factor and `ADMIN_JAN_ONLY_R28` (factor 0 outside January) is preferred as the simpler rule.
- Headline effect of the promoted candidate from 2024: h12 RMSE lower by 0.02–0.05 pp and bias lower by about 0.2 pp; the CNB-pair RMSE from 2024 lower by 0.01–0.03.

## Rules kept

Specification committed before code; code committed before the single run; evaluation rehearsed on a scratch copy; hash-frozen files untouched; every figure in the results document reproduced by an exported file; no survey, expectations series or CNB forecast enters the candidate; the announcement ledger is read as it stands and not edited.
