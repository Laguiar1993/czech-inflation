# Core goods/services experiment implementation plan

Approved design: Luis approved separating core goods and services, followed by targeted services groups where the data justify them, and comparing the result with the existing aggregate forecast. No further design approval is needed for this bounded experiment.

Goal: establish whether a properly mapped core decomposition improves the independent release nowcast and material surprise capture.

Architecture: keep the R9 independent baseline and non-core forecasts fixed. Retrieve and freeze official CNB/CZSO component histories and metadata. Forecast disjoint subcomponents from only previously released observations, aggregate them using origin-available weights or an explicitly labelled estimated projection, and compare the split and a fixed half blend with the existing baseline. Do not label broad total-goods/total-services indices as core subcomponents.

Implementation uses the existing isolated branch, Python/pandas/scikit-learn and the existing first-release calendar. Execution follows the test-first and review workflow. The existing portable R9 package is retained.

- [ ] Source and partition audit: inspect ARAD metadata and local CZSO tables; establish exact definitions, tax treatment, weights and historical coverage. Save requests, raw replies, retrieval timestamps and SHA256. If official core subcomponents are unavailable, document the exact restricted alternative before estimating.
- [ ] Add source/aggregation tests in `test_core_split_r10.py`: invalid or duplicate calendars, unavailable observations, empty histories, disjoint contributions, no forward weights/outcomes. Add `data/core_split.py` for validated frozen input loading and publication eligibility.
- [ ] Add `models/core_split.py`: fixed ridge alpha 3, minimum 48 released observations, target lags 1/2/12 and month dummies; shared independent features and a restrained channel-specific comparison where appropriate. All standardisation/imputation estimated within the training slice. Test future-data and expectations poisoning.
- [ ] Add `core_split_experiment.py`: read the 90 R9 origin clocks; recombine the unchanged non-core remainder with the split core. Include aggregate reference, split and fixed 50/50 blend. A identical-design split is a diagnostic control: linear estimators with constant weights and identical regressors may commute, so a meaningful improvement needs a justified difference in dynamics, information or weighting.
- [ ] Report common/own coverage, first-release MAE/RMSE/bias, ex-January, 2024+, flash, large surprises >=0.4pp, material gains/losses >=0.15pp and alerts >=0.2pp including false alarms. Add paired block-bootstrap differences and release/component attribution. Core outcomes are auxiliary targets; headline first prints remain the primary evaluation.
- [ ] Where source coverage permits, test a small documented services breakdown and its fixed blend; otherwise finish the broad split and explicitly identify the missing mapping/data. Do not fit dozens of searched subgroups or tune against all outcomes.
- [ ] Test, independently review arithmetic/timing, and freeze code/data/results. An exploratory practical promotion requires >=2% common headline RMSE improvement without >2% MAE or >5% recent RMSE deterioration; inspect large-surprise and false-alarm results separately. Historical model search is not erased by this rule.
- [ ] Record the verdict in model documentation, provide a runnable frozen experiment and optional live challenger only if justified, commit the experiment on the isolated branch, and deliver a user-readable report and portable addendum.

## Source findings and frozen specification before scoring

The verified ARAD CPI_CLE catalogue exposes NSA year-on-year tradables excluding
food/fuel and nontradables excluding regulated prices, not their monthly NSA
changes. Its methodology explicitly retains first-round tax effects. The DPSZ
monthly series are seasonally adjusted and lack historical vintages; they are
excluded from this experiment. A fictitious exact monthly core split is not built.

The experiment therefore has three declared parts:

1. Predictor audit: compare R9 BASE with removing the six-division proxy and
   replacing it with the two official NSA annual inflation rates, lagged one
   published month. Their units and tax-inclusive concepts are explicit.
2. Broad split: forecast monthly changes in log annual gross inflation of
   tradables and nontradables using separate own dynamics. A constrained past-only
   60-month projection estimates the tradables coefficient. A separately forecast
   residual preserves the distinction between these tax-inclusive aggregates and
   core. Convert predicted core log annual change to monthly inflation by adding
   the observed same-month-last-year core log change. This identity is tested;
   the coefficient is a statistical projection, not an official basket weight.
3. Targeted services: forecast actual rent, imputed rent, catering, accommodation
   and package holidays in monthly percentages, plus a remainder. The remainder
   is core's weighted contribution minus these five weighted contributions and
   explicitly includes tax/classification/reconciliation differences. It is not
   labelled pure 'other goods'. At each origin all historical residuals use that
   origin's frozen coefficients. Category weights come from detailed archived
   baskets with the existing publication convention. Catering includes canteens
   and accommodation includes dormitories, so clean core membership of every item
   is not claimed. Aggregate/common-window and identical-design linear controls
   distinguish disaggregation effects from training-window effects.

Fixed variants: own lags 1/2/12 plus calendar-month dummies; a channel variant adds
lagged food/processor prices for catering, observable FX and known Easter exposure
for accommodation/holidays, and independent FX/import/state inputs for the
remainder. No wage interpolation, SA vintage, survey expectations or new training
hyperparameter search. Missing exogenous values are imputed within the training
slice, while unavailable target histories cause an explicit failure. Fixed 50/50
blends are reported without selecting a weight on the scored outcomes.

CNB/CZSO component release dates inherit the detailed-CPI publication convention
and basket dates inherit the existing declared rule. Retrieval dates are genuine;
historical available_from stamps are rules, not archived observation vintages.

Pre-scoring control clarification: all broad goods/services/reconciliation
equations and the aggregate annual-change control fit the same intersection of
released target dates. Own predictor histories can extend earlier where those
observations are known. The reviewer identified an 11-month label-window
difference before the first scored run; it is corrected and regression-tested.
Category coefficients remain base-basket weights and are labelled approximate
projections; they are not substituted for price-updated official contributions.
