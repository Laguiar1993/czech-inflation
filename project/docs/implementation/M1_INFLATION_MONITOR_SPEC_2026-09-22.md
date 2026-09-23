# M1 specification: Czech Inflation Monitor — contribution engine, base-effect ledger, monthly note

22 September 2026, Claude. Declared before the code; committed before the run. An analysis lane next to the models: nothing here changes a forecast model or the Bloomberg promotion discipline. The user's question of 22 September: what drives headline and core, which part of a move is base effect, what services contribute, and a one-page summary a person can read next to the models.

## Inputs (read only, hashed in the run manifest)

| Input | File | Use |
|---|---|---|
| CZSO national CPI groups, 37 COICOP-2018 groups, 2015-01 to 2026-07 | `data/research_r18/categories/monthly_levels.csv`, `series_metadata.csv` | group y/y, momentum, contributions |
| Basket weights, 2026 basket (all 37 groups mapped) | `data/research_r18/categories/basket_weights_long.csv` | contribution weights — used for every month (only the 2026 basket has a full concordance; earlier baskets are on other classifications). The residual headline − Σ contributions is reported as its own line, never absorbed |
| CZSO goods and services y/y | `data/core_split/broad_yoy.csv` | the official goods/services split |
| Headline y/y and m/m; core and regulated m/m; food level | Bloomberg snapshots: `CZCPYOY`, `CZCPMOM` (2015–) with `CZCIPM` (2007–2014), `CZCIXM`, `CZCIRM`, `CZCPF` | aggregates; core and regulated y/y compounded from m/m |
| Pipeline series | `EPP0BCCZ` (domestic PPI B+C), `CZEIIMOM` (import prices, cumulated), `CZPPA10M` (food PPI, cumulated), farm-price basket `agri4` from `data/bloomberg_inputs_20260922_foodppi/path/food_log_levels.csv` | readings and the lead-lag table |
| Roster path at the latest origin | `output/bloomberg_lane_20260922_foodppi/path/path_rows.csv` (R31B lane, origin 2026-07, `mm_lane` h1–h12) | the model m/m for the ledger |
| Latest CNB report and roster quarterly paths | `output/cnb_rounds_v3/replay_data.json` (report of 2026-08-13) | the CNB strip |
| Prints and consensus | `data/czcpmom_survey_history_extended.csv`, `output/independent_nowcast_forecasts.csv` | last print vs consensus vs recorded BASE |

## Blocks

Eight blocks from the 37 groups (weights of the 2026 basket, per mille): food & non-alcoholic beverages (01.1, 01.2; 168.6); alcohol & tobacco (02.1, 02.3; 82.9); household energy (04.5; 82.0); vehicle operation incl. fuel (07.2; 50.0); rents — imputed and actual (04.2, 04.1; 153.8); catering & accommodation (11.1, 11.2; 68.2); other services & mixed (04.3, 04.4, 05.6, 06, 07.3, 07.4, 08.3, 09.4, 09.6, 09.8, 10, 12, 13; 236.7); core goods (03.1, 03.2, 05.1–05.5, 07.1, 08.1, 09.1–09.3, 09.5, 09.7; 157.9). The eight sum to 1000. Composition is written to `blocks.json`. Eight blocks because the page's categorical palette validates eight adjacent slots; the table below the chart shows the 37 groups.

## Measures

For every group, block and the total: y/y from the index levels; contribution = weight⁄1000 × y/y (fixed-weight approximation of the CZSO contribution; the residual against the published headline y/y is shown); `d3_yy` = change of y/y over three months; `momentum_3m_ann` = 4 × Σ over the last three months of (m/m − seasonal norm of that calendar month) + Σ of the twelve monthly norms, where the norm is the median m/m of the calendar month over 2015–2019 and 2024–2025 (2020–2023 excluded as the shock years). Aggregates: headline (published y/y), core and regulated (compounded from the CNB m/m), CZSO goods and services, food.

## Base-effect ledger

For the twelve months after the last known headline m/m: the m/m dropping out (twelve months earlier), the seasonal norm, the model m/m (R31B path at the latest origin; the published value where the month is already known), the implied y/y under the norm and under the model, and the decomposition of each month's change in y/y: base effect = norm − drop-out, momentum = model − norm. A month is flagged "base effect" when |base effect| ≥ 0.7 × |change under the model| and the change is at least 0.2 pp.

## Pipeline and comparison strips

Latest y/y of the four pipeline series and a lead-lag table — corr(x at t−k, y at t), k = 0…12, on 2015–2026 and excluding 2021–2023 — for farm → food CPI, food PPI → food CPI, domestic PPI → core goods, domestic PPI → core, import prices → core goods, domestic PPI → services. The CNB strip: the latest report's quarterly path against the roster's quarterly means for the same quarters. Last print: actual, consensus, recorded BASE.

## Outputs

`output/inflation_monitor_20260922/`: `contributions.csv` (month × block: yy, contribution, d3_yy, momentum), `groups_latest.csv` (37 groups at the latest month), `base_effects.csv`, `pipeline_leadlag.csv`, `monitor_data.json` (everything the page needs), `blocks.json`, `note.md` (the one-page note, sentences filled from the numbers), `monitor.html` (page from `tools/inflation_monitor/template.html`), `manifest.json`. The page is published as an artifact ("Czech Inflation Monitor") and its URL recorded in the results document `INFLATION_MONITOR_M1_2026-09-22.md`.

## Not in M1 (declared for later)

Wages → services regression (M2), the demand block (M3), the exact CZSO contribution formula with December-based weights and the classification concordance for pre-2026 baskets, a live nowcast on the page (needs the production loader switch).

## Rules kept

Specification committed before code; code committed before the run; no hash-frozen file edited; every number on the page and in the note comes from the run's exported files.
