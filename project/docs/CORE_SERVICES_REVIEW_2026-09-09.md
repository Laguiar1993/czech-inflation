# CZK CPI forecasting — services and core review

9 September 2026. R10 research extension of the independent R9 models.

**Finding:** the simple five-category services model improves core RMSE by 17.8%
and headline RMSE since 2024 by 9.7%. It is useful enough to keep as an accuracy
challenger and category monitor. It is not a better large-surprise model, and
the overall headline advantage is too fragile to justify replacing the main
forecast. The experiment also uncovers a mislabelled legacy services input.

## What this experiment addresses

Services already affect the core inflation target. A model does not need an
explicit restaurant equation to contain restaurant inflation. The question is
whether separately predicting rents, catering, accommodation and holidays makes
the forecast more accurate, more interpretable, or both.

Those are distinct objectives. A useful category monitor can show pressure
building without earning the right to replace the headline model. Conversely, a
precise aggregate forecast does not tell us which individual prices will rise.
We now test both objectives, retaining the independent R9 forecasts as fixed
references. No professional or household inflation expectations, ESI or current
release consensus enters a new predictor. The survey file is opened only after
all forecasts have been produced.

## A correction to the existing input description

The legacy `services_l1` input is **not official services CPI**. Its source table
contains the simple arithmetic average of the index levels of six whole CPI
divisions: health, information/communication, education, restaurants/hotels,
insurance/financial services, and personal care/other services in the current
classification. The older labels differ, but the numeric selection is divisions
06, 08, 10, 11, 12 and 13. The table's `weight_sum = 6` is a count, not a consumer
expenditure weight. The audit reproduces all 834 stored rows to 5.68e-14.

This construction includes some goods and omits rents, passenger transport and
package holidays. Worse, averaging differently based price-index levels is not
invariant to rebasing. Using the stored 2015 and 2025 bases changes this proxy's
monthly rate by as much as **0.224 percentage points**. That number is a change
in the input, not a measured 0.224-point change in the headline forecast.

An arbitrary proxy can still carry predictive information. Its misdescription
does not invalidate every historical error calculation. It does invalidate the
claim that this feature measures official aggregate services inflation. We retain
the frozen R9 results and test removal and replacement explicitly; silently
rewriting the input would destroy the comparison.

## What the official data do and do not provide

The ARAD CPI_CLE series identify other tradables excluding food and fuel
(`SCPICLEM02YOYPECNA`) and nontradables excluding regulated prices
(`SCPICLEM03YOYPECNA`). They are mainly goods and mainly services, respectively,
not exact economic synonyms. The published monthly observations are **year-on-year
rates**, not month-on-month changes. The two histories have 283 observations,
January 2003–July 2026.

First-round indirect-tax effects remain in those series. Our CNB core target
excludes them. Consequently, combining them as if they were an exact tax-adjusted
monthly core partition would be wrong. The separately available monthly
seasonally adjusted macro series lack archived historical seasonal vintages and
are excluded from this experiment. We do not manufacture a monthly NSA history
by treating annual rates as monthly rates.

