# Model register — 21 September 2026

One page that says what models exist, what each one is for, what it reads, where each input comes from today, whether Bloomberg holds the same series, and whether the model gives the same numbers when the Bloomberg series is put in its place. Written by Claude from the frozen research outputs; every "same results" entry below is backed by a test in `output/model_register_20260921/tests.csv` (builder `tools/model_register_20260921/build.py`, hash-sealed), and every input-level verdict by the 12–13 September Bloomberg probes (`output/bloomberg_probe_comparison_20260912/exactness/exactness.csv`, `output/bloomberg_model_inputs_20260913/model_input_inventory.csv`, `docs/implementation/DATA_SOURCES_BLOOMBERG_MAP_2026-09-12.md`).

Vocabulary. *Exact*: the Bloomberg series equals our stored series on every common observation, on the model's own transform. *Extremely similar*: differs only by publication rounding (Bloomberg carries one-decimal indices and published one-decimal m/m; we difference the unrounded CZSO 2015=100 index). *Same results*: the block model re-run at all 90 origins with the Bloomberg series gives the recorded numbers; where it does not, the size of the difference is stated.

**Update, 22 September (R31).** Every exact and rounding-only input below is now read from Bloomberg through the input lane — a frozen bundle (`data/bloomberg_inputs_20260922/`, provenance and hashes inside) built by `tools/bloomberg_lane/build_bundle.py`, with `run_nowcast.py` and `run_path.py` running the roster on it. The lane is the declared source for the roster; the whole-model differences it produces are in `R31_RESULTS_2026-09-22.md` and are summarised in sections A, B and G below. "Lane (R31)" in a *Same results* cell means the input is read from Bloomberg in the lane and its effect is measured at the model level there.

## 0. The map

| Lane | Models | Status | Owner document |
|---|---|---|---|
| **Nowcast** (next monthly print, decided on release eve) | BASE (HARD_BASE), HALF, FULL, Category Raw; consensus as the benchmark | operating (BASE), challengers (HALF, FULL, Category Raw) | `CZK_CPI_FORECASTING_LATEST_MODELS_2026-09-14.md` |
| **Path** (h0–h12 monthly, annual rates) | R27 research path; its predecessor R24; FAST reference; the current-core presentation frame; the R29B core phase rule (research, not promoted); the R26 benchmark family | research roster | `R27_RESULTS_2026-09-20.md`, `R26_RESULTS_2026-09-18.md`, `R29_RESULTS_2026-09-20.md` |
| **CNB lane** (conditioned; never inside the independent forecast) | comparison at report dates, lead test, ledger, revision tracker, the rounds page | evaluation | `CNB_TRACKER_RESULTS_2026-09-17.md`, artifact `4Wo4R9YeuJoRXDry2UVgcL` |
| **Declared, prospective** | R30B January spirits steps (nowcast); R29B (path) | to be scored on future prints | `R30_RESULTS_2026-09-20.md` |
| **Input lane** (Bloomberg bundle for every roster model) | bundle builder, nowcast runner, path runner | declared source from 22 September | `R31_RESULTS_2026-09-22.md` |
| **Retired or superseded** | path_live F1b/F2/E7 lines, the TVW-QRF paper lane, INDEPENDENT_BRIDGE, the weekly nowcast (removed 13 Sep), LEGACY/SENTIMENT nowcasts (survey-based; comparison only) | not on the roster | inventory rows kept for reference |

## A. Nowcast lane

**A1. BASE** — the independent next-print forecast. Five block forecasts added with the basket weights of the month plus a reconciliation wedge: core (ridge on the CNB core m/m and a small feature set), food (X-13 plus ridge on food m/m, farm prices, food PPI), administered (ten-year calendar median with the January announcement gate), alcohol and tobacco (expanding same-month mean), fuel (measured from the weekly pump-price survey). RMSE .418 all / .219 from 2024 / .173 flash era, consensus .382 / .241 / .195. Code: `cz_struct.py` (STRUCT_EVE frame), recorded backtest `output/cz_struct_backtest.csv`, current forecasts `output/independent_nowcast_forecasts.csv`.

**A2. HALF and FULL** — BASE plus half or all of a quantile-forest correction of the core error learned from past core errors. FULL is the surprise-capture challenger (9 material wins / 2 losses on the 23 large surprises). Same inputs as BASE plus the error history.

