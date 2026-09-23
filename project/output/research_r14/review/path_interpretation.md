# R14B path interpretation and two next tests

9 September 2026. Read-only interpretation of the saved R14B integration, core
history comparison and attribution. No new models were fitted or tuned. Numerical
claims below use the existing common samples; proposed explanations and future
tests are explicitly marked as inference.

## What the apparent LOCAL reversal actually measures

**Established sample fact.** At h12, recent targets means targets January 2024
through July 2026, hence origins January 2023 through July 2025: 31 realised
origins. Recent origins means origins January 2024 through July 2025: 19 realised
origins. The latter removes all 12 forecasts issued during 2023. These are
different forecasting environments, not inconsistent scores on the same forecasts.
At h6 the analogous recent-target panel adds July-December 2023 origins to the
25 recent-origin observations.

The saved combined-common headline YoY RMSE values are:

| Model | Full h12, N75 | Recent targets h12, N31 | Recent origins h12, N19 | Recent origins h6, N25 |
|---|---:|---:|---:|---:|
| Original bridge | 5.395 | 1.892 | 1.347 | 0.678 |
| Stable food + constant pump, original core | 5.418 | 1.686 | 1.210 | 0.660 |
| Same, LOCAL core | 5.397 | 2.619 | 0.708 | 0.467 |
| Same, extended-history level ridge | 5.478 | 2.208 | 0.906 | 0.570 |
| Same, extended-history gap ridge | 5.582 | 2.729 | 0.927 | 0.548 |

**Established cohort arithmetic.** In the 12 added 2023 origins, LOCAL combined
h12 RMSE is 4.114 and signed bias +3.510 percentage points. The original-core
stable pipeline is 2.241/+1.490; extended level ridge is 3.360/+2.659. LOCAL's
squared errors sum to 203.057 in those 12 origins and 9.516 in the 19 later
origins. Thus **95.52% of its recent-target h12 squared error comes from the 2023
origin cohort**, although that cohort contains only 38.71% of the observations.

**Established model identity.** LOCAL repeats the last twelve-month mean of
monthly log core inflation and adds an origin-estimated seasonal vector whose
twelve coefficients sum to zero. Therefore its h12 cumulative core log forecast
is exactly the sum of core log changes over t-12,...,t-1. In annual-rate terms,
it carries the last known twelve-month core inflation rate into the next complete
t+1,...,t+12 window. It does not independently estimate the speed of disinflation.

Direct calculations from the frozen core history illustrate that identity:

| Origin | LOCAL forecast of core inflation over t+1..t+12 | Realised same-window core inflation |
|---|---:|---:|
| January 2023 | 13.226% | 2.930% |
| June 2023 | 8.607% | 2.113% |
| December 2023 | 3.961% | 2.111% |
| January 2024 | 3.547% | 2.417% |
| June 2024 | 2.521% | 2.724% |
| January 2025 | 2.111% | 2.623% |

These are compounded core-window rates, not headline forecasts or the ordinary
published YoY rate at the forecast origin. h0 is excluded from the future window.

**Inference, supported by that arithmetic.** A backward-looking annual mean carries
the 2022 inflation surge forward during 2023, after the monthly pace has fallen.
Once that surge leaves the twelve-month window, the same persistent, low-variance
forecast becomes well suited to the slower-changing recent core environment.
That interpretation explains the sign and timing of the errors. It does not
identify the economic causes of disinflation, demonstrate a stable future regime,
or show that the decline should have been completely foreseeable.

The longer import history helps learned models without solving this problem
uniformly. On the same 19 recent h12 origins, extending history reduced core
cumulative-log RMSE from 1.409 to 0.589 for level ridge and 1.243 to 0.727 for gap
ridge. LOCAL remains 0.469. All extended adaptive choices now have 36 released
validation errors, so recent simplicity's advantage cannot be explained solely
by the old short-history validation default. The extended level model still has
a worse recent-target core cumulative-log RMSE than its short-history version.

**Established attribution, with an economic limitation.** LOCAL's recent-origin
core improvement is visible directly: cumulative-log core RMSE 0.469 versus
1.543 for the bridge, and weighted cumulative core error RMSE 0.252 versus 0.823.
Its excellent headline score also includes offsetting errors. The exact annual
core-error mean for the LOCAL combined model is -0.097, while its shared
other-component/reconciliation error mean is +0.591. Replacing core with its
realised future path would give headline RMSE 0.829, above LOCAL's actual 0.708.
Thus correcting core perfectly would remove some helpful offset. These are
evaluation-only arithmetic oracles, not deployable predictors or causal shocks.

## CNB comparisons and the latest archived path

**Established comparison.** The issue-vintage quarterly table has 66 common
report/quarter observations, 18 unique realised quarters and 18 reports. LOCAL
RMSE is 2.339, extended level 2.280 and CNB 2.295. CNB's MAE is 1.061 versus
1.409 for extended level. The small all-report RMSE advantage for the latter
does not mean broad superiority to CNB.

In recent reports there are 34 common observations and 10 unique quarters/reports.
LOCAL is 0.402 RMSE versus CNB 0.372, with MAE 0.275 versus 0.287. This is a mixed
comparison: LOCAL is close and has lower MAE, while CNB has lower RMSE. These
recent issued forecasts also mostly originate in the calmer post-2023 period;
they do not resolve the earlier disinflation failure.

These are averages of three exact monthly YoY forecasts, **not six-month endpoint
surveys**. Repeated forecasts of one target quarter are not independent outcomes.
The model clock strictly precedes the report-date convention: on the scored
all-report pairs its age disadvantage has median 7.001 days and maximum 30.042
days; recent reports have median 8.001 and maximum 29.001 days. Preserve issue
vintages, all target months, paired coverage and those ages. CNB also has a
different information and judgement set. Model-minus-CNB is not an identified
specification error, and shared error is not an identified unforeseen shock.

