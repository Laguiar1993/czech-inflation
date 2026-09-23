# Predeclared ablation: what the survey variables contribute to the nowcast and to the path

Declared 8 September 2026, BEFORE running. One run, no adoption rule:
this is a measurement the user asked for ("is the nowcast using surveys,
and how much worse without them"), not a candidate change. The frozen
trio is not touched.

## What the nowcast uses

The core block's ridge frame carries four survey-based columns and one
interaction: `exp12` and `exp36` (CNB Financial Market Inflation
Expectations, one- and three-year CPI expectations, monthly, published
mid-month), `household_exp` (European Commission consumer survey, price
expectations balance, published month-end), `esi` (European Commission
Economic Sentiment Indicator, month-end), and `exp12_x_state` (the
one-year expectation interacted with the high-inflation state). The
consensus of the CPI print (Bloomberg survey) is never a predictor. Food,
administered, alcohol-tobacco and fuel blocks use no survey.

## Cells (release-eve clock, the 90 backtest origins, core block only)

- A0 incumbent frame (equals the backtest `core_pred_eve`; harness check).
- A1 without the CNB expectations (`exp12`, `exp36`, `exp12_x_state`).
- A2 without the household expectations (`household_exp`).
- A3 without the sentiment index (`esi`).
- A4 without all four survey columns and the interaction.
Headline effect through the origin's solved core weight:
`headline = STRUCT_EVE + w_core x (core_cell - core_A0)`, as in EN_SPEC.
Direct-horizon effect: the same cells for the core ridge at h = 1, 3, 6
and 12 (plain frame at every horizon so the comparison is one frame),
block RMSE only.

## Reported

Core block RMSE and headline RMSE on all 90, ex-January, 2024+, 2025+;
big-surprise MAE and material W-L at 0.15 against the survey; mean
absolute change of the headline forecast per origin; the direct-horizon
core RMSE by cell at h = 1, 3, 6, 12 on the common valid sample, all
origins and 2024+ targets.

## Reading rule (stated before the numbers)

Differences under about 0.005 RMSE on the headline are noise at n = 90
(the standard error of an RMSE difference between two nearly identical
forecasts on this sample is of that order). The frozen trio stays as it
is whatever the result; if a cell were clearly better, that would be a
separate declared change with its own rule.

## RESULTS (8 September 2026, single run; log `output/survey_ablation_run.log`; rows `output/survey_ablation.csv`, `output/survey_ablation_h.csv`)

Harness: A0 equals the backtest core column to 4e-16.

Nowcast, release eve, headline RMSE (core block RMSE in brackets):

| split | n | A0 all surveys | A1 no CNB expectations | A2 no household exp. | A3 no ESI | A4 none | survey |
|---|---|---|---|---|---|---|---|
| all 90 | 90 | 0.420 (0.308) | 0.420 (0.301) | 0.419 (0.315) | 0.416 (0.298) | 0.418 (0.300) | 0.382 |
| ex-January | 83 | 0.404 (0.306) | 0.404 (0.298) | 0.404 (0.313) | 0.401 (0.297) | 0.403 (0.299) | 0.380 |
| 2024+ | 31 | 0.217 (0.182) | 0.220 (0.188) | 0.216 (0.182) | 0.216 (0.182) | 0.219 (0.190) | 0.241 |
| 2025+ | 19 | 0.170 (0.140) | 0.173 (0.141) | 0.171 (0.128) | 0.170 (0.140) | 0.173 (0.132) | 0.195 |

Big surprises (23): MAE 0.506 / 0.491 / 0.504 / 0.497 / 0.485; material W-L
7-1 / 7-2 / 5-2 / 7-1 / 7-3. Removing all four survey columns changes the
headline nowcast by 0.031 pp on average (maximum 0.158 pp). Every RMSE
difference is inside the 0.005 noise band declared above: the nowcast
does not depend on the surveys; the ridge holds their coefficients near
zero, which is also what the elastic-net experiment found when it dropped
`exp12` at half the origins.

Direct horizons, core block RMSE (all origins | 2024+ targets):

| h | A0 | A1 no CNB exp. | A2 | A3 no ESI | A4 none |
|---|---|---|---|---|---|
| 1 | 0.381 / 0.223 | 0.365 / 0.230 | 0.388 / 0.215 | 0.367 / 0.222 | 0.362 / 0.225 |
| 3 | 0.430 / 0.212 | 0.428 / 0.192 | 0.458 / 0.207 | 0.423 / 0.207 | 0.430 / 0.181 |
| 6 | 0.618 / 0.252 | 0.615 / 0.238 | 0.673 / 0.263 | 0.599 / 0.251 | 0.611 / 0.235 |
| 12 | 0.527 / 0.279 | 0.641 / 0.416 | 0.643 / 0.437 | 0.474 / 0.272 | 0.607 / 0.437 |

At twelve months the CNB expectation columns carry real level
information: without them the core block is 22% worse on all origins and
49% worse on 2024+ targets; the household expectation matters at twelve
months as well; the sentiment index does not help anywhere and removing
it improves h = 12. Reading: the surveys are irrelevant for the next
print and important for the level a year out, which is exactly where the
path model needs them (F2 of PATH_SPEC_v2 uses the CNB expectation as a
measurement of the trend). No change to the frozen trio.
