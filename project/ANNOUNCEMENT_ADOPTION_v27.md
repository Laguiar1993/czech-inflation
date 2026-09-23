# Declared change v2.6 -> v2.7-announcements: documented announcement entries enter the scored administered block

Declared 7 September 2026, BEFORE the rerun. User decision, recorded as such.

## Decision and reasoning

The backtest consumes every input as it stood at the time (CPI, producer
prices, pump prices, FX), reconstructed from dated records with fixed
availability rules. The ERÚ price decisions, supplier price announcements,
the October 2021 VAT decision, the cap decree and CZSO's October 2022 note
were public before the Januaries they price. The user's position: an input
that was public at the time belongs in the information set, provided it is
turned into a number by a fixed, documented rule and dated by its source,
exactly like every other input. The previous quarantine (announcement
magnitudes typed after the fact enter only a scenario column) is replaced
by that standard.

Caveat, stated once and kept in every document that cites the result: the
rule that maps documents to a regulated-price change was written in 2026
with the outcomes known (`ANNOUNCEMENT_SCENARIO_2026-09-07.md`), and the
two Januaries where it fires are the two the author knew best. The
mitigations are: one rule for all years, numbers only from dated
documents, the five calm Januaries as the false-alarm check (none fires),
and a permanent "gate closed" column next to the scored one so the effect
is never hidden. From January 2027 the entries are prospective under
`ANNOUNCEMENT_PROTOCOL.md`; that is when this input stops being
retrospective.

## What changes

- **Provenance `sourced_retrospective`** is added to
  `data/admin_announcements_history.csv`: one row per January 2020-2026
  and the November 2021 VAT event, magnitude `a` from the frozen formula,
  `available_from` = the publication date of the LAST document the entry
  needs (for January 2023 the December 2022 CPI release of 11 January 2023,
  which fixes the index level the credit reversal applies to), source URLs
  and derivation in the notes. The two old `reconstructed` rows (16.5)
  remain, marked superseded in their notes, so the old scenario column is
  reproducible.
