# Czech CPI: Bloomberg G6 commodity refresh — 10 September 2026

This is an immutable Bloomberg Desktop API (`xbbg.blp.bdh`/`bdp`) capture made
while the local Bloomberg Terminal was connected. Historical `PX_LAST` data run
from 2000-01-01 through 2026-09-09 (FX starts in 1998 where available). The
capture includes the three newly requested G6 securities alongside the existing
energy, FX and rate references. The raw daily responses are retained under
`raw/`; `daily.csv` is the wide untouched daily panel.

## Newly requested securities

| Security | Bloomberg description | Currency / units | Returned history |
|---|---|---|---|
| `BCOMAGSP Index` | BBG Agriculture Spot | USD index points (no QUOTE_UNITS returned) | 2000-01-03 to 2026-09-09, 6,702 observations |
| `BCOMINSP Index` | BBG Industrial Met Spot | USD index points (no QUOTE_UNITS returned) | 2000-01-03 to 2026-09-09, 6,702 observations |
| `TTFGDAHD BCFV Index` | Netherlands TTF natural-gas generic | EUR/MWh | 2011-02-01 to 2026-09-09, 4,038 observations |

`TTFGCY1 Index` remains the user-selected Year-1 gas forward. `FSBTY1 Index`
remains the user-selected Year-1 Brent forward. `CO1`, `CO7` and `CO13` are
kept as separate generic Brent references; they are not silently substituted
for the Year-1 strips.

## Derived files

`prepare.py` was run after the pull. It creates:

- `monthly.csv`, containing every raw and derived series with monthly mean,
  last quote, observation count, quote dates and the assumed availability date;
- `monthly_complete.csv`, containing completed calendar months through August
  2026;
- `monthly_mtd.csv`, containing September 2026 month-to-date rows; and
- `derived_daily.csv`, containing same-date CZK conversions for the existing
  Brent and Year-1 gas series.

Daily market prices are aggregated by arithmetic monthly mean for the level
features used by the current paper experiment. The fuel panel remains weekly
and is handled separately. Month-end/last values are retained for rate-like
series and comparison specifications.

## Timing and provenance

This is a current-vintage historical download, not an archive of what was known
on each historical date. A daily quote is conservatively treated as available
from the following Prague calendar day, and a completed monthly aggregate from
the following month. These are explicit modelling assumptions. The snapshot is
data-only: no nowcast or path backtest has been recalculated or promoted.

`coverage.csv` records each security's actual date range and observation count;
`metadata.json` records the Bloomberg reference fields returned at capture;
`request.json`, `errors.json` and `MANIFEST.json` make the pull reproducible and
auditable. The new broad indices have currency metadata but no Bloomberg
`QUOTE_UNITS`; they must therefore remain labelled as index points rather than
being converted as if they were physical prices.
