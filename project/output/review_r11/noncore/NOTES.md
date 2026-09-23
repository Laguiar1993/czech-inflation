# Frozen R9 non-core attribution audit

All figures are percentage points of monthly headline inflation. Error means forecast minus first-release actual. The audit creates no forecasting candidate and changes no repository model, data or output.

## Result and checks

The dominant non-core weakness is administered prices. Weighted component-error RMSE across the 90 origins is admin 0.347293, food 0.161949, alcohol/tobacco 0.080294 and fuel 0.007208. The reconciliation-error RMSE is 0.083601. Fixed non-core error RMSE is 0.384192; HARD_BASE headline RMSE is 0.417952. On the 23 large surprises, admin RMSE is 0.615041 and fixed non-core RMSE is 0.632813. Excluding October 2022, admin remains the largest non-core error (RMSE 0.235128 versus food 0.158190).

* `solve_weights(..., as_of=ref.as_of_eve)` reproduces `independent_nowcast_forecasts.coreweight` exactly at all 90 origins.
* Weighted food + fuel + administered + alcohol forecasts + forecast wedge reproduce frozen `fixed_noncore` within 3.99e-16. HARD_BASE forecast identity is within 8.89e-16; its error identity is within 6.32e-16. The earlier large-surprise diagnosis's fixed non-core error agrees within 5.56e-16.
* Alcohol, admin, fuel and wedge were independently replayed from frozen fixtures at all 90 release-eve timestamps: maximum deltas respectively 2.43e-17, 0, 0 and 1.39e-17. Food/X-13 replay at all eight requested focus origins is exactly equal to the frozen forecast. All eight used X-13, with histories ending at t-1 and no unavailable or missing food feature at the origin.
* The 11 input fixture hashes match their frozen manifest. The scored headline is from `czcpmom_survey_history_extended.csv`, after excluding the one `flash_survey_suspect` row. All 90 origins have one valid actual.
* `contribution_report.py:57` uses month-end weights with release-eve forecasts. This is a clock inconsistency but has **zero numerical impact on these 90 origins**: every report weight agrees exactly with the independently solved release-eve weight. Its actuals also agree with frozen fixture actuals to floating-point precision. It did not cause the reported misses.

## Focus cases

| Month | HARD_BASE error | Admin error | Food error | Alcohol error | Wedge error | Diagnosis |
|---|---:|---:|---:|---:|---:|---|
| 2020-06 | -0.256118 | -0.016191 | +0.047211 | -0.270385 | -0.043323 | Alcohol forecast -0.1602% versus actual +2.9486% is dominant. |
| 2022-02 | -0.433575 | -0.303590 | -0.123830 | -0.038291 | -0.072433 | Admin and food undershoot. |
| 2022-04 | -1.058141 | -0.441586 | -0.383161 | +0.120001 | -0.071240 | Admin and food compound the core undershoot; alcohol partly offsets. |
| 2022-05 | +0.027343 | -0.158512 | +0.032960 | -0.040349 | -0.066906 | Apparent accuracy is cancellation between positive core error and negative non-core error. |
| 2022-09 | -0.637908 | -0.648012 | -0.081847 | -0.006868 | -0.038215 | Admin undershoot dominates. |
| 2022-10 | +2.572948 | +2.436129 | -0.365120 | -0.033997 | +0.343683 | Admin forecast 0% versus actual -16.9%; reconciliation error further amplifies the miss. |
| 2022-11 | -0.441484 | -0.750841 | -0.061545 | -0.034650 | +0.087410 | Admin forecast 0% versus actual +4.8%; positive core and wedge errors partly offset it. |
| 2024-04 | -0.164486 | -0.015141 | -0.124884 | -0.187526 | -0.036014 | Alcohol forecast -0.0564% versus actual +2.1597%, plus food undershoot. |

Fuel contribution errors in these eight cases are between -0.003526 and +0.006343 pp; fuel is not a material explanation.

## Why better core can worsen headline

In each of the four large events, the old core error offsets negative fixed non-core error. Improving core accuracy removes that offset. This is a forecast-loss identity, not evidence that better core measurement is harmful.

