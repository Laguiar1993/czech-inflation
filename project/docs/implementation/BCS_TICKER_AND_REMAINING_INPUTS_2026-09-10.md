# BCS ticker note and remaining input list — 10 September 2026

> **Update 12 September 2026.** Every Bloomberg EC ticker has now been compared
> month by month with the official ECFIN archive (`CNB_WP9_A6_AUDIT_2026-09-12.md`).
> `EUS2CZ` equals the current official services demand-past-3-months series;
> `EUA2CZ` is the row-10 question and `EUA4CZ` is not. The retail tickers
> Bloomberg labels NSA carry the EC seasonally adjusted values. Agricultural
> producer price aggregates (CZSO CEN02A, from 2015) and a monthly Petrol 98 series
> (CZSO CEN0101J, 2001-2025) exist; see the audit.

## Services question mapping

Bloomberg's wording is shorter than the European Commission's official
question wording. The model must use the official concepts and keep the
Bloomberg label only as provenance:

| Bloomberg series | Official EC/Eurostat series | Meaning | Paper use |
|---|---|---|---|
| `EUS2CZ Index` | `BS-SARM` / `SERV_002` | Demand/turnover evolution over the past 3 months | A6 #4 |
| `EUS3CZ Index` | `BS-SAEM` / `SERV_003` | Expected demand/turnover over the next 3 months | A6 #30 |
| `EUS5CZ Index` | `BS-SEEM` / `SERV_005` | Expected employment over the next 3 months | A6 #31 |
| `EUB3CZ Index` | `BUIL_004` | Construction employment expectations over the next 3 months | A6 #37 |

The user-supplied `EUS3CZ Index` history (21.9, 15.5, 21.0, 27.6, 30.6,
20.6, 13.8 for the recent observations) is therefore treated as a candidate
for the official `BS-SAEM` balance. “Month ahead” is not interpreted literally
as a one-month horizon: the Commission questionnaire asks about the next three
months. The exact mapping should be confirmed with Bloomberg `BDP` metadata
and a value-by-value comparison with Eurostat's `ei_bsse_m_r2` (`geo=CZ`,
`s_adj=SA`, `unit=BAL`, `indic=BS-SAEM`).

`EUB3CZ Index` has been recorded as a pending candidate for the construction
employment question. The 11 September Bloomberg capture confirms that
`EUS5CZ Index` exists and is a monthly signed balance with the expected services
employment wording. Keep the official `BS-SEEM` cross-check and SA flag as a
final definition check before scoring it.

The paper's `T3` is a transformation (`x_t - x_{t-1}` in the balance), not a
three-month release lag. These survey inputs remain outside the primary
independent nowcast; they belong in the CNB-paper replication and sentiment
challenger lanes.

## Additional identifiers supplied for the next pull

The operating industrial-production level is now `CZIPITS Index` (Czech
Industrial Production Index SA). `CZIPITN Index` remains archived as the raw
NSA/X-13 challenger. The following Bloomberg identifiers are candidates for
the detailed Czech confidence block and should be compared with the official
EC/Eurostat balances before admission:

| Bloomberg series | Intended concept | Paper use |
|---|---|---|
| `EUA2CZ Index` | Consumer financial situation expected over the next 12/13 months, candidate A | A6 #10 |
| `EUA4CZ Index` | Consumer financial situation expected over the next 12/13 months, candidate B | A6 #10 |
| `EUICCZ Index` | Czech industrial confidence | A6 #29 |
| `EUSCCZ Index` | Czech services confidence | A6 #32 |
| `EUICDE Index` | German industrial confidence | A6 #18 |
| `EUSCDE Index` | German services confidence | A6 #19 |
| `EURTDE Index` | German retail confidence | A6 #20 |
| `EURTPL Index` | Polish retail confidence | A6 #22 |
| `EUR3CZ Index` | Czech retail orders expected over the next 3 months | A6 #33 |
| `EUR4CZ Index` | Czech retail business-activity expectations over the next 3 months | A6 #34 |
| `EUR5CZ Index` | Czech retail employment expectations over the next 3 months | A6 #35 |
| `EURTCZ Index` | Czech retail confidence | A6 #36 |
| `EUA1CZ Index` | Czech consumer financial situation over the last 12 months | A6 #39 |
| `EUA0CZ Index` | Czech consumer savings expected over the next 12 months | A6 #40 |
| `EUAUCZ Index` | Czech consumer unemployment expectations | A6 #41 |
| `EUA6CZ Index` | Czech consumer major-purchase intentions | A6 #42 |
| `EUCOCZ Index` | Czech construction confidence | A6 #38 |
| `EUCODE Index` | German construction confidence | A6 #21 |
| `EUB4CZ Index` | Czech construction-price expectations over the next 3 months | A6 #68 |
| `EUI5CZ Index` | Czech industry selling-price expectations over the next 3 months | A6 #67 |

