# Independent component bridge and CNB comparison — 9 September 2026

The independent bridge completed 90 release-eve origins, February 2019–July 2026,
with 1,170 monthly forecast rows. It has lower ex-ante YoY RMSE than the newly
estimated target, driver, BVAR and forest paths on the full common sample. It also
slightly improves on stored F1b over that window. The stored references remain
stronger for recent targets. In the report-aligned quarterly comparison, CNB has
lower overall error and a clearer advantage on reports from 2024 onward.

This is retrospective research. Independence here means no survey expectations
or other forecasters' inflation predictions enter the bridge at any horizon.
It does not establish an untouched holdout or a complete historical data-vintage
archive for every statistical driver.

## Specification and boundaries

`forecast_bridge(frames, target, as_of, h0)` accepts the same frozen frame
dictionary as the independent nowcast runner, an explicitly aware timestamp,
and an independently supplied h0. It returns `path[0..12]`, per-horizon block
values, weights, contributions and diagnostics. It does not query a database or
load stored forecast references. Its static release, basket and announcement
rules are the existing audited package rules.

At origin t, all component outcomes are cut at t−1 and screened by the same
Prague decision clock. Both core and food feature frames use that clock. The
hard feature policy removes expectations and sentiment from every horizon.
Relevant monthly frames must have unique, ordered, contiguous monthly indexes
before any positional direct-horizon shift. Missing interior months are rejected;
irrelevant future rows are excluded before that validation.
The direct core ridge predicts t+h from the feature row at t; its final training
label is no later than t−1. There are no slow-core blocks.

The component path is specified before evaluation:

- Core: direct hard-feature ridge at every h1–12, using the existing fixed ridge
  penalty and training-only imputation/scaling.
- Food h1–3: origin-fitted one-sided X-13, direct ridge and the destination
  month's seasonal factor. The existing plain-ridge fallback is explicitly
  recorded. Food h4–12 uses the last five released observations for the same
  calendar month, with the last 24-month mean only if no same-month history exists.
- Administered prices: the existing documented announcement gate at the origin's
  clock, passed the contemporaneous computed administered weight.
- Alcohol/tobacco: the existing rule with history known only through t−1 and the
  same announcement clock.
- Fuel: the median of the last eight released observations for the destination
  calendar month when at least three exist; otherwise the last 24-month median.
- Wedge: the currently released weighted historical wedge, evaluated with the
  same known-through date.

The origin's computed weights remain in force for a future basket regime unless
that regime's basket was already published at the clock. Every saved h1–12 row
includes the five component contributions, wedge, unweighted block forecasts
and weights. Their sum is the headline forecast. H0 is exactly `HARD_BASE` from
the independent nowcast evaluation, including its separate fuel treatment.

Exact rolling twelve-month compounding produces YoY. The ex-ante calculation
uses independent h0; a separately labelled conditional diagnostic substitutes
current-stored CPI h0 only in that calculation. It is not a reconstruction of
the rounded first-release h0. The models are not refitted using actual h0.
At h12 the two calculations coincide because h0 has left the annual window.

The frozen components and hard drivers inherit their documented cached/latest-
vintage limitations. This bridge has no unemployment input. Other models in the
comparison retain the genuine origin-selected unemployment archive described in
`VINTAGE_FINDINGS.md` and the FX scenarios described in `PATH_RESULTS.md`.

## Coverage and failures

All 90 origins are retained. The food fixture begins in February 2015. At the
first three evaluation origins, some direct food horizons have fewer than the
existing minimum 48 training labels. February 2019 fails at h1–3, March at h2–3,
and April at h3. Both X-13/ridge and plain-ridge fallback return no estimate for
those six points. They remain NaN with the nonfinite food block and fallback
method recorded. The threshold was not weakened and seasonal forecasts were
not substituted into the prescribed h1–3 rule.

The run records 264 successful X-13 food forecasts, six fallback attempts ending
in insufficient-history failures, and 810 prescribed seasonal food forecasts.
All later monthly points are finite. A failure earlier in a path also prevents
YoY compounding until it leaves the twelve-month window. Saved per-horizon
status distinguishes a finite later monthly forecast from an incomplete origin
path. A live caller must require a complete finite path before certification.

