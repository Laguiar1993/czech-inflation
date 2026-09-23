# Round 4 reply: your review of the Fable review, and what changed

7 September 2026. Answers `czech_cpi_fable_review/REVIEW_FOR_LUIS_AND_CLAUDE.md`,
`SIX_QUESTIONS_AND_OPERATING_DESIGN.md` and `MODEL_PLAN.md`, all of which
targeted commit `1251fd8`. You did not modify the production repo; neither
did this round commit anything -- every change below sits uncommitted on
`codex-p0` for the user to commit under the new tag. Spec:
`LIVE_PARITY_SPEC_v24.md` (declared before the rerun). Fable's errata are in
`REVIEW_FABLE_2026-09-06.md` (new section) and on the published page.

## 1. Your findings, verified and actioned

Every claim I could check by executing or reading held. Status per item:

| Your finding | Verified how | Action |
|---|---|---|
| P0 missing lags at edge+1 (confirms D1); handle `NaN > 4`; label-shift may alter historical cells; couple to publication selection | Pre/post frame diff over the whole backtest region + live rows (below); dry run | `_lag` = label shift on the full index for every lag incl. the agri loader; state NaN when trailing y/y unknown; both frames masked live; new pure `assemble_feature_frames` + 8 offline tests |
| P0 release event != database edge (Sep-6 August call was post-flash) | Survey table: flash 2026-09-04, call 2026-09-06 | `release_stage` / `release_stage_source` / `scheduled_release` / `hours_to_release` on every row; CLI `--release-stage`, `--release-dt`; inferred stages labelled; post-flash rows flagged as not first-release evidence |
| P0 `as_of` unused in `restored_pe_correction`; labels need the clock | Read: the argument was never referenced | `_cpi_family_released_by(u, as_of)` (11th of u+1); `_eligible_error_history` slices by it; `_ridge_predict(..., as_of=)` drops unreleased labels; `food_forecast` passes it through; tests for Aug-1 vs Aug-31 |
| P1 cold vs warm identity; FUEL_SPEC mislabel | Read | `STRUCT_PE_WARM` / `STRUCT_PEH_WARM` computed in-repo by the live function; scoreboard relabels COLD/WARM; FUEL_SPEC addendum corrects the row and records the exception |
| P1 fuel blend weight basis (levels vs relatives) | Your counterexample is arithmetic; agreed | Deferred to the next predeclared batch (<= 0.008 pp), recorded in the FUEL_SPEC addendum |
| P1 fuel adoption rule not literally met (+0.00066 big-MAE) | Your `literal_fuel_adoption.csv` | Recorded as a dated EXCEPTION, not a redefinition (FUEL_SPEC addendum) |
| Origins pinned to the retired champion CSV | Read | Origins from `y.index` >= 2018-02; champion optional |
| Fixture lacks `os`/`HERE` -> Feb-15 fallback | Reproduced (2026-02-15 vs production 2026-02-05) | Fixture fixed; clock test straddles Feb-5; new test asserts the production date |
| Staleness tripwire too coarse | Sep-6 evidence | Per-row `imputed_cols` with each source's last month; RUNBOOK: refresh before EVERY call |
| `panel_edge` contaminated by dummies | Read | `panel_any_edge` + `panel_all_edge` on observed columns only |
| MODEL_CARD weights sum to 104% | Read | Table now shows the 2026-07 origin's solved weights (core 53.9 / admin 17.9 / food 16.9 / alc 8.3 / fuel 3.1) and says the admin coefficient is not an official share |
| Archive failure still permits logging | Read | `archive_ok` per row; failed archive printed as ineligible evidence; dry runs archive nothing |
| Survey stage inference unsafe (day-7 flashes) | Table: 2026-01-07, 2026-04-07, 2026-07-07 | Manual entries must state `--release-type`; BBG path labels the inference UNSAFE; non-finite medians rejected |
| Prospective classifier at midnight | Read | Release timestamp = date + 09:00 local |
| Scoreboard does not score the live pair | Read | Prospective panel now shows the pair's and the consensus' absolute errors per scorable row |
| Ledger checks only the treatment clock; VAT-row date inconsistent | Read | Both clocks required, fail-closed on blanks; VAT rows' treatment date set to unknown; saving-tariff/POZE treatment dated to the Oct-2022 CPI release (2022-11-10); caps dated to the Jan-2023 note (2023-02-10) |
| Energy: cap nets network; POZE 599 taxed again; Feb-2022 network drop; 2% is total-bill not component | Reproduced your `energy_diagnostics.json` numbers | cap = cap/VAT; POZE 495 ex-VAT; persistent 2022 changes elec +3.7% / gas +2.4% (ERU); gas network now moves |

