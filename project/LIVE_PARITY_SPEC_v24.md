# Predeclared change v2.3 -> v2.4-live-parity (provisional pending Codex)

Declared 7 September 2026, BEFORE the rerun. Motivation: Fable review D1-D7
and Codex round-4 review (`czech_cpi_fable_review/REVIEW_FOR_LUIS_AND_CLAUDE.md`)
against commit `1251fd8`. Every item below is a correctness repair of the
live path or of evidence hygiene; none is a model-selection change.

## What changes

- **P1 Calendar-lag construction (D1 / Codex P0).** Every lagged feature is
  built as `src.reindex(full_index).shift(k)` (function `_lag`), never
  `src.shift(k).reindex(...)`. Applies to core_l1/l2/l12, services_l1,
  import_l2, wage_l3, the state dummy and its smooth variant, food_l1,
  food_l12, agri_l1, food_ppi_l1; `load_agri_price_mm` label-shifts
  (`shift(1, freq="M")`) so its newest month is not lost. The frame assembly
  is extracted into the pure function `assemble_feature_frames` so it is
  unit-testable offline. An unknown trailing y/y now yields state = NaN,
  not 0.
- **P2 Availability on both frames.** `_mask_row_by_availability` gains
  rules for state (t,11), food_l1 (t,11), food_l12 (t,1), agri_l0 (t,26),
  agri_l1 (t,1), food_ppi_l1 (t,16); masking `state` also masks every
  `*_x_state`; `struct_live` masks the food frame too.
- **P3 Decision clock for labels and past errors (Codex P0).**
  `_cpi_family_released_by(u, as_of)` (11th of u+1, the same declared rule
  as core_l1). `_ridge_predict(..., as_of=)` restricts training labels to
  released months; `restored_pe_correction` now READS `as_of`: an error of
  month u is eligible only when core(u) is released by `as_of`.
  `food_forecast(..., as_of=)` passes the clock through.
- **P4 Release-event identity (Codex P0).** `struct_live` logs
  `release_stage` (pre_flash / pre_final / post_flash / post_release /
  unknown), its source (explicit vs inferred from the survey table's flash
  date), `scheduled_release` (09:00 local) and `hours_to_release`. CLI:
  `--release-stage`, `--release-dt`, `--no-log`.
- **P5 Imputation transparency.** Each live row records `n_imputed` and
  `imputed_cols` (with each source's last available month), `archive_ok`,
  and two honest panel edges (`panel_any_edge`, `panel_all_edge`) instead of
  the dummy-contaminated `panel_edge`.
- **P6 Backtest growth (D3).** Origins = every month of `y.index` from
  2018-02; the retired champion file is optional (benchmark print only).
- **P7 Warm challenger in-repo (Codex P1).** `main()` adds
  `STRUCT_PE_WARM`, `STRUCT_PEH_WARM`, `pe_corr_warm` via the same
  `restored_pe_correction` the live call uses (frozen history sliced by the
  clock). `STRUCT_PE` keeps its cold-start meaning and is relabelled
  "cold" in the scoreboard.
- **P8 Tests.** Fixture gets `os`/`HERE` so `_basket_available_from` runs
  the production path (2026-02-05); the clock test straddles that date.
  New `test_live_parity.py`: edge+1/edge+2 lags, gapped source, NaN state,
  clock helper boundary, food/state masking, past-error eligibility,
  ridge label eligibility.

Out of scope for v2.4 (declared for the next batch, not silently changed):
month-to-date FX for the EOM call (D5), NSA household expectations, the
fuel blend on price relatives (Codex P1, measured <= 0.008 pp), basket
publication date from a CZSO source (D6), the energy calculator's status
as a validated reconstruction, the probability layer, the January package.

## Expected effect (stated before the rerun)

- Backtest region (origins <= CPI edge): all existing columns bit-identical
  to v2.3 (max |diff| < 1e-9) EXCEPT where the pre/post frame diff shows a
  changed cell. Two changes are anticipated from the mechanism: `import_l2`
  at origins whose row lies beyond the import series' last label (the last
  one or two origins), and any cell where a source series has a calendar
  gap (positional shift previously bridged it). The frame diff is run and
  reported BEFORE the backtest.
- Live rows: change by construction (that is the repair). The 16 rows in
  `output/struct_shadow_log.csv` at spec <= v2.3 are retained unchanged
  and are to be read as produced with defective feature construction.
- New warm columns: compared with Codex's frozen `PAST_FULL_WARM`
  (`v23_matched_forecasts.csv`); the difference is a measurement of the
  cross-environment forest gap, not an adoption criterion.

## RESULTS (filled in after the rerun, 2026-09-07 morning)

- (a) Frame diff, backtest region: core and smooth-state frames 2 of 5,875
  cells changed, both the anticipated `import_l2` (+ interaction) at the
  2026-07 origin; food frame 0 of 1,175. A first helper (reindex-then-
  shift) lost the 2007-01 state cell because it dropped history older than
  the frame index; the diff caught it and the label shift replaced it.
- (b) Backtest identity: 18 columns changed in exactly one cell each, all
  at 2026-07 (STRUCT +0.007, core_pred +0.013, STRUCT_H1 +0.017); zero
  changes elsewhere. Aggregates unchanged at the third decimal.
- (c) Tests 24 / 24.
- (d) Dry run 2026-08 pre_final: BASE_RIDGE +0.38, PAST_FULL +0.39,
  PAST_HALF +0.39; construction imputations zero; the three remaining
  imputed inputs (exp12, exp36, esi) are database staleness (D2), to be
  cleared by `update_cz.py` before the next logged call.
- New columns: STRUCT_PE_WARM vs Codex frozen PAST_FULL_WARM: max |diff|
  0.033 pp, mean 0.0032, correlation of corrections 0.9992; scores equal to
  the third decimal (0.727 / 0.227 / 0.600 / 10-4).
- Outputs: v2.3 preserved as `output/cz_struct_backtest_v23.csv`; v2.4 is
  `output/cz_struct_backtest.csv`; run log `output/backtest_run_v24.log`;
  scoreboards `output/scoreboards_v24.log`.

**ADOPTED provisionally** under the rule below (all four gates met; the
refresh part of gate d is an operator step, not a construction defect).
Codex sign-off requested in REPLY_TO_CODEX_R4. Not committed.

## Adoption rule

ADOPT v2.4 if (a) the pre/post frame diff over the backtest region shows no
changes other than the anticipated classes above, (b) every pre-existing
backtest column is bit-identical outside the cells the frame diff flags,
(c) the full test suite passes, (d) the live dry-run for the current
target shows zero released-source columns imputed in the origin row. If
any other number moves, STOP and investigate: that is a found bug, not a
spec change. v2.3 outputs are preserved as `output/cz_struct_backtest_v23.csv`.