The bridge has 75 observed complete h12 YoY cases. The stored F1b reference has
66 on the joint sample. Direct component recombination also avoids dependence on
an unused long-horizon food ridge in legacy arithmetic. The difference is
coverage, not evidence that nine extra cases are comparable with absent F1b
predictions. All comparisons below explicitly use common rows.

## Ex-ante monthly-origin comparison

YoY RMSE, percentage points. These are identical origin/target rows across the
seven newly calculated or independent baseline methods in each column.

| Method | h1, N88 | h3, N84 | h6, N81 | h12, N75 |
|---|---:|---:|---:|---:|
| Independent bridge | 0.911 | 1.537 | 2.516 | 5.395 |
| Target ML | 0.970 | 1.957 | 3.380 | 6.592 |
| Target + FX | 0.969 | 1.960 | 3.420 | 6.646 |
| Target + U + FX | 0.969 | 1.960 | 3.423 | 6.649 |
| BVAR + U + FX | 0.946 | 1.891 | 3.166 | 6.223 |
| Fixed forest + U + FX | 0.975 | 1.772 | 2.817 | 5.602 |
| Seasonal naive | 1.040 | 2.123 | 3.633 | 6.572 |

The bridge's corresponding monthly m/m RMSE is 0.691/0.800/0.821/0.925.
The forest's is 0.779/0.761/0.792/0.904. The bridge improves the compounded
inflation path; it does not dominate each individual month's error.

Adding the stored forecast references narrows the h6 and h12 samples:

| Method | h1, N88 | h3, N84 | h6, N78 | h12, N66 |
|---|---:|---:|---:|---:|
| Independent bridge | 0.911 | 1.537 | 2.563 | 5.743 |
| Stored F1b reference | 0.916 | 1.596 | 2.663 | 5.788 |
| Stored survey-trend reference | 0.937 | 1.862 | 3.307 | 6.664 |
| Fixed forest + U + FX | 0.975 | 1.772 | 2.869 | 5.968 |
| Target ML | 0.970 | 1.957 | 3.439 | 7.018 |

Stored references keep their saved future monthly paths and are recomposed with
the same independent h0 for this accounting comparison. They are not newly
estimated independent models. Small full-window differences from F1b do not
establish statistically significant superiority.

For targets from January 2024 onward, each horizon has 31 common rows:

| Method | h1 | h3 | h6 | h12 |
|---|---:|---:|---:|---:|
| Independent bridge | 0.365 | 0.547 | 0.748 | 1.892 |
| Stored F1b reference | 0.357 | 0.511 | 0.723 | 1.412 |
| Stored survey-trend reference | 0.387 | 0.565 | 0.616 | 1.330 |
| Fixed forest + U + FX | 0.337 | 0.674 | 1.345 | 3.414 |
| BVAR + U + FX | 0.437 | 0.746 | 1.005 | 4.042 |
| Target ML | 0.392 | 0.676 | 1.332 | 4.084 |
| Seasonal naive | 0.730 | 1.536 | 2.606 | 4.648 |

The bridge retains more of the component framework's recent long-horizon
accuracy than the standalone statistical paths, but removing forecast inputs
does not improve the stored references over this recent window. Crisis-target
results remain weak: for 2020–2023 targets its h12 RMSE is 6.862 on 44 common
independent-model rows. There is no claim that the historical inflation surge
has been solved.

## CNB report comparison

The input is `data/cnb_mpr_cpi_quarterly.csv`, whose source rows retain official
CNB workbook URLs, publication dates, cutoff dates and forecast flags. For each
report, the comparison chooses the latest already-generated origin strictly
before 00:00 Europe/Prague on the publication date. Date-only publication
metadata is not assigned a guessed intraday release time. The comparison is
aligned to public availability; it does not claim the model shares CNB's
earlier internal information cutoff.

Each forecast quarter is the mean of all three monthly YoY rates. Months before
the chosen origin use observed historical rates; months at or after it use the
saved ex-ante forecasts, including independent h0. Later actual releases never
replace a required forecast month. A quarter missing any predicted month stays
incomplete. Scoring also requires three realized target months and intersects
the same report/quarter keys across every listed model and CNB.

