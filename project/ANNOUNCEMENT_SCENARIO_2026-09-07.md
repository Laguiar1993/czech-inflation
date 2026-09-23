# Sourced retrospective scenario: the January energy gate fed with the documents that existed

7 September 2026. Script `announcement_scenario.py`, inputs
`data/announcement_scenario_inputs_2019_2026.csv` (each row carries its
document, date and derivation), log `output/announcement_scenario_run.log`.

## Status of this evidence

Provenance **sourced_retrospective**: the entries were assembled after the
outcomes were known. It is NOT ex-ante skill and it does NOT enter any
scored column. What it establishes is narrower and still useful: the
information the model needed was public before each January, and the
protocol's own machinery, fed with that information and nothing else,
would have moved the forecast to the print without firing in calm years.
The prospective test is January 2027, under `ANNOUNCEMENT_PROTOCOL.md`.

## How bias was limited (and what remains)

- Inputs are numbers printed in dated documents: ERÚ November releases
  (regulated-component change, regulated share of the bill, stated total
  bill impact), the dominant supplier's price announcements (ČEZ), the VAT
  decision of October 2021, the cap decree 298/2022, CZSO's October 2022
  methodology note (published 10 Nov 2022) and the published December 2022
  electricity index.
- One fixed rule per fuel, written before the run: the regulator's stated
  total household bill change when the release states one; otherwise
  regulated change x pre-change regulated share + supplier commodity change
  x (1 - share); VAT and the credit reversal multiplicative on top; heat
  zero (no document). Fuel weights = CPI basket weights of the previous
  regime; gate as coded (|a| >= 8, forecast = a + base); single pass.
- Remaining bias: the author knew the outcomes. The "regulator's statement
  takes precedence" clause was written knowing the direction of 2024 and
  2025; it does not affect the result because neither year reaches the
  gate under either reading. The January 2023 entry rests on the declared
  assumption that the cap equalled the prevailing underlying price (X = 1).

## What the documents give

| month | electricity | gas | a (regulated m/m) | headline add, pp | gate | print | survey | BASE_RIDGE | scenario | regulated actual |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-01 | +0.7 | +0.1 | +0.2 | +0.03 | no | 1.5 | 1.0 | 0.88 | 0.88 | +1.5 |
| 2021-01 | −0.8 | −0.5 | −0.3 | −0.04 | no | 1.3 | 0.9 | 0.81 | 0.81 | +0.5 |
| 2021-11 | −17.4 | −17.4 | −7.0 | −1.05 | no (below 8) | 0.2 | 0.3 | 0.69 | 0.69 | −5.7 |
| 2022-01 | +44.0 | +68.5 | +23.2 | +3.20 | yes | 4.4 | 3.8 | 1.22 | 4.42 | +17.1 |
| 2023-01 | +106.3 | +0.2 | +27.1 | +4.22 | yes | 6.0 | 5.8 | 1.18 | 5.40 | +30.9 |
| 2024-01 | 0.0 | −4.0 | −0.5 | −0.08 | no | 1.5 | 2.0 | 0.94 | 0.94 | +5.8 |
| 2025-01 | −10.0 | −8.0 | −3.4 | −0.60 | no | 1.3 | 1.1 | 1.20 | 1.20 | +0.8 |
| 2026-01 | −14.9 | −4.1 | −4.3 | −0.74 | no | 0.9 | 0.8 | 0.95 | 0.95 | −0.9 |

January 2019 is before the first backtest origin. October 2022 is left as
it is: CZSO's treatment of the saving tariff became public with the
October release itself, so no call before that release could have known it.

## Effect on the 90-origin board (release-eve clock, BASE_RIDGE)

| | base | scenario | survey |
|---|---|---|---|
| RMSE all 90 | 0.729 | 0.406 | 0.382 |
| RMSE January only (7) | 2.213 | 0.433 | 0.398 |
| RMSE ex-January (83) | 0.404 | 0.404 | 0.380 |
| big-surprise MAE (23) | 0.642 | 0.504 | 0.578 |
| material W-L at 0.15 | 6-2 | 7-1 | |

Fired in 2022 and 2023 only; no false alarm in 2020, 2021, 2024, 2025,
2026 (the largest calm-year value is −4.3, half the threshold). The
January 2022 result is exact by offset (gas overshoots +68 against +31
realised, electricity +44 against +39, heat +10 missed); January 2023
undershoots by 0.6 because the underlying price rose about a sixth between
September and January as fixed contracts expired into the cap. November
2021 shows why the threshold exists: the VAT waiver entry (−7.0) would
have overshot the print had it fired.

## What follows from it

- The January 2027 entry is the test that counts: the same sources, typed
  before the print, hashed and committed. The autumn checkpoints are in
  the protocol.
- The historical announcement file still carries the older reconstructed
  magnitudes (16.5 for 2022 and 2023, x0.55 mapping). Replacing them with
  these sourced values (23.2, 27.1, provenance sourced_retrospective) would
  make the scenario column `STRUCT_R` consistent with this note; it does
  not touch the scored columns. Proposed, not done.
- Heat is the documented gap: local suppliers announce in December and no
  aggregate source exists; a heat entry would need its own collection.
