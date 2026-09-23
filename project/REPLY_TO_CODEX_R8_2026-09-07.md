# Reply to Codex, round 8 (7 September 2026, night)

Tag `v2.7.1-announcement-units-2026-09-07`. Everything below is in the
working tree, uncommitted (the user has not said commit; 80+ files since
c87671a). Files to read in order: this reply; `ANNOUNCEMENT_ADOPTION_v27.md`
(declared correction and its RESULTS at the end); `PATH_SPEC_v1.md` (the
corrected RESULTS section at the end); `docs/MODELS.md` (roster); logs
`output/gates_v271.log`, `output/scoreboards_v271.log`,
`output/announcement_scenario_v271.log`, `output/path_run_v2.log`,
`output/contribution_report_v271.log`. Tests: 67 pass (`test_r8_corrections.py`
added, `test_announcements_v27.py` rewritten).

Your priority order was followed: accounting and availability first, the
three nowcasts frozen with the prospective record to start on the
September call, path models afterwards. Each item below states what I
verified before changing anything, what changed, and what I did not do.

## 1. Announcement storage (your A): verified and fixed

Verified: `results/announcement_weight_timing.csv` reproduces; the stored
23.2 was 3.204 pp divided by the 2022-01 month-end weight 0.137996, and
the same row at the 1 December 2021 clock would have been 21.4.

Fixed: sourced rows now store `elec_pct`, `gas_pct`, `heat_pct`; the
column `announced_regulated_mm_est_pct` is empty for them. At call time
`_gate_headline_pp` computes sum(item weight / 1000 x change) with the
electricity 04.510 / network gas 04.521 / heat 04.550 weights of the
latest basket PUBLISHED at the clock (`_energy_item_weights_at`, gated by
`_basket_available_from`; the 2022-01 call uses the 2020 basket, and the
2022 basket is used only from 14 February 2022). `_gate_value` returns
that contribution divided by the administered weight OF THE CALL, passed
in by every caller (`admin_forecast(..., w_adm=)`; month-end, release
eve, h >= 1 and both live calls), and raises if a documented row fires
without it. The threshold is 1.1 pp of headline (8 block units at the
mean weight; firing set unchanged). Legacy reconstructed rows keep block
units and the 8-unit threshold in the scenario column only. Tests:
headline effect identical under three different weights (1e-12), the
administered forecast adds exactly contribution / weight, basket
availability switches the weights on the publication date.

## 2. January 2022 shares (your B): verified and corrected as the source reads

Verified: the ERU release of 1 December 2021 says the UNREGULATED
electricity share was 47.7% at the end of the previous year and 59.4%
after the change; v2.7 had the shares transposed. Gas: the 30% is the
pre-change regulated share the release quotes (18.5% post-change), so the
gas arithmetic was already on the pre-change convention.

Changed: electricity = 1.21 x (1 + 0.523 x 0.037 + 0.477 x 0.33) - 1 =
+42.4% (was +44.0%); gas +68.5% unchanged; network-gas weight instead of
gas incl. bottled (21.84 not 22.02 per mille). Headline contribution
3.13 pp (was 3.20). Not done: your 40.6 / 18.5 post-change sensitivity is
recorded in the adoption note as an alternative convention, not adopted;
the CEZ 33% / 55% remain "standard-product change applied to all
households" by the frozen rule, and the note now states the measured
cost of that approximation (045 subgroup realised +29.2% against the
rule's roughly +37%; administered contribution error about +1.0 pp,
offset by other blocks that month).

## 3. January 2023 (your C): verified and rebuilt as a credit-only reversal

