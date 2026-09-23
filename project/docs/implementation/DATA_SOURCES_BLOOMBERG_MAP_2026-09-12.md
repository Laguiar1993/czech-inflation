# Model data sources and Bloomberg coverage

Working document, 12 September 2026, updated after sixteen Bloomberg Terminal probe rounds and a strict equality test the same day.

The goal is to source model data from Bloomberg wherever the same, or extremely similar, data exist, and to minimise what is pulled from CNB ARAD, the CNB website and other sites, so that a single Bloomberg refresh updates the models. The inventory comes from the model code: `cz_struct.py`, `data/local_adapter.py`, `data/struct_inputs.py`, `forecast_independent.py`, the fixtures in `tests/fixtures/cleanup/`, the bridge, R14 and R14B runners, `models/path_inputs.py`, `path_live.py` with its step-2 and step-4 drivers, and the CNB-paper A6 catalog.

## Probe and tests

- **Snapshots.** `data/market_snapshots/20260912_bloomberg_probe`, `_probe2` … `_probe16`, each immutable, with request, coverage, metadata, history and search results; configs are `tools/market_data/probe_round2_20260912.json` … `probe_round16_20260912.json`. Histories start in 1990, except round 16, which sets the new `history_start` option to 1980 for the CNB-paper survey tickers. Round 13 holds only searches and one ticker that did not resolve (EUPPCZ Index), so it has no coverage or history file. Ticker validity for rounds 1–12 and 14 is in `output/bloomberg_probe_comparison_20260912/ticker_validity.csv`.
- **Tools.**
  - `tools/market_data/probe_bloomberg_candidates.py` pulls reference fields and history in the Bloomberg-enabled anaconda Python.
  - `tools/market_data/compare_bloomberg_exactness.py` tests equality on the transform each model uses (published rate, level, monthly mean, month-end value, log change) and writes `output/bloomberg_probe_comparison_20260912/exactness/exactness.csv` and `eurczk_cnb_fixing_by_year.csv`.
  - `tools/market_data/compare_bloomberg_probe.py` and `compare_bloomberg_followup.py` hold the earlier tolerance comparisons (`comparisons.csv`, `followup/`).
  - The CNB-paper survey and hard-data mirrors were validated on 12 Sep in `output/cnb_paper_candidate_validation_20260912/` (`bcs_candidate_verdicts.csv`, `hard_candidate_checks.csv`).
- **User's ticker list.** `data/bloomberg_catalog/cz_terminal_tickers_20260912.csv`.
- **Verdicts** (tool definitions):
  - **Exact:** every overlapping observation equal.
  - **Extremely similar:** at least 90% of observations equal once the reference is rounded to the decimals Bloomberg publishes, with no gap above 1.5 units of that decimal; or, without a published precision, at least 95% within the stated tolerance and none above five tolerances.
  - **Similar:** correlation of the model transform at least 0.98.
  - **Different:** anything else.
- **Windows.** The tool's verdict uses the full overlap. Several ARAD and CNB series differ only in the 1990s or on a handful of dates, so the tables below say when a series is exact from a given year; `exactness.csv` carries exact shares and largest gaps from 2000 and from 2015.

## ARAD and CNB inputs

