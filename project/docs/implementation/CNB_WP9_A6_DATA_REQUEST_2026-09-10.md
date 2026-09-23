# CNB WP 9/2026 — exact predictor request

> **Update 12 September 2026.** The audit has been rebuilt against official
> downloads in `CNB_WP9_A6_AUDIT_2026-09-12.md`; its statuses supersede the counts
> in this request. Row 38 (Czech construction confidence) is printed with
> transform 3 in Table A6, not `T0` as listed below; the runner is corrected.

This is the data checklist for the closest possible replication of Table A6 in
Blaha, Botka, Švéda and Michl, *AI-Based Forecasting of Czech Inflation:
Quantile Regression Forests with Dynamic Weights* (CNB Working Paper 9/2026).
The paper uses 72 predictors, monthly May 2002–September 2025. `T0` means the
level is used, `T2` means `ln(Xt)-ln(Xt-1)`, and `T3` means `Xt-Xt-1`. The paper
says it seasonally adjusts all series with X-13 before applying these
transformations. Every supplied file should carry a `period` and an
`available_from` timestamp; a revised historical value without its vintage
date is not a real-time observation.

## G1 — real activity, Czech Republic

1. `T0` EC business/consumer survey: production development observed over the past 3 months.
2. `T0` EC business/consumer survey: production expectations over the next 3 months.
3. `T3` EC business/consumer survey: business-situation development over the past 3 months.
4. `T3` EC business/consumer survey: evolution of demand over the past 3 months.
5. `T3` EC business/consumer survey: business-activity/sales development over the past 3 months.
6. `T3` EC business/consumer survey: building-activity development over the past 3 months.
7. `T3` EC building survey: factor limiting activity, shortage of labour.
8. `T3` EC building survey: factor limiting activity, shortage of material/equipment.
9. `T3` EC building survey: factor limiting activity, financial constraints.
10. `T3` EC consumer survey: financial situation expected over the next 13 months.
11. `T0` Czech unemployment.
12. `T0` Czech index of industrial production.
13. `T0` Czech building permits, converted from the published cumulative series to monthly counts.
14. `T0` CNB Rushin activity index.
15. `T0` CNB LUCI (Labour Utilisation Composite Index), total.
16. `T0` CNB LUCI, wages and labour costs component.
17. `T0` nominal unit labour costs.

The first ten are detailed Eurostat/EC balance-of-answers series, not the broad
ESI. In the current ECFIN naming, the relevant question codes are `INDU_001`
(production past 3m), `INDU_005` (production next 3m), `SERV_001`/`SERV_002`
(services business situation/demand past 3m), `RETA_001` (retail sales past
3m), `BUIL_001` (building activity past 3m), `BUIL_002` (building constraints),
and `CONS_002` (consumer financial situation next 12m; the paper calls this
13m). Request the Czech `geo=CZ`, seasonally-adjusted balance series and keep
the original frequency and vintage. IP and unemployment can be obtained from CZSO/Eurostat. Permit counts
must retain the release date. Rushin is a CNB series. LUCI and nominal ULC are
not in the current ARAD snapshot; the paper temporally disaggregates the
quarterly series with Chow–Lin, which must be reproduced prospectively with a
one-sided vintage rule.
The selected Bloomberg candidate for nominal ULC is `LCTQCZI Index` (quarterly);
`LCTOCZI Index` is retained only as an annual benchmark until its definition
and release timing are verified.

## G2 — foreign influence

18. `T0` German industrial confidence.
19. `T3` German services confidence.
20. `T3` German retail confidence.
21. `T3` German construction confidence.
22. `T2` Polish retail confidence.
23. `T2` German HICP.
24. `T0` German unemployment.
25. `T2` Czech external balance of trade (FOB/FOB).
26. `T2` Czech import prices.
27. `T0` Euro-area domestic-inflation-expectations balance.
28. `T0` Euro-area perceived-inflation balance.