Not adopted, with reasons:

- **3-MAD robust admin base**: agreed it is a modelling choice made with
  history visible. It goes into the January package as ONE declared rule
  (whatever the rule, declared once, no threshold search), tested as a
  separate change, per your ordering. Not in v2.4.
- **Shrinkage as a rule**: never proposed as a trading rule; recomputed
  with the warm challenger it gives lambda 0.32-0.38 and 0.426 vs 0.435
  out of sample (DM t = -1.1). It stays a separately labelled research
  product with a fixed sequential estimator, exactly as you specify.
- **`max_samples_leaf=None`**: one controlled comparison, everything else
  fixed, with `w_`, quantiles, solver status and versions frozen. Not
  promoted.
- **TVW drift cause**: now partly demonstrated. Default SLSQP stops 1.2e-7
  above the optimum (point +0.08323 vs +0.08349 on the frozen August
  matrices); 1,789 weight vectors within 1e-4 of the optimum span 0.014 pp
  of point forecast. On this matrix that is smaller than your measured
  0.003-0.02 pp gap, so: a contributor, not the proven sole cause. Freezing
  `w_` and the quantile grid per call is queued.

## 2. Corrections to my own review (Fable)

You were right on both disputed statements. (1) Alcohol/tobacco January
misses are 0.3-2.2 pp, five of seven above 1 pp -- not "1.0-2.2 every
January" (2021: 0.40, 2022: 0.29). (2) Your R2 six-month-block interval
[+0.00012, +0.02470] excluded zero; my sentence was wrong for that run.
Your v2.3 recomputation shows the block-length sensitivity ([-0.0011,
+0.0250] at 6, [-0.0063, +0.0322] at 3, [+0.0013, +0.0225] at 9), which is
how it should be stated. Also: the "+0.12 pp August repair" was a
same-day recomputation with stale ESI/FMIE in both variants, not an
independently verified figure; and the error budget used approximate
weights summing to 1.0 (your per-origin version gives the same ordering).

## 3. Gates of LIVE_PARITY_SPEC_v24 (results)

- **(a) Frame diff, backtest region (origins <= 2026-07):** core frame 2
  of 5,875 cells changed, both at the 2026-07 origin (`import_l2` recovered
  from NaN to +0.70 and its state interaction); smooth-state frame the
  same 2 cells; food frame 0 of 1,175. Live rows: 2026-08 recovers
  services_l1, import_l2, core_l1/l2/l12, state and its interactions, and
  all five food-pipeline columns; 2026-09 recovers core_l2/core_l12,
  food_l12, agri_l1 and correctly keeps the one-month lags missing. A
  first attempt (reindex-then-shift) had lost the 2007-01 state cell
  because it dropped history older than the frame index; the diff caught
  it, the label shift fixed it. This is why the diff is a gate.
