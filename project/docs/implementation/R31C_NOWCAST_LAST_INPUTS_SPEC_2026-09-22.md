# R31C specification: the nowcast's last three non-Bloomberg live inputs

22 September 2026, Claude. Declared before the code; committed before the run. After R31 and R31B the roster reads four live series outside Bloomberg: the farm-price basket (no Bloomberg route; stays), the services proxy, the CZSO fuel item m/m and the CZSO weekly pump survey. This round measures the nowcast without the last three, one at a time and together, on the R31B bundle (whose nowcast frames are R31's, byte for byte). The user's aim is a port to another Bloomberg machine with the fewest manual and non-Bloomberg pulls.

## The three changes

| | Input today | Change | Where it enters |
|---|---|---|---|
| C1 | `services_l1`: lag-1 m/m of the average of CZSO division index levels 06, 08, 10, 11, 12, 13 (`cpi_czso.cpi_services`) | column removed from the core feature frame; the ridge, the sequential error history and the residual forest read the remaining columns (`policy_frame` and `_mask_row_by_availability` tolerate the absence; no `_x_state` interaction exists for it) | core ridge (BASE); the forest's feature rows (HALF, FULL) |
| C2 | fuel item m/m: CZSO 07.2.2 from the unrounded 2015=100 index | `CP7FCZ Index` (HICP 07.2.2 fuels, two-decimal index): 100·(I_t ⁄ I_{t−1} − 1) — 95% of months within 0.1 pp of the CZSO item, max 0.157, mean 0.040 (the published `CP7FCZMM` is one decimal and slightly further: max 0.176) | the reconciliation wedge and the weight projection (`solve_weights`); not the fuel block itself, which is measured from pump prices |
| C3 | weekly pump prices: CZSO CENPHMT Monday survey | EC Weekly Oil Bulletin from `ECOBETCZ`/`ECOBOTCZ` — R31 variant B, already run at the 90 clocks | the fuel block (weight 3.1–3.5%) |

R10 (9 September, old frame) measured C1 alone at 0.4160 against 0.4180 on all origins. The register's T9 measured C3's fuel block at 0.201 against 0.217 over the 90 prints and 0.188 against 0.158 from 2024, and R31 measured its headline effect within 0.001 in every sample.

## What is built and run

`tools/bloomberg_lane/r31c.py` (new module; the R31 runners are not edited): reads the R31B bundle (manifest verified), builds the variant frames in memory — C1 (column dropped), C2 (fuel column replaced; provenance of the replacement recorded), C123 (both, plus the variant-B weekly file) — and runs BASE, HALF and FULL through `forecast_independent.calculate` at the 90 recorded release-eve clocks, exactly as `run_nowcast.py` does (its `run`, `score` and `bundle_frames` are imported). C0 is the R31 lane's variant A and C3 its variant B, read from `output/bloomberg_lane_20260922/nowcast/` (hashes recorded), not re-run. Scores: RMSE / MAE / bias over all 90, from 2024, flash era; closer-than-consensus counts; material wins and losses on the 23 large surprises; alerts at 0.20 pp with direction, W/L and net pp — the R31 definitions.

Path effect: every variant changes the path only through h0. The R31B path rows (`mm_lane` at h ≥ 1, the bundle's headline history) are recompounded with each variant's BASE as h0; the recompounding must reproduce R31B's `yy_lane` exactly when given R31's h0 (a check that fails the run). Scored as R31: h3/h6/h12 RMSE against the previous truth on the 969-key support, full and from 2024, and the 34 matched CNB pairs from 2024.

Outputs: `output/bloomberg_lane_20260922_r31c/` — `run_C1.csv`, `run_C2.csv`, `run_C123.csv`, `comparison.csv` (every print, every variant, recorded, actual, consensus), `scores.csv`, `path_scores.csv`, `summary.json`, `manifest.json`.

## Expectations, written before the run

- C2: BASE within 0.02 pp of the R31 lane on every print (a wedge input with a 3.1–3.5% weight and gaps ≤ 0.16); RMSE within 0.001 in every sample.
- C1: BASE RMSE over the 90 prints within 0.005 of the lane's 0.4181, on either side; from 2024 within 0.008 of 0.2208; the largest print change up to 0.15 pp (a removed feature moves the ridge more than rounding does); the large-surprise material wins not down by more than one; alert counts within two.
- C123: the changes add — BASE within 0.15 pp on any print, RMSE within 0.006 of 0.4181 over all prints and within 0.010 of 0.2208 from 2024; HALF and FULL within 0.01 of their lane RMSEs.
- Path: h12 RMSE moves by at most 0.005 (h0 only); CNB pairs within 0.005 of R31B's 0.406.

## Decision rule, written before the run

C123 becomes the default nowcast input set (and the register's declared source) if BASE's RMSE over all 90 prints and from 2024 are each within 0.005 of the R31 lane's and its material wins on large surprises do not fall by more than one. If C123 fails, each component is judged alone on the same rule and the failing ones stay on CZSO. C2 is accepted on the C2 rule (0.02 pp, 0.001) whatever C1 does.

## Rules kept

Specification committed before code; code committed before the run; no hash-frozen file edited; R31 and R31B outputs read only; every number in the results comes from an exported file.
