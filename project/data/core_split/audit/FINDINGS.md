# Czech CPI services input audit

Read-only source audit, 9 September 2026. All evidence was written beside this report. Neither the database nor repository code was changed.

## Verdict

`data.struct_inputs.load_services_cpi_mm()` does **not** load the official CZSO services index, and cannot serve as a core-services accounting target. It loads the monthly percentage change of a locally constructed, equally weighted arithmetic mean of six broad division indices. The five requested detailed service groups have usable continuous current-vintage histories and archived basket weights, subject to the scope and availability limitations below.

## Services proxy: reproducible proof

- Loader: `work/cpi-independent/data/struct_inputs.py:89-101` selects `cpi_czso.cpi_services`, all households (`0`), `base_2015_eq_100`, then computes `100 * pct_change`.
- Generator: `C:/Users/luis_/.agents/skills/em-macro-forecaster/scripts/pull_czso_opendata.py:258-286`. `SERVICES_DIVS` is `{06,08,10,11,12,13}`. The grouping uses `value=("value","mean")`; `weight_sum` is a division count. No CPI basket weights, core classification, regulated-price exclusion or tax correction enter this calculation. Its docstring incorrectly says “geometric mean”.
- Migration: `migrate_to_czechia_db.py:38-39,97-98` mirrors the generated tables from `inflation/czso_opendata.duckdb` into the consolidated `cpi_czso` schema. The generator was found in the durable skill scripts, not `economic_db/scripts/inflation` (that directory does not exist).
- Recomputing the arithmetic mean from `cpi_long` reproduces **all 834 stored services rows**, across the two household groups and three bases, to a maximum absolute difference of **5.68e-14**. Level-index rows use six divisions in every one of the 139 months, January 2015 to July 2026. The YoY-labelled rows use only three divisions in early history and up to six later.
- The same calculation using 2025-base indices produces a different monthly growth series: maximum difference **0.223955 percentage points**, mean absolute difference **0.041045 pp**. For April 2022, the 2015-base proxy gives **1.338670% m/m**, versus **1.114714%** with the 2025-base proxy. An average of independently rebased division indices changes its implicit weights. This base sensitivity is additional evidence against using it as an official expenditure-weighted aggregate.
- Scope errors are visible directly in the stored category labels. Entire divisions 04 (housing), 07 (transport), and 09 (recreation) are assigned to “goods”, thereby excluding actual/imputed rent, passenger transport, cultural/recreational services and holidays from the proxy “services”. Division 08, included as services, contains equipment subgroup 081. Division 13 explicitly includes miscellaneous goods as well as services.

Evidence: `arithmetic_proof.csv`, `numeric_summary.json`, `services_base_sensitivity.csv`, `division_mixture_labels.csv`, and numbered `source_excerpts.txt`. `queries.json` contains the exact read-only SQL.

## Detailed groups and the 2026 classification

All five requested groups have **139 distinct, gap-free months** in each level base, January 2015 to July 2026, hence 138 derived m/m observations from February 2015. All **695 frozen 2015-base level observations match the raw official CEN0101E file exactly**, with no duplicate keys. The raw header explicitly names `Klasifikace COICOP 2018`. The current raw file already uses the current classification throughout that history; no manual splice at January 2026 is warranted from these data.

| Group | Current CEN0101E subgroup | Basket code through 2024 | 2026 basket code | 2026 weight, per mille of headline |
|---|---|---|---|---:|
| Actual rent | 041 | 04.1 | 04.1 | 34.497805 |
| Imputed rent / owner housing | 042 | 04.2 | 04.2 | 119.295072 |
| Catering | 111 | 11.1 | 11.1 | 60.074047 |
| Accommodation | 112 | 11.2 | 11.2 | 8.090192 |
| Package holidays | 098 | 09.6 | 09.8 | 18.543302 |

**Do not select current subgroup 096 for holidays:** it is cultural services. Conversely, reading historical basket row 09.8 would miss the holiday weight. Older basket identifiers have an `E` prefix in the 2018–2024 files. Old division 12 is “Miscellaneous goods and services”; 2026 division 12 is insurance/financial services, with division 13 carrying personal/social care and miscellaneous goods/services. Broad divisions therefore also require a classification-aware mapping.

Evidence: `selected_calendar_audit.csv`, `selected_transition.csv`, `selected_category_levels.csv`, `raw_cen0101e_selected.csv`, and `basket_selected_rows.csv`. The raw-file excerpts contain both January 2015 and January 2026 under current group labels. This establishes continuity in the **current published history**; it does not prove that the same recut histories were available at historical forecasting origins, or establish an independently verified item-by-item concordance.

## Weights, availability and experiment implications

The isolated repository already contains seven detailed official basket workbooks: `data/baskets/spot_kos{2014,2016,2018,2020,2022,2024,2026}.xlsx`. Their headers say effective from January of the filename year, using constant weights from two years earlier. All requested group weights are present. The 2026 rows are E187 (actual rent), E199 (imputed rent), E714 (catering), E756 (accommodation), and E679 (holidays). Their numbers agree with the saved 2026 basket PDF (rent page 3; holidays and catering/accommodation page 9), visually checked. `basket_manifest.json` records workbook/PDF hashes, and `basket_selected_rows.csv` records sheet names and exact row numbers for every vintage.

The database's `cpi_weights` table contains only 66 headline/division rows for basis years 2016, 2018, 2020, 2022, and 2024. It does not contain these detailed weights. Its `first_seen_in_release` is the earliest release loaded locally, not proof of the first date the weights became public. Use the archived detailed workbooks with the established publication gate, not the table's `basis_year` as an effective or availability date.

The existing `_basket_available_from` uses the January detailed-release date, falling back to February 15 outside the calendar. The helper normalizes that date to midnight; a strict intraday experiment should retain the detailed-release hour, 09:00 Prague. This is the existing reconstruction rule, not an independently established historical publication timestamp for every basket. The CEN0101E metadata likewise has no release timestamp or retained vintages: the present metadata records a 7 September 2026 refresh, July 2026 last observation. Freeze this snapshot and label auxiliary category histories as current-vintage reconstructions.

Recommended treatment:

1. Keep this local division proxy out of an official core goods/services partition. If retained as a predictor, name and document it as a broad division proxy. Preserve the fixed R9 baseline as requested.
2. Use 041, 042, 111, 112 and 098 as a small, predeclared auxiliary services experiment, with explicit publication eligibility, classification-aware weight lookup and previous-month price updating when constructing contributions.
3. Do not equate their sum with official core services. CEN0101E lacks the core/regulation/tax flags needed for that identity, and broad catering includes canteens and schools. For example, 2026 catering contains 12.764376 per mille in canteens, of which 5.737985 is school canteens. The available 111 history does not separately identify restaurant-only inflation. An exact CNB-core partition still requires the official scope/concordance and corresponding tax treatment; otherwise label the aggregation as an estimated projection.

Canonical model inputs are `monthly_levels.csv` (139 rows by five named groups, base 2015=100), `selected_basket_weights.csv` (35 long-form rows), and `canonical_metadata.json` (scope, mappings, source hashes and availability assumptions). `manifest.json` records retrieval time, raw CEN0101E hash, database metadata and generator/loader hashes. Reproduce database checks with `audit_services.py` using DuckDB/pandas, workbook/PDF extraction with `audit_baskets.py`, and canonical freezing/verification with `freeze_canonical_inputs.py` using the bundled runtime. `evidence_manifest.json` hashes every saved evidence file.