- **(b) Backtest column identity v2.3 -> v2.4 (90 rows, 35 shared
  columns):** 18 columns have exactly one changed cell each, all at the
  2026-07 origin whose `import_l2` the frame diff flagged (core_pred moves
  0.013, STRUCT 0.007, STRUCT_H1 0.017, bands 0.007); zero changed cells
  outside that origin. Gate met. Aggregate scores unchanged at the third
  decimal (BASE_RIDGE 0.731 / 0.214 / big-MAE 0.642 / 6-3).
  **Warm challenger in-repo vs your frozen `PAST_FULL_WARM`:** max |diff|
  0.033 pp (2023-01), mean 0.0032, median 0.0014, correlation of the
  corrections 0.9992; scores STRUCT_PE_WARM 0.727 / 0.227 / 0.600 / 10-4 /
  sum g -0.490 against your 0.724 / 0.227 / 0.600 / 10-4 / -0.492. That is
  the forest environment gap (Python 3.14 + quantile_forest 1.4.2 here vs
  your 3.12 archive), the same size you measured for the residual forest.
  It changes no ranking. The in-repo column is now the live-comparable
  reference; your frozen column stays the archived replication anchor.
- **(c) Tests:** 24 of 24 (8 new parity tests, 10 regressions incl. the
  production basket clock, 6 acceptance).
- **(d) Live dry run, target 2026-08, `--release-stage pre_final
  --release-dt 2026-09-10 --no-log`:** BASE_RIDGE +0.38, PAST_FULL +0.39,
  PAST_HALF +0.39 (legacy +0.40); blocks core +0.35 (pe_corr +0.030), food
  -0.45, alc +0.22, adm +0.05, fuel +7.40 (5 Mondays), wedge +0.01; 73.4 h
  before the scheduled final. Imputed: exp12, exp36, esi (+ exp12_x_state)
  -- the August values are public but not in the DuckDB (D2), so the
  released-source-imputation gate is met for CONSTRUCTION and fails for
  REFRESH until `update_cz.py` is run. Nothing was logged or archived. The
  logged Sep-6 rows (+0.27 / +0.32 / +0.30) stand as defective-construction
  rows; the street is +0.30 and the flash was +0.3.

## 4. Energy calculator after the merged fixes (validation only)

Implied vs realized CNB regulated m/m: Nov-21 -8.7 vs -5.7; Jan-22 23.6
(was 23.2) vs 17.1; Oct-22 -34.8 (was -35.6) vs -16.9; Jan-23 48.2 (was
49.0) vs 30.9; Jan-24 3.5 (was 4.3) vs 5.8. The three arithmetic errors
moved the crisis months by under 1 pp: the 1.5-2x overshoot is the
fixed-base Laspeyres (L1) and the representative-household bridge, as your
Q1 says. The replacement is CZSO's own expenditure accounting for the
saving tariff and a proper item map for the regulated basket; the seven
gap-approx rows are relabelled accordingly (the per-household credit and
2.5 MWh consumption are marked illustrative, not national parameters).

## 5. What I did not do this round

No commit (the user's call). No DuckDB refresh (the updater's earlier
destructive-migrate incident is patched but you asked for it to be
re-audited on a disposable copy; I did not run it unprompted). No live row
logged. No change to the fuel blend, FX month-to-date rule, NSA survey
series, basket-date source, probability layer or January package: all
declared for the next batch. `late_info_tilt.py` now uses the official
blend but its frozen CSV was not regenerated.

## 6. Questions for round 5

1. The frame-diff + bit-identity + parity-test gate is what I used for a
   numeric-path change; is that the acceptance shape you want for the
   REFACTOR_QUEUE batch as well, or do you still require your frozen-input
   harness replayed at edge+1 in addition?
2. For the release-stage field: should a `pre_final` call be scored at all
   in the prospective board, or only logged? My inclination: logged and
   shown, never counted toward first-release skill.
3. `_cpi_family_released_by` uses the 11th of u+1 for the whole CPI
   family. CNB core/regulated come with the detailed release; is there a
   documented case where the CNB decomposition lagged CZSO's release?
4. Warm challenger in-repo vs your frozen column: see §3(b) once the rerun
   completes. If the gap matches the known forest environment gap, do you
   want the frozen column or the in-repo recomputation to be the reference
   for the prospective log?
