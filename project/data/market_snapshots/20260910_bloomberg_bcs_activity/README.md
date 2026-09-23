# Bloomberg BCS and Czech activity snapshot — 10 September 2026

This snapshot was pulled through the local Bloomberg Desktop API (`xbbg.blp.bdh`/`bdp`) while the terminal was connected. It contains the Czech detailed European Commission business and consumer survey series supplied for the CNB WP 9/2026 predictor audit, Czech unemployment and the CNB Rushin activity index. The industrial-production YoY capture was removed after the definition audit; `CZIPITN Index` is listed as a pending replacement in `request.json`. The history runs through 9 September 2026 (the previous Prague calendar day).

## Important correction found during the pull

`EUB5F6CZ Index` is **the construction factor “other”**, not financial constraints. The financial-constraints series is `EUB5F7CZ Index`. The snapshot keeps `EUB5F6CZ Index` under the explicit diagnostic name `building_constraint_other_diagnostic` so the original request is preserved, but it must not be used for paper variable 9. `EUB5F4CZ Index` is the labour-shortage series and is included for paper variable 7.

## Files

- `daily.csv` — raw `PX_LAST` histories returned by BDH. The survey and macro series are monthly observations dated at month end; Rushin is weekly.
- `raw/*_bdh.csv` — one untouched BDH response per ticker.
- `raw/*_bdp.csv` — reference fields captured at the same run, including Bloomberg description, source and current `PX_LAST`.
- `coverage.csv`, `metadata.json`, `errors.json`, `request.json`, `MANIFEST.json` — coverage, metadata, request and integrity records.
- `ticker_mapping.csv` — paper-variable mapping, transformations and audit notes.

## Mapping and timing

The paper’s `T0`/`T3` labels are transformation codes, not release lags. For the paper replication, `T3` means the month-to-month difference in the reported percentage-point series. The BCS factor-limitation series are percentages of construction firms, whereas the BCS activity series are answer balances; preserve the raw units before transforming.

Bloomberg omitted currency and quote-unit fields for the dimensionless BCS and Rushin indices; no currency conversion is applied. The BDH observation date is a period/quote date. It is not proof of the original publication timestamp, and Bloomberg’s current-vintage history may include later revisions. Keep a separate release calendar and `available_from` field before using any series in a real-time backtest. Rushin’s native observations are weekly; the paper’s monthly panel needs an explicit aggregation rule (the existing public-data adapter uses a monthly mean). For a live origin, do not use later weeks from the same month.

The previous `CZIPITWY Index` capture has been removed from this snapshot: Bloomberg identified it as an industrial-production WDA year-on-year rate, not the fixed-base level required by paper variable 12. The selected replacement is `CZIPITN Index`, which is pending a Bloomberg pull and metadata check. Do not use an industrial-production growth rate in the paper's level slot.

`CZGRIDX Index` is the user-supplied building-permits candidate for paper variable 13. The identifier is known, but its statistical definition is not yet verified. Keep the raw observations and release dates first, then classify the series as a direct monthly total count, a January-to-date cumulative count, a fixed-base index, a YoY rate, a permit-value series or a dwelling count. Only the total Czech permit-count concept is eligible. If the series is cumulative, convert it within each calendar year by `monthly_t = cumulative_t - cumulative_{t-1}` (January equals the January cumulative value); a direct monthly count needs no differencing.

`LCTQCZI Index` is the selected quarterly nominal unit-labour-cost input for paper variable 17; `LCTOCZI Index` is retained as an annual benchmark. Neither has been pulled in this snapshot. The quarterly series must be temporally disaggregated prospectively; annual observations must not be repeated as monthly inputs.

`LONSCZNF Index` is the user-supplied candidate for paper variable 58, the Czech non-financial-corporation loan balance. It is pending a definition check. Accept it only if Bloomberg identifies an outstanding nominal stock for Czech-resident NFCs, with the intended bank/MFI perimeter, monthly month-end frequency and a positive level. Record whether it is seasonally adjusted. Compare its level and log difference with the ARAD VST total; retain both if their perimeters differ.

`EUB3CZ Index` is the user-supplied candidate for paper variable 37 (construction employment expectations). It is pending a Bloomberg definition check and pull; confirm that the long name is the seasonally adjusted percentage-balance question for employment expectations over the next three months, and record its release timing before using it in a real-time model.

`EUS3CZ Index` is the user-supplied candidate for paper variable 30 (services demand expectations). Bloomberg's “month ahead” wording is treated as a legacy label pending verification against the official `BS-SAEM` question, which covers the next three months. The 11 September capture also confirms `EUS5CZ Index` as the services-employment expectation candidate; the official `BS-SEEM` comparison remains the final definition check.

`CZRUSHIN Index` starts in June 2008, so it cannot by itself reproduce a May 2002-start paper panel without an explicit missing-data or backcast rule. Do not fill its pre-2008 history with zeros.

The extended Bloomberg definitions in `definition_check_bdp.csv` show that several supplied mnemonics are broad or adjacent questions: `EUS1CZ`, `EUS2CZ`, `EUR1CZ` and `EUB1CZ` do not use the exact past-three-month wording in their long names, and `EUCCCZ` is the broad consumer-confidence indicator rather than the detailed financial-situation expectation. They are retained as labelled proxies until the exact EC question tickers are found. The European Commission BCS source and metadata are available from the official [BCS time-series portal](https://economy-finance.ec.europa.eu/economic-forecast-and-surveys/business-and-consumer-surveys/download-business-and-consumer-survey-data/time-series_en). CNB’s official Rushin page describes the index as weekly and built from high-frequency and monthly indicators: [The Rushin](https://www.cnb.cz/en/economic-research/the-rushin-an-index-of-czech-economic-activity/index.html).