These distinctions follow the [CNB tradable/nontradable methodology](https://www.cnb.cz/docs/ARADY/MET_LIST/cpi_cle_en.pdf)
and [CNB monetary-policy inflation methodology](https://www.cnb.cz/docs/ARADY/MET_LIST/cpi_mz_en.pdf).
The freshly retrieved monthly core series agrees exactly with all 235 overlapping
observations in the frozen target.

CZSO supplies five useful national CPI groups. All 695 saved index observations
match the current official raw file exactly, covering January 2015–July 2026.

| Group | Current code | What it measures | 2026 base-basket weight |
|---|---|---|---:|
| Actual rent | 041 | Rent paid by tenants | 3.450% |
| Imputed rent | 042 | Owner-occupied housing costs under the Czech CPI concept | 11.930% |
| Catering | 111 | Restaurants and catering, including canteens and school meals | 6.007% |
| Accommodation | 112 | Hotels and other accommodation, including dormitories | 0.809% |
| Package holidays | 098 | Package travel; historical basket code 09.6 through 2024 | 1.854% |

Source: [CZSO CPI open dataset CEN0101E](https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv)
and the archived detailed baskets in the repository. The current code 096 means
cultural services, so matching holidays by the old numeric code would pick the
wrong category. The export explicitly uses COICOP 2018 classifications throughout
the current history. This establishes the present file's coverage, not that the
same classification and values were available at every historical forecast date.

## Construction and controls

All new equations use expanding ridge regression with a fixed penalty of 3 and
at least 48 released target observations. Scaling and missing predictor means
are estimated only on the training sample. No hyperparameter search is performed.

**Predictor audit.** `NO_PROXY` removes the six-division input. The
`OFFICIAL_PREDICTORS` version replaces it with the two official annual rates,
lagged one published month. The other independent core features stay fixed.

**Broad goods/services experiment.** For each official annual inflation rate Y,
define its monthly change in log gross annual inflation:

    d_t = 100 × [log(1 + Y_t/100) − log(1 + Y_(t−1)/100)].

Separate equations forecast goods and services d using their own lags 1, 2 and
12 plus calendar-month indicators. A convex projection, estimated on only the
last 60 past months, links these quantities to the core target. A separately
forecast reconciliation residual covers tax, scope and aggregation differences.
The goods coefficient is a statistical projection, **not an official basket
weight**. There is also an aggregate annual-change control.

The conversion back to core monthly inflation is an exact index identity:

    predicted core m/m = 100 × {exp[predicted core d/100
                               + log(1 + core m/m_(t−12)/100)] − 1}.

The identity is exact; the forecast and the estimated projection need not be.

**Targeted monthly services experiment.** Each index becomes its exact percentage
change, 100 × (index_t/index_(t−1) − 1). Five category equations are combined with
an explicit remaining-core/tax/reconciliation equation. At every origin:

    remaining contribution_s = core_weight × core_m/m_s
                               − sum(category_weight_j × category_m/m_j,s).

The origin's weights are frozen when constructing the entire historical residual.
The residual and category forecasts then add back to the projected core
contribution. The remaining term is not claimed to be pure goods, and including
these groups does not double-count their realised contribution: the residual
subtracts them by construction. Their uncertain core membership can nevertheless
make that residual harder to predict.

The weights are base expenditure weights, not price-updated current shares.
These are therefore **approximate contribution projections**, not a reproduction
of official CPI contribution arithmetic. This distinction matters especially for
large holiday-price movements and changing relative prices.

`TARGET_OWN` uses each group's own lags and month indicators. `TARGET_CHANNEL`
adds previously available food/processor prices for catering, FX and a known
nine-day Easter exposure for accommodation/holidays, and independent FX/import/
state features for the remainder. Rents use their own dynamics in this bounded
test. There is no wage interpolation or new sentiment input.

`AGG_COMMON` fits aggregate core on the same shorter, complete target window.
`TARGET_SHARED` uses the same regressors and training dates for every category
and its residual. With fixed weights, these linear fits must reproduce
`AGG_COMMON` exactly. This is an arithmetic control, not another forecasting
discovery. It prevents attributing a training-window change to disaggregation.

Fixed half blends combine each substantive candidate with R9 BASE. The blend
weights are not selected on these outcomes. The original R9 HALF/FULL corrections
remain separate reference models; their fitted residual corrections are not
transplanted onto a different core estimator.

## Timing and interpretation

The score uses the same 90 first-release origins, February 2019–July 2026,
and the same release-eve clocks as R9. Before January 2025 the target is the
ordinary first release; from January 2025 it is the flash. Later detailed CPI
values supply historical component labels, not replacement first-release
headline outcomes.

New component histories are masked before constructing their lags. The current
target and future rows cannot influence a fit. Component availability follows
the existing detailed-CPI release calendar at 09:00 Prague, with the declared
pre-calendar fallback. An unrecorded release inside or after the calendar fails
closed. Basket selection retains the previously agreed midnight publication-date
convention and selects only an effective regime already published at the origin.

These are reconstructed availability rules. In particular, the exact historical
ARAD posting lag and historical recoded CPI vintages have not been recovered.
Source retrieval timestamps and hashes are genuine; they do not turn this into
a recorded real-time backtest. The same caveat applies to R9's frozen predictor
histories. Honest timing code reduces look-ahead risk but cannot undo historical
model selection or source revisions.

All candidates receive ordinary MAE, RMSE and bias scores, plus recent,
ex-January and flash-era panels. Large surprises mean |first print − corresponding
survey| ≥ 0.4 points. A material win means reducing absolute error by at least
0.15 points; material losses are counted symmetrically. Every forecast deviation
of at least 0.2 points is evaluated as an alert, including false calls. Merely
predicting the right side of consensus earns no material win. Overshoot incurs
the full absolute and squared forecast loss.

Paired circular block-bootstrap intervals use 3, 6 and 12-month blocks, 5,000
draws and seed 42. They describe uncertainty conditional on the explored models;
they do not correct for all past model searches. The prespecified practical gate
requires at least 2% all-period RMSE improvement, no more than 2% MAE deterioration,
and no more than 5% recent RMSE deterioration. Passing it earns further testing,
not proof of prospective skill or a trading rule.

## Results and operating recommendation

All models cover the same 90 releases. Errors below are percentage points;
lower is better. The 2024+ window has 31 releases and the flash window has 19.

| Model | Headline RMSE, all | Headline MAE, all | Headline RMSE, 2024+ | Headline RMSE, flash |
|---|---:|---:|---:|---:|
| Existing independent BASE | 0.4180 | 0.2625 | 0.2190 | 0.1730 |
| Existing HALF correction | 0.4137 | 0.2644 | 0.2196 | 0.1656 |
| Existing FULL correction | 0.4139 | 0.2696 | 0.2253 | 0.1638 |
| Remove the old proxy | 0.4160 | 0.2621 | 0.2193 | 0.1731 |
| Official annual rates as predictors | 0.4125 | 0.2586 | 0.2203 | 0.1725 |
| Broad split, half blend with BASE | 0.4103 | 0.2607 | 0.2053 | 0.1648 |
| **Five categories, own dynamics** | **0.4089** | **0.2565** | **0.1978** | **0.1610** |
| Five categories, half blend with BASE | 0.4099 | 0.2558 | 0.2059 | 0.1650 |
| Five categories, additional economic channels | 0.4114 | 0.2595 | 0.2021 | 0.1586 |
| Corresponding first-release survey | 0.3815 | 0.2533 | 0.2410 | 0.1947 |

The own-dynamics category model is the only candidate to pass all three
prespecified practical gates. It improves overall headline RMSE by 2.15%, MAE
by 2.29%, and recent RMSE by 9.67%. The half blend improves MAE slightly more
but narrowly misses the 2% RMSE gate; that cutoff is an operating rule, not a
statistical law. We do not relabel the rule after seeing that near miss.

The broad split alone has headline RMSE 0.4150 and MAE 0.2703. Its aggregate
annual-change control has RMSE 0.4134: broad disaggregation itself does not beat
that control. The shorter-window aggregate core control scores 0.4168, reproduced
by the identical-design category split to numerical precision. The own-dynamics
category result is therefore more than a simple change of training window.

### Is the core block itself better?

Yes, on these reconstructed histories. The category forecast reduces core RMSE
from 0.2997 to 0.2465 (17.8%), and core MAE from 0.2409 to 0.1829 (24.1%). Since
2024, core RMSE falls from 0.1901 to 0.1416 (25.5%). The same-window aggregate
control has core RMSE 0.3005 overall and 0.1754 recently; it does not explain
away the category result. These core scores use the detailed tax-adjusted core
target, whereas headline scores always use the first print.

The own-category equations also beat the mean of up to five previous
same-calendar-month observations
for all five categories over the full window. The gains are strongest for
imputed rent, catering and package holidays. Actual rent barely improves, and
its recent RMSE is worse than that seasonal comparison. This argues for selective
category modelling and a simple benchmark for every group, not automatically
building a large separate model for each item.

Adding the extra economic channels reduces core RMSE slightly further overall
(0.2445), but its core MAE and headline accuracy worsen relative to the simple
category model. The present evidence does not justify that extra complexity.

### Why the headline improvement needs restraint

The all-period paired RMSE difference versus BASE is -0.0090 points. The
six-month-block 95% interval is roughly **[-0.0274, +0.0093]**, spanning no gain.
The recent estimate is stronger but its interval is sensitive to block length;
the three-month-block interval still crosses zero. None adjusts for the many
models explored over the life of this project.

There is also a material concentration issue. **Omitting October 2022 reverses
the full-period headline ranking:** BASE RMSE becomes 0.3198 and the category
model 0.3236, a 1.18% deterioration. Omitting the whole of 2022 instead leaves
the category model 4.25% better. These are diagnostics, not alternative samples
selected to support a claim; the saved table reports every single-origin deletion.

October's category core forecast is actually much closer to the core outcome:
1.214% versus 1.200%, compared with BASE's 1.533%. But the unchanged non-core
and reconciliation contribution leaves the headline prediction at +0.995%
against a -1.400% first print. A core improvement cannot fix that miss. More
generally, improving one block may remove an accidental offset to another
block's error. The saved attribution decomposes every headline squared-error
gain into the weighted core improvement and this cross term.

This is why I would retain the category model as a serious challenger while
examining the energy-policy/non-core accounting behind the large remaining
misses. I would not claim that splitting core has solved the headline forecast.

### Does it better serve the large-surprise objective?

Not consistently. There are 23 large surprises in this sample.

| Model | MAE on large surprises | Correct side of survey | Material wins / losses vs survey |
|---|---:|---:|---:|
| BASE | 0.485 | 17/23 | 7 / 3 |
| Existing HALF | 0.479 | 16/23 | 7 / 1 |
| Existing FULL | **0.476** | **17/23** | **9 / 2** |
| Five-category own-dynamics model | 0.512 | 13/23 | 8 / 2 |
| Five-category half blend with BASE | 0.491 | 17/23 | 8 / 3 |
| Survey | 0.578 | — | — |

The new model still reduces average absolute error versus consensus on those
events, but it captures them less well than BASE/FULL. It improves ordinary
forecasting without earning the same surprise-capture role. Its better material
win/loss count alone would miss this deterioration in average capture and sign.

The category model emits 21 alerts: nine coincide with large surprises and
twelve do not. Total absolute-error reduction versus consensus across its alerts
is only +0.165 points, about +0.008 per alert. This is weak evidence for a usable
selection rule, particularly after model exploration. It is not a trading
profit calculation; pricing, horizons, execution costs and position sizing have
not been backtested here.

## What the category monitor adds

The latest retrieved category month is **July 2026**. These are observed values,
not a new prospective forecast. The seasonal comparison uses the previous five
Julys, which include the inflation shock years; it is a descriptive benchmark.

| Category | July m/m | July y/y | Previous five Julys, mean m/m | Approximate excess contribution |
|---|---:|---:|---:|---:|
| Actual rent | +0.830% | +6.116% | +0.958% | -0.0044 pp |
| Imputed rent | +0.897% | +5.698% | +0.691% | **+0.0246 pp** |
| Catering | +0.239% | +4.010% | +0.748% | -0.0306 pp |
| Accommodation | +0.794% | +6.365% | +1.149% | -0.0029 pp |
| Package holidays | +23.042% | +3.611% | +23.406% | -0.0067 pp |

Holidays illustrate the value of disaggregation particularly well. Their 23%
monthly increase looks dramatic, and their base-weight contribution is about
0.427 headline points, but that increase is slightly below the previous five
Julys' average. Imputed rent shows the stronger positive deviation from that
seasonal benchmark. Looking only at raw percentage increases would tell the
wrong story about unusual pressure.

The next version of this display should consistently show level/momentum,
same-month history, approximate contribution, forecast error and the publication
clock for every monitored category. It should distinguish official observed
data, model forecasts and judgemental scenarios visibly.

## Recommended structure and next work

1. **Keep the existing independent BASE as the frozen main reference.** HALF and
   FULL retain their already documented accuracy/surprise comparison roles.
   Correct the services-proxy description now; do not silently rewrite history.
2. **Keep one new category accuracy challenger: `TARGET_OWN`.** It has simple,
   interpretable dynamics and the strongest justified accuracy case here. Keep
   its fixed half blend in the evidence as a sensitivity check. Do not turn each
   experimental column into another live operating model.
3. **Use the category monitor now as an explanatory diagnostic.** It adds useful
   information even before the forecasting model is promoted. The frozen
   experiment is runnable offline; a refreshed prospective category forecast is
   not yet integrated into the production live command.
4. **Before integrating that challenger, resolve contribution mapping and archive
   the actual releases.** Establish price-updated shares, an item-level core/
   regulated/tax concordance, recorded category vintages and reliable refresh
   timestamps. A detailed-services forecast plus a broad reconciliation residual
   is an effective experiment, but not yet an official disjoint CPI partition.
5. **Prioritise the large residual headline misses.** Audit energy-policy starts,
   expiries and household bill exposure against the unchanged non-core leg. The
   October 2022 diagnostic is a concrete target. Do not repair it by selecting
   whatever core equation happens to offset it.
6. **For a subsequent declared category experiment, test restrained pooling and
   group-specific seasonal benchmarks.** Shrink weak rent/accommodation equations
   toward their simple histories, and investigate imputed-housing repricing and
   holidays' price-collection/calendar mechanics. These are proposals; no such
   new search was run in this round. The CNB's
   [analysis of different goods/services price dynamics](https://www.cnb.cz/en/monetary-policy/monetary-policy-reports/boxes-and-articles/Several-perspectives-on-the-different-development-of-goods-and-services-prices/)
   supports separating mechanisms, not indiscriminately adding predictors.

The path model should eventually reuse these category definitions and price-index
accounting. It needs different dynamics and assumptions beyond the next release;
extending this short-term autoregression twelve months is not a substitute for
that work. The category experiment leaves the previously delivered path models
unchanged.

## Reproduction and evidence map

`python core_split_experiment.py` regenerates the frozen experiment.
`python core_split_experiment.py --verify` checks current saved outputs and input
hashes, blocks network/database access and regenerates all outputs for comparison.
Use the supplied Python dependency environment; the experiment itself requires
no X-13 executable or quantile forest fitting because the non-core reference
contribution is frozen.

| File or directory | Purpose |
|---|---|
| `data/core_split/` | Official snapshots, definitions, source replies and SHA256 manifest |
| `models/core_split.py` | Fixed forecasting equations and identities |
| `evaluation/core_split.py` | Coverage, event scores, paired uncertainty and practical gates |
| `output/core_split_forecasts.csv` | Every headline candidate for all 90 releases |
| `output/core_split_releases.csv` | First print, matching survey, errors, material gains and alerts |
| `output/core_split_core_scores.csv` | Core target accuracy and unchanged reference |
| `output/core_split_category_scores.csv` | Each group's forecasts against seasonal history |
| `output/core_split_contributions.csv` | Forecast categories and reconciliation, seasonal comparison |
| `output/core_split_component_error_attribution.csv` | Exact core/non-core error decomposition |
| `output/core_split_leave_one_out.csv` | Every omitted-origin sensitivity |
| `output/core_split_latest_categories.csv` | Latest observed category monitor |
| `output/core_split_fit_audit.csv` | Per-fit training dates and last target release |
| `output/core_split_observation_calendar.csv` | Per-month assumed availability, explicitly distinguished from recorded vintages |
| `output/core_split_weights.csv` | Origin-specific basket regime and publication assumption |
| `output/core_split_manifest.json` | Code/input/output hashes and declared interpretation |

Independent review found and cleared two implementation issues: mismatched broad
training calendars and replay verification that originally checked regenerated
results without first validating saved output files. Both have regression tests.
The full repository suite passes **326 tests**, with three existing X-13 warnings.
The R9 core baseline reproduces exactly at every origin. Final offline replay
and delivery integrity are recorded in the accompanying verification receipt.
