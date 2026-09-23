# R14 papers and benchmark audit

9 September 2026. Initial independent source research against R13 baseline
`4507182`, followed by an independent R14 audit. Core declaration is `06c2907`.
After that audit closed, the parent separately assigned this reviewer the optional
historical-import loader and runner interface under declaration `709d4b3`; that
later implementation is explicitly distinguished from the independent audit.
Local source PDFs were read from the user's Czech folder, with page-labelled
extraction retained outside the repository in `work/r14_papers_review/`.

## Prioritised implementable conclusions

1. **Learn departures from a moving core baseline.** R13's mean-loss ridge
   penalty of one strongly shrinks toward its global target mean. A separate
   local-trend-plus-gap specification can instead shrink the economically
   uncertain correction while retaining a baseline that moves when inflation
   changes. Retain short-minus-long own inflation momentum so the model can learn
   disinflation, rather than mechanically perpetuating a trailing twelve-month
   rate. This is a proposed adaptation, not a claimed replication of a paper.
2. **Use a tiny sequential selection problem.** Compare a fixed gap-ridge control
   with six declared configurations: conventional sum-loss ridge alpha
   3/30/300 crossed with last-60/expanding training. Use only stored candidate
   predictions made at their own historical clocks; select on at most 36
   fully released band errors, requiring 24, with a fixed default and deterministic
   tie rule. That is computationally tractable with the aggregate core history
   beginning in 2007, although the actual joint predictor coverage must be checked
   before claiming that much regression training history. It is much less
   statistically informative than 36
   independent observations because adjacent future bands overlap. It can test
   whether the arbitrary fixed penalty/window is harmful, not establish a
   universal optimal tuning rule.
3. **Use nonlinear models as bounded challengers to the same target.** A level
   forest and gap forest with identical predictors can distinguish nonlinear
   fit from local anchoring. Ordinary forest forecasts remain inside historical
   response support; a moving baseline plus bounded learned gap can change the
   forecast level outside the old level support. It still cannot anticipate a new
   residual shock without relevant training examples. The fixed leaf-five,
   one-third-feature convention has direct precedent in Medeiros et al.; extensive
   depth/leaf/window searches are not justified by this short Czech sample.

The parent's quarterly-band design (h1..3, h4..6, h7..9, h10..12) is a useful
bounded way to reduce separately estimated cumulative-target differencing noise.
Forecasting a mean monthly log core rate for each band, then adding destination
calendar effects and compounding, yields a coherent whole path. It is distinct
from R12's food smoothing/direct headline correction and R13's separate
monthly-versus-cumulative core equations. Do not call it a published-paper result.

For every historical origin, estimate seasonality and trend with that origin's
released history. Define its label using that saved seasonal vector, not the
outer origin's later seasonal estimate. Inner training features and outcomes must
be reconstructed at the inner forecast clock; a validation row becomes eligible
only after the last band month has been detailed-released. Alpha must have its
declared scale: sum squared error plus alpha times squared coefficients. R13's
mean-loss lambda=1 is equivalent to conventional alpha=n, not alpha=1.

Report default versus adaptive gap on identical dates, selected alpha/window
counts by band/year, and all fixed level/gap forest challengers. Keep endpoint
monthly errors, exact annual errors, cumulative log errors and component
attribution separate. Preserve all origins and bad years in the coverage ledger.

## What the papers actually establish

Page references below give PDF page followed by printed page where different.
The local PDFs are the sources of the detailed methodological descriptions.

### CNB: Blaha, Botka, Sveda and Michl, WP 9/2026

