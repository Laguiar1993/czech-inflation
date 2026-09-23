# CZK CPI path: shared shocks and model-specific weaknesses

9 September 2026. These diagnostics use frozen forecasts and never enter the
estimation of a model. They address whether a large realised miss necessarily
implies bad economic modelling. It does not. Equally, a forecast close to CNB
is not automatically a well-founded or accurate forecast.

## What the data show

| Forecasts issued in | Report/quarter pairs | Bridge RMSE | CNB RMSE |
|---|---:|---:|---:|
| 2022 | 16 | 4.202 | 4.615 |
| 2023 | 16 | 2.150 | 0.375 |
| 2024 | 16 | 0.560 | 0.370 |
| 2025 | 15 | 0.661 | 0.383 |
| 2026, realised pairs only | 3 | 0.303 | 0.319 |
| All | 66 | 2.362 | 2.295 |

Errors are percentage points of quarterly-average annual inflation, across
available one-to-four-quarter horizons. They are not the monthly nowcast or
the twelve-month endpoint score. The all-period table covers 18 unique realised
quarters; multiple forecasts of a quarter are dependent observations. Recent
reports have 34 scored pairs but only ten unique quarters.

The 2022 numbers are consistent with an unusually difficult common forecasting
environment. The 2023 numbers show that a shared-shock explanation cannot account
for all the bridge's subsequent weakness. For example, the February 2023 report
comparison for 2023Q1 is bridge 11.36%, CNB 16.31%, realised 16.39%. That gap is a
diagnostic flag, not a causal allocation: the model path was frozen on 10 January,
29 days before the report. It did not have the same information set as the bank.

Across all 66 scored pairs, 44 have same-direction forecast errors. Sixteen have
same-direction errors of at least 0.5pp for both forecasts. Our bridge is closer
on 20 pairs, CNB on 46. These figures do not count unpredictable shocks or trading
opportunities. Common errors may also reflect common assumptions or weaknesses.

The archive contains 161 bridge report/quarter rows, including unavailable and
not-yet-realised destinations. Seventy-six have complete model/CNB forecasts;
66 can be scored. Model-CNB disagreement can be assessed before the outcome is
known; realised accuracy cannot. Summary and coverage files keep the distinction.

## Forecast updates and information timing

There are 48 scored adjacent-report revisions of the same destination quarter.
Model and CNB revisions have the same direction on 30. The model reduces absolute
error on 32 updates and CNB on 27, but these counts ignore revision size and initial
error: they do not establish superior adaptation. New information may require a
rational forecast revision that happens to be wrong ex post.

The model forecast used at each report predates publication by a median eight
days, sometimes roughly a month. CNB's internal cutoff is different again.
Matching public report dates prevents using a future model forecast; it does not
deliver identical information sets. Missing intermediate model reports remain
explicit unavailable revision pairs, rather than being silently skipped.

## How to evaluate economic plausibility

Keep three separate assessments:

1. Realised forecast accuracy on every available outcome, including shock periods.
2. Ex-ante plausibility: declared assumptions, component accounting, sensible
   responses, and explained differences from an independent professional forecast.
3. Updates after new information: same-destination revisions, changes in underlying
   assumptions and components, and uncertainty calibration.

The exact identity e_model = e_CNB + (model-CNB), including its squared-error cross
term, is useful accounting. The discrepancy is not an identified specification
error, and the CNB error is not an identified unforeseeable shock. The present
bridge does not have the archived forward external assumptions or structural
counterfactual system needed to separate those causally.

The CNB's review of forecasts made in 2022 explicitly discusses mistaken foreign,
fiscal and administered-price assumptions, including war-related energy changes.
Its review of the 2024 forecasts also distinguishes assumptions from the core
model's behaviour. That motivates a dated assumptions archive and conditional
scenario tests for our future work. A retrospective run with realised external
assumptions would be an explanatory diagnostic, never an honest historical forecast.

Sources, accessed 9 September 2026:

- [CNB review of its 2022 forecasts](https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/boxes-and-articles/Assessment-of-the-fulfilment-of-the-2022-forecasts)
- [CNB review of its 2024 forecasts](https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/boxes-and-articles/Assessment-of-the-fulfilment-of-the-2024-forecasts/)

The frozen statistical values still have the previously declared latest-vintage
and reconstructed-publication limitations. This is not a new untouched holdout.
