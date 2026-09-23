# CZK CPI forecasting — handoff from Claude, R30 to R31C and the Inflation Monitor

**Start here. 22 September 2026.** Follows `HANDOFF_TO_CODEX_R30_2026-09-20.md`. The user's objective is unchanged: an independent next-release CPI forecast, a useful monthly path h0–h12, occasional defensible calls against the CNB; no CNB forecast or inflation-expectations survey inside the independent forecast. Two things were added to that objective this week: **the roster's inputs come from Bloomberg wherever Bloomberg holds the series** (the user intends to run the code on another Bloomberg machine with the fewest manual pulls), and **an analysis lane next to the models** that explains the Czech inflation situation to a reader.

Branch `codex/independent-cpi-20260909`; every commit from `9b2743e` to `3bf9e98` is mine; the tree is clean. Line-ending rule as before: every new path needs a `-text` rule before its first commit; new directories carry their own `.gitattributes` (`* -text`); root-level results documents are written with CRLF bytes because the root `.gitattributes` is hash-frozen.

Read in this order:

1. `MODEL_REGISTER_2026-09-21.md` — one page per model: what it reads, where each input comes from, whether Bloomberg holds it, and the same-results tests. Sections A (nowcast), B (path), G (the Bloomberg lane) carry the current state.
2. `R31_RESULTS_2026-09-22.md` — the Bloomberg input lane (R31), the food-PPI level (R31B) and the nowcast's last three non-Bloomberg inputs (R31C), with the differences against the recorded results.
3. `INFLATION_MONITOR_M1_2026-09-22.md` — the analysis lane and its artifact.
4. `R30_RESULTS_2026-09-20.md` — the excise-calendar round (negative; January spirits steps declared prospective as R30B).
5. The specifications in `docs/implementation/` dated 2026-09-20 (R30) and 2026-09-22 (R31, R31B, R31C, M1), each committed before its code, each code commit before its single run.

## Decisions

| Item | Decision |
|---|---|
| R30 excise steps | Not promoted (tobacco timing and partial pass-through fail the rule). **R30B**: January spirits excise steps in the alcohol-and-tobacco block, prospective from January 2027; scored on future prints only |
| Bloomberg as the source (R31) | Every exact and rounding-only input of the roster is read from Bloomberg through a frozen bundle: CNB core and regulated (`CZCIXM`, `CZCIRM`, exact), the path's pump panel (`ECOBETCZ`/`ECOBOTCZ` ÷1000, exact), headline (`CZCPMOM`, `CZCIPM` before 2015), food m/m and level (`CZCPFMOM`, `CZCPF`), alcohol (`CZCPAMOM`), import prices (`CZEIIMOM`), food PPI m/m (`CZPPA10M`), EUR/CZK monthly mean of the CNB fixing, regime state (`CZCPYOY`/`CZCIPY`). Differences from the recorded results: BASE ≤ 0.044 pp on any print, RMSE .418/.219/.173 → .418/.221/.176; FULL ≤ 0.075; tallies move only at thresholds; R27 path h12 4.769/0.659 → 4.768/0.660; CNB pairs 0.405 → 0.410. Scoring stays on the unrounded CZSO truth (the h3/h6 changes of up to 0.19 pp are the rounded history months in the compounding window, not the forecast) |
| Food-PPI level (R31B) | The path's food-products PPI level = cumulated `CZPPA10M` (Σ 100·ln(1 + m/m⁄100), re-based to 2015-01; within 0.31 log points of the CZSO level). Eurostat `EPT010CZ`/`EPTC10CZ` rejected as a different series. Food block within 0.043 pp of R31; h12 4.767/0.655; CNB pairs 0.406. **Promoted**; `data/bloomberg_inputs_20260922_foodppi/` supersedes the R31 bundle for the path |
| Nowcast's last three CZSO inputs (R31C) | `services_l1` **dropped**; fuel item m/m from `CP7FCZ` (HICP fuels, m/m of the two-decimal index; wedge and weight projection only); pump prices from the EC bulletin (R31 variant B). BASE .4181 → .4159 over the 90 prints, .2208 → .2219 from 2024, every tally unchanged; the declared rule (on BASE) passed and the set is the **default**. Cost, stated: FULL .4150 → .4194 and 9/2 → 7/3 on the 23 large surprises (Dec-2023 and Dec-2024 wins lost, Aug-2021 loss gained; summed gain 2.23 → 2.07 pp, three quarters of it the single Dec-2024 print); HALF 8/1 → 7/2. The user accepted this ("ok lets keep it") |
| Manufacturing PPI (R29B research line) | Not on Bloomberg as a domestic manufacturing series; `EPP0BCCZ` (domestic B+C) is the closest live proxy (momentum correlation .996, phase agrees 88 of 90). Map row 47 updated. Research line only |
| Rounds page | Unchanged: `output/cnb_rounds_v3/cnb_rounds_v3.html` = artifact `4Wo4R9YeuJoRXDry2UVgcL` (version 2), roster of 20 September |
| Inflation Monitor (M1) | New analysis lane, no model change: artifact **`7QWKgLUtWoex31JV2dTACD`** ("Czech Inflation Monitor", version 2), builder `tools/inflation_monitor/`, run `output/inflation_monitor_20260922/`, one-page `note.md` |