Source: [AI-Based Forecasting of Czech Inflation: Quantile Regression Forests
with Dynamic Weights](https://www.cnb.cz/export/sites/cnb/en/economic-research/.galleries/research_publications/cnb_wp/cnbwp_2026_09.pdf).
Local file `cnbwp_2026_09.pdf`, 42 PDF pages, issued April 2026.

- PDF pp9-10 / printed pp7-8: direct h-step **monthly** inflation quantiles are
  combined under simplex and stability bounds. The weighting criterion uses a
  twelve-month validation window and six-month exponential half-life. Forecasting
  uses an expanding sample with horizon-delayed labels. This is a precedent for
  adapting a low-dimensional combination to recent forecast errors, not for
  unrestricted hyperparameter searches on the final test sample.
- PDF p17 / printed p15: the 2021-23 surge exceeded predicted upper tails. The
  authors explicitly discuss trees' inability to extrapolate beyond previously
  observed patterns. Learning improves once surge observations enter training.
  Their later in-sample illustration is not prospective evidence of shock skill.
- PDF p23 / printed p21 reiterates that limitation. Upside-risk information is
  useful, but changing quantile weights alone cannot manufacture a new level
  outside response support. The proposed moving-anchor gap model addresses a
  different part of that problem and must still be tested.

The paper includes inflation expectations. Its performance is not evidence that
an expectations-free implementation will obtain the same gain. Keep the user's
independent predictor restriction and retain surveys only as benchmarks.

### Bank of England: Buckmann, Potjagailo and Schnattinger, 2025

Source: [Blockwise Boosted Inflation, Staff Working Paper 1143](https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2025/blockwise-boosted-inflation-non-linear-determinants-of-inflation-using-machine-learning.pdf).
Local file `Buckmann_Potjagailo_Schnattinger_2025_BlockwiseBoostedInflation.pdf`,
45 PDF pages, September 2025.

- PDF pp12-13 / printed pp9-10: blocks are fitted sequentially to residuals,
  permuting their order. The learning rate is .02, tree depth three, minimum node
  size five, half-observation subsampling and quarter-feature subsampling.
  Forecasting uses 100 fixed rounds. Crucially, the paper explicitly avoids
  forecast early stopping because its validation sample is too small to find the
  stopping point without test leakage; its separate cross-validation exercise
  allows up to 200 rounds with early stopping.
- PDF pp14-15 / printed pp11-12: the structural decomposition uses repeated
  ten-fold full-sample cross-validation. Its trend block includes a time indicator,
  expectations, wages and services inflation. Its decomposition of trend is not
  an independent, real-time Czech trend estimator ready to copy.
- PDF p25 / printed p22: pseudo out-of-sample forecasting starts in 2000 after a
  sample ending in 1999; models are refitted quarterly and ten random subsample
  fits are averaged. Footnote 13 explicitly abstracts from **data revisions and
  publication delays**. Long-horizon forecasts are muted/lagged, and the inflation
  surge remains underpredicted. The full-sample decomposition should not be
  mistaken for those sequential forecast results.
- PDF p27 / printed p24, Table 2 distinguishes monthly-endpoint forecasting at
  h1/h6/h12 from a separate twelve-month-ahead YoY target. Those metrics cannot
  be compared directly with this repository's exact annual path errors.
- PDF p32 / printed p29 uses an unobserved-components benchmark with stochastic
  level and trend. This supports considering a filtered moving baseline before a
  large boosted system. A full BBIM replication would require many unavailable or
  non-vintage inputs and is not the fastest defensible next experiment.

Monotonic demand/supply restrictions organise predictive contributions under
assumptions. They do not, by themselves, identify which Czech shock was unforeseen.
Do not transfer the paper's household-expectations thresholds to independent
headline inflation as if they were a universal structural breakpoint.

### Medeiros, Vasconcelos, Veiga and Zilberman, 2021

Source: [Forecasting Inflation in a Data-Rich Environment: The Benefits of
Machine Learning Methods](https://doi.org/10.1080/07350015.2019.1637745).
Local file `Medeiros_Vasconcelos_Veiga_Zilberman_2021_ForecastingInflationDataRich.pdf`,
23 PDF pages; journal pp98-119.

- PDF p5 / journal p101: direct monthly targets avoid forecasting every covariate.
  Rolling estimation attenuates structural changes, but their windows are hundreds
  of observations, not proof that sixty is optimal. Their baseline uses a January
  2016 vintage, with a separate real-time robustness exercise for 2001-15.
- PDF p9 / journal p105: LASSO penalties use BIC; forest leaves have five
  observations, one third of predictors enter each split, and there are 500 trees.
  These give defensible complexity controls. R14's 200 trees is a declared
  computational choice, not an exact replication. Data-driven factor/lag choices
  did not uniformly improve results, cautioning against expanding the tuning grid.
- PDF p7 / journal p103: their jackknife averaging removes nearby observations
  around a held-out row. For our delayed band targets, chronological sequential
  errors with complete publication gates are safer than borrowing this symmetric
  leave-out procedure or ordinary random folds.

### Hauzenberger, Huber and Klieber, 2023

Local source `Hauzenberger_Huber_Klieber_2023_RealTimeInflationNonlinearDimReduction.pdf`,
21 PDF pages, International Journal of Forecasting 39, pp901-921.
The abstract and PDF pp6-7 / journal pp906-907 compare nonlinear factors with
constant and time-varying parameter regressions under horseshoe/adaptive Minnesota
shrinkage. Estimation uses 240-observation rolling windows and actual US vintages;
combined forecasts need a separate initial 24-observation evaluation-history period.
Results emphasise one-month and one-quarter horizons. This supports separating
time-varying relationships from nonlinear features and accounting for combination
warmup; it does not establish six-to-twelve-month gains from an autoencoder in a
short Czech component sample. A new large latent-factor system is lower priority
than the declared moving-gap experiment.

The local file named `DeMol_Giannone_Reichlin_2008_BayesianShrinkageVsPCA.pdf` is
actually the December 2006 ECB WP700 version (35 pages). Version identity matters:
do not cite its filename as a verified 2008 journal edition. It supports the
general comparison of shrinkage and factors, not a numerical justification for
R13's fixed penalty of one.

## Survey horizons and fair runnable benchmarks

The [CNB FMIE methodology](https://www.cnb.cz/en/financial-markets/inflation-expectations-ft/)
states that the monthly analyst survey asks for CPI year-on-year inflation at
one and three years. It is a forecast of the YoY CPI rate at those endpoints,
not the average inflation rate over the next year, and it is distinct from the
Bloomberg median for the next monthly release. There is no six-month CPI horizon
in this questionnaire. Its one-month horizons concern interest rates/FX, not CPI.

Read-only inspection of `consensus.inflation_expectations` in the local Czech
database found exactly **327 monthly rows at each of 12 and 36 months**, May
1999-July 2026, source `cnb_fmie`, target `cpi_headline_yoy`, metric `mean`.
There are no six-month rows and no other source in that table. All survey dates
are month-start labels. The table has a retrieval timestamp but **no historical
publication timestamp**; treating `survey_date` as the release instant is invalid.

The [August 2026 official report](https://www.cnb.cz/export/sites/cnb/en/financial-markets/.galleries/inflation_expectations_ft/inflation_expectations_ft_2026/A_inflocek_08_2026.pdf)
is dated Prague, 24 August 2026 (PDF p3), with explicit 1Y/3Y CPI columns on p4.
This also refutes assuming that every FMIE report is available by calendar day15.
Report issue dates are useful evidence but are not exact website publication times.

The old `path_experiment.py` B4 reader picks the last survey month <= model origin
and places it at h12. Preserve the source month and compute target=survey_month+12:
a stale survey must not be rolled forward to a new destination. The currently
stored 327-month series is contiguous, but the generic reader has no such
target/date protection and no publication clock.

Completed source audit and declared comparison:

1. Preserve raw survey month, target horizon, mean, retrieval metadata, source
   document and issue date in an immutable benchmark snapshot.
2. The fixed 24-report panel covers August 2023-July 2025 and targets August
   2024-July 2026. All official PDFs were downloaded and hashed; all printed
   Prague issue dates are on PDF p3. July 2024, April 2025 and July 2025 reports
   are dated in the following month. Define availability as the next calendar
   day's Prague midnight, with explicit reconstructed-date provenance.
3. Source-only reconciliation shows the last saved model clock before availability
   needs h13 for 22 of 24 reports, outside the declared path. First-after clocks
   yield 22 h12 and two h11 comparisons. Preserve both brackets, their ages and
   unsupported rows; do not move the survey target or force twelve-month labels.
   The primary comparison therefore re-runs the bridge and three already
   declared pipelines at each reconstructed issue clock with origin=survey_month.
   Only h12 is scored: its twelve-month compounding excludes h0, allowing an
   explicitly tested irrelevant h0 placeholder. Rebuild current features at the
   custom clock and preserve historical own-clock training and complete label
   gates. Details are frozen in `R14_BENCHMARK_SPEC.md` before custom scoring.
4. For six-month context, retain the CNB **issue-vintage quarterly-average YoY
   path** and average the model's exact monthly YoY forecasts over the same quarter.
   Label quarter and all constituent monthly horizons; a quarter average is not a
   six-month endpoint survey. Retain all reference forecasts and unavailable rows.

The existing R13 CNB diagnostic has 161 report-quarter rows, 76 complete forecast
pairs and 66 realised pairs over 18 unique quarters. Its model paths predate report
issue by a median eight days and as much as thirty. That age mismatch and repeated
quarters remain explicit; CNB error is not an identified external shock and
model-minus-CNB is not an identified specification error. Fair new runs must use
the same issue vintages, same target quarters and one common candidate roster.

The immutable `data/research_r14/benchmarks/` snapshot now preserves 654 DB rows,
24 source PDFs, their extracted issue dates, source hashes and model-clock
reconciliation. Read-only database file size and modification time were unchanged.
The 24 CPI tables on PDF p4 were independently extracted and visually checked.
All 24 one-year and all 24 three-year database values agree with the published
one-decimal means when rounded. Extra DB digits have not been traced to an
official unrounded mean; precision alone does not prove interpolation or synthetic
data. The largest raw 1Y difference is 0.049776 percentage points. Primary and
bracket scores must use `fmie_official_panel.csv`'s published values; old date and
FIRST_AFTER-only extraction files retain the raw DB numbers only for provenance.
The date convention is not a certified website publication time or the analysts'
information cutoff, and the English report may not be the earliest edition.
No benchmarks enter the R14 estimators or inner tuning loss.

Implementation references: the [official Ridge definition](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)
confirms the sum-loss alpha scale. The [official TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
describes chronological splitting and its gap parameter; a generic gap does not
replace the experiment's explicit horizon and detail-release eligibility checks.

## Independent audit of the original R14 core experiment

The independent audit closed before this reviewer implemented the later optional
history loader. On the original saved run, all 39 declared input fingerprints and
13 output hashes matched. An executed fixture-reader dependency,
`independent_nowcast_experiment.py`, was missing from the explicit closure; this
was reported and subsequently added to the runner's fingerprints.

Numerical oracles reconstructed the calculations from source rows, without calling
the estimator helpers for their algebra. Results:

- All 125 historical states matched exactly, including trend, seasonal factors,
  source-month mapping and publication eligibility.
- All 3,000 candidate rows reconciled training counts and target clocks. The
  1,668 estimable ridge candidates were independently refitted; maximum absolute
  forecast difference was 6.22e-15.
- All 360 adaptive decisions, validation calendars and candidate losses matched;
  24 selected level/gap forests independently refitted exactly.
- All 7,020 native component rows preserved h0 and noncore values/weights, and
  destination-month seasonal inversion matched exactly. All 12,870 headline path
  rows reconciled origin/target dates and exact annual product arithmetic within
  1.31e-13. All 1,440 published scoring rows replayed exactly on their own declared
  common or own-coverage rosters. The independent focused/adjacent suite passed
  44 tests before the optional extension implementation.

The main scientific qualification was coverage: original `import_l2` starts at
fixture March 2015, so the twelve-source predictor window permits historical
states only from March 2016. The 2007+ core history benefits seasonal/trend
estimation, not the original regression-origin sample. Learned h12 forecasts begin
in March 2021; full primary h12 uses 53 common realised origins, recent targets 31
and recent origins 19. Adaptive selection remains at the declared default for
43/49/55/61 of 90 origins in bands 1..3/4..6/7..9/10..12 respectively. Only
47/41/35/29 origins have sufficient validation history for actual adaptive choice.
This limits claims about a robustly learned long-horizon tuning policy.

That finding motivated a separately declared historical-data comparison, with
all original model formulas/settings preserved. The source agent verified 84
earlier missing import cells against official CZSO series and documented a
January 2014 release on 17 March, refuting an unconditional 16th-day release rule.
The extension therefore uses source+3 month-start Prague availability. It never
replaces finite original cells or fills later missing data. See
`R14B_CORE_HISTORY_DESIGN.md` and `R14B_IMPORT_HISTORY_AUDIT.md` for the independent
source evidence and outcome-informed status of this further experiment.

The optional loader was implemented after explicit reassignment; it is not being
represented as independently reviewed code by its own implementer. Fourteen
extension tests first failed on missing behavior, two metadata tests then failed
on the missing candidate-status correction, and one declaration-fingerprint test
failed before its fix. The resulting 61-test focused/adjacent suite passed before
either policy was refitted. Native `converged` now means finite numerical
availability, inherited driver fields carry `legacy_source_` prefixes, and original
noncore fallback evidence is separate from the core model's no-fallback policy.

## Extended-history experiment: verification and interpretation

After declaration `709d4b3`, both policies were refitted with frozen code. The
default run's forecasts, scores, historical states and selections are byte-for-byte
identical to its original payloads; only native metadata and its validation
explanation changed. Full offline refits reproduced all 13 default payloads with
41 input fingerprints and all 13 extended payloads with 63 input fingerprints.
The evaluation-only history comparison passed three tests after a missing-module
red run and reproduced its six payloads offline. The combined focused and adjacent
tests total 64 passing tests.

The extension increases historical states from 125 (March 2016 onward) to 199
(January 2010 onward). Every outer origin now has 36 fully released common
validation errors in each band; none needs the insufficient-validation default.
The unchanged local-trend control is exactly equal across all 90 origins and
1,080 future steps, including unscored future values. A separate numerical oracle
reconstructed all 4,776 extended candidate rows and 3,444 estimable ridge fits
(maximum difference 6.22e-15), all 360 choices/losses, 24 selected forests, all
native paths and 1,440 score rows. Annual product arithmetic agreed within 1.31e-13.
This is a distinct algebra check of the implemented extension, not a claim that
the loader's own author independently reviewed that implementation.

Use `output/research_r14b/core_history_comparison/paired_summary.csv` for accuracy
changes and its separate own-coverage table for increased availability. For
twelve-month headline forecasts on the same 53 full-sample origins, level-ridge
RMSE improves from 6.681 to 6.284 and gap-ridge from 7.060 to 6.476; the level
forest worsens from 6.414 to 6.446. The extended full roster has 75 common realised
origins, so comparing its headline score directly with the old 53-origin score
would mix history effects with coverage effects.

On the 19 recent-origin twelve-month targets, level-ridge headline RMSE improves
from 1.727 to 1.128, gap-ridge from 1.595 to 1.174 and adaptive gap from 1.301 to
1.081. Their actual core cumulative-log errors also improve: level-ridge 1.409 to
0.589, gap-ridge 1.243 to 0.727 and adaptive gap 0.799 to 0.546. The unchanged
local-trend core remains lower at 0.469 in that panel. Recent-target results differ:
level-ridge's cumulative core error worsens from 2.915 to 3.123 despite a small
headline improvement. Longer verified history helps several fits, but it does not
establish a uniformly superior long-horizon model or justify a new parameter
search after these results. The originally declared algorithms and combinations
remain unchanged, and all models and periods remain reported.
