# Bloomberg full input snapshot — 11 September 2026

This folder is a fresh Bloomberg Desktop API (`xbbg`) capture made while the
Terminal was connected. It contains 29 raw `PX_LAST` histories through the
previous Prague calendar day, 10 September 2026, plus the BDP reference files.
The snapshot is current-vintage market/statistical data, not an original
historical-vintage archive. `reference_probe.json` records the additional
Bloomberg fields queried for frequency, adjustment and release metadata. The
key field `SEASONALITY_AND_TRANSFORMATION` is populated for the tested
economic securities and is the preferred Bloomberg check for SA/WDA/NSA.

## Definition audit

| Ticker | Pull result and current classification | Adjustment treatment before model use |
|---|---|---|
| `LONSCZNF Index` | Monthly Czech NFC loan stock, EUR millions, ECB source; 295 observations from 2002-01 through 2026-07; Bloomberg field: `Value NSA` | Bloomberg classifies it as unadjusted. Convert to CZK with the contemporaneous EUR/CZK rate before comparing growth with ARAD. Keep as a comparison/backup series; ARAD VST remains the baseline perimeter. |
| `CZIPITN Index` | Czech industrial-production level, monthly, 2000-01 through 2026-07; Bloomberg field: `Index NSA` | NSA fixed-base level. Use the local CZSO SA series or X-13 as a separate feature; do not call this ticker SA. |
| `CZIPITW Index` | Czech industrial-production level, monthly; Bloomberg field: `Index WDA` | Working-day adjusted level; this is the Bloomberg WDA lane. |
| `CZIPITWY Index` | Czech industrial-production growth, monthly; Bloomberg field: `YoY% WDA` | WDA year-on-year percentage; do not treat it as a level. |
| `CZGRIDX Index` | Total number of granted building permits, monthly, 2002-01 through 2026-07; Bloomberg field: `Units/Persons NSA` | NSA count. Preserve raw count and use the declared log/seasonal transformation; do not difference it as if it were cumulative. |
| `LCTQCZI Index` | Eurostat nominal unit-labour-cost index, quarterly, 2000Q1 through 2026Q1; Bloomberg field: `Index NSA` | NSA quarterly level. Do not apply an SA filter before prospective disaggregation; `LCTOCZI` is annual benchmark only. |
| `LCTOCZI Index` | Eurostat nominal unit-labour-cost annual benchmark; Bloomberg field: `Index Annual` | Annual level; never repeat as a monthly input. |
| `EUS3CZ Index` | Czech services demand evolution expected over the next three months, signed balance, monthly 2002-05 through 2026-08; Bloomberg field: `% Balance/Diffusion Index SA` | Published SA EC balance; retain the signed balance. |
| `EUS5CZ Index` | Czech services employment evolution expected over the next three months, signed balance, monthly 2002-05 through 2026-08; Bloomberg field: `% Balance/Diffusion Index SA` | Published SA EC balance; retain the signed balance. |
| `EUB3CZ Index` | Czech construction employment expectations, signed balance, monthly 2000-01 through 2026-08; Bloomberg field: `% Balance/Diffusion Index SA` | Published SA EC balance; retain the signed balance. |
| `GRCPHCPI Index` | Germany HICP level, monthly 2000-01 through 2026-08; Bloomberg field: `Index NSA` | NSA index level; index-level transform is `log(X_t)-log(X_{t-1})`. Confirm the Eurostat all-items dimension before scoring. |
| `UMRTDE Index` | Germany unemployment rate, percent, monthly 2000-01 through 2026-07; Bloomberg field: `Percent SA` | Published SA rate; confirm the Eurostat total age 15–74 dimension. |
| `CZEII Index` | Czech import-price index level, monthly 2007-02 through 2026-07; Bloomberg field: `Index NSA` | NSA index level; transform with `log(X_t)-log(X_{t-1})` and retain the raw level. |

The remaining market histories are the supplied Brent/gas spot and Year-1
forwards, Bloomberg food and industrial-metals spot indexes, Czech FX, PRIBOR
and FRA quotes. Their unit checks are in `metadata.json`; they are market
conditioning variables and are not silently substituted for official CPI
inputs.

## NFC loan cross-check

The Bloomberg loan series is in EUR millions, so a level comparison must use
the same-month EUR/CZK quote and a factor of one million. On the common monthly
window with ARAD `SUCM100311XXX101101`, the converted levels have correlation
0.99975 and a median level ratio of 1.006. The log-growth correlation is 0.959
with a mean absolute difference of 0.246 percentage points (257 observations).
This is strong evidence that the series tracks the same economic stock, while
the ECB/MFI perimeter and currency conversion remain reasons to keep ARAD as
the primary paper input until the exact coverage is documented.

The Bloomberg `CZEII` log change agrees closely with the frozen CZSO CEN0303
import-price change: correlation 0.992 and mean absolute difference 0.037
percentage points over 222 common months. This supports the level concept, while
the raw level is still retained for source and revision comparison.

## Timing

`LAST_UPDATE_DT` is an observation/current-vintage date, not a release
timestamp. Bloomberg's `ECO_RELEASE_DT`, where populated, is the next scheduled
release date as known at the pull (for example 7 October for Czech industrial
production, 12 October for Czech import prices and 25 September for NFC loans).
Historical backtests must continue to use the project's explicit
`available_from` rules or an authority release calendar.