## Where the roster stands

Nowcast (90 release-eve prints, R31C default inputs): BASE RMSE .416 all / .222 from 2024 / .176 flash era (consensus .382 / .241 / .195); closer than consensus 46 of 90; large surprises 8 wins / 2 losses of 23; alerts at 0.20 pp: 21, 14 right, 7/8. HALF .415 / .224 / .169, 7/2. FULL .419 / .231 / .166, 7/3.

Path (R31B lane, annual-rate RMSE on the 969-key support, previous truth): R27 h3 1.440 / 0.523, h6 2.243 / 0.481, h12 4.767 / 0.655 (all / from 2024); matched CNB pairs from 2024: 0.406 (CNB 0.372), four quarters ahead 0.538 (CNB 0.426). R27 α at the −0.25 bound at every origin; R24 drift 2.51–2.83% a year.

## What is not from Bloomberg now (the port list, one by one)

1. **Farm-gate prices** (CZSO open data CEN0203B → `data/cz_agri_prices_raw.csv`; 7 products): the only live non-Bloomberg series of the roster; monthly file download, scriptable.
2. **Next release dates**: after each detailed release, the two "Next News Release" dates from the CZSO page into `MANUAL` in `tools/build_release_calendar.py`, rerun → `data/release_calendar_cz_cpi.csv` (Bloomberg's ECO calendar is already a source of the file). The file is hash-frozen and the calendar conflict of 17 September is still open.
3. **January energy announcement** (once a year): one row in `data/admin_announcements_history.csv` — `effective_month`, `available_from`, `elec_pct`, `gas_pct`, `heat_pct`, `provenance = prospective` (ERÚ decisions, supplier notices, government measures). The gate fires only when the implied headline contribution is ≥ 1.1 pp.
4. **Basket weights** (every even year, next February 2028): `cz_struct._OFFICIAL_FOOD/_FUEL/_ALC`, `_ENERGY_ITEM_WEIGHTS`, `models.components.OFFICIAL_PETROL_SHARE` from `data/baskets/spot_kos{year}.xlsx`.
5. Static, copied once: food CPI 1995–2015-01 (`data/research_r14/food/coverage_extension/`), headline m/m before 2007 (`output/independent_path_frozen_inputs.csv`), basket XLSX files, announcement history, the survey-history CSVs, the X-13 binary.

Not needed by the roster: FMIE/ESI/household-expectations columns (HARD drops them), Category Raw's CZSO category levels (challenger), CNB MPR tables (evaluation only), the excise calendar (R30B). No CNB ARAD pull remains.

## The one open engineering item

**The production loader switch.** Everything above was measured through `forecast_independent.calculate` on bundle frames; production still reads the DuckDB mirrors through `cz_struct.load_all`, and the live month-to-date FX reads the CNB year files (`cz_struct._eurczk_mtd_mm`; `EURCZK CNB Curncy` is exact). Pointing the loader at `data/bloomberg_inputs_20260922_foodppi/` frames (with the R31C changes: no `services_l1`, fuel item from `CP7FCZ`, weekly file = the EC bulletin) and resolving the release-calendar conflict is what makes the first live run possible. Until then there is no recorded nowcast for the August 2026 print onward. Design note for the live path: the known months of the compounding window should come from the CPI index level rather than the rounded m/m (R31 results, path section).

## What is new in the tree

| Location | Purpose |
|---|---|
| `data/excise_calendar_cz_r30.csv`, `models/excise_steps_r30.py`, `tools/research_r30/`, `tests/test_excise_steps_r30.py`, `output/research_r30/final` | R30 |
| `tools/model_register_20260921/{build,nowcast_parity}.py`, `output/model_register_20260921{,_nowcast}/` | The register and its tests (T1–T9; BASE reproduces the recorded prints to 1e-4 from the fixtures) |
| `tools/market_data/probe_ppi{,2}_20260922.json`, `compare_ppi_20260922.py`, `data/market_snapshots/20260922_bloomberg_ppi_probe{,2}/`, `output/bloomberg_ppi_comparison_20260922/` | The manufacturing-PPI probe (62 tickers) |
| `tools/bloomberg_lane/build_bundle.py`, `run_nowcast.py`, `run_path.py`, `food_ppi_variant.py`, `r31c.py`; `data/bloomberg_inputs_20260922/`, `data/bloomberg_inputs_20260922_foodppi/`; `output/bloomberg_lane_20260922/`, `output/bloomberg_lane_20260922_foodppi/`, `output/bloomberg_lane_20260922_r31c/` | R31, R31B, R31C: bundles with per-column provenance and hash manifests; runners at the 90 recorded clocks |
| `tools/inflation_monitor/{build.py,template.html}`, `output/inflation_monitor_20260922/` | M1 |

`docs/implementation/DATA_SOURCES_BLOOMBERG_MAP_2026-09-12.md` row 47 updated (manufacturing PPI). Tests: the seven round files that run in this runtime pass (40); `tests/test_r15_runner.py` and the other tests that import `cz_struct` need `duckdb`, which the codex runtime lacks (unchanged since R25). The lane runners inject stub `duckdb`/`requests` modules before importing `forecast_independent`; `decision_clock` requires tz-aware timestamps.

## The monitor, in short

Eight blocks partition the 37 CZSO COICOP-2018 groups (fixed 2026 weights; residual against the published headline shown, not absorbed). First build (groups through July 2026, August flash): headline 1.9, core 3.0 (2.5 a year ago), services 4.6 vs goods 0.4; up: rents +0.89 pp, other services +0.81, fuel/vehicle operation +0.62; down: energy −0.55, food −0.52. Base-effect ledger: November, December and February are drop-out arithmetic (the −0.3/−0.3/−0.1 prints of 2025 leaving the window); the norm path reaches 2.9 by December, the roster path 2.5. Pipeline: farm → food CPI 2–3 months and food PPI → food CPI 1 month in every sample; domestic PPI → core goods only inside 2021–23 (no relation excluding it); PPI → services at 8 months is a common-driver correlation. Bloomberg holds CZSO CPI at division level only and nothing for imputed rent, so the group engine needs the CZSO CEN0101E file (one more open-data CSV in the same monthly script as the farm prices); a division-level Bloomberg-only fallback mode is a small addition, not yet built. Declared next: M2 wages → services (quarterly CZSO wages; `CZNWYOY` differs from the CZSO file by up to 2 pp), M3 the demand block (retail sales, household credit, `EUA8CZ`, unemployment), then the live nowcast on the page.

## Open decisions carried forward

The rule-tolerance amendments (would promote R29B); the January-2023 energy ledger row; the release-calendar conflict; R30B's source for the January-2026 alcohol anomaly; whether FULL should keep `services_l1` as a forest feature (kept out by the user's decision, at a stated cost).