| Input (current source) | Used by | Bloomberg | Result |
|---|---|---|---|
| CNB core inflation m/m (ARAD SCPIMZM09MOMPECNA) | nowcast, bridge, R14B | **CZCIXM Index** | **Exact**: 235 of 235 months, 2007-01 to 2026-07 |
| CNB regulated prices m/m (ARAD SCPIMZM02MOMPECNA) | nowcast, bridge, R14B | **CZCIRM Index** | **Exact**: 235 of 235 months |
| CNB EUR/CZK fixing, daily (cnb.cz year files) | live month-to-date FX (nowcast, bridge), R14 fuel | **EURCZK CNB Curncy** | **Exact since 2010**: 99.91% of 5,682 common days since 2004; the five differing days are four in 2004 and 3 Feb 2009 |
| CNB EUR/CZK monthly average (`monetary.fx_monthly`; the frozen path input `eurczk` equals it) | independent path FX driver, path_live and gap-model drivers | monthly mean of **EURCZK CNB Curncy**, rounded to 3 dp | **Extremely similar from 2008**: 2011–2026 180 of 188 months identical, the other eight differ by 0.001 CZK; 2008 and 2010 within 0.003; 2009 within 0.019; 1999–2007 up to 0.071 CZK |
| m/m of that monthly average (nowcast `eurczk_mm`, path `fx_mm`) | nowcast, path drivers | m/m of the above | **Extremely similar since 2015**: 90% identical, largest gap 0.004 pp (since 2007: largest 0.089 pp) |
| CNB USD/CZK fixing, daily | R14 fuel | **USDCZK CNB Curncy** | **Exact since 2010**: 99.98% of 5,692 days; only 3 Feb 2009 differs |
| 2-week repo rate, month-end (ARAD SFTP01M11) | CNB paper row 55 | **CZBRREPO Index**, last value of the month | **Exact since June 2007**: 364 of 368 months; the four misses (2002-10, 2003-07, 2005-03, 2007-05) are 0.25 pp on rate changes around month-end |
| 3M PRIBOR, month-end (the paper runs already use PRIB03M; ARAD SFTP04M2106 is the official alternative) | CNB paper row 54 | **PRIB03M Index**, last value of the month | **Already Bloomberg.** Against ARAD: 2000–2014 identical; since 2015 94% identical, misses of 0.01 pp; 1990s up to 0.22 pp |
| 3M PRIBOR, monthly average (ARAD SFTP04M2206) | path_live, gap model | **PRIB03M Index**, monthly mean | **Extremely similar since 2000**: largest gap 0.014 pp (72–84% identical to the last digit); 1990s up to 0.53 pp (May 1997) |
| M3 stock (ARAD SMV5M108) | slow-block feature `m3_yoy` | **CZMSM3 Index** (CZK mn), y/y from the level | **Extremely similar**: y/y within 0.006 pp in every month 2003–2026 (90% identical). CZMSM3Y Index, the published growth rate, differs (mean gap 0.56 pp). |
| Import prices m/m (ARAD SIMCSUM2005PM01 + SIMCSUM2015PM01) | CNB paper row 26 | **CZEIIMOM Index** | **Extremely similar**: 231 of 233 months identical; Dec-2016 1.2 vs 1.3 and Jun-2017 −1.8 vs −1.9 |
| Brent, USD, monthly (the paper runs already use CO1 Comdty; ARAD MEDACOMOILXXUSBVALM is the alternative) | CNB paper row 60 | **CO1 Comdty**, monthly mean | **Already Bloomberg.** ARAD's series equals the CO1 monthly average within 0.005 USD in all 402 months |
| Rushin activity index (CNB) | CNB paper row 14 | **CZRUSHIN Index**, monthly mean of weekly values | **Extremely similar**: mean gap 0.001, largest 0.003, 218 months (validation output) |
| 10-year government yield, monthly average (ARAD SVSDM12) | CNB paper row 53 | GTCZK10Y Govt | Similar: never identical; mean gap 0.045 pp, largest 0.16 pp since 2015 |
| Household loans (ARAD SUCM102211XXX101101) | CNB paper row 59 | CZBLHHTV Index | Similar: y/y mean gap 0.33 pp |
| Trade balance (ARAD SVEVZM4) | CNB paper row 25 | CZCMTRBA Index | Similar in shape (correlation 0.993); levels differ |
| Non-financial corporate loans (ARAD SUCM100311XXX101101) | CNB paper row 58 | LONSCZNF Index | Different: ECB/MFI perimeter; y/y gaps up to 8.5 pp since 2015 |
| Real effective exchange rate, CPI and PPI deflated (ARAD SREERM103, SREERM101) | CNB paper rows 56–57, path_live E3 | OECZFRAA Index, 935.028 Index | Different: log m/m correlation 0.965 (CPI) and 0.90 (PPI) at best |
| Gas, industrial metals and food commodity prices (the paper runs already use Bloomberg monthly means: TTFGDAHD BCFV, BCOMINSP and BCOMAGSP Index, plus TTFGCY1 and FSBTY1 Index for rows 65–66, by user decision on 12 Sep; CNB's own ARAD indices MEDACOM…, 2018=100, were downloaded only as alternatives) | CNB paper rows 61–63, 65–66 | the same Bloomberg tickers | **Already Bloomberg.** They are not CNB's indices: log m/m correlation with ARAD 0.985 for metals, 0.91 for gas and 0.92 for food |
| Agricultural producer prices (ARAD MOPAAPPXXNAJYOYPECM; CZSO CEN02032) | CNB paper rows 43, 50–52 | none live (CZPPAMOM Index ended in 2017) | Not on Bloomberg |
| LUCI (ARAD MLUCLU…) | CNB paper rows 15–16 | none | Not on Bloomberg |
| FMIE inflation expectations, 1 and 3 years (CNB survey) | nowcast survey inputs, path_live, CNB paper rows 69–70 | none (security searches empty) | Not on Bloomberg |
| CNB forecast paths (Monetary Policy Reports) | path_live, evaluation | none | CNB only |

**What this means for ARAD and CNB pulls.**

| Decision | Series |
|---|---|
| Already Bloomberg in the CNB-paper runs (`data/paper_replication/paper_model_panel_20260912_luci/manifest.json`, `model_choice`) | building permits (row 13), unit labour costs (17), 3M PRIBOR month-end (54), Brent (60), gas (61), industrial metals (62), food commodities (63), one-year gas and Brent futures (65–66) |
| Replaceable now (exact or extremely similar over the window the models use) | core m/m; regulated m/m; EUR/CZK and USD/CZK daily fixings; EUR/CZK monthly average and its m/m from 2008; repo month-end; 3M PRIBOR monthly average from 2000; M3; import prices (row 26); Rushin |
| Stay on ARAD or CNB | FMIE; LUCI; CNB forecast paths; both REERs; corporate loans; agricultural prices |
| Similar only | 10-year yield; household loans; trade balance |

The FX history before 2008 would move by up to 0.071 CZK (about 0.2%) if rebuilt from Bloomberg; keeping the stored CNB history for those years avoids that.

## CZSO inputs

| Input (current source) | Used by | Bloomberg | Result |
|---|---|---|---|
| Headline CPI m/m (m/m of CZSO 2015=100 index) | nowcast target, bridge, paths | CZCIPM Index (2007+), CZCPMOM Index (2015+) | **Extremely similar**: equal in 96% of months once our input is rounded to one decimal; largest gap 0.10 |
| Headline CPI y/y | compounding checks | **CZCPYOY Index** | **Exact** against CZSO's published y/y (139 months) |
| CPI index levels, total and 13 divisions (2025=100) | aggregation | **CZCPI Index … CZCP13 Index** | **Exact** (139 months each); their m/m is not the model input (see "CPI index levels") |
| Food (01) and alcohol and tobacco (02) m/m | nowcast, bridge | CZCPFMOM Index, CZCPAMOM Index | **Extremely similar**: 94% and 95% equal at one decimal |
| Import prices m/m (CEN0301; CEN0303) | nowcast `import_l2`; path_live E7 | CZEIIMOM Index | **Extremely similar**: 98.5% and 99.1% identical; misses of 0.1 |
| Food-products PPI m/m (CEN0201B) | food block | CZPPA10M Index | **Extremely similar**: 98% equal at one decimal |
| R10 service groups: actual rent (041), catering (111), package holidays (098) | R10 category challenger | CP41CZ Index, CP1SCZ Index, CP96CZ Index (HICP) | **Extremely similar**: 100%, 98% and 96% of months within 0.1 pp |
| Fuel item (07.22) m/m | nowcast, bridge | CP7FCZ Index (HICP fuels) | Similar: 95% within 0.1 pp, largest 0.16 |
| Weekly pump prices (CENPHMT, Monday survey) | nowcast fuel block | ECOBETCZ Index, ECOBOTCZ Index (EC Weekly Oil Bulletin) | Different survey: petrol within 0.2 CZK/l in 99.4% of weeks (largest 0.48), diesel 99.2% (largest 1.10) |
| Industrial production (PRU01C, seasonally adjusted) | CNB paper row 12 | CZIPITS Index | Similar: growth mean gap 0.05 pp (different base year) |
| Accommodation (112) | R10 | CP1ACZ Index | Different (correlation 0.92) |
| Imputed rent (042), 11.9% of the basket | R10 | none (outside the HICP) | Not on Bloomberg |
| Services proxy (average of six divisions) | nowcast `services_l1` | none | Drop (R10) |
| Farm-gate prices (CEN0203B) | food block, R14B | none | Not on Bloomberg |
| LFS unemployment 15–64, release vintages | path lines (`un_d`), gap model | UMRTCZ Index (Eurostat 15–74) | Different: monthly-change correlation 0.45 against the trend-cycle series |
| Average nominal wages y/y (`czso.wages_headline`) | path_live E6 | CZNWYOY Index | Different: mean gap 0.31 pp, largest 2.0; the local table also carries a quarter value of 5 (see fragilities) |
| House prices (old apartments); construction PPI | housing channel; slow block | HOPICZI Index; CZPPCYOY Index | Different; construction PPI ticker ended 2017 |
| Building permits | CNB paper row 13 | Bloomberg raw permits candidate, as reported | Already Bloomberg in the paper runs; not validated against CZSO |

## Eurostat, ECFIN, EC and other inputs

| Input (current source) | Used by | Bloomberg | Result |
|---|---|---|---|
| Household expected and perceived inflation (BS-PT-NY, BS-PT-LY) | nowcast survey inputs; CNB paper rows 71–72 | **EUA8CZ Index, EUA7CZ Index** | **Exact** (236 and 380 months) |
| Economic sentiment indicator | survey nowcasts, path drivers | **EUESCZ Index** | **Exact** against ECFIN's official CZ.ESI (380 months). Our stored copies are older vintages (23–40% identical, largest gap 0.3). |
| 31 business and consumer survey rows (CZ, DE, PL) | CNB paper rows 1–10, 18–22, 29–42, 67–68 | EU… Index mirrors | **Exact** in every overlapping month, tested against the paper model's inputs with Bloomberg histories from 1980 (round 16). Bloomberg covers the full model history (1993–95; services from 2002) except 1980–84 for German rows 18 and 21 and Feb–Dec 1984 for row 20. |
| Euro-area expected and perceived inflation | CNB paper rows 27–28 | EUA8EMU Index, EUA7EMU Index | **Not the same**: the model reads Eurostat's EA20 series (ends Dec 2025), while Bloomberg matches ECFIN's euro-area series; 17% and 54% of months identical, largest gaps 1.1 and 0.3 |
| Unemployment rate, CZ and DE (une_rt_m SA) | CNB paper rows 11, 24 | **UMRTCZ Index, UMRTDE Index** | **Exact** over the full model histories (from 1993 and 1991) |
| Domestic PPI y/y, B-E36 | CNB paper row 44 | **EUPPCZY Index** | **Exact** (427 months) |
| Domestic PPI indices: total, mining, energy, water | CNB paper rows 45, 46, 48, 49 | **PPTXCZ Index, EPP00BCZ Index, EPP00DCZ Index, EPP036CZ Index** | **Exact** (439 months each, levels and m/m) |
| German HICP (2025=100) | CNB paper row 23 | GRCPHCPI Index | **Extremely similar**: Bloomberg rounds the level to one decimal (largest gap 0.05) |
| EC Weekly Oil Bulletin pump prices, with taxes | R14 fuel | **ECOBETCZ Index, ECOBOTCZ Index** | **Exact** (1,081 weeks, within 0.00001 CZK/l) |
| EC Weekly Oil Bulletin pump prices, net of taxes | R14 fuel | ECOBEFCZ Index, ECOBOFCZ Index | Petrol extremely similar (one week differs by 0.03); diesel similar (two weeks, largest 1.94) |
| Unit labour costs | CNB paper row 17 | Bloomberg quarterly nominal ULC candidate, as reported | Already Bloomberg in the paper runs; LCTQCZI Index is similar to Eurostat (mean gap 0.07 pp against nominal ULC per person) |
| Domestic PPI, manufacturing (C) | CNB paper row 47; R29B phase | **none exact.** 22 Sep 2026 probe of 62 tickers (`data/market_snapshots/20260922_bloomberg_ppi_probe{,2}`, `output/bloomberg_ppi_comparison_20260922/`): the Terminal's Eurostat family has manufacturing in every concept but the domestic one (EPT00CCZ total level, EPA00CCZ total m/m, EPN/EPC/EPD00CCZ non-domestic; EPP00CCZ, EPM00CCZ, EPY00CCZ do not resolve). Closest live: **EPP0BCCZ Index** (domestic, mining + manufacturing, B+C): m/m within 0.05 in 45% of months, max gap 1.07 (2023), six-month momentum correlation 0.996, R29B phase agrees at 88 of 90 origins (2023-03 and 2024-08 differ). OECZPEBV Index (OECD, manufacturing domestic) is a rebased copy of the same series (level within 0.1 of row 47 in every year, m/m within 0.05 in 64% of months) but stops in December 2022. CZPPCM/CZPPCY (CZSO manufacturing m/m and y/y, one decimal) are the CZSO publication of the same aggregate (m/m within 0.05 in 60%, max 0.20; y/y max 0.24). PPTXCZ (total B–E36) agrees on the phase at 69 of 90 only | Keep Eurostat for the research line; EPP0BCCZ is the live proxy if it is ever promoted |
| Labour cost index | path_step4 | LNTNCZ Index | Different (Bloomberg working-day adjusted, our file unadjusted) |
| Brent spot (EIA RBRTEd) | R14 fuel | CO1 Comdty (front-month future) | Similar only (daily gaps up to 29 USD) |
| Headline CPI 1991–2014 (FRED CZECPIALLMINMEI) | path models' long history | CZCIPM Index from 2007 only | Partial |

**Not from any vendor:**
- CZSO basket weights;
- the administered-price announcement ledger;
- release-calendar overrides;
- CNB report dates;
- publication-day rules.

**Vintages.** Bloomberg holds the latest revised values. Live refreshes get the current official data (ESI and survey revisions included), but as-published histories for backtests still come from our frozen fixtures and release archives.

## CPI index levels

- **Levels are identical.** CZCPI Index and the 13 division tickers equal CZSO's published 2025=100 indices in every month from 2015-01 to 2026-07, and already hold August 2026.
- **Their m/m is not the model input.** CZSO publishes each base to one decimal. The models difference the 2015=100 index (about 100–159); Bloomberg carries the 2025=100 index (about 64–102), so each month's m/m carries a different rounding error.

  | Headline, 2015–2026 | Value |
  |---|---|
  | Months where Bloomberg-level m/m equals the model input | 5% |
  | Mean / largest gap | 0.060 / 0.208 pp |
  | Gaps inside the combined one-decimal rounding band | 100% |
  | RMS against official m/m: 2015-base m/m / 2025-base m/m | 0.030 / 0.073 pp |

- **Consequence.** Use the published m/m and y/y tickers for rate inputs, and the level tickers only where a level is needed. Evidence: `followup/cpi_levels_vs_czso_2025base.csv`, `cpi_mm_from_levels.csv`.

## Services

- **Current input.** The nowcast's `services_l1` reads `cpi_czso.cpi_services`, the arithmetic average of the index levels of CZSO divisions 06, 08, 10, 11, 12 and 13. The builder's docstring says geometric mean, but the code averages levels. It is not an official services index and not base-invariant (up to 0.224 pp, R10).
- **ARAD split.** On 9 September (R10, `data/core_split/`) we pulled SCPICLEM03YOYPECNA (non-tradables excluding regulated prices) and SCPICLEM02YOYPECNA (other tradables excluding food and fuel), year-on-year only. Bloomberg has no equivalent: HICP services y/y differs from non-tradables (correlation 0.90, mean gap 0.93 pp), and searches for Czech tradable and non-tradable inflation return nothing.
- **CZSO service groups.** CZSO's own group indices are stored locally in `cpi_czso.cpi_long` (CEN0101E, 2015-01 to 2026-07): every COICOP 2018 group of divisions 01–05, 07–09 and 11, including actual rent (041), imputed rent (042), package holidays (098), catering (111) and accommodation (112). The five service groups are frozen for R10 in `data/core_split/monthly_levels.csv`. Bloomberg carries CZSO CPI only at division level (CZCPI … CZCP13); searches for the groups (round 15) return only Eurostat HICP tickers (CP41CZ, CP1SCZ, CP1ACZ, CP96CZ, CP1RCZ) and nothing for imputed rent.
- **R10 results (headline RMSE, all origins).**

  | Variant | RMSE |
  |---|---:|
  | BASE | 0.4180 |
  | Proxy removed | 0.4160 |
  | ARAD annual rates | 0.4125 |
  | Five categories, own dynamics | 0.4089 |

Evidence: `followup/services_candidates.csv`; `docs/CORE_SERVICES_REVIEW_2026-09-09.md`.

## Unemployment

- **Series.** CZSO's LFS general unemployment rate, ages 15–64, archived as released in `data/vintages/unemployment.csv.gz`: seasonally adjusted releases March 2018 to May 2025, trend-cycle and NSA tables since 2 June 2025.
- **Users.** Only the survey-free path lines (`un_d` in TARGET_U_FX_ML, BVAR_U_FX, RF_U_FX, path_live E2–E7) and the gap model. The frozen nowcast, INDEPENDENT_BRIDGE and R14B do not use it (`INCLUDE_WAGE = False`).
- **Bloomberg.** UMRTCZ Index is Eurostat's 15–74 SA rate: level gap 0.067 pp against CZSO's last SA vintage, but no first-release history. CZUEUR, OECZRUAX and OECZRUAW Index are quarterly and end in 2024. CZJLUNR Index is registered unemployment.

## REER against CNB ARAD

Log m/m is the paper's transform 2; daily tickers are averaged by month.

| Ticker | vs CPI REER: log m/m correlation / mean gap | vs PPI REER: log m/m correlation / mean gap |
|---|---|---|
| OECZFRAA Index (OECD, CPI-based) | 0.965 / 0.28 pp | 0.874 / 0.50 |
| 935.028 Index (IMF, CPI-based) | 0.956 / 0.29 | 0.903 / 0.47 |
| BISBCZR Index (BIS broad) | 0.956 / 0.36 | 0.871 / 0.57 |
| BREERCZK Index (Bloomberg Intelligence, from 2016) | 0.948 / 0.35 | 0.824 / 0.62 |
| BRERCZ Index (Bloomberg Economics) | 0.874 / 0.73 | 0.828 / 0.87 |

None is identical; J.P. Morgan REER tickers return no data on this Terminal. Evidence: `followup/reer_candidates.csv`.

## Traps found

- **EUR/CZK fixing.** Use **EURCZK CNB Curncy** and **USDCZK CNB Curncy**.
  - EURCZKF Curncy resolves to EURCZK6M, the six-month forward.
  - EURCZK F143 and EURCZK BFIX Curncy are Bloomberg's own fixings, identical to the CNB fixing on only about 2% of days; F143 has a 3.58 CZK jump on 24 Jun 2008.
  - EURCZK Curncy is the market close.
  - BOPCECZK, DKCFCZK and BFCFCZK Index are foreign central-bank fixings that ended in 2023, 2012 and 2001.
- **M3.** CZMSM3Y Index is the published growth rate, not the y/y of the stock; use CZMSM3 Index.
- **PPI.**
  - CZSO's PPI m/m tickers (CZPPMOM, CZPPBM, CZPPCM, CZPPDM, CZPPEM Index) are not the Eurostat domestic PPI the CNB paper uses; use PPTXCZ, EPP00BCZ, EPP00DCZ and EPP036CZ Index.
  - CZPPDM and CZPPEM stop in December 2025.
  - EPP00CCZ Index does not resolve.
- **Import prices.** CZEIE Index holds export prices; CZEII Index has an April 2016 splice (use CZEIIMOM Index).
- **CPI levels.** CZCPI, CZCPF, CZCPA and the division indices are one-decimal 2025=100 levels; their m/m matches official m/m in only 48–61% of months.
- **Look-alikes.** CPEXCZM Index is not CNB core, CPAPCZMM Index is not CNB regulated prices, and CZCIFM Index is not the CZSO fuel item.
- **Ended or quarterly series:**
  - CZPPAMOM and CZPPAYOY Index (swapped labels, end 2017);
  - CZPPCMOM and CZPPCYOY Index (2017);
  - OECZGSJM and OECZGSHA Index (2018);
  - CZUEUR, OECZRUAX and OECZRUAW Index (quarterly, 2024).
- **Vintages.** Stored ESI and survey copies are older vintages; UMRTCZ Index has no first-release history.
- **Euro-area surveys.** EUA8EMU and EUA7EMU Index match ECFIN's euro-area series, not the Eurostat EA20 series the CNB-paper model reads.
- **EC Oil Bulletin tickers** are quoted in CZK per 1000 litres and dated on Fridays.

## Fragilities found during the inventory

- **Live HARD depends on surveys it does not use.** A live HARD run calls the Eurostat survey loaders inside `load_all`, so a failed fetch stops it.
- **The live food-PPI fetch breaks R14/R14B verification.** It rewrites `data/cz_ppi_product_raw.csv`, a hashed R14/R14B input.
- **September calls fail closed.** The release calendar has no 2026-09 row.
- **The CNB FX parser breaks on some year files.** `local_adapter.fetch_cnb_daily_eur_fixings` fails when a year file repeats its header mid-year (2022 does).
- **The wage table looks wrong.** `czso.wages_headline` contains a quarter value of 5, and its nominal wage growth differs from CZNWYOY Index by up to 2 pp (2026Q1: 8.1 against 6.1). Check before any wage driver is used.

## Next steps

1. **Bloomberg input lane.** Build the nowcast and bridge inputs from the exact and extremely similar tickers above, including the EURCZK CNB monthly average, in a parallel lane; rebuild the fixture and check HARD_BASE parity.
2. **Decisions.**
   - FX history before 2008: keep the stored CNB values or accept gaps up to 0.071 CZK.
   - Services proxy; fuel item; unemployment.
   - REER, commodity indices and the 10-year yield in the CNB-paper model.
3. **Vintages.** Archive a monthly Bloomberg snapshot so as-published histories accumulate.
4. **Wage table.** Check `czso.wages_headline` against CZSO.
