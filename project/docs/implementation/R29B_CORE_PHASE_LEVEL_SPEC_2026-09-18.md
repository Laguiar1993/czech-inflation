# R29B specification: the phase read from the level of upstream momentum, and fixed persistence pairs as candidates

18 September 2026, Claude. Declared after the R29 rehearsal and before any R29B code; committed before the code, the code before the single run. Judged by the R26 promotion rule.

## Why, in numbers from the R29 rehearsal

R29 defined the phase as the sign of the change in six-month producer-price momentum. Two things failed. On the EU panel the phase did not separate persistence before the surge rows matured (separation −0.05 to −0.07 through 2022, +0.08 to +0.11 from 2023), so the declared gate failed. On the Czech side the definition misread the 2022 plateau as fading (January to March 2022, momentum 6.6 to 7.2 log points a half-year but below the 2021 peak) and read the 2024 trough as building (momentum rising from 0 to +1 while core was unwinding). The panel-estimated weights, at about 0.5 in band 1 for both phases, then failed at h3 exactly as R25 did.

The fixed pairs run for the specificity condition told a different story. With weight 1.0 when building and 0.6 or 0.8 when fading, around the 2%-a-year norm, the core block was at or below FAST in ten of twelve cells and cut full-sample h12 RMSE by 8–9% (3.92 and 4.05 against 4.28) and 2022–23 by 12–21%. The two cells they failed were from 2024 at h6 and h12, by 0.3–4.5%, where the phase had been misclassified as building. This round changes only the phase definition and promotes the fixed pairs to candidates.

## The phase

At an origin, from the last published producer-price month L: momentum `m` = 100 × (log PPI_L − log PPI_{L−6}). Phase = **building** if `m` > 1.0 log point (2% a year, the target-consistent upstream rate), otherwise **fading**. Same rule for every panel country and for Czechia. No estimation.

## Candidates

All act on the FAST frame's core block (roster frame at the time of the run) for h1–12, band by band, `mu + lambda(phase) × (f − mu)` with `mu` = 2% a year (0.165 log points a month), converted back with the origin's seasonal pattern as in R25 and R29.

| Candidate | lambda(building) | lambda(fading) |
|---|---|---|
| `CORE_LEVELPHASE_FIXED040_R29B` | 1.0 | 0.4 |
| `CORE_LEVELPHASE_FIXED060_R29B` | 1.0 | 0.6 |
| `CORE_LEVELPHASE_FIXED080_R29B` | 1.0 | 0.8 |
| `CORE_LEVELPHASE_PANEL_R29B` | panel-estimated per band and phase (R29 machinery, level-based phase) | panel-estimated |

The three fixed pairs are candidates in their own right. `CORE_LEVELPHASE_PANEL_R29B` is judged with condition 3 against them.

## Gates, read before any score

- The panel weights by band and phase at the six named origins under the level-based phase, with the separation. The R29 stop rule is kept for the panel candidate only: if the panel does not separate the phases in every band at every named origin, `CORE_LEVELPHASE_PANEL_R29B` is not scored against the rule. The fixed pairs do not depend on the panel and are scored regardless.
- The Czech phase at every origin and by era.
- Needed-against-applied sign agreement and era-mean agreement for each candidate at h6 and h12, full sample and from 2024.

## Promotion rule

The R26 rule against FAST's core block, block first; condition 4 in the level-type reading; condition 5 at h6 and h12; condition 6 on the roster frame. For the fixed pairs, condition 3 is the choice among them: if more than one passes conditions 1–2 and 4–6, the promoted object is the pair with the best era-balanced score, and the others are reported; the rounding of the grid (0.2 steps) is the declared resolution and no finer value is searched.

## Expectations, written before running

- Czech phase: building from March 2021 to September 2022 without interruption; fading from October 2022 through 2026 except for isolated months; 2019–20 mostly fading with a few building months in 2019.
- `CORE_LEVELPHASE_FIXED080_R29B` passes all twelve cells: within 1% of FAST in 2019–21, 12–18% better in 2022–23 at h12, 5–10% better from 2024 at h12. `FIXED060` better in 2022–23 and from 2024 but at risk in 2019–21 at h3–6 (a 40% pull toward 2% at fading origins in 2019–20 when core was 2.5–3.5%). `FIXED040` fails 2019–21.
- The panel gate fails again before 2023 (the panel effect is learned from the surge); the panel candidate is not scored.
- If a fixed pair passes, the promoted object is a fixed rule with two numbers, declared here, and the results say that its evidence is one Czech cycle plus the failed panel gate.

## Rules kept

Specification committed before code; code committed before the single run; evaluation rehearsed on a scratch copy; the R29 modules are read only; every figure reproduced by an exported file; no survey, expectations series or CNB forecast enters the candidate.