The source contains 19 reports from February 2022 through August 2026. Scoring
uses 66 report-quarter pairs from 18 reports dated 10 February 2022–14 May 2026,
covering 18 distinct realized quarters, 2022Q1–2026Q2. The August 2026 report has
no fully realized future quarter yet. Forecasts beyond model coverage remain in
the detailed output with missing model values. Repeated reports forecast the
same target quarters: **66 pairs are not 66 independent observations**.

| Method | All matched RMSE | All matched MAE | 2024+ reports RMSE | 2024+ reports MAE |
|---|---:|---:|---:|---:|
| CNB | 2.295 | 1.061 | 0.372 | 0.287 |
| Independent bridge | 2.362 | 1.528 | 0.590 | 0.463 |
| Stored F1b reference | 2.433 | 1.552 | 0.555 | 0.378 |
| Stored survey-trend reference | 3.126 | 1.616 | 0.450 | 0.336 |
| Fixed forest + U + FX | 3.110 | 1.967 | 0.756 | 0.562 |
| BVAR + U + FX | 3.075 | 1.832 | 1.130 | 0.824 |
| Target ML | 3.565 | 2.174 | 0.764 | 0.573 |
| Target + FX | 3.580 | 2.174 | 0.770 | 0.589 |
| Target + U + FX | 3.584 | 2.182 | 0.780 | 0.600 |
| Seasonal naive | 3.828 | 2.790 | 2.320 | 1.821 |

The recent columns contain 34 pairs, 10 reports and 10 unique quarters. The
independent bridge is the closest newly calculated model to CNB overall, while
CNB has materially lower recent error and lower MAE in both windows. No model
was chosen or tuned to match CNB's forecasts.

Quarter-ahead RMSE is also retained rather than hidden in the pooled score:

| Quarter ahead | Common pairs | Independent bridge | Stored F1b | CNB |
|---|---:|---:|---:|---:|
| 1 | 18 | 1.542 | 1.588 | 0.947 |
| 2 | 17 | 1.955 | 2.116 | 2.075 |
| 3 | 16 | 2.236 | 2.411 | 2.506 |
| 4 | 15 | 3.469 | 3.426 | 3.245 |

Quarter ahead is measured from the quarter containing the final observed month
t−1. These small, overlapping samples support descriptive comparisons only.

## Reproduction and verification

Run `python independent_bridge_experiment.py`. The final full run took about
74 seconds and wrote only `output/independent_bridge_*`. It checkpoints forecasts
and diagnostics after every origin. The original independent path forecast file
is unchanged. Code and input fingerprints are captured before the run and checked
again before the final manifest is written.

The output set contains bridge forecasts and all component contributions, the
merged comparison forecasts, monthly-origin summary scores, detailed CNB
report/quarter rows, CNB summary scores, diagnostics, manifest and validation
receipt. Missing estimates are retained in both the forecasts and diagnostics.

Nine bridge tests pass: expectation poisoning at every horizon; future outcome
and feature invariance; contributions and weights adding correctly; unpublished
future baskets remaining unavailable; insufficient food history exposing failure
and fallback; and conservative CNB quarter construction without future-actual
substitution. Two additional cases reject deleted interior months in the target
and feature histories, and one verifies irrelevant future index gaps cannot
alter the forecast. Contribution checks share the future-invariance case.

The saved-artifact audit verified all 90 origins and all 13 horizons, independent
h0 equality, component sums including missingness, weight sums, finite-status
consistency, the six exact expected missing food points, h12 compounding identity,
strict pre-report clocks, unique report/quarter/model keys, common-pair counts,
and all captured hashes. The reviewed monthly-grid safeguard left all monthly
and compounded forecasts unchanged to ten decimal places on the frozen inputs.
After that safeguard and the
separate path-resume hardening, the combined bridge, input, model-math and
vintage suite passed all 90 tests. The X-13 warning on the deliberately short
food history is retained. Final repository-wide verification belongs to the
integrating task.