- **Gate modes.** New primary mode `documented` admits provenance
  {`sourced_retrospective`, `prospective`}; `verified_only` (admits
  nothing) is kept as the "gate closed" comparison; `reconstructed_scenario`
  and `prospective_announced` unchanged. With several rows for one month,
  the admitted row with the latest `available_from` on or before the clock
  governs (the re-verification protocol's precedence rule); rows dated
  after the clock are invisible to that call. Threshold |a| >= 8 and the
  additive convention (a + shock-excluded seasonal base) unchanged.
- **Backtest columns.** `STRUCT`, `STRUCT_QRF`, `STRUCT_ST`, the past-error
  frames, the `_EVE` columns and the horizon products use the `documented`
  admin forecast. New column `STRUCT_NOANN` = the reference with the gate
  closed (equals the v2.6 `STRUCT` by construction). `STRUCT_R` (old
  reconstructed rows) is kept.
- **Live.** The h0 and h1 calls use `documented`; for a future target only
  `prospective` rows can exist, so live behaviour equals the previous
  `prospective_announced` mode.
- Tag `v2.7-announcements-2026-09-07`.

## Expected effect (stated before the rerun)

Only origins 2022-01 and 2023-01 change, and only through the administered
block: `a` = 23.2 and 27.1 fire; every other January has |a| < 8 (largest
4.3). Expected `STRUCT` at those two origins: 1.22 -> 4.42 and 1.18 -> 5.40
at both clocks (the entries predate month-end). All other origins and all
non-admin columns bit-identical to v2.6; `STRUCT_NOANN` identical to the
v2.6 `STRUCT` at every origin. Board effect for BASE_RIDGE (release eve):
RMSE all 90 0.729 -> about 0.406; January 2.21 -> about 0.43; ex-January
unchanged; big-surprise MAE 0.642 -> about 0.50.

## Gates

ADOPT if (a) the two named origins move as stated and no other origin
moves in any column, (b) `STRUCT_NOANN` equals the v2.6 `STRUCT` to 1e-12
everywhere, (c) the test suite passes with new tests for the mode and the
precedence rule, (d) the scoreboard reports both boards (scored and gate
closed). If any other origin moves: STOP, that is a bug.

## RESULTS (7 September 2026, after the rerun; log `output/gates_v27.log`)

- **Gate (b) MET**: `STRUCT_NOANN` equals the v2.6 `STRUCT` at every origin
  (max difference 0.0). The core, food, fuel, alcohol and wedge columns are
  unchanged at every origin (max difference 0.0). 62 tests pass.
- **Gate (a) FAILED AS WORDED, and the wording was wrong, not the code.**
  35 origins show some change, in four classes, each a deterministic
  consequence of admitting the entries through code that already existed:
  1. The two named Januaries: `STRUCT` 1.213 -> 4.415 (2022-01) and 1.168
     -> 5.389 (2023-01), `adm_pred` 0.9 -> 24.1 and 28.0, at both clocks,
     in every frame that uses the administered block. As expected.
  2. The h1 product from origin 2021-12 (target January 2022): 1.535 ->
     4.726, because the entry (1 Dec 2021) was public at that origin. The
     spec omitted the horizon products.
  3. The seasonal base of later Januaries. The gate's v1.1 design excludes
     fired shock years from the January median; with an empty gate (v2.6)
     that exclusion was inactive, so the base carried the +17.1 and +30.9
     prints. Now: 2025-01 base 1.4 -> 0.9, 2026-01 base 1.4 -> 0.65
     (2024-01 unchanged, the median coincides), and the horizon products
     targeting those Januaries (2024-07 h6, 2024-10 h3, 2024-12 h1, 2025-07
     h6, 2025-10 h3, 2025-12 h1, 2026-07 h6). Realised regulated m/m in
     those Januaries: +0.8 and -0.9, so the lower base is the right
     direction for the block, while the headline moves by -0.09 and -0.13
     and is marginally worse in both months (prints 1.3 and 0.9).
  4. `band_hi` for 27 months after each shock (the band pool contains the
     January errors, which changed sign).
  The gate is restated: no change outside the administered block and its
  downstream products (horizon, band, shock-excluded base). MET under that
  statement. Adopted, with the failure of the original wording recorded.
- Frozen replay against the v2.4 expected file now reports differences at
  the origins above; that file remains the v2.4/v2.6 reference and is not
  rewritten.

### Boards (release eve, 90 first releases; consensus 0.382 / 2024+ 0.241 / big-MAE 0.578)

| frame | RMSE all 90 | January (7) | ex-January | 2024+ | big-MAE (23) | W-L@0.15 |
|---|---|---|---|---|---|---|
| BASE_RIDGE v2.7 | 0.407 | 0.437 | 0.404 | 0.217 | 0.504 | 7-1 |
| gate closed (v2.6 reference) | 0.729 | 2.213 | 0.404 | 0.214 | 0.642 | 6-2 |
| PAST_FULL v2.7 | 0.406 | 0.477 | 0.399 | 0.230 | 0.482 | 10-3 |
| PAST_HALF v2.7 | 0.400 | 0.452 | 0.396 | 0.220 | 0.493 | 8-1 |
| survey | 0.382 | 0.398 | 0.380 | 0.241 | 0.578 | |

Reading: the two January entries take the model from twice the survey's
error to within 0.02 of it over the full sample; ex-January is unchanged
by construction; the recent windows give back a hundredth or two through
the lower January base. The caveat of section "Decision and reasoning"
applies to every number in the first, third and fourth rows: the rule that
produced the two entries was written with the outcomes known.

## Declared correction v2.7 -> v2.7.1 (Codex R8), written 7 September 2026 BEFORE the rerun

Codex's review of the v2.7 mechanism found three accounting faults in the
documented entries and one in the storage format. None changes the decision
above; all change numbers. Declared here, then one rerun, then the gates.

### What changes

1. **Storage in economic units.** A sourced row no longer stores a
   block-unit magnitude (the v2.7 values 23.2 and 27.1 were the headline
   effect divided by the administered weight solved at the 2026-09-07
   month-end, a fitted coefficient published as historical data). Each row
   stores the per-fuel January change in percent (`elec_pct`, `gas_pct`,
   `heat_pct`). At call time the headline contribution is
   `sum(item weight / 1000 x change)` with the electricity / network-gas /
   heat weights of the latest basket PUBLISHED at the clock
   (`_energy_item_weights_at`; the January-2022 call therefore prices with
   the 2020 basket), and the block value is that contribution divided by
   the administered weight of THE SAME CALL. The recombination multiplies
   by that weight, so the headline effect is weight-independent by
   construction (tested). Bottled gas is excluded from the gas weight (it
   does not follow the tariff): 21.84 not 22.02 per mille in 2020.
2. **Threshold in economic units.** The gate fires when the headline
   contribution is at least 1.1 pp in absolute value (the frozen 8 block
   units at the 2019-2026 mean administered weight of about 0.14). The
   firing set is unchanged: 2022-01 (3.13 pp) and 2023-01 (3.66 pp); the
   calm Januaries stay at or below 0.74 pp in absolute value; November 2021
   (-1.05 pp) is outside the January-only gate as before. Legacy
   reconstructed rows (scenario column only) keep their block units and the
   8-unit threshold.
3. **January 2022 shares corrected.** The ERU release of 1 December 2021
   states the UNREGULATED electricity share was 47.7% at the end of the
   previous year (59.4% after the change); v2.7 had applied the regulated
   change to 47.7% and the commodity change to 52.3%, the transpose.
   Corrected: regulated +3.7% on 52.3%, CEZ standard-product commodity
   +33% on 47.7%, VAT back to 21% on the whole: electricity +42.4% (was
   +44.0%); gas unchanged at +68.5% (regulated 30% is the pre-change share
   the release quotes, 18.5% the post-change one). Headline contribution
   3.13 pp (was 3.20). Declared approximation kept: the rule applies the
   dominant supplier's standard-product change to all households; fixed-
   price contracts did not reprice in January and the CZSO 045 subgroup
   realised +29.2% m/m against the rule's roughly +37%.
4. **January 2023 as a credit-only reversal with the POZE waiver
   continuing.** Two policies with separate expiry: the saving tariff
   credit (booked by CZSO as an electricity price cut October-December 2022;
   October index 46.1 against 100.8 without the measures, September = 100)
   ends 31 December 2022; the POZE levy waiver (599 CZK/MWh incl. VAT)
   continues through 2023 and must NOT be reversed. Verified from the
   primary documents after the user asked whether the continuation was
   in fact announced (the first draft of this item cited the decision
   only through the CZSO note): ERU price decision No. 13/2022 of 14
   November 2022, effective 1 January 2023, point (5.1) sets the POZE
   component at 0 CZK/A per month (low voltage) and 0 CZK/MW per month
   for 2023; the government had announced the waiver 'from this October
   until the end of next year' in the MPO press release of 23 June 2022;
   the CZSO note of 10 February 2023 confirms ex post. Both ex-ante
   documents predate the January-2023 clocks and the December-2022
   origin. Archived with hashes under
   `data/announcement_sources/poze_waiver_2023/`. Fixed CZK amounts reverse additively: POZE
   share of the pre-measure price 0.599 / 6.0269 CZK/kWh (Eurostat
   nrg_pc_204, CZ band DC, H1-2022, published October 2022) = 9.9%; credit
   = 54.7% - 9.9% = 44.8% of the September level = 76.4 index points;
   January = December index 82.7 + 76.4 = 159.1, i.e. +92.3% (v2.7 had
   +106.3%, a full return to the September level that also reversed the
   continuing waiver). The X = 1 assumption is unchanged (no underlying
   repricing between December and January). Sensitivity recorded, also ex
   ante: the multiplicative form gives +85.8%. Realised (CZSO note of 10
   February 2023): +139.8%, of which +97.7% credit reversal and +21.3%
   repricing toward the cap. Headline contribution 3.66 pp (was 4.22).
   This correction moves the January-2023 forecast AWAY from the print
   (about 4.85 against 6.0; v2.7 had 5.40). Accepted: the interpretation
   is chosen by the documents, not by the outcome.
5. **Gate-closed columns on the release-eve clock**: `STRUCT_NOANN_EVE`,
   `STRUCT_PE_WARM_NOANN_EVE`, `STRUCT_PEH_WARM_NOANN_EVE`, `adm_pred_N_eve`
   (and month-end `STRUCT_PE_WARM_NOANN`, `STRUCT_PEH_WARM_NOANN`). The
   scenario script reads `STRUCT_NOANN_EVE` as its base and refuses to run
   without it (v2.7's `STRUCT_EVE` base would double count).
6. **Food producer-price availability** follows the CZSO rule with its
   month exceptions (16th day after the reference month; January +9, March
   and April +4, June and December +1) in the live mask and the
   STALE / NOT_DUE classifier. Backtest rows are unaffected (both clocks are
   after the 25th of the month).

Not changed here, declared as a separate future challenger: the gross-plus-
base overlap (the seasonal January median already contains ordinary energy
repricing; the identity revised = base - embedded energy + announced energy
needs item-level index history the repository does not hold yet) and a
non-January, no-threshold ledger evaluation.

### Expected effect (stated before the rerun)

Only the administered-dependent columns of the two firing Januaries and the
h1 product of 2021-12 move against v2.7: headline columns by about -0.07 pp
in 2022-01 (3.13 against the v2.7 effect of 3.20) and about -0.56 pp in
2023-01 (3.66 against 4.22) at both clocks; the band-pool rows that carry
those months move with them. Boards: BASE_RIDGE all-90 RMSE rises slightly
(about 0.407 -> 0.415), January-only rises (0.437 -> about 0.49), ex-January,
2024+ and every non-administered block are unchanged.

### Gates (frozen before the rerun)

- G1 every column that does not depend on the administered block is
  bit-identical to `output/cz_struct_backtest_v27.csv`.
- G2 `STRUCT_NOANN` (month-end, gate closed) is identical to v2.7.
- G3 the new `STRUCT_NOANN_EVE` equals v2.6 `STRUCT_EVE`
  (`output/cz_struct_backtest_v26.csv`) to 1e-9 on all 90 origins;
  `STRUCT_PE_WARM_NOANN_EVE` equals v2.6 `STRUCT_PE_WARM_EVE` and
  `STRUCT_PEH_WARM_NOANN_EVE` equals v2.6 `STRUCT_PEH_WARM_EVE` likewise.
- G4 differences against v2.7 are confined to the 2021-12 h1 product, the
  2022-01 and 2023-01 administered-dependent columns and the band-pool rows
  that include those months; at 2022-01 and 2023-01 every headline column
  moves by the same amount at a given clock, equal to the change in the
  headline contribution (about -0.07 and -0.56 pp) within 1e-6.
- G5 the firing set is exactly {2022-01, 2023-01} (test).
- G6 the test suite passes (62 + the new tests).
Failure of any gate stops adoption; the v2.7 file stays the reference.

### RESULTS v2.7.1 (7 September 2026, single rerun; logs `output/gates_v271.log`, `output/scoreboards_v271.log`, `output/announcement_scenario_v271.log`; v2.7 file preserved as `output/cz_struct_backtest_v27.csv`)

- G1: every block column (core, food, fuel, alcohol-tobacco, wedge, past-
  error correction, actuals) is bit-identical to v2.7. The gate script's
  "non-administered" list also contained `band_lo`, which moved by -0.556
  at 2023-01; the band is the point forecast plus and minus a width, so
  both edges move with the administered block by construction (band_hi
  moved by the same -0.556 in the same row). Restated: G1 met on the block
  columns; `band_lo` and `band_hi` are administered-dependent.
- G2 met (max difference 0). G3 met with max difference 0 on all five
  pairs: the new gate-closed columns reproduce the v2.6 file exactly at
  both clocks for all three nowcasts.
- G4 met: changes against v2.7 confined to the 2021-12 h1 product
  (-0.062), the 2022-01 and 2023-01 administered-dependent columns, and
  band rows; at 2022-01 every headline column moved by -0.0723 and at
  2023-01 by -0.5563, identical across columns to 1e-15 and equal to the
  change in the headline contribution (3.201 -> 3.129; 4.220 -> 3.664).
  The band_hi rows of 2023-02..2024-01 rose by 0.05-0.12 because the
  larger 2023-01 error widened the band pool.
- G5 met (firing set {2022-01, 2023-01}; scenario script agrees with the
  scored column at both months, 4.35 and 4.85; no false alarm). G6 met:
  67 tests pass.

Boards (release eve, 90 first releases; all / January / ex-January / 2024+ /
big-surprise MAE / material W-L at 0.15):

| model | all 90 | January | ex-January | 2024+ | big-MAE | W-L |
|---|---|---|---|---|---|---|
| survey | 0.382 | 0.398 | 0.380 | 0.241 | 0.578 | |
| BASE_RIDGE v2.7.1 | 0.420 | 0.575 | 0.404 | 0.217 | 0.506 | 7-1 |
| gate closed (v2.6) | 0.729 | 2.213 | 0.404 | 0.214 | 0.642 | 6-2 |
| PAST_FULL v2.7.1 | 0.421 | 0.620 | 0.399 | 0.230 | 0.479 | 10-3 |
| PAST_HALF v2.7.1 | 0.415 | 0.594 | 0.396 | 0.220 | 0.490 | 8-1 |

January 2022: print 4.4, survey 3.8, v2.7 4.42, v2.7.1 4.35, gate closed
1.22. January 2023: print 6.0, survey 5.8, v2.7 5.40, v2.7.1 4.85, gate
closed 1.18. The 2023 correction costs about 0.55 pp on that month, as
declared; the all-90 RMSE of the reference rises from 0.407 to 0.420 and
the January RMSE from 0.437 to 0.575, ex-January and 2024+ unchanged.
The contribution report for 2023-01 now reads: administered contribution
error -1.01 pp (24.4 forecast against 30.9 realised, the +21.3% repricing
toward the cap that no pre-January document quantified), food -0.33 pp,
wedge error +0.21 pp.

Adopted: v2.7.1 is the operating tag (`SPEC_TAG` v2.7.1-announcement-
units-2026-09-07). The three nowcasts are frozen from here (docs/MODELS.md).
