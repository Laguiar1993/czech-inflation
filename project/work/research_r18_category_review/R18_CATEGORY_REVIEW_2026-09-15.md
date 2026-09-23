# R18 category model independent review and versioned corrections

The fitted model follows its predeclared equations. No material error was found
in the 90 saved category paths, their signal updates, maturity rules or component
accounting. Independent numerical reconstruction matches the original results
at machine precision. The review identified two unused source-gap fallback
defects and one history-count metadata issue. They were corrected in a separately
versioned runner/output at the parent's request; every original fitted forecast
remains unchanged.

Use `output/research_r18_category_verified/` for integration. Preserve
`output/research_r18_category/` and its original manifest as the original record.
The correction note is `docs/implementation/R18_CATEGORY_CORRECTION_NOTE.md`.

## Equations and source clocks

The source contains exactly ten goods, six services and two housing proxies.
Core is a nineteenth separate measurement. The metadata and specification
correctly state that these are national CPI categories plus a separate CNB core
series, not an expenditure-weighted or exhaustive core partition. Historical
categories are today's official recoding, with reconstructed availability dates;
neither a true revision-vintage archive nor historical group membership is
claimed. Different measurement signals are not independent statistical samples.

Category units are 100*log(level/previous_calendar_level); core units are
100*log1p(monthly_percent/100). The original source loader gates categories on
the detailed-release date at midnight Europe/Prague, an explicitly recorded
availability assumption. Core uses the existing detail-release calendar at
09:00 local. No earlier flash is substituted for a category/core detail release.
The runner additionally requires reference month < origin t. It gates levels
before differencing and refuses noncontiguous/missing fitted histories, so an
unavailable endpoint cannot silently become a multi-month change.

For each origin, destination-month means and robust observation variances are
estimated from the released fitting window only: minimum 48, maximum 96 months.
These current-origin fitted seasonal parameters may use the entire current
window when replaying its filter recursion; historical forecast labels use their
own separately saved origin forecasts, not a later fitted seasonal vector.

The common persistent random walk, common temporary AR(.3), and per-measurement
persistent AR(.95) enter each observation with the declared unit loadings. Q
contains q_mu=.0025/.01, q_v=.04 and .05*R_j; robust R_j has the declared .05
standard-deviation floor. Initial covariance, simultaneous Gaussian update and
Joseph covariance formula match the specification. Core forecasts use h+1
transitions from t-1, including two transitions for h1. The latent components
remain statistical persistent/temporary components; no supply/demand shock or
calibrated posterior-uncertainty interpretation is established.

An independent information-form covariance/mean update was used instead of the
production Kalman-gain/Joseph implementation. It reconstructs both filters at
February 2019, April 2020, November 2021, December 2022, January 2024 and July
2026. Maximum state discrepancy is 2.00e-15, covariance discrepancy 2.78e-16.
Seasonal means, robust variances, breadth, and every h1..12 matrix-power forecast
agree at those twelve fits. These checks include the initial 48-month window,
longer pre-cap windows, and the capped 96-month window.

## Signal equations and saved historical features

All 90 six-variable macro feature rows match the frozen R15 own-origin table
exactly. That table's preserved generating code evaluates hard-data transformations
at t-1 with its original publication masks. Breadth3 and the unweighted goods
minus services sector-state mean match all 90 saved MCT_FAST states. Housing
states do not enter the goods/services contrast; core is not included in breadth.

All 1,080 labels are verified as actual future core log rate minus the saved
same-origin MCT_FAST prediction, with target s+h and the CNB detail-release gate.
Targets beyond stored core coverage are NaN/NaT and cannot enter training, even
when a calendar row for a later scheduled release exists. Labels are joined to
their historical feature rows, not recalculated from a current fitted state.

The signal solve matches the objective exactly: data loss and independent ridge
blocks receive 1/12 weights; eleven adjacent-horizon differences receive 1/11.
There is no intercept, and each feature's RMS uses only the pooled eligible rows.
The smoothness links coefficients but never inserts an unobserved target into
another horizon's training set. Current features are transformed with that same
historical RMS; no future row changes the fit.

