# R31B specification: the path's food-products PPI level from Bloomberg

22 September 2026, Claude. Declared before the code; committed before the run. A one-input extension of R31: the last Bloomberg-reachable input of the food block.

## The input

The R27 research path's food block (R14B system, R24 drift, R27 gap correction) reads three log levels: the food CPI (Bloomberg `CZCPF` since R31), the farm-price basket `agri4` (CZSO, not on Bloomberg) and the food-products PPI (CZSO CEN0201B division 10, domestic market, unrounded). The nowcast already reads the PPI's lag-1 m/m from `CZPPA10M Index`; the path needs the level.

Candidates in the 12 September snapshots, compared with the CZSO level as `100·ln(level / level at 2015-01)` over 2015-01 to 2026-07 (139 months):

| Candidate | Log-level gap, max / mean | m/m within 0.11 | Verdict |
|---|---|---|---|
| `EPT010CZ Index` (Eurostat NACE 10 index) | 2.55 / 0.87 | 41% | a different series (market coverage), not used |
| `EPTC10CZ Index` (Eurostat NACE 10 index) | 4.34 / 1.06 | 30% | a different series, not used |
| cumulated `CZPPA10M Index`: Σ 100·ln(1 + m/m ⁄ 100), re-based to 2015-01 | 0.31 / 0.13 (0.006 at 2026-07) | rounding only (published m/m vs unrounded log m/m, max 0.115) | **tested here** |

The cumulated series carries the one-decimal rounding of every published m/m, so its level wanders around the CZSO level by up to 0.31 log points and comes back; the m/m information is the same to publication rounding.

## What is built and run

- `tools/bloomberg_lane/food_ppi_variant.py build --bundle data/bloomberg_inputs_20260922 --output data/bloomberg_inputs_20260922_foodppi`: copies the R31 bundle, replaces the `food_ppi` column of `path/food_log_levels.csv` with the cumulated `CZPPA10M` level (every month of the frame is covered; nothing kept from the previous source), rewrites `provenance.json` for that column (ticker, transform, snapshot hash, coverage, largest gap) and `MANIFEST.json` (hashes; `variant_of` = the R31 bundle manifest hash). Nothing else in the bundle changes; the nowcast frames are untouched.
- `tools/bloomberg_lane/run_path.py --bundle data/bloomberg_inputs_20260922_foodppi --nowcast output/bloomberg_lane_20260922/nowcast --output output/bloomberg_lane_20260922_foodppi/path`: the R31 path runner, unchanged; h0 from the R31 nowcast run (variant A).
- `tools/bloomberg_lane/food_ppi_variant.py compare --lane output/bloomberg_lane_20260922/path --variant output/bloomberg_lane_20260922_foodppi/path --output output/bloomberg_lane_20260922_foodppi/comparison`: the variant's rows against the R31 lane's rows and against the recorded R27 — food block change per month, annual-rate change per horizon, the score table side by side, the R27 alpha and drift audits side by side.

## Expectations, written before the run

Food block within 0.05 pp a month of the R31 lane (the PPI enters only through the system's regressors and the R27 gap regression, and the level differences are rounding noise around zero); annual rates within 0.05 pp at every horizon; h12 RMSE within 0.005 of the lane's 4.768 (all origins) and 0.660 (from 2024) against the previous truth; CNB-pair RMSE within 0.005 of 0.410; R27 alpha unchanged at the −0.25 bound at every origin. If the food block moves by more than 0.1 pp at any month, the cumulated level is not a substitute and the PPI level stays CZSO.

## Rules kept

Specification committed before code; code committed before the run; no hash-frozen file edited; the R31 bundle and runs are read only; every number in the results comes from an exported file.