`EUA2CZ` and `EUA4CZ` must be pulled together and compared value by value with
the official consumer-survey question. The ticker mnemonic alone is not enough
to choose between them.

The supplied `EEUR3CZ Index` spelling was invalid in Bloomberg (no BDH or BDP
response). The established Bloomberg retail prefix is `EUR`, and the successful
`EUR3CZ Index` capture is therefore the canonical candidate for A6 #33.

The four new country-confidence candidates have the same admission rule:
compare each history with the matching official ECFIN/Eurostat balance, confirm
the country and seasonal-adjustment dimensions, and preserve the release clock
before scoring. `EUICDE`, `EUSCDE` and `EURTDE` are German aggregates; `EURTPL`
is the Polish retail aggregate. They are useful for the paper/sentiment lane,
but remain outside the independent nowcast until those checks pass.

## Offline Bloomberg-versus-official checks

The already captured Bloomberg activity histories were compared with the
official broad Eurostat balances in the frozen local file
`data/paper_replication/bcs_aggregate_surveys.csv`. This is a diagnostic only:
the broad confidence indicator is not automatically the paper's individual
question. The results confirm that the adjacent Bloomberg labels are not
interchangeable with the broad aggregates. For `EUS1CZ`, `EUS2CZ`, `EUR1CZ` and
`EUB1CZ`, level correlations are 0.898, 0.934, 0.879 and 0.764, with mean
level gaps of +20.85, −12.08, +16.70 and +44.63 balance points respectively.
The construction series has only 0.157 correlation in monthly changes with the
broad construction-confidence indicator. `EUCCCZ`, however, matches the broad
consumer-confidence indicator essentially exactly (correlation 1.000 and
zero last-observation gap), proving that it is not the detailed consumer
financial-situation expectation question required for A6 #10.

The full comparison and seven-period tail are saved in
`output/bloomberg_bcs_official_comparison_20260911.csv` and
`output/bloomberg_bcs_official_latest_20260911.csv`. The exact detailed
question check still requires the Eurostat/EC series, not just the broad
aggregate.

## Euro-area perceived and expected inflation balances

The paper's A6 #27 and #28 are consumer-survey balances, not the ZEW
financial-analyst survey and not a market-implied inflation rate. The official
Commission questions are:

| Paper row | Official question | Eurostat/EC indicator | Interpretation |
|---:|---|---|---|
| 27 | Price trends over the next 12 months | `CONS_006` / `BS-PT-NY` | Net balance of households expecting prices to rise, stay the same or fall over the next year |
| 28 | Price trends over the last 12 months | `CONS_005` / `BS-PT-LY` | Net balance of households reporting that prices rose, were unchanged or fell over the previous year |

The Bloomberg candidates supplied for these two euro-area balances are
`EUA8EMU Index` (next 12 months) and `EUA7EMU Index` (last 12 months). They are
now present in the full immutable pull, but remain pending a BDP metadata check
and a value-by-value comparison with the official aggregate.

These are qualitative balances, normally between -100 and +100 percentage
points. A reading of +40 means that positive responses exceed negative
responses by 40 points; it does **not** mean that households forecast 40%
inflation. The paper uses the euro-area aggregate, historically matching the
appropriate EA composition for each vintage. Use the official `ei_bsco_m`
series from the Commission/Eurostat archive where possible, freeze the vintage,
and preserve its release date. Bloomberg can be used as a convenience mirror,
but these mnemonics should not be admitted until they match the official EA
balance value by value. The current independent Czech nowcast excludes both variables;
they belong in the optional sentiment/path lane.

The Commission's methodology lists the exact wording for `CONS_005` and
`CONS_006`, and the official time-series portal provides the downloadable
consumer-survey histories. These are distinct from the ZEW Economic Sentiment
survey, whose respondents are financial analysts and whose inflation questions
are not the variables used by this paper.