Every one of the 54 fitted signal updates has the correct horizon-specific
origin/target calendars. First fit February 2022 uses counts 35,34,...,24;
latest July 2026 uses 88,87,...,77. The first 36 origins have insufficient labels
and keep zero signal correction. A separate augmented-design least-squares
solve reconstructs February 2022, December 2022, January 2024, June 2025 and
July 2026. Maximum coefficient error is 3.75e-16 and correction error 1.33e-15.

The original implementation does not explicitly export incomplete-predictor
exclusion counts despite that detail in the spec. On this saved experiment all
90 feature rows are finite, so the excluded-feature count is independently zero.
This omission affects audit convenience, not these forecasts; it should be
made explicit if a future source vintage contains incomplete predictors.

## Accounting and corrected contracts

The original h0 and every noncore value, contribution and weight are exact copies
of FAST. The six-contribution sum matches headline monthly to 8.89e-16 using a
different summation order. Annual headline paths are recomputed using the
unchanged anchor. Component and aggregate forecast quality still require the
parent's same-calendar evaluation; these numerical checks establish correctness,
not improved economic forecasting.

The following original issues were found and demonstrated:

1. `category_trend_experiment_r18.py:42` called `levels_asof` outside the fallback
   handler. A missing/invalid availability timestamp aborted the runner instead
   of issuing the promised complete unchanged FAST fallback. The verified
   runner's tested `fit_origin` helper now records source availability failures
   and returns all twelve control horizons.
2. The original fallback path converted control monthly values to logs and back.
   That roundtrip changes 380 of the 1,080 frozen FAST core values by up to
   4.44e-16 pp if exercised. The verified helper copies monthly control values
   directly; zero signal correction preserves its parent's monthly values too.
3. `status.csv:n_history` reported untrimmed available history rather than fitted
   history in 82 first-stage rows from March 2023 onward. July 2026 said 137
   although the correct fitted count in states.json was 96. The verified output
   reports actual fitted n_history and separate n_available_history.

All original first-stage fits succeeded. Thus the fallback corrections do not
alter current-sample behavior, and the metadata correction does not alter any
estimate. Source integrity/hash failure still stops execution; it is distinct
from an origin's explicitly recorded availability/coverage fallback.

The new runner is `category_trend_experiment_r18_verified.py`. It verifies every
original category input/output hash, declares its own sources before fitting,
refuses an existing destination, and checks every numeric prediction/label/feature
column against the original before finalizing. A separate verifier additionally
checks every shared table column, all 180 pre-existing saved-state fields, and
all 90 signal-update dictionaries for exact equality. The engine and original
runner/spec/manifests were not modified.

## Tests and reproduction

`tests/test_r18_category_audit.py` adds seven independent tests. Five cover late
and unknown label releases, own-horizon maturity counts, future-feature poisoning,
missing current predictors, local/UTC source-clock equivalence, endpoint gaps,
and the zero-noise covariance floor. Two tests exercise the actual verified
runner helper for source failure, exact FAST monthly fallback and fitted versus
available history counts. Both helper tests failed before implementation.

Combined with the four original category tests, the fresh suite has **11 passing
tests**. The initial independent date-poisoning fixture used mixed date-string
formats unsupported by the frozen API; it was normalized to the declared
timestamp format. A first partial smoke comparison retained original filtered
row indices; resetting comparison indices fixed that harness issue before full
execution. No generating equation was changed in response to an outcome.

```powershell
$env:PYTHONPATH='../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m pytest tests/test_r18_category_audit.py tests/test_category_trend_r18.py -q -p no:cacheprovider
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r18_category_review/verify_category.py
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r18_category_review/verify_verified.py
```

`verification.json` records the independent original-math reconstruction and
metadata findings. `verified_runner_verification.json` records the immutable
original/verified hashes, exact point/state parity and corrected counts. The new
output also contains its own `original_point_parity.json` manifest payload.
Future reproduction must use a fresh destination with the verified runner;
the original and verified research directories remain immutable.
