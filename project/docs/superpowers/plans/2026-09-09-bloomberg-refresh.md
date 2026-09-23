# Czech CPI Bloomberg market refresh

User approved Bloomberg history pulls and the two path research tracks. Use the
existing Anaconda xbbg BDH/BDP connection, not a new data provider.

1. Confirm the two requested tickers through BDP and a short BDH request. DONE.
2. Pull PX_LAST from 2000-01-01 through the previous calendar day for both annual
   energy strips, Brent generics, USD/CZK, EUR/CZK, PRIBOR and the seven existing
   FRA tenors. Preserve actual starting dates and missing observations.
3. Archive each raw response, request settings, current reference metadata and
   separate live quotes in a new timestamped directory. Never replace a frozen
   research result, fixture or source input. Include coverage and SHA256 hashes.
4. Build separate monthly mean and last-observation panels, with per-series
   quote dates, same-day FX conversion, explicit retrospective availability
   assumptions and incomplete-month flags. An annual strip remains a distinct
   feature; do not rename it CO13 or invent a monthly delivery curve.
5. Verify no future quotes enter an as-of selection, FX dates match, empty or
   malformed downloads fail visibly, monthly sample counts are per series, and
   existing frozen data remain unchanged. Independently review new code.
6. Save a user-facing coverage report and portable data package. Make clear that
   data refresh alone is not a model promotion or a new measured backtest.

History downloaded now is a current-vintage snapshot, not a vintage archive.
Reference fields are current metadata, not historical metadata. Preserve all
raw data locally; do not send Bloomberg observations to external services.