| Month | Old weighted core error | Category weighted core error | Fixed non-core error | Increase in headline absolute error |
|---|---:|---:|---:|---:|
| 2022-02 | +0.098228 | +0.041166 | -0.531802 | +0.057061 |
| 2022-05 | +0.258501 | -0.130008 | -0.231158 | +0.333823 |
| 2022-11 | +0.318717 | +0.211282 | -0.760201 | +0.107435 |
| 2024-04 | +0.197207 | +0.145347 | -0.361693 | +0.051860 |

May 2022 is the clearest example: +0.258501 core error and -0.231158 non-core error produce a nearly correct +0.027343 headline error. Category core is closer to its own actual, but its -0.130008 error combines with the same -0.231158 remainder to produce -0.361166 headline error.

## Wedge interpretation

Use `wedge_error = forecast_wedge - (first_release_headline - sum(weight * realised_component))`. Treating the forecast wedge itself as an error is incorrect.

The forecast wedge is small (RMS 0.022392 pp), while the realised reconciliation is RMS 0.080200 pp. Forecast-wedge error offsets the aggregate weighted component error in 48/90 origins and reduces its absolute size in 42/90. Nevertheless, it raises mean absolute error by 0.006245 pp overall, and by 0.034605 pp on the 23 large surprises. Setting this error to zero is an **oracle reconciliation diagnostic**, not an attainable forecast.

Removing only the predicted wedge from frozen forecasts gives diagnostic RMSE 0.418415 versus actual HARD_BASE 0.417952: the predicted wedge itself adds little aggregate accuracy. This arithmetic is not a fitted candidate or adoption recommendation. In October 2022 the predicted wedge is only -0.013238, whereas realised reconciliation is -0.356921, producing +0.343683 reconciliation error. In November 2022 wedge error +0.087410 partly cancels the admin undershoot, while February/May 2022 and April 2024 wedge errors worsen negative non-core error. The four core-improvement reversals are principally core/non-core cancellation, not a large predicted wedge.

## What is a bug, and what is a model limitation

No arithmetic, fixture mismatch, unavailable current food feature, X-13 fallback or release-eve weight error was found in the requested cases. The report's clock inconsistency is harmless in the scored sample and should be aligned when the report is next maintained.

`admin_forecast` (`cz_struct.py:794-852`) returns its same-month seasonal median immediately whenever the target month is not January. Thus February, April, May and September 2022 receive only 0.1% admin forecasts, and October/November receive 0%. The historical announcement file has no October-2022 event row; its January-2023 notes explicitly describe the October-December electricity saving tariff and its reversal. The code also explicitly records that its November-2021 VAT row is outside the January-only gate. These observations establish a coverage limitation in the model/event calendar. This audit has not independently verified an ex-ante October-2022 bill-to-CPI magnitude; importing the realised -16.9% would be hindsight.

Alcohol uses an expanding same-calendar-month mean (`cz_struct.py:455-466`), so the June-2020 and April-2024 jumps receive no current tax, repricing or product information. The frozen data establish the miss but cannot alone identify excise, timing or product-level causes. Food has genuinely large misses despite correctly replayed X-13 and available lagged pipeline features; the frozen data do not establish that any different specification would improve an untouched sample.

First-release headline and the fixture's index-derived headline differ in 86/90 months, RMS 0.031008 pp and maximum 0.089873 pp. This is consistent with differing target representations/rounding or vintages, but the audit does not separately identify those causes. The exact error identity uses the first-release headline and assigns that difference to reconciliation, not to component prediction errors.

## Priority and scope

1. Preserve the simple BASE/category/HALF/FULL nowcast roster. These diagnostics do not justify additional forecasting candidates.
2. If undertaking new work, the largest potential issue to investigate is dated administered-price event coverage outside January, with archived ex-ante sources and an explicit bill-to-CPI mapping. Keep retrospective reconstructions separately labelled.
3. Next investigate food and the alcohol/tobacco jumps with archived component/tax timing before changing forecasts. Fuel has very low attribution priority.
4. Align the report's timestamp and retain frozen source hashes, first-release target choice and exact reconciliation checks as reporting maintenance.

This remains pseudo-OOS research on frozen latest-vintage component/features data with publication rules, not a vintage-certified historical nowcast. Source hashes, runtime, X-13 binary hash and replay checks are in `manifest.json`. Detailed exact identities are in `exact_attribution_all90.csv`; focus cases, replay tables and score tables are separate CSVs. `audit_noncore.py` followed by `targeted_replay.py` reproduces the diagnosis entirely offline and writes only in this directory.