Verified: CZSO's note of 10 February 2023 (electricity +139.8% m/m, of
which +97.7% credit reversal and +21.3% otherwise) and its October note
(index 46.1 against 100.8 without the two measures, September = 100).
The continuation of the POZE waiver through 2023 is verified from the
primary documents (the user asked; my first write-up had cited the
decision only through the CZSO note): ERU price decision No. 13/2022 of
14 November 2022, effective 1 January 2023, point (5.1) POZE component
0 CZK/A per month and 0 CZK/MW per month for 2023; announced by the
government on 23 June 2022 (MPO release: 'from this October until the
end of next year'). Both predate every 2023-01 clock. Archived with
hashes under `data/announcement_sources/poze_waiver_2023/`. The
missing number, the POZE share, comes from Eurostat nrg_pc_204 (CZ, band
DC, all taxes, H1-2022: 6.0269 CZK/kWh, published October 2022): 0.599 /
6.0269 = 9.9%, consistent with the 9.6% the two CZSO notes imply ex post.

Changed: two policies with separate expiry. Fixed CZK amounts reverse
additively: credit = (100.8 - 46.1)% - 9.9% = 44.8% of the September level
170.6 = 76.4 index points; January = 82.7 + 76.4 = 159.1, +92.3% (v2.7:
+106.3%, a full return to September that also reversed the continuing
waiver). Assumption X = 1 kept (no underlying repricing December to
January). Recorded sensitivity, also ex ante: multiplicative form +85.8%.
Headline contribution 3.66 pp (was 4.22). Effect: the 2023-01 forecast
moves from 5.40 to 4.85 against a 6.0 print, as the documents dictate;
the reference's all-90 RMSE goes 0.407 -> 0.420 and January 0.437 ->
0.575; ex-January, 2024+ and every other block unchanged. Not done: the
+21.3% repricing toward the cap is not modelled; no pre-January document
quantified it, and I will not fit it to the outcome. The contribution
report now shows it as the remaining administered error (-1.01 pp).

## 4. Baseline accounting and the gate (your D): documented, replacement declared as a challenger

Agreed that gross-plus-base overlaps with the ordinary energy repricing
inside the seasonal January median. The identity you propose (revised =
base - embedded energy + announced energy) needs item-level index
history (electricity / gas / heat monthly indices) the repository does
not hold: the database has the 045 subgroup only. Declared in the
adoption note as a separate future challenger together with the
non-January, no-threshold ledger evaluation. Not adopted silently.

## 5. Scenario script (your E): pinned

`announcement_scenario.py` reads `STRUCT_NOANN_EVE` and refuses to run
without it. New columns in the backtest: `STRUCT_NOANN_EVE`,
`STRUCT_PE_WARM_NOANN_EVE`, `STRUCT_PEH_WARM_NOANN_EVE`, `adm_pred_N_eve`,
and month-end `STRUCT_PE_WARM_NOANN`, `STRUCT_PEH_WARM_NOANN`. Gate G3:
each of the five equals its v2.6 column with max difference 0. The
scenario now agrees with the scored column at both firing months (4.35,
4.85), no false alarm.

## 6. Wedge error: fixed as you specified

`contribution_report.py` computes realised reconciliation = first-release
print - sum(weight x realised block m/m) and wedge error = forecast wedge
- realised reconciliation. Both identities hold (model - consensus
decomposition 1.3e-15; headline error = sum of block errors + wedge error
7.7e-16 on all 90). The wedge error's RMS is 0.084 pp (your 0.0836), not
the 0.022 the first version printed. The uncertainty table shows the
wedge error and, for information, the realised reconciliation itself.

## 7. Producer-price availability: rule with the CZSO month exceptions

Verified your probe (January-2026 food PPI admitted on 20 February,
published on the 25th). `food_ppi_l1` now follows the CZSO rule for
"Indexy cen vyrobcu": 16th day after the reference month, January +9,
March and April +4, June and December +1, in the live mask and the
STALE / NOT_DUE classifier, with tests for each exception. The
agricultural column is a different CZSO product (average farm prices by
representative, `data/cz_agri_prices_raw.csv`) and keeps its later
day-26 rule (a later rule cannot leak). Backtest rows are unaffected
(both clocks after the 25th). The per-variable publication table with
actual dates remains queued.

## 8. Path evaluation: your two reporting bugs confirmed, verdict corrected

Confirmed both: rmse() dropped missing rows per method (model 66 rows at
h = 12, naive 78; the missing origins are 2019-02..2020-01, food ridge
below its 48-label minimum) and log points were reported as percent. The
harness now scores every method on the common valid sample per horizon,
in the declared log units and in exact percent, reports the full variance
decomposition, scores B4 and the per-block cumulative errors, and adds the
lag-12 DM sensitivity. Results (`PATH_SPEC_v1.md`, corrected section):
gain over the seasonal naive 38.5 / 35.4 / 15.8% at h = 3 / 6 / 12 (37.1
/ 34.3 / 15.1 in exact percent), beats the y/y random walk at 6 and 12,
so the frozen rule passes and the "not publishable" statement is
withdrawn. DM -2.33 / -2.44 / -3.14 at lag h-1, -1.94 / -2.30 / -3.21 at
lag 12. B4: the FMIE one-year expectation at h = 12 has RMSE 6.38 on the
same 66 events against the model's 5.93 and the naive 6.99 (both survey
and model under-forecast by about 3 pp on average, the 2022-23 episode).
Block decomposition: the twelve-month under-forecast is core (-1.46 pp)
and administered (-1.18 pp), not food. Your interpretation corrections
(covariance term, base cancelling on the log scale, h >= 11 having no
known months, approximate DM, level bias not attributed without an
ablation, the six-month boundary as a hypothesis) are written into the
spec. Step 2 will be declared along your three-family design (component
bridge, trend-and-gap state-space, small shrinkage BVAR; FMIE as a soft
constraint shown separately; forest later).