Use the EC BCS detailed German/Polish balances (`INDU_COF`, `SERV_COF`,
`RETA_COF`, `BUIL_COF` with `geo=DE` or `geo=PL`), Eurostat HICP and
unemployment, and CZSO trade/import-price levels. The local panel currently
has broad or short proxies for several of these; a German retail growth rate
is not the same thing as German retail confidence and must not be labelled
exact.

## G3 — confidence and sentiment, Czech Republic

29. `T3` Czech industrial confidence.
30. `T3` demand expectations over the next 3 months.
31. `T3` employment expectations over the next 3 months.
32. `T0` Czech services confidence.
33. `T3` expectations for orders placed with suppliers over the next 3 months.
34. `T3` business-activity expectations over the next 3 months.
35. `T3` employment expectations over the next 3 months.
36. `T3` Czech retail confidence.
37. `T3` construction employment expectations.
38. `T3` Czech construction confidence (corrected 12 September 2026; previously listed as `T0`).
39. `T3` financial situation over the last 13 months.
40. `T3` savings over the next 13 months.
41. `T3` unemployment expectations over the next 13 months.
42. `T3` major purchases over the next 13 months.

These are the detailed Czech EC balances. The current ECFIN codes are
`INDU_COF`, `SERV_003`, `SERV_005`, `SERV_COF`, `RETA_003`, `RETA_004`,
`RETA_005`, `RETA_COF`, `BUIL_004` and `BUIL_COF`, plus `CONS_001`,
`CONS_011`, `CONS_007` and `CONS_009` for the consumer questions. The six broad local aggregates
(industrial, services, retail, construction, consumer and ESI) are useful
project variables but do not reproduce this block.

The public archive currently exposes these ZIPs, which are the most efficient
way to collect the block: `industry_total_sa_nace2.zip`,
`services_total_sa_nace2.zip`, `retail_total_sa_nace2.zip`,
`building_total_sa_nace2.zip`, `consumer_total_sa_nace2.zip`, and
`consumer_inflation_nace2.zip`. They are linked from the European Commission's
BCS time-series page. The all-surveys archive is also available if one file is
preferred. Keep the `geo`, sector, question code, answer-balance type and
seasonal-adjustment flag; do not replace the detailed questions with the ESI.

## G4 — producer prices

43. `T0` year-on-year producer prices of agricultural products.
44. `T0` year-on-year producer prices of industrial products.
45. `T2` total industrial producer-price level.
46. `T2` industrial mineral-resources producer-price level.
47. `T2` industrial manufactured-goods producer-price level.
48. `T2` industrial electricity, gas and steam producer-price level.
49. `T2` industrial water producer-price level.
50. `T2` agricultural producer prices, animal-based products.
51. `T2` agricultural producer prices, plant-based products.
52. `T2` agricultural producer prices, agriculture, production and fish.

CZSO CEN0201A/PPI can supply 43–49, but the raw level (not only a published
year-on-year change) and release timestamp are needed for 45–49. The current
local detailed industry file begins in 2015. Farm-gate price baskets are not
official agricultural PPI aggregates and should remain proxies for 50–52
unless the CZSO aggregates are obtained.

## G5 — financial variables

53. `T0` ten-year Czech government-debt yield, monthly average.
54. `T0` three-month PRIBOR, value at month-end.
55. `T0` two-week CNB repo rate, value at month-end.
56. `T2` PPI-deflated real effective exchange rate.
57. `T2` CPI-deflated real effective exchange rate.
58. `T2` client-loan balance of Czech resident non-financial corporations.
59. `T2` client-loan balance of Czech resident households.

ARAD contains 53, 55–57 and household loans. The local PRIBOR series is a
monthly average, so it is not an exact match for 54; use an end-month ARAD or
Bloomberg observation. The VST client-loan data contain an NFC total and three
original-maturity rows. Use the total code once, with the three buckets only as
a fallback when the total row is absent; adding all four rows double-counts the
stock. The VST methodology describes these as monthly nominal client-loan
balances reported by commercial banks and foreign bank branches in Czechia,
excluding the CNB. This is a strong match to the paper's client-loan concept,
but it is narrower than a harmonised MFI aggregate if any non-bank MFI
subsectors are included in a comparison series.

