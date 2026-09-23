# Czech CPI: Bloomberg data refresh — 9 September 2026

**Successfully pulled through the local Bloomberg Terminal using xbbg BDH and BDP.**

The archive contains 91,603 daily observations across 15 securities. The requested window starts in 2000 (1998 for FX); the table shows the actual history returned. All histories end on 8 September 2026. Today’s live quotes are saved separately.

| Bloomberg security | First observation | Last observation | Daily observations | Last historical PX_LAST | Unit |
|---|---|---|---:|---:|---|
| FSBTY1 Index | 2013-07-17 | 2026-09-08 | 3,430 | 82.54 | USD/barrel |
| TTFGCY1 Index | 2013-04-02 | 2026-09-08 | 3,493 | 56.138 | EUR/MWh |
| CO1 Comdty | 2000-01-04 | 2026-09-08 | 6,856 | 97.92 | USD/bbl. |
| USDCZK Curncy | 1998-01-01 | 2026-09-08 | 7,483 | 20.8119 | CZK per USD |
| EURCZK Curncy | 1999-01-04 | 2026-09-08 | 7,222 | 24.192 | CZK per EUR |
| CO7 Comdty | 2000-01-04 | 2026-09-08 | 6,858 | 83.25 | USD/bbl. |
| CO13 Comdty | 2000-01-17 | 2026-09-08 | 6,005 | 77.94 | USD/bbl. |
| PRIB03M Index | 2000-01-03 | 2026-09-08 | 6,741 | 3.87 | % |
| CKFR0CF Curncy | 2000-01-04 | 2026-09-08 | 6,917 | 4.083 | % per annum (rate quote) |
| CKFR0FI Curncy | 2000-01-04 | 2026-09-08 | 6,911 | 4.403 | % per annum (rate quote) |
| CKFR0I1 Curncy | 2000-01-04 | 2026-09-08 | 6,912 | 4.508 | % per annum (rate quote) |
| CKFR011C Curncy | 2002-07-17 | 2026-09-08 | 5,968 | 4.603 | % per annum (rate quote) |
| CKFR1C1F Curncy | 2002-07-17 | 2026-09-08 | 5,848 | 4.63 | % per annum (rate quote) |
| CKFR1F1I Curncy | 2004-02-25 | 2026-09-08 | 5,488 | 4.645 | % per annum (rate quote) |
| CKFR1I2 Curncy | 2004-02-25 | 2026-09-08 | 5,471 | 4.668 | % per annum (rate quote) |

## What is ready for the models

- The two requested annual energy indices are preserved under their exact Bloomberg identities.
- USD/CZK and EUR/CZK allow same-observation-date conversion into Czech crowns. Missing FX is not filled.
- Brent CO1, CO7 and CO13 are refreshed as separate reference and legacy features.
- Three-month PRIBOR and seven FRA quotes cover the existing 3×6 through 21×24 rate-curve inputs.
- Separate monthly averages and month-end observations are available. September is explicitly month-to-date.

## How to use the files

The accompanying ZIP contains raw Bloomberg responses, a wide daily panel, a separate live-quote table, derived daily inputs, monthly panels, coverage, metadata, hashes, preprocessing tests and the refresh scripts. It can be copied to the other computer and read offline; future BDH refreshes require that computer’s own Bloomberg connection.

The data are staged for the new path experiments. The frozen nowcast, historical backtests and existing path forecasts have not been recalculated or promoted by this data-only update. No inflation survey was added as a model input. Bloomberg composite FX quotes do not silently replace official CNB fixings.

## Interpretation and timing

**Annual energy strips:** Bloomberg identifies the Brent series as a commodity fair-value series and gas as a TTF forward series. The verified units are USD/barrel and EUR/MWh. The general reference descriptions do not independently establish an exact constant-twelve-month delivery rule. We preserve the user-selected Year 1 indices; they are distinct from CO13 and do not by themselves provide all monthly delivery prices from h0 to h12.

**Historical availability:** this is history downloaded today, not data vintages archived in 2013–2026. The preprocessing assumes a dated quote is usable from the following calendar day in Prague. That is an explicit availability assumption, not a verified historical publication timestamp. Current BDP metadata and live values must never be carried backward into a historical forecast.

**Coverage:** both new annual series begin in 2013. Compare new specifications on common eligible forecast origins; do not fill earlier years with another contract under the same name. Some early long-tenor FRA and CO13 histories have gaps. Each series retains its own dates, counts and staleness rather than relying on the newest date anywhere in the panel. Those dates identify Bloomberg daily observations, not independently verified fresh market transactions. A completed calendar month is not proof of a complete exchange-day sample. Bloomberg did not return QUOTE_UNITS for the FRA securities; their percent scale is the existing rate-curve convention, with raw values retained unchanged.

**Economic use:** energy forward prices are conditioning information, not guaranteed future spot prices. FRA rates also include market premia. Their contribution to inflation forecasting still needs a rolling-origin comparison against the existing baseline.

## Verification

All 15 requested securities returned data without download errors. Date uniqueness, request bounds, per-security coverage, total counts and raw-file hashes were checked. Dedicated preprocessing tests cover quote timing, missing FX, incomplete months and staleness. See validation.json for the final test record.

Raw pull started 2026-09-09T17:29:10.157945+00:00 and finished 2026-09-09T17:29:40.651222+00:00.