## Research I would do next, in order

1. The production loader switch and the first live run (engineering, not research; everything else waits on it).
2. The persistent form of the food gap through h12 (declared shape, amended rule) — unchanged from the last handoff.
3. M2 and M3 of the monitor; then a division-level fallback for Bloomberg-only machines.
4. The prospective record from the Autumn 2026 CNB report.

## Rules I followed, and ask you to keep

Specification committed before code; code committed before its single run; rehearsal on a scratch copy; never edit a hash-frozen file (everything hashed by any manifest under `output/`, the frozen data files, `tools/cnb_rounds_v2/*`, `tools/review/*`, the dated specifications); errata go into results documents; expectations and decision rules written before running and scored after; new modules rather than edits to committed runners.

## Reproduce

```powershell
$env:PYTHONPATH='../pythonlibs'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython -m pytest tests/test_benchmarks_r26.py tests/test_food_ecm_r27.py tests/test_food_ecm_r27_review.py tests/test_administered_level_r28.py tests/test_core_phase_r29.py tests/test_core_phase_r29b.py tests/test_excise_steps_r30.py -q -p no:cacheprovider
& $cpiPython -m tools.bloomberg_lane.build_bundle --output <new directory>
& $cpiPython -m tools.bloomberg_lane.food_ppi_variant build --bundle <that directory> --output <new directory>
& $cpiPython -m tools.bloomberg_lane.run_nowcast --bundle <bundle> --output <new directory>
& $cpiPython -m tools.bloomberg_lane.run_path --bundle <variant bundle> --nowcast <nowcast output> --output <new directory>
& $cpiPython -m tools.bloomberg_lane.r31c --bundle <variant bundle> --output <new directory>
& $cpiPython -m tools.inflation_monitor.build --output <new directory>
```

Bloomberg pulls run in the anaconda Python from PowerShell (`tools/market_data/probe_bloomberg_candidates.py --output <snapshot dir> --config <json>`, with the anaconda `Library\bin` on PATH). Do not re-run `tools.claude_20260917.seal` or `tools.claude_20260920.seal` (they rewrite their manifests).

There is still no untouched holdout, no prospective record, no calibrated position-sizing rule and no proof of consistent superiority over consensus or the CNB.
