# Bloomberg inputs for Czech CPI research

`pull_bloomberg.py` uses the existing `xbbg.blp.bdh` and `xbbg.blp.bdp`
connection to a logged-in Bloomberg Terminal. It writes a new timestamped
directory below `data/market_snapshots/`. It never updates shared Bloomberg
caches, frozen model inputs or old backtests.

The ticker map also includes the supplied macro candidates: Czech industrial
production, permits, quarterly/annual nominal ULC, services and construction
expectations, Germany HICP/unemployment, Czech import prices, and Czech NFC
loans (`LONSCZNF Index`). Statistical index and survey securities may omit
`CRNCY`; the downloader records that as an optional absence while still
requiring currency and verified units for financial and energy quotes.

```
python tools/market_data/pull_bloomberg.py
python tools/market_data/prepare.py data/market_snapshots/<snapshot>
```

Use a Python environment with `xbbg`, `blpapi`, `pandas` and timezone data for
the pull. The downloader records the environment used. Offline preprocessing
only needs pandas and NumPy. On this computer the Bloomberg environment is
Anaconda; its `Library/bin` must be on PATH. A second computer needs its own
authorized Bloomberg connection to refresh; archived CSVs can be read offline.

The requested annual indices are **FSBTY1 Index** (USD/barrel) and
**TTFGCY1 Index** (EUR/MWh). The G6 commodity extensions are **BCOMAGSP Index**
(Bloomberg Agriculture Spot), **BCOMINSP Index** (Bloomberg Industrial Metals
Spot) and **TTFGDAHD BCFV Index** (TTF gas generic, EUR/MWh). Keep all of these
identities distinct from CO7/CO13 generic Brent futures and from an individual
contract delivering exactly twelve months after the observation date. The two
annual series do not supply a complete thirteen-point monthly energy curve.
Current Bloomberg descriptions and units are saved alongside each history.

`daily.csv` contains unfilled daily PX_LAST history through the previous
calendar day. `raw/` retains the original returned dataframes and reference
fields per ticker. `metadata.json` also contains BDP live PX_LAST values,
which may be intraday and must not replace the completed daily history.
`coverage.csv` records actual coverage separately for each ticker.

The reference pull includes Bloomberg's country and next scheduled economic
release fields where they are available. `reference_probe.json` in the full
11 September snapshot records an additional query for frequency, seasonal
adjustment and release fields; Bloomberg did not populate those fields for
most of the statistical securities.

`prepare.py` creates same-date currency conversions and separate monthly mean
and last-observation values. Missing FX leaves the converted value missing.
A completed calendar month does not imply every expected market quote exists:
use the observation count and first/last observation dates. Historical daily
availability on the following calendar day is an explicit approximation;
these are not recorded publication timestamps or original data vintages.

The refreshed USD/CZK and EUR/CZK Bloomberg composite quotes are research
inputs. They are not silent replacements for the official CNB fixings used
in the frozen independent nowcast. Likewise FRA quotes are market inputs,
not inflation-survey forecasts and not a risk-premium-free policy forecast.

Before integration into a scored model, freeze the specific feature
definition, missing-data treatment and training window. Compare with the
baseline over the same eligible origins. Do not backfill pre-2013 annual
strips with CO13 under the same feature name.
