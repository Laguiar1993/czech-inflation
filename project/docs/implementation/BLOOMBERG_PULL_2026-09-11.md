# Bloomberg pull and ticker audit — 11 September 2026

The latest full snapshot is
`data/market_snapshots/20260911_bloomberg_full_refresh/`. It contains the
consolidated candidate map: 65 successful histories and BDP metadata through
10 September 2026. The earlier `20260911_bloomberg_full_clean` folder remains
immutable as the narrower pre-refresh capture. The raw BDP and BDH responses,
request, coverage, errors and manifest are kept in the full snapshot. The
invalid diagnostic spelling `EEUR3CZ Index` returned no history or reference
data and has been removed from the active pull map; the canonical `EUR3CZ Index`
series returned successfully.

## What the pull establishes

- **LONSCZNF Index is a useful NFC-loan candidate.** Bloomberg identifies it as
  a Czech non-financial-corporation series from the ECB, quoted in EUR millions.
  It is monthly, month-end dated and positive from January 2002. After
  converting by the same-month EUR/CZK rate, its level correlation with the
  ARAD VST NFC total is 0.99975 and its log-growth correlation is 0.959 on the
  common window. The Bloomberg description says the underlying bank aggregate
  may include commercial banks and central banks, so it is a close harmonised
  comparison, not an automatic replacement for the ARAD commercial-bank
  perimeter. For the paper transform, use a CZK-equivalent level and then the
  log difference; keep the raw EUR series and FX conversion visible.

- **CZIPITS Index is now the operating Bloomberg industrial-production input.**
  It is the user's Czech Industrial Production Index SA identifier and will
  be checked by BDP before admission. The existing `CZIPITN Index` capture is
  explicitly NSA and remains a raw/X-13 challenger; it must not replace the
  SA operating level. The frozen CZSO PRU01C series is already seasonally and
  calendar adjusted, so applying X-13 to that operating series would double
  adjust it.

- **CZGRIDX Index is the requested total permit count.** It is a direct monthly
  count rather than the cumulative year-to-date series described in the paper:
  within-year changes are positive in only about 53% of observations and the
  path moves down as well as up. Preserve it as the raw count and do not apply
  cumulative differencing. Confirm the geography/revision clock against CZSO
  before admitting it to the scored paper panel.

 - **LCTQCZI Index is quarterly nominal ULC** (2000Q1–2026Q1); `LCTOCZI` is the
  annual benchmark only. It must be disaggregated prospectively. Bloomberg
  labels `LCTQCZI` `Index NSA`; retain that status unless Eurostat provides a
  more specific revision or adjustment definition.

- **EUS3CZ, EUS5CZ and EUB3CZ are monthly signed EC balances.** `EUS3CZ` is
  the services demand expectation over the next three months; `EUS5CZ` is the
  analogous services employment expectation; and `EUB3CZ` is construction
  employment expectations. They belong to the paper/sentiment lane and remain
  outside the primary independent nowcast.

- **The new confidence and price-balance candidates are now captured.**
  `EUA2CZ` and `EUA4CZ` are both retained for the consumer
  financial-situation expected question; choose between them only after a
  value-by-value check against the official `CONS_002`/`BS-FS-NY` series.
  `EUICCZ` and `EUSCCZ` are candidates for the broad Czech industrial and
  services confidence indicators, while `EUICDE`, `EUSCDE`, `EURTDE` and
  `EURTPL` cover the German/Polish confidence inputs. `EUA8EMU` and
  `EUA7EMU` are candidates for the euro-area consumer price-trend balances
  (`CONS_006` and `CONS_005`). Their BDP definitions, geography, unit and SA
  status must be checked against the official ECFIN/Eurostat aggregates before
  they enter a scored model.

 - **GRCPHCPI and CZEII are index levels; UMRTDE is a percentage rate.** Apply
  log differences to the two price levels and use the unemployment level as
  declared. Bloomberg labels the price levels `Index NSA` and the unemployment
  rate `Percent SA`; verify the official Eurostat/CZSO dimensions before
  scoring.

## Seasonal adjustment and release metadata

The Bloomberg reference field
`SEASONALITY_AND_TRANSFORMATION` is the useful adjustment check. The saved
`seasonality_probe.json` shows, for example, `CZIPITN Index = Index NSA`,
`CZIPITW Index = Index WDA`, `CZIPITWY Index = YoY% WDA`, the three EC survey
balances as `... SA`, and `UMRTDE Index = Percent SA`. It also identifies
`CZGRIDX`, `LCTQCZI`, `GRCPHCPI`, `CZEII` and `LONSCZNF` as NSA (with
`LCTOCZI` labelled annual). Empty fields still require an official-source
check; a blank Bloomberg response is not evidence of either SA or NSA. The
snapshot README records the returned value alongside the model treatment so
we do not infer adjustment from the observation date.

The other generic fields (`FREQUENCY`, `SEASONAL_ADJ`, and similar) were not
populated for these securities. The raw histories make the frequency clear
(month-end or quarter-end), but they do not replace the explicit adjustment
field or the statistical-source metadata.

`ECO_RELEASE_DT` is a current next-scheduled release date, not a historical
publication archive. For real-time backtests, retain the existing CZSO/Eurostat
release calendars and attach `available_from` separately.

The ARAD comparison and the total-vs-maturity-row correction remain documented
in `NFC_LOAN_DEFINITION_2026-09-10.md`. The exact paper input still uses ARAD
until the ECB/MFI perimeter and adjustment status of `LONSCZNF` are formally
confirmed; the Bloomberg series is a strong validation and late-data backup.
