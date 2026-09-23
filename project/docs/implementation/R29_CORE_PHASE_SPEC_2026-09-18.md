# R29 specification: which phase are we in — core persistence conditioned on upstream momentum, estimated on the EU panel

18 September 2026, Claude. Declared before any code or data work on outcomes; committed before the code, the code before the single run. Judged by the R26 promotion rule.

## Why

R21 (a-priori anchors), R23B (learned corrections), R25 (a panel-estimated persistence weight) and R26 (the sell-side benchmark) all fail the same way on core: a symmetric pull toward a norm hurts while inflation builds and helps while it unwinds. R25 put a number on the pull (0.40–0.53 of a filtered deviation survives to h1–6 on the EU panel, 0.55–0.65 to h7–12) and showed it works from 2022–23 origins (core h12 5.09 → 2.65) and fails in 2019–21 (4.82 → 5.93). R23B found producer-price momentum to be the one imported-cost measure with a stable sign. The missing input named in every one of those documents is the phase: whether upstream pressure is building or fading. This round conditions the persistence weight on that phase, estimates the two weights outside the Czech sample, and applies them with a fixed norm.

## Data

- The frozen R25 panel of HICP excluding energy, food, alcohol and tobacco, 26 member states without Czechia (`data/research_r25/hicp_core_panel_20260917`).
- A new frozen download of Eurostat producer prices in industry, domestic market (`sts_inppd_m`, NACE B–E36, not seasonally adjusted, index 2021 = 100), for the same 26 states, written by `data/ppi_panel_r29.py` to `data/research_r29/ppi_panel_YYYYMMDD` with a manifest. Availability rule for the panel: month m is treated as published on day 10 of month m+2 (Eurostat releases producer prices about five weeks after the month; the extra margin is deliberate).
- Czech producer prices with their publication stamps exactly as R23 and R23B read them: series 47 of the frozen A6 input panel (`data/paper_replication/a6_inputs_20260912`) through `data.cost_gaps_r23.load_inputs` and `visible`, imported and not re-derived.

## The phase

For a country and origin s, with the last published producer-price month L:

- momentum `m` = 100 × (log PPI_L − log PPI_{L−6}), the six-month change in log points;
- phase = **building** if `m − m_{−6}` > 0 (momentum higher than six months earlier), otherwise **fading**.

Two numbers, one sign, no estimation. Published values only.

## Weights from the panel

As in R25, every panel country is run through the unchanged R15 filter at quarter-end origins, giving per band b ∈ {1..4} (three-month bands of h1–12) the FAST forecast deviation `f − mu` and the realised deviation `r − mu` from the country's own robust norm. R29 adds the phase at each panel origin and estimates, at every Czech origin from rows whose labels are already published, one pooled no-intercept slope per band and phase, `lambda(b, building)` and `lambda(b, fading)`, each clipped to [0, 1]. The R25 single weight `lambda(b)` is re-estimated on the same rows as a control.

## Candidates

All act on the FAST frame's core block for h1–12 (the R24 research path frame at the time of the run, named in the run manifest); h0, every other block, the wedge and the weights are untouched. The Czech core path becomes, band by band, `mu + lambda × (f − mu)` in seasonally adjusted log points and is converted back with the origin's own seasonal pattern exactly as in R25.

| Candidate | lambda | norm mu |
|---|---|---|
| `CORE_PHASE_TARGET_R29` | lambda(b, phase at the Czech origin) | 2% a year in log points a month (0.165), the target-consistent norm |
| `CORE_PHASE_OWN_R29` | lambda(b, phase) | the Czech own-history robust norm of R25 (published months only) |
| `CORE_SINGLE_TARGET_R29` (control) | lambda(b), no phase | 2% a year |
| `CORE_PHASE_FIXED_R29` (specificity grid) | building 1.0; fading ∈ {0.4, 0.6, 0.8} | 2% a year |

`CORE_SINGLE_TARGET_R29` is the R21/R25 combination that has already failed, re-run here so the phase's contribution is read against it on the same rows.

## Gates, read before any score

- The panel weights by band and phase at six Czech origins (2019-02, 2021-02, 2022-02, 2023-02, 2024-02, 2026-02), the row counts behind them, and the difference between phases. If `lambda(building)` is not above `lambda(fading)` in every band at every origin, the phase carries no information in the panel and the round stops there; the results say so and nothing is scored against the rule.
- The Czech phase at every origin (a table of building/fading months) and the share of the 90 origins in each phase by era.
- Needed-versus-applied correlation and sign agreement of each candidate's change against FAST at h6 and h12, full sample and from 2024.

## Promotion rule

The R26 rule against FAST's core block, block first, with the R26 amendment for level-type candidates in condition 4 (sign agreement of at least one half and the era means' signs agreeing). Condition 3 (specificity) for `CORE_PHASE_TARGET_R29` against `CORE_PHASE_FIXED_R29`: the panel-estimated weights are promoted as estimates only if the h12 full-sample squared-loss difference against the best fixed pair has a circular block bootstrap interval excluding zero; otherwise the promoted object, if any, is the fixed pair chosen by the era-balanced score among those passing condition 1. Condition 5 at h6 and h12. Condition 6 on the roster frame.

## Expectations, written before running

- Panel: `lambda(building)` 0.7–0.9 and `lambda(fading)` 0.3–0.5 at h1–6; the gap narrows at h7–12. If the panel does not separate the phases by at least 0.2 at h1–6, I expect nothing else in this round to work.
- Czech phase: building from mid-2021 to late 2022, fading from early 2023 through 2024, mixed in 2019–20 and 2025–26.
- `CORE_PHASE_TARGET_R29`: core h12 lower than FAST in 2022–23 (by 30–45%) and from 2024 (by 10–25%); the risk is 2019–21, where a fading phase in 2019–20 pulls a 2.5–3.5% core toward 2%. I expect the 2019–21 h6 and h12 cells to be within +5% of FAST, and condition 1 to be the one most likely to fail, on those cells. Full-sample h12 lower than FAST by 5–15%.
- `CORE_PHASE_OWN_R29` worse than the target version in 2019–21 (the own norm was 0.8–1.1% then) and similar from 2024.
- `CORE_SINGLE_TARGET_R29` fails condition 1 on the 2019–21 and full-sample cells, as R21 and R25 did.
- Specificity: the panel weights not distinguishable from the fixed pair (1.0, 0.6); if the candidate passes at all, the promoted object is that fixed pair with the phase rule, and the results say so.

## Rules kept

Specification committed before code; code committed before the single run; evaluation rehearsed on a scratch copy; hash-frozen files untouched (the R25 panel and code are read only; new modules for everything); every figure in the results document reproduced by an exported file; no survey, expectations series or CNB forecast enters the candidate; only two weights per band come from the panel, never a level or a Czech observation.