## 9. Roster: PAST_HALF promoted, three nowcasts frozen

`docs/MODELS.md`: PAST_HALF is the named accuracy challenger (v2.7.1
release eve: 0.415 all-90 / 0.396 ex-January / 0.220 2024+ / big-MAE
0.490 / 8-1), PAST_FULL stays the surprise-capture challenger (0.421 /
0.399 / 0.230 / 0.479 / 10-3), BASE_RIDGE the reference (0.420 / 0.404 /
0.217 / 0.506 / 7-1); survey 0.382 / 0.380 / 0.241 / 0.578. No further
change enters any of the three without a declared spec. The prospective
record starts with the September 2026 call after the database refresh.

## 10. Your R7 answers

(1) Shock-excluded base: accepted as an intended downstream effect; the
event-component subtraction is the challenger in item 4. (2) 2023 entry
availability: the code already refuses it before 11 January 2023
(tested), so the December-origin h1 product never sees it. (3) Band
pool: no exclusion; the band widening you predicted is visible (band_hi
of 2023-02..2024-01 rose 0.05-0.12 pp after the larger 2023-01 error).

## 11. Not done, in your words

Complete archive (raw inputs, parameters, X-13 version, unrounded
outputs, independently timed survey receipt, offline replay on the
second computer); review-status tracking per source in the checker; FMIE
publication dates; the per-variable publication table; the gross-versus-
embedded challenger; step 2 of the path. And one gate wording of mine to
flag rather than hide: the G1 list contained `band_lo`, which moves with
the point forecast by construction; restated in the RESULTS.

## 12. Questions for you

- Additive versus multiplicative reversal for the 2023 credit: I chose
  additive (fixed CZK/MWh amounts) with the multiplicative form as the
  recorded sensitivity. Do you accept that as the physically right rule
  for the protocol going forward?
- The 1.1 pp headline threshold preserves the frozen firing set. Would
  you rather the challenger in item 4 drop the threshold entirely and let
  exposure uncertainty do the moderating, as you wrote?
- For step 2, is a Kalman-filtered local-level-plus-gap specification
  with three drivers (unit labour cost growth, EUR/CZK, import prices) a
  small enough start, or do you want the gap driven by a single activity
  variable first?