## Additional price-expectation questions worth collecting

The paper requests industry `INDU_006` and construction `BUIL_005`, which we
interpret as Czech (`geo=CZ`) because the surrounding G7 inflation inputs are
Czech; the paper table itself does not print that geography, so DE/EA versions
should remain labelled challengers until the original data confirm it. The
current Bloomberg candidates are `EUI5CZ Index` for `INDU_006` and `EUB4CZ
Index` for `BUIL_005`; both remain pending BDP and official value checks. The
Commission programme also publishes the directly analogous price questions for
services (`SERV_006`) and retail trade (`RETA_006`). Those two series are not
part of the paper's 72-row A6 table and have no confirmed Bloomberg ticker in
this project. They are nevertheless high-value candidates for an independent
Czech inflation-path model because services and retail prices have a much more
direct connection to the CPI basket than construction confidence. Collect them
from the official BCS archive, preserve `unit=BAL` and `s_adj=SA`, and test them
with release-date lags rather than treating the balance as a percentage
inflation forecast.

### Exact question spot-check against EC annexes

The first direct check is now possible without relying on Bloomberg's short
label. I transcribed the Czech rows in the Commission's November 2025
services annex (December 2024 through November 2025) and compared them with
the current-vintage Bloomberg histories:

| Bloomberg candidate | Intended EC question | Common-window result | Decision |
|---|---|---:|---|
| `EUS1CZ Index` | `SERV_001`, business situation over the past 3 months | MAE 0.11 balance points; maximum gap 0.2 | Strong match; keep as the candidate for A6 #3, subject to a full Eurostat extract and release-clock check |
| `EUS2CZ Index` | `SERV_002`, demand over the past 3 months | MAE 2.25 points; maximum gap 5.0 | Do not admit to A6 #4 yet; Bloomberg's long name says “demand in recent month,” and the values do not reproduce the annex row |

This is a vintage check rather than a claim that the Commission never revises
a balance. It is nevertheless strong evidence that `EUS1CZ` is the requested
past-three-month business-situation series and that `EUS2CZ` is a different or
differently constructed series. The next-three-month candidate `EUS3CZ` also
passes a smaller six-month spot check against the Commission's June 2025
annex (MAE 1.18 points), but it still needs the full official series and
publication clock before scoring.

The next pull therefore contains both the Bloomberg candidates and the
official-question labels, while model admission remains a separate step. The
Commission defines `SERV_001`, `SERV_002` and `SERV_003` as business situation
past three months, demand past three months and demand next three months;
the official definitions are linked below.