The latest archived path has origin July 2026 and clock **4 August 2026, 21:59 UTC**.
It is not a fresh September forecast. Its h6 target is January 2027 and h12 target
July 2027. h12 forecasts are 3.187% bridge, 3.008% stable pipeline, 2.729% LOCAL,
2.708% extended level and 2.800% extended gap. The long level and LOCAL estimates
are currently close even though their retrospective rankings differ. No outcome
exists yet for those endpoints; closeness to a CNB or survey number cannot select
one. FMIE's independently verified CPI horizons remain 1Y and 3Y, with no 6M CPI
series. Keep its dated custom-clock h12 benchmark separate from these quarterly
comparisons and retain the unknown report-posting/respondent-cutoff caveat.

## Next test 1: estimate a changing core trend instead of carrying a trailing year

**Proposed test, not an established performance result.** Fit one parsimonious
unobserved-components model to released monthly log core inflation, with a
stochastic local level, a damped local slope, origin-specific seasonality and a
separate transitory observation disturbance. Estimate the variance parameters
inside each historical training sample; keep the damping specification and
complexity constraints fixed before seeing the new scores. Do not force core to
2% or feed survey/CNB expectations into its level. Keep LOCAL as the unchanged
control and the stable food/constant-pump legs fixed.

This directly tests whether a persistent underlying pace can adjust during a
disinflation episode while an individual monthly shock is mostly transitory. It
also uses the full observed core history from 2007 without waiting for external
predictor availability. Forecast from the last observed state t-1 through t+12,
so the h12 endpoint is **13 state transitions** away and the evaluated future
component window is still t+1..t+12. Check that distinction explicitly.

The economic hypothesis is a changing underlying price-setting pace, not a
permanent continuation of every shock-month price increase. Require improvement
in direct core cumulative errors as well as exact headline errors on the original
full, recent-target and recent-origin panels. The diagnostic acceptance question
is whether it reduces the 2023 carry-forward error without recreating high variance
or missing the 2021-22 acceleration. A failure on either side is informative;
do not tune the damping on those same episodes afterward.

Evidence: [BoE BBIM, PDF p32 / printed p29](https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2025/blockwise-boosted-inflation-non-linear-determinants-of-inflation-using-machine-learning.pdf)
uses a stochastic-level/trend unobserved-components benchmark. Hauzenberger,
Huber and Klieber's local PDF pp6-7 discusses constant versus time-varying
regressions and disciplined shrinkage. Neither paper establishes that this exact
Czech implementation will work; the proposed damped-trend form is our adaptation.

## Next test 2: distinguish imported-goods reversal from domestic-service persistence

**Proposed test, not an established causal finding.** Retain the extended-history
level-ridge band target and fixed complexity as a control. Add only two released
hard-data signals from the already archived broad goods/services history:
the services-minus-goods YoY differential, and the three-month change in goods
YoY inflation. Keep the existing publication-gated import and FX inputs. These
test whether a decline concentrated in tradable prices should unwind faster than
price pressure concentrated in domestic services. Compare with a control using
the identical available historical rows; do not repeat the short five-category
forecast system or choose category weights by their final test errors.

The source is `data/core_split/broad_yoy.csv`, whose verified metadata records
2003+ observed other-tradables excluding food/fuel and nontradables excluding
regulated prices. These are **realised analytical CPI statistics**, not CNB
forecasts or analyst expectations. They remain latest-vintage data with reconstructed
detail-release availability. Treat the two series as predictive signals only:
they are annual changes, not monthly inflation rates, and their first-round tax
treatment means they are not an exact partition of tax-corrected CNB core.
Do not convert them into monthly levels or mechanically recombine them as core.

This proposal adds an economically interpretable distinction missing from the
aggregate own-lags/import-only state, while preserving the longer training
calendar. It targets the same 2023 failure through composition rather than only
through a faster statistical filter. It can be tested independently of test 1.
Do not add broad forest/grid searches at the same time: keep one new signal pair
and a matched control so any gain is interpretable.

Evidence: BBIM's ordered economic blocks and delayed/muted long-horizon responses
(PDF pp12-15 and p25) motivate separating transmission mechanisms, but its
forecast exercise abstracts from publication delays and revisions. [CNB WP9/2026,
PDF p17 / printed p15](https://www.cnb.cz/export/sites/cnb/en/economic-research/.galleries/research_publications/cnb_wp/cnbwp_2026_09.pdf)
documents tree extrapolation limits during the surge; adding more trees to the
same aggregate state does not supply the missing economic distinction. This is
a testable interpretation, not a replication claim or a forecast guarantee.

Both next tests would be outcome-informed research after many inspected historical
experiments. Freeze their specifications first, retain all earlier failures and
shared target calendars, and reserve genuinely later releases for confirmation.

## Inputs inspected

- `output/research_r14b/integration/summary.csv`, `forecasts.csv`,
  `cnb_summary.csv`, `cnb_quarters.csv`, `latest_archived_paths.csv`.
- `output/research_r14b/core/historical_states.json` and the unchanged frozen
  CNB core m/m history; exact cohort and future-window calculations above.
- `output/research_r14b/core_history_comparison/paired_summary.csv` and
  `history_coverage.csv`.
- `output/research_r14b/attribution/component_summary.csv` and the previously
  independently checked arithmetic/target contracts; no attribution was fitted.
- `data/core_split/canonical_metadata.json`; local papers and the detailed
  evidence recorded in `docs/implementation/R14_PAPERS_AND_BENCHMARKS.md`.