**A3. Category Raw** — BASE with core split into its 2015+ CPI categories. Accuracy challenger (.409 / .198 / .161). Inputs: BASE's plus the CZSO category levels (`data/research_r18/categories`).

**A4. R30B** — declared 20 September: January spirits excise steps added to the alcohol-and-tobacco block; prospective from January 2027.

Inputs of BASE (and of HALF, FULL and Category Raw, which share them), with the Bloomberg verdict of the 13 September inventory:

| Block | Input | Source today | Bloomberg | Verdict | Same results |
|---|---|---|---|---|---|
| core | CNB core m/m (level and lags 1, 2, 12) | ARAD fixture | CZCIXM Index | **exact** (235/235) | identical by construction |
| core | month-to-date EUR/CZK (live) | CNB daily fixings | EURCZK CNB Curncy | **exact** since 2010 | identical |
| core | monthly EUR/CZK m/m (`eurczk_mm`) | CNB monthly average | monthly mean of EURCZK CNB | extremely similar (0.001 CZK; m/m gap ≤ .004 pp since 2015, .089 before) | lane (R31): 84% of months identical |
| core | import prices m/m, lag 2 | CZSO | CZEIIMOM Index | extremely similar (2 months differ by 0.1) | lane (R31) |
| core | services m/m, lag 1 (`services_l1`) | CZSO, average of six division index levels | none (CPSVCZM is not it) | different | **dropped (R31C)**: without it BASE scores .4162 against .4181 over the 90 prints, .2212 against .2208 from 2024, every tally unchanged; FULL 9/2 → 7/3 on large surprises |
| core | regime state (trailing y/y > 4%) | compounded extended headline | CZCIPY / CZCPYOY | similar (one month, 2007-11, differs at the threshold in the bundle) | lane (R31) |
| core | calendar dummies | — | — | static | — |
| food | food m/m (lags 1, 12) | CZSO 2015=100 index | CZCPFMOM Index | extremely similar (rounding ≤ .105) | lane (R31) |
| food | farm-price basket m/m (lags 0, 1) | CZSO CEN0203B | none (CZPPAMOM ended 2017) | not on Bloomberg | stays CZSO |
| food | food-products PPI m/m, lag 1 | CZSO CEN0201B division 10 | CZPPA10M Index | extremely similar (rounding ≤ .100) | lane (R31) |
| administered | CNB regulated m/m | ARAD fixture | CZCIRM Index | **exact** (235/235) | identical |
| administered | January announcement ledger; energy item weights | hand-maintained documents; CZSO basket | none | documents / static | stays |
| alcohol & tobacco | division 02 m/m | CZSO 2015=100 index | CZCPAMOM Index | extremely similar (rounding ≤ .105) | lane (R31) |
| fuel | weekly petrol 95 and diesel prices | EC Weekly Oil Bulletin via Bloomberg (R31C default; CZSO CENPHMT survey before) | ECOBETCZ / ECOBOTCZ (exact to the path's panel) | different survey from CENPHMT: petrol within 0.2 CZK/l in 99.4% of weeks (max 0.48), diesel 99.2% (max 1.10) | **lane (R31C)**: T9 fuel block 0.201 against 0.217 over the 90 prints, 0.188 against 0.158 from 2024; headline within 0.001 in every sample, BASE prints within 0.020 pp |
| fuel | petrol share | CZSO basket | — | static | — |
| wedge, weight projection | fuel item m/m (07.2.2) | CP7FCZ via Bloomberg (R31C default; CZSO before) | CP7FCZ Index (HICP fuels, two-decimal index), m/m of the index | similar: 95% within 0.1 pp, max 0.157, mean 0.040 | **lane (R31C)**: BASE within 0.003 pp on every print, RMSE unchanged to four decimals |
| target, wedge, HALF/FULL error state | headline CPI m/m | CZSO 2015=100 index (FRED before 2015) | CZCIPM (2007–) / CZCPMOM (2015–) Index | extremely similar (rounding ≤ .13) | lane (R31): CZCPMOM from 2015-02, the frame's whole span |
| Category Raw | CPI category levels (2015+) | CZSO groups | CZSO division levels only; a few HICP classes | partial | stays CZSO |
| weights, clock | basket weights; release calendar | CZSO; hand-maintained | — | static | — |
| dropped by HARD | FMIE expectations; EC consumer expectations | CNB survey; ECFIN | none; EUA8CZ exact | — | not used by the independent models |

Count for BASE after R31C: 3 inputs identical on Bloomberg, 8 extremely similar (rounding), 1 similar (regime threshold), 2 similar and promoted (fuel item via CP7FCZ, pump prices via the EC bulletin), 1 dropped (services proxy), 1 not on Bloomberg (farm prices; plus the categories for Category Raw), the rest static or documents.

**Model-level parity, run on 21 September** (`tools/model_register_20260921/nowcast_parity.py` → `output/model_register_20260921_nowcast/`): BASE, HALF and FULL were re-run at all 90 recorded release-eve clocks from the frozen fixture frames (`forecast_independent.calculate`, the recorded code path; BASE reproduces the recorded numbers to 1e-4 at every print, HALF and FULL to 0.008 and 0.017 — the quantile forest), and then from the same frames with every input Bloomberg holds replaced by the Bloomberg series on the model's own transform: headline, food and alcohol m/m and their lags (CZCPMOM, CZCPFMOM, CZCPAMOM), core and regulated (CZCIXM, CZCIRM), import prices (CZEIIMOM), the EUR/CZK monthly mean of the CNB fixing, the regime state from the published y/y, the food-products PPI (CZPPA10M) and the EC bulletin pump prices. Kept from CZSO: the fuel item m/m (weights, wedge), the services proxy and the farm prices.

| | BASE | HALF | FULL |
|---|---|---|---|
| Largest change on any print, pp | 0.044 (Jan-22) | 0.051 | 0.075 |
| Mean absolute change, pp | 0.013 | 0.014 | 0.017 |
| Prints changed by more than 0.10 pp | 0 | 0 | 0 |
| RMSE all 90 prints, frozen → Bloomberg | .418 → .418 | .414 → .414 | .414 → .415 |
| RMSE from 2024 | .219 → .222 | .220 → .223 | .226 → .229 |
| RMSE flash era | .173 → .176 | .166 → .170 | .164 → .169 |
| Large surprises, material wins / losses (23) | 7 / 3 → 8 / 2 | | 9 / 2 → 8 / 2 |
| Alerts at 0.20 pp: count, direction right, W / L | 20, 14 → 21, 14 | | 23, 16, 9/10 → 24, 17, 9/9 |

Block contributions move by at most 0.036 pp (food), 0.026 (core), 0.023 (wedge), 0.020 (fuel), 0.014 (administered), 0.005 (alcohol and tobacco). The largest whole-forecast changes are the policy Januaries and the 2022 surge months, where the one-decimal published m/m rounds a large number. Verdict for the nowcast lane: **the same models, the same scores to within a few thousandths, no alert or large-surprise outcome flips**. Category Raw is BASE's non-core blocks plus a category core built from CZSO category levels: it inherits exactly BASE's non-core change (≤ 0.04 pp) and its core categories stay CZSO. Consensus is the benchmark and is not an input.

## B. Path lane

Every path keeps the independent BASE h0 and adds twelve months of block forecasts, compounded into annual rates from the origin's own history (R17 stack). The blocks are shared; the models differ in the core and food blocks only.

| Model | Core block | Food block | Fuel | Administered | Alcohol & tobacco | Status |
|---|---|---|---|---|---|---|
| **B1. R27 research path** (`FOOD_ECM_R27`) | FAST filter (R15) | R14B system + R24 fixed drift 2.6%/yr + R27 fixed producer-price gap correction, h1–6 | constant pump prices (R14 control) | ten-year calendar median + January gate | expanding same-month mean | research roster |
| B2. R24 path (`FOOD_NORM_SHIFT_R24`) | FAST filter | R14B + R24 drift | same | same | same | predecessor |
| B3. FAST (`STATE_FAST_R15`) | FAST filter | R14B system | same | same | same | reference |
| B4. current core + R27 food | R14B local-core filter | as B1 | same | same | same | presentation frame only |
| B5. R29B core phase rule (`CORE_LEVELPHASE_FIXED080_R29B`) | FAST filter pulled to 2% at 0.8 while producer-price momentum ≤ 2%/yr | as B1 | same | same | same | research line, not promoted (failed conditions 4 and 6 by a hair) |
| B6. R26 benchmark family | zero, seasonal-naive, SA-AR per block | — | — | — | — | the bar every candidate must clear |

Scores of the roster (annual-rate RMSE, pp): R27 h12 4.769 all origins / 0.659 from 2024; matched CNB pairs from 2024 0.405 (CNB 0.372). Block inputs and the substitution tests (all 90 origins, `output/model_register_20260921/`):

| Block | Input | Source today | Bloomberg | Verdict | Same results (test) |
|---|---|---|---|---|---|
| h0 | BASE nowcast | nowcast lane | — | see section A | follows the nowcast |
| core | CNB core m/m | ARAD fixture | CZCIXM Index | exact, 235/235 (T1) | **identical** by construction |
| administered | CNB regulated m/m | ARAD fixture | CZCIRM Index | exact, 235/235 (T2) | **identical** |
| administered | announcement ledger | documents | none | — | stays |
| fuel | weekly pump prices, petrol and diesel | EC Weekly Oil Bulletin files | ECOBETCZ / ECOBOTCZ Index ÷ 1000, Friday-stamped | exact, 1,081 weeks within 6e-6 CZK/l (T4a–b) | **identical**: fuel block re-run with the Bloomberg panel differs by at most 2e-5 pp at any (origin, h); the reproduction of the recorded FAST fuel path is exact (T4c–d) |
| fuel | petrol share | CZSO basket | — | static | — |
| food | CZSO food CPI level (division 01) | 2015=100 index, unrounded | CZCPF Index (2025=100, one decimal) | extremely similar: log levels differ by up to 0.15 (T5a) | **not identical**: the food system re-run with the Bloomberg level moves monthly food forecasts by up to 0.078 pp (RMS 0.027) and twelve-month sums by up to 0.096; recorded FAST food reproduced exactly with the frozen levels (T5b–c). Lane (R31): the R27 food block on CZCPF moves by at most 0.083 pp a month (mean 0.023) |
| food | farm-gate prices (agri4) | CZSO CEN0203B | none | not on Bloomberg | stays CZSO |
| food | food-products PPI level | CZSO product PPI | cumulated CZPPA10M (Σ 100·ln(1 + m/m), re-based; Eurostat EPT010CZ/EPTC10CZ are a different series) | extremely similar: log level within 0.31 (mean 0.13) | **lane (R31B)**: food block within 0.043 pp a month of R31, h12 4.767 / 0.655, CNB pairs 0.406 — promoted |
| food (R24, R27) | long food history 1995–2025 | CZSO division 01 | CPF1CZ / CPFOCZ are not it (43% / 29% of months within 0.1); CZCPF only from 2015 | partial | stays CZSO |
| alcohol & tobacco | division 02 m/m | CZSO 2015=100 index | CZCPA Index (level) / CZCPAMOM (published m/m) | extremely similar: m/m gaps ≤ .20 (level) / ≤ .105 (published) (T6a–b) | **not identical**: block forecasts move by up to 0.046 pp a month, twelve-month sums by ≤ 0.018; recorded FAST block reproduced exactly (T6c–d). Lane (R31): at most 0.049 pp |
| compounding, wedge, scoring truth | headline CPI m/m history | CZSO 2015=100 index (FRED before 2015) | CZCIPM (2007–) and CZCPMOM (2015–), identical to each other | extremely similar: 8.5% of months identical, max gap .13 (T3a–b) | **not identical, and the truth moves too**: R27 annual rates change by up to 0.21 pp at h3 (history months inside the window), 0 at h12; h12 RMSE 4.769 → 4.775 all origins and 0.659 → 0.631 from 2024 because the realised annual rates are recompounded from the rounded series (T3c). Lane (R31), scored on the unrounded truth: h12 4.768 all origins and 0.660 from 2024; h3 and h6 annual rates move by up to 0.19 pp through the rounded history months in the window, the blocks themselves by at most 0.055 |
| core (R29B only) | manufacturing PPI (Eurostat, A6 row 47) for the phase | Eurostat via the A6 panel | none exact (22 Sep probe of 62 tickers): EPP0BCCZ (domestic, mining + manufacturing) is the closest live series — momentum correlation 0.996, phase agrees at 88 of 90 origins; PPTXCZ (total) 69 of 90; OECZPEBV is the same series but ends in 2022; CZPPCM/CZPPCY are the CZSO one-decimal publication of the aggregate | similar | **not identical**: two origins flip with EPP0BCCZ (2023-03, 2024-08); 21 with PPTXCZ (T7c); map document row 47 |
| weights | basket weights | CZSO | — | static | — |

Reading: the path lane's information content is already on Bloomberg for core, regulated prices and fuel (identical results); the three CZSO index series (headline, food, alcohol) are on Bloomberg only in published one-decimal form, which moves the paths by a few hundredths of a point and, more importantly, redefines the scoring truth; farm prices, the food PPI level, the long food history and the manufacturing PPI are not on Bloomberg. The lane (R31) reads all of the first two groups from Bloomberg and keeps the third; its R27 path scores 4.768 / 0.660 at h12 and 0.410 on the CNB pairs (recorded 4.769 / 0.659 / 0.405).

## C. CNB lane

CNB Monetary Policy Report tables (`data/cnb_mpr_tables_20260917`, 19 reports, bold = forecast), the announcement ledger, the release calendar and the tracker's assumptions read cnb.cz and hand-maintained files. Nothing here is on Bloomberg and nothing here enters the independent forecast.

## D. What one Bloomberg refresh would cover today, and what it would not

Covered exactly: CNB core and regulated m/m; the CNB EUR and USD fixings; the EC pump-price panel; ECFIN's ESI and household expectations (not used by the independent models); Eurostat total PPI and the unemployment rate (CNB-paper lane). Covered up to publication rounding: headline, food and alcohol CPI (one-decimal 2025=100 levels and published m/m), import prices, the food-products PPI m/m, M3, PRIBOR, Brent (monthly mean). Covered by a different survey with an immaterial measured effect: the nowcast's weekly pump prices (T9). Not covered: farm-gate prices, the food-products PPI level, the CZSO services groups and CPI categories (Category Raw), the long 1995+ food history, the manufacturing PPI, FMIE and LUCI, the CNB report tables, and every hand-maintained document (ledger, excise calendar, release calendar).

Two consequences for "the same results". First, where the source changes the *truth* (the CPI index itself), the choice is not about accuracy but about which series the scoring is defined on; the register recommends keeping the unrounded CZSO index as the truth and treating the Bloomberg one-decimal series as a live proxy. Second, the fuel block of the nowcast reads a different survey from the path's (CZSO CENPHMT against the EC bulletin); moving it to the EC bulletin changes the block's numbers by up to 0.7 on six of 90 months and the headline RMSE by less than 0.001 pp (T9), so it is a source swap with a measured, immaterial effect rather than identical results. ARAD (the CNB database) is not an alternative for what CZSO alone holds: it republishes CZSO's divisions and aggregate indices, not the product-level farm prices, the CPI class detail or the weekly pump survey.

## E. Open item

The live loader switch. The lane (section G) is the declared source: a bundle built from Terminal snapshots and two runners that take the roster through it. Production still reads CZSO and ARAD through `cz_struct.load_all` (DuckDB-backed); pointing it at the bundle's frames is the remaining change, with a known answer: the exact inputs (core, regulated, fixings, pump prices) switch without a further check; the rounding-only inputs switch with the differences measured in R31; the fuel item m/m, the services proxy, the farm prices, the CPI categories and the long food history stay on the CZSO API. No ARAD pull remains for the operating models after the switch. One design point is open for the live path: the known months of a compounding window should come from the index level rather than the rounded m/m (R31, path section).

## G. The Bloomberg input lane (22 September, R31)

`tools/bloomberg_lane/build_bundle.py` writes the input frames of every roster model in their own schemas from the 12 and 22 September Terminal snapshots, with a provenance entry per column (ticker, transform, months from Bloomberg, months kept from the previous source, largest gap) and a hash manifest; `run_nowcast.py` takes BASE, HALF and FULL through `forecast_independent.calculate` at the 90 recorded release-eve clocks (variant A with the CZSO pump survey, variant B with the EC bulletin); `run_path.py` takes the R27 research path through the 90 origins with the core and administered blocks reused from the recorded FAST rows and the fuel, alcohol, food and h0 blocks re-run on the bundle. Whole-model differences against the recorded results (details and the truth question in `R31_RESULTS_2026-09-22.md`):

| | Recorded | Lane | Largest change |
|---|---|---|---|
| BASE RMSE all / 2024+ / flash | .418 / .219 / .173 | .418 / .221 / .176 | 0.044 pp on one print |
| HALF | .414 / .220 / .166 | .414 / .222 / .170 | 0.050 |
| FULL | .414 / .225 / .164 | .415 / .229 / .169 | 0.075 (four prints above 0.05) |
| Large surprises, wins / losses (BASE, HALF, FULL) | 7/3, 7/1, 9/2 | 8/2, 8/1, 9/2 | flips at the 0.15 line only |
| Alerts, right, W / L (FULL) | 23, 16, 9/10 | 24, 17, 9/9 | one print crosses 0.20 |
| R27 h12 annual-rate RMSE, all / 2024+ (unrounded truth) | 4.769 / 0.659 | 4.768 / 0.660 | 0.024 pp |
| R27 h3, h6 from 2024 | 0.507 / 0.463 | 0.524 / 0.486 | 0.19 / 0.16, the rounded history months in the window; blocks ≤ 0.055 |
| CNB pairs from 2024, 1Q / 4Q (CNB 0.372 / 0.426) | 0.405 / 0.537 | 0.410 / 0.543 | — |

R31B (same day, `tools/bloomberg_lane/food_ppi_variant.py`, bundle `data/bloomberg_inputs_20260922_foodppi/`, run `output/bloomberg_lane_20260922_foodppi/`): the path's food-products PPI level from cumulated `CZPPA10M` — food block within 0.043 pp of R31, h12 4.767 / 0.655, CNB pairs 0.406 / 0.538; promoted, and that bundle supersedes R31's for the path (nowcast frames identical).

R31C (same day, `tools/bloomberg_lane/r31c.py`, run `output/bloomberg_lane_20260922_r31c/`): the nowcast without `services_l1`, with the fuel item from `CP7FCZ` and the EC-bulletin pump prices — BASE .4181 → .4159 over the 90 prints, .2208 → .2219 from 2024, tallies unchanged; FULL .4150 → .4194 and 9/2 → 7/3 on large surprises; the declared rule (BASE) passes and the set is the default.

Left outside Bloomberg by the lane after R31C: the farm prices (the one live CZSO pull), the 1995–2014 food history (static file), the CPI category levels (Category Raw, challenger), the basket weights, the release calendar, the announcement ledger, and the manufacturing PPI of the R29B research line.

## F. Files

`R31`: `data/bloomberg_inputs_20260922/` (`MANIFEST.json`, `provenance.json`, `nowcast/*.csv`, `path/*.csv`), `output/bloomberg_lane_20260922/nowcast/` (`run_variant_A.csv`, `run_variant_B.csv`, `comparison.csv`, `scores.csv`, `summary.json`, `manifest.json`), `output/bloomberg_lane_20260922/path/` (`path_rows.csv`, `audit.csv`, `scores.csv`, `summary.json`, `manifest.json`), logs `output/bloomberg_bundle_20260922_build.log`, `output/bloomberg_lane_20260922/{nowcast_run,path_run}.log`. `R31B`: `data/bloomberg_inputs_20260922_foodppi/`, `output/bloomberg_lane_20260922_foodppi/path/` (same layout), `output/bloomberg_lane_20260922_foodppi/comparison/` (`rows.csv`, `by_horizon.csv`, `scores.csv`, `audit.csv`, `summary.json`, `manifest.json`), logs `bundle_build.log`, `path_run.log`, `comparison.log`. `R31C`: `output/bloomberg_lane_20260922_r31c/` (`run_C1.csv`, `run_C2.csv`, `run_C123.csv`, `comparison.csv`, `scores.csv`, `path_rows.csv`, `path_scores.csv`, `summary.json`, `manifest.json`), log `output/bloomberg_lane_20260922_r31c_run.log`.

`output/model_register_20260921/register.csv` (107 rows: lane, model, block, input, source, Bloomberg, verdict, same-results, evidence), `tests.csv` (23 tests), `T3_headline_substitution_rows.csv`, `T4_fuel_block_rows.csv`, `T5_food_block_rows.csv`, `T6_alcohol_tobacco_block_rows.csv`, `T7_r29b_phase_rows.csv`, `T9_nowcast_fuel_block_rows.csv`, `details.json`, `manifest.json`; `output/model_register_20260921_nowcast/` (`substitutions.csv`, `frozen_run.csv`, `bloomberg_run.csv`, `comparison.csv`, `scores.csv`, `summary.json`, `manifest.json`).