The authoritative wording is in the [European Commission BCS methodology](https://economy-finance.ec.europa.eu/economic-forecast-and-surveys/business-and-consumer-surveys/methodology-business-and-consumer-surveys/methodological-concepts_en).
The downloadable monthly dataset is [Eurostat `ei_bsse_m_r2`](https://ec.europa.eu/eurostat/databrowser/view/ei_bsse_m_r2/default/table?lang=en).

## Bloomberg items still to pull or verify

These are the remaining useful terminal pulls, in priority order:

1. `EUS3CZ Index` — services demand expectations, next 3 months (captured;
   verify against the official series).
2. `EUS5CZ Index` — services employment expectations, next 3 months (pulled;
   cross-check the official `BS-SEEM` balance and seasonal-adjustment flag).
3. `EUB3CZ Index` — construction employment expectations (captured; verify
   against the official series).
4. `CZIPITS Index` — Czech industrial-production seasonally adjusted level,
   replacing the removed `CZIPITWY` growth series. Keep `CZIPITN Index` only
   as the raw NSA/X-13 challenger.
5. `CZGRIDX Index` — user-supplied Czech building-permit candidate. Pull the
   historical series and metadata without assuming that it is cumulative. Keep
   the raw observations and release dates, then classify it as a direct monthly
   total count, a January-to-date cumulative count, a fixed-base index, a YoY
   rate, a permit-value series or a dwelling count. The paper input is the total
   number of permits granted converted to monthly counts: if the Bloomberg
   series is cumulative, use `monthly_t = cumulative_t - cumulative_{t-1}` within
   each calendar year (January equals the January cumulative value). A direct
   monthly count is preferable and needs no differencing.
6. `LCTQCZI Index` — quarterly nominal ULC; `LCTOCZI Index` is an annual
   benchmark only. The quarterly series must be disaggregated prospectively.
7. Czech Petrol 98/Super Plus pump price — no Bloomberg ticker is needed; CZSO
   publishes it in the weekly CENPHMT fuel survey. Import and clock-check the
   historical series alongside Petrol 95, diesel and LPG.
8. End-month three-month PRIBOR — use an exact month-end ARAD/Bloomberg quote,
   not the existing monthly-average proxy.
9. `GRCPHCPI Index` — user-supplied Germany HICP candidate. Verify the
   all-items monthly index level, coverage and history before using A6 #23.
10. `UMRTDE Index` — user-supplied Germany unemployment candidate. Verify the
    Eurostat total, age 15–74, seasonally adjusted monthly percentage before
    using A6 #24.
11. `CZEII Index` — user-supplied Czech import-price candidate. Verify that it
   is the total monthly raw index level before using A6 #26; retain the CZSO
   series as the comparison benchmark.

For the next Bloomberg session, capture `BDP` fields `NAME`, `SECURITY_DES`,
`CRNCY`, `QUOTE_UNITS`, `INDX_SOURCE`, `DES_NOTES`, `PX_LAST`,
`LAST_UPDATE_DT`, `LAST_UPDATE`, plus the terminal's frequency and seasonal-
adjustment labels. The acceptance checks are:

| Ticker | Accept only if the metadata says | A6 use |
|---|---|---|
| `GRCPHCPI Index` | Germany, HICP, all items, monthly **index level**; record NSA/SA status and history | #23, T2 log difference |
| `UMRTDE Index` | Germany unemployment rate, total age 15–74, monthly SA percentage | #24, T0 level |
| `CZEII Index` | Czech total import-price **index level**, monthly; not a rate, export index or terms of trade | #26, T2 log difference |

The Bloomberg observation date is not itself a publication timestamp. Preserve
the release calendar or apply the declared conservative `available_from` rule
when these series enter a scored run.

The commodity candidates already supplied are `BCOMAGSP Index` (food),
`BCOMINSP Index` (industrial metals), `TTFGDAHD BCFV Index` (European gas spot),
`TTFGCY1 Index` (gas Year-1 forward), and `FSBTY1 Index` (Brent Year-1 forward).
The project decision is to use these Bloomberg series as our own market
conditioning inputs. They remain labelled proxies in the paper-comparison lane,
but acquiring exact Refinitiv histories is out of scope.

## Inputs that do not require a Bloomberg ticker

The detailed EC business and consumer balances are better downloaded directly
from the Commission/Eurostat archives: Czech retail expectations and
confidence, Czech consumer financial/savings/unemployment/purchase questions,
German and Polish confidence, euro-area perceived/expected price balances, and
industry/construction/services selling-price expectations. The exact codes and
dataset names are in `CNB_WP9_A6_DATA_REQUEST_2026-09-10.md`.

The remaining non-Bloomberg gaps are CNB LUCI total and wages/costs component,
the exact coverage of the NFC loan aggregate, a verified official monthly
permit-count concept, and agricultural PPI subcomponents. `GRCPHCPI Index`,
`UMRTDE Index` and `CZEII Index` are now candidate Bloomberg identifiers for the
German HICP, German unemployment and Czech import-price level respectively, but
they are still definition checks until their BDP metadata, history and release
clocks have been captured. Petrol 98 is a retrieval gap rather than a source
gap: CZSO's weekly CENPHMT survey contains the series. All of these should
carry an `available_from` timestamp rather than being replaced silently by a
later revised level.

## Updated list of variables with no confirmed ticker

The user has now supplied identifiers for the industrial-production level
(`CZIPITS Index`), permits (`CZGRIDX Index`), quarterly nominal ULC
(`LCTQCZI Index`), services demand expectations (`EUS3CZ Index`), construction
employment expectations (`EUB3CZ Index`), German HICP (`GRCPHCPI Index`),
German unemployment (`UMRTDE Index`), Czech import prices (`CZEII Index`), the
food and industrial-metals commodity indexes, gas spot and Year-1 forward, and
Brent Year-1 forward. The full 11 September refresh contains all of these
identifiers, with 65 successful histories through 10 September 2026. The
remaining work is definition/seasonal-adjustment checking rather than ticker
discovery. `PRIB03M Index` is also known and has a complete pull, although its
exact month-end use remains a model-side timing choice.

The items below still have no confirmed Bloomberg ticker, or should be sourced
directly from the statistical authority instead of searching for a ticker:

| Paper input | Numbers | Preferred source and status |
|---|---:|---|
| CNB LUCI total | 15 | CNB publication/ARAD; exact published series not in the bundle |
| CNB LUCI wages-and-labour-costs component | 16 | CNB publication/ARAD; exact published series not in the bundle |
| German HICP **level** | 23 | `GRCPHCPI Index` pulled; Eurostat all-items and adjustment dimensions remain the benchmark check |
| German unemployment | 24 | `UMRTDE Index` pulled; confirm Eurostat total age 15–74, SA dimension |
| Czech import-price **level** | 26 | `CZEII Index` pulled; compare log changes with CZSO total |
| NFC loan balance coverage | 58 | `LONSCZNF Index` pulled as ECB/MFI comparison; ARAD VST total remains the primary commercial-bank perimeter |
| Agricultural PPI animal, plant, agriculture/fish aggregates | 50–52 | CZSO agricultural PPI tables; no ticker confirmed |
| Czech Petrol 98/Super Plus pump-price history | 64 | CZSO weekly CENPHMT source exists; no Bloomberg ticker required; import and clock-check it |
| Exact detailed EC/Eurostat balances | 1–10, 18–21, 27–28, 29–42, 67–68, 71–72 | Download by ECFIN/Eurostat question code; adjacent Bloomberg mnemonics are not automatically exact |

The NFC loan definition and the total-versus-maturity-row correction are
documented in `docs/implementation/NFC_LOAN_DEFINITION_2026-09-10.md`.

The paper-comparison lane still labels the market series as proxies because the
paper does not identify every original index construction. That is a fidelity
label, not an outstanding data request: for the operating project we will use
the supplied Bloomberg commodity and energy series consistently and document
their observation and availability rules.

The 11 September capture now contains `EUS5CZ Index` alongside the other
supplied identifiers. It is a strong candidate for the services-employment
question, but the final acceptance step remains a value-by-value comparison
with Eurostat `BS-SEEM` and its SA dimension. Petrol 98 should be collected
from CZSO even if Bloomberg also carries a quote, because the paper specifies
the Czech weekly pump-price representative. Everything else above should be
collected from ARAD, CZSO or Eurostat, with release timing retained.

## Agricultural PPI versus oils-and-fats PPI

The Czech “vegetable and animal oils and fats” PPI is **not** the same as the
agricultural PPI aggregates requested in A6 numbers 50–52. It is a downstream
industrial-manufacturing category (NACE/CZ-CPA C104): prices received by an
oil/fat processor for products such as crude or refined oils and fats. The
agricultural output index is measured at the farm gate and covers raw crop,
livestock and livestock-product prices; the agriculture-including-fish total is
the official aggregate of that output basket. The distinction is described in
the Eurostat agricultural-price metadata and the food-chain metadata, while
CZSO reports oils and fats under industrial producer prices.

Therefore oils-and-fats PPI must not be used as A6 #50 (animal), #51 (plant) or
#52 (agriculture including fish). It is a sensible optional downstream food
chain feature for the path model or a food challenger, subject to its own
release clock. Because it is nested within manufactured-food/industrial PPI,
test it separately or with regularisation rather than automatically adding it
alongside every broader industrial aggregate. Preserve the agricultural
aggregates as the target paper inputs.

### Permit-definition audit

The ticker mnemonic alone does not establish the statistical definition. The
official CZSO catalogue has both a current monthly table for the number of
building permits and an older monthly cumulative dataset. Therefore the
Bloomberg pull must be audited before use. Required checks are: Czech-total
geography; permits granted rather than dwellings, construction value or starts;
monthly frequency; NSA/SA flag; units; whether the level resets in January; and
the release date/time. Values rising through the year and resetting in January
indicate a cumulative series. Values that are ordinary monthly counts without a
January reset are direct counts. Values near a base of 100 or expressed as a
percentage are not eligible for this paper input. Until those checks pass,
`CZGRIDX Index` remains a pending candidate rather than an exact mapping.
