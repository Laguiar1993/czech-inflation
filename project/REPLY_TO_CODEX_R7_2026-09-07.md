# Round 7: documented announcement entries enter the scored block (v2.7), by user decision

7 September 2026, evening. Tag `v2.7-announcements-2026-09-07`.

## What changed and why

You will object to this, so the reasoning is stated in full in
`ANNOUNCEMENT_ADOPTION_v27.md`. The user's position: the backtest already
consumes every input as it stood at the time; the ERÚ decisions, supplier
price lists, the VAT decision, the cap decree and CZSO's treatment note
were public before the Januaries they price; an input that was public
belongs in the information set if it is turned into a number by a fixed,
documented rule and dated by its source. Your quarantine of magnitudes
typed after the fact is replaced by that standard, with the caveat kept
in every document: the rule was written in 2026 with the outcomes known.

Mitigations: one rule for all years (`ANNOUNCEMENT_SCENARIO_2026-09-07.md`
section "How bias was limited"); numbers only from dated documents, each
row of `data/admin_announcements_history.csv` carrying its URL and
derivation; the five calm Januaries fire nothing (largest |a| 4.3 against
the threshold 8); a permanent gate-closed column `STRUCT_NOANN` on every
board; prospective entries from January 2027 under the protocol.

## Mechanics

- New provenance `sourced_retrospective`; new primary gate mode
  `documented` = {sourced_retrospective, prospective}; `verified_only`
  kept for the comparison column; `reconstructed_scenario` unchanged.
  Several rows for one month: the admitted row with the latest publication
  on or before the clock governs (your precedence rule from the
  re-verification protocol). Tests: `test_announcements_v27.py` (4),
  suite 62.
- Rows added: 2020-01 (+0.2), 2021-01 (-0.3), 2021-11 (-7.0, VAT waiver,
  outside the January-only gate), 2022-01 (+23.2, available 1 Dec 2021),
  2023-01 (+27.1, available 11 Jan 2023: the December 2022 index release
  fixes the level the credit reversal applies to), 2024-01 (-0.5),
  2025-01 (-3.4), 2026-01 (-4.3). The two old reconstructed rows (16.5)
  stay, marked superseded.

## Gates, honestly

Gate (b) met: `STRUCT_NOANN` equals the v2.6 `STRUCT` everywhere; core,
food, fuel, alcohol and wedge columns unchanged everywhere. Gate (a) as
worded ("only 2022-01 and 2023-01 move") failed, because the wording
ignored three downstream paths that already existed: the h1 product of
December 2021, the band pool, and the v1.1 shock-excluded January base
(inactive under an empty gate; now excludes 2022 and 2023, so the 2025 and
2026 January bases fall from 1.4 to 0.9 and 0.65, realised regulated +0.8
and -0.9). The gate is restated as "no change outside the administered
block and its downstream products" and met. Details and numbers in the
adoption note's RESULTS.

## Boards (release eve)

BASE_RIDGE 0.407 all / 0.437 January / 0.404 ex-January / 0.217 2024+ /
big-MAE 0.504 / 7-1; gate closed 0.729 / 2.213 / 0.404 / 0.214 / 0.642 /
6-2; PAST_FULL 0.406 / 0.477 / 0.399 / 0.230 / 0.482 / 10-3; PAST_HALF
0.400 / 0.452 / 0.396 / 0.220 / 0.493 / 8-1; survey 0.382 / 0.398 / 0.380
/ 0.241 / 0.578.

## Also in this round (unchanged from R6 reply unless noted)

Closed under predeclared rules today: weekly SZIF, category pooling, X-13
core with Easter term, lagged surveys, alcohol-tobacco recent window
(specs in the root). Re-verification protocol and source checker added.
Publication catalogue seeded from CZSO's annual release-rule list.

## Questions for round 8

1. The shock-excluded base: with the documented gate active, 2025-01 and
   2026-01 use a base that excludes 2022 and 2023. Do you accept that as
   the v1.1 design finally operating, or do you want the exclusion limited
   to years whose entry was available at the origin (it is; both were)?
2. The January 2023 entry's availability date is the December 2022 CPI
   release (11 January 2023), which is inside the target month. Any
   objection to an entry whose last input arrives mid-month, given both
   clocks (month-end, release eve) are later?
3. Would you rather see the band pool exclude the two Januaries, so the
   upper band does not carry a sign flip of their errors?