The 11 September Bloomberg capture adds `LONSCZNF Index`, an ECB-sourced
monthly stock in EUR millions beginning in 2002. After same-month EUR/CZK
conversion its log growth tracks the ARAD total closely, but the ECB/MFI
perimeter is not explicit in Bloomberg's description. Keep it as a labelled
comparison/backup and retain the ARAD VST total as the baseline until the
perimeter is confirmed.

## G6 — commodities and energy

60. `T0` Brent crude oil spot, USD/barrel.
61. `T2` average European natural-gas price.
62. `T2` industrial-metals price index.
63. `T2` food-commodity price index.
64. `T2` first principal component of Czech Petrol 95 Natural, Petrol 98 Super Plus, diesel and LPG prices (CZSO).
65. `T0` Refinitiv TRPC natural-gas forward price.
66. `T0` Refinitiv ICE Europe Brent crude electronic-energy future.

The paper describes 65–66 as a quote observed at `t` for delivery at `t+12`
and shifts the series forward by 12 monthly positions. Bloomberg
`TTFGCY1 Index` and `FSBTY1 Index` are useful Year-1 proxies, but the generic
strip is not proof of an exact constant 12-month contract. The paper's PCA
uses four fuel types and says PC1 explains over 93%; the current local file has
only Petrol 95, diesel and LPG, but CZSO's weekly CENPHMT survey also publishes
Petrol 98 Super Plus and it must be imported before the four-price PCA is called
exact. The 11 September Bloomberg capture now stores the operating proxies
`BCOMINSP Index` (industrial metals) and `BCOMAGSP Index` (agriculture/food),
while the paper's original index identities remain unspecified.

## G7 — inflation expectations

67. `T3` selling-price expectations over the next 3 months.
68. `T3` construction-price expectations over the next 3 months.
69. `T0` financial-market inflation expectation at a 3-year horizon, percentage points.
70. `T0` financial-market inflation expectation at a 1-year horizon, percentage points.
71. `T0` perceived-inflation balance.
72. `T0` expected-domestic-inflation balance.

The first two and 71–72 are detailed EC balances. The likely ECFIN codes are
`INDU_006` for industry selling-price expectations, `BUIL_005` for construction
price expectations, and `CONS_005`/`CONS_006` for perceived and expected price
trends. The paper's table does not print a geography for rows 67–68; because
the surrounding inflation-path inputs are Czech, the operating interpretation
is `geo=CZ`, with any DE/EA version kept as a labelled challenger until the
authors' original data or a value match confirms otherwise. CNB FMIE supplies monthly
market expectations for 69–70, but their release timestamp must be retained.
The current Bloomberg candidates for the Czech interpretation are `EUI5CZ Index`
for #67 and `EUB4CZ Index` for #68; keep them as candidates until their BDP
definitions and official `geo=CZ`, `unit=BAL`, seasonally-adjusted histories
match the EC series.
These variables are part of the paper comparison only; the project's primary
independent nowcast intentionally excludes inflation-expectation inputs.

## What to collect first

For the largest improvement in paper fidelity, obtain (a) the 34 detailed
Czech/German/Polish/Euro-area EC balances, (b) LUCI total and labour-cost
component plus nominal ULC, (c) raw monthly building-permit counts, (d) the
five missing agricultural/PPI levels and (e) end-month PRIBOR and exact loan
definitions. Market/commodity series 60–66 can be supplied separately.

Use one CSV per logical source or one wide CSV with this minimum schema:
`period`, one value column per series, and `available_from` (or a companion
release-calendar table). Preserve units, seasonal-adjustment flags, source
identifiers and revisions. Do not fill a missing historical period with a
later revision and then call it a real-time vintage.

The current closest-data lane records the status of every predictor in
`output/cnb_paper_replication_20260910/a6_variable_audit.csv`. The corrected
mapping currently has 15 exact mappings, 20 clearly-labelled proxies and 37
missing predictors;
therefore its score is a screening result, not a replication of the paper's
published TVW3 RMSEs.
