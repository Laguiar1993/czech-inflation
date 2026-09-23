# Corrected independent path comparison — 9 September 2026

The fixed comparison completed **90 primary release-eve origins (February
2019–July 2026)** and **133 earlier no-driver control origins (January 2008–January
2019)** in 274 seconds, producing 12,818 monthly forecast rows. Adding the chosen
unemployment and FX channels did not improve the target-only model over the main
window. The restrained forest was better at horizons three, six and twelve, but
the stored F1b reference remained stronger on their common rows. These results
support continued research, not promotion of a new driver-based path model.

## Fixed specification and information boundary

The primary roster was fixed before execution:

- `TARGET_ML`: target-anchored maximum-likelihood trend/gap model, no drivers.
- `TARGET_FX_ML`: the same model with twelve-month EUR/CZK change at destination
  lag three.
- `TARGET_U_FX_ML`: the same plus change in the latest genuinely published
  unemployment history at destination lag one.
- `BVAR_U_FX`: corrected direct Minnesota regression, three lags, tightness 0.2,
  lag decay 1.0, with the same hard drivers and seasonally adjusted headline.
  This is a direct shrunk regression, not a structural jointly estimated VAR.
- `RF_U_FX`: direct horizon forests with 200 trees, minimum leaf five,
  max_features=1/3 and seed 42. Inputs are headline lags 1/2/3/12, released trailing
  twelve-month inflation/state, target-month dummies, and the same available U/FX
  drivers. No hyperparameters were tuned.
- `NAIVE`: last five available observations for the target calendar month.

ML and BVAR seasonality uses centered, same-calendar-month medians fitted
separately at each origin. All finite contiguous extended headline history is
used, starting February 1991. The existing target function approximates the
pre-2002 target by 4%, including the pre-1998 period; this is a model assumption,
not a reconstruction of actual historical target announcements. Unavailable
initial driver history has neutral zero values and its count is recorded.

At origin `t`, released headline ends at `t-1`. Forecast target `t+h` therefore
uses model horizon `h+1`. A source transition row `s` carries U.diff()[s] and
FX12[s-2]; the corrected state-space transition supplies the final one-month lag.
The driver frame is not shifted again. In the state-space ML paths, already-known
FX observations continue through the future lag boundary. Unknown future FX
levels are held at the last completed observed monthly level; unpublished
unemployment changes are zero. The direct BVAR and RF benchmarks use predictors
at the end of their history, without the future scenario rows. The comparison
therefore combines different forecasting methods and terminal information sets;
it is not a controlled test of model form with identical future-driver inputs.

The clock is `_eve(t)`, interpreted as 23:59 Europe/Prague. CPI is screened by its
release calendar. Unemployment uses the actual archived release available at the
clock, including its whole then-published historical series. It is SA before the
June 2025 presentation change and trend-cycle thereafter. FX uses an explicit
completed-month assumption. The outcome CPI and FX histories are the current
stored series; independent h0 inherits its cached-driver limitations. These are
**retrospective research results with corrected unemployment vintages**, not a
claim of a fully archived real-time information set or an untouched holdout.

Every primary model uses exactly the same independent `HARD_BASE` h0 from
`output/independent_nowcast_forecasts.csv`. All monthly forecasts h=0..12 are
retained. Ex-ante YoY compounds the exact twelve required monthly rates with this
h0. The separately labelled conditional diagnostic substitutes the current
stored CPI h0 in the compounding calculation; it does not refit future states
using the outcome. This is not a first-print diagnostic: stored h0 differs from
the first-release rounded value in 86 of the 90 origins, by up to 0.089873 pp
(May 2026: 0.189873% stored versus a 0.1% first print). Rounding and the distinction
between flash and stored outcomes must not be described as revision effects alone.
At h12, h0 lies outside the twelve-month window, so both cases are identical.

## Primary ex-ante results

YoY RMSE in percentage points. Each column uses identical target rows across the
six independent methods. Available observations fall only because the final
targets have not yet been observed; fitted forecasts are retained beyond that edge.

| Method | h1 (N=89) | h3 (N=87) | h6 (N=84) | h12 (N=78) |
|---|---:|---:|---:|---:|
| Target ML | 0.964 | 1.924 | 3.322 | 6.470 |
| Target + FX | 0.963 | 1.927 | 3.361 | 6.523 |
| Target + U + FX | 0.964 | 1.928 | 3.363 | 6.526 |
| BVAR + U + FX | 0.941 | 1.864 | 3.120 | 6.126 |
| Fixed forest + U + FX | 0.970 | 1.742 | 2.767 | 5.494 |
| Seasonal naive | 1.034 | 2.088 | 3.569 | 6.456 |

Monthly m/m RMSE on the same rows:

| Method | h1 | h3 | h6 | h12 |
|---|---:|---:|---:|---:|
| Target ML | 0.763 | 0.790 | 0.819 | 0.889 |
| Target + FX | 0.764 | 0.794 | 0.827 | 0.893 |
| Target + U + FX | 0.764 | 0.794 | 0.828 | 0.893 |
| BVAR + U + FX | 0.760 | 0.775 | 0.806 | 0.905 |
| Fixed forest + U + FX | 0.775 | 0.749 | 0.778 | 0.888 |
| Seasonal naive | 0.860 | 0.870 | 0.883 | 0.953 |

The forest improves primary YoY RMSE versus the target-only model by approximately
9.5%, 16.7% and 15.1% at h3/h6/h12. This is a descriptive comparison, without a
claim of statistical significance or historical selection independence. At h1
the BVAR has the smallest RMSE among the new roster. U/FX barely changes the
anchored model at h1 and slightly worsens h3/h6/h12.

Conditional-h0 YoY RMSE for target-only is 0.836/1.876/3.246/6.470; for the forest
it is 0.850/1.712/2.707/5.494. The h0 diagnostic should not be presented as an
ex-ante forecasting result.

## References on their own common rows

The stored `mm_F1b` and survey-anchored `mm_F2_D1_fixed` future monthly paths from
`output/path_step2.csv` remain legacy references. They were not re-estimated or
made independent here. Their h0 is replaced only for this common accounting
comparison by the same independent h0 used above. Their shorter stored coverage
requires a separate intersection; do not compare its RMSE directly with a different
sample in the primary table.

| Method | h1 (N=88) | h3 (N=84) | h6 (N=78) | h12 (N=66) |
|---|---:|---:|---:|---:|
| Target ML | 0.970 | 1.957 | 3.439 | 7.018 |
| BVAR + U + FX | 0.946 | 1.891 | 3.217 | 6.612 |
| Fixed forest + U + FX | 0.975 | 1.772 | 2.869 | 5.968 |
| Stored F1b reference | 0.916 | 1.596 | 2.663 | 5.788 |
| Stored survey-trend reference | 0.937 | 1.862 | 3.307 | 6.664 |
| Seasonal naive | 1.040 | 2.123 | 3.696 | 6.990 |

F1b is stronger at all four horizons on this common comparison. That does not
make its legacy forecast-expectation inputs eligible for the independent model.
A genuinely independent component bridge must be tested separately at every
horizon, not obtained by replacing h0 alone.

## Recent and crisis behavior

For **2024+ target months**, each horizon has 31 common rows:

| Method | h1 | h3 | h6 | h12 |
|---|---:|---:|---:|---:|
| Target ML | 0.392 | 0.676 | 1.332 | 4.084 |
| Target + U + FX | 0.390 | 0.666 | 1.339 | 4.041 |
| BVAR + U + FX | 0.437 | 0.746 | 1.005 | 4.042 |
| Fixed forest + U + FX | 0.337 | 0.674 | 1.345 | 3.414 |
| Seasonal naive | 0.730 | 1.536 | 2.606 | 4.648 |

The forest is not best at every recent horizon: the BVAR is better at h6. The
anchored target model has positive h12 bias of 3.043 pp on recent targets; the
forest's is 2.711 pp, while BVAR's is -0.084 pp despite its large RMSE.

For 2020–2023 target months, the target model's h12 RMSE is 7.647 pp, the forest's
6.513 pp, and naive's 7.411 pp (47 common rows). The largest errors include the
September 2021 origin's September 2022 target: target-only forecast 2.277% versus
actual 17.973%, an error of -15.695 pp. Merely correcting lags or adding these
small driver channels does not make the framework anticipate the inflation surge.

The older 133-origin control uses each target model's own h0 forecast, shared with
its naive comparator because the independent rich-input nowcast is unavailable
there. Target-only versus naive YoY RMSE is respectively 0.472 vs 0.460 at h1,
0.694 vs 0.681 at h3, 0.927 vs 0.956 at h6, and 1.295 vs 1.464 at h12. For
2008–2009 targets specifically, h12 is 2.327 vs 2.422 (12 rows). These controls
contain no unemployment channel and do not manufacture missing 2008 vintages.

## Diagnostics, artifacts and reusable API

There were 403 ML estimates: all 223 target-only fits and all 90 FX fits converged;
89 U/FX fits converged immediately and one converged with the prescribed retry.
All 90 BVAR and 90 forest origins returned estimates. No origin required a model
fallback or was removed for failure. The code still records genuine failures and
failed projections rather than silently excluding them. Reference convergence is
unknown and is not counted as a successful new fit.

Outputs are `output/independent_path_forecasts.csv`, `_summary.csv`,
`_fit_status.csv`, `_diagnostics.jsonl`, `_parameters.csv`, `_manifest.json`,
`_frozen_inputs.csv`, `_validation.json` and `_resume_validation.json`. The manifest
records exact CPI/FX arrays, model/input/reference file hashes, package versions,
scenario assumptions and the experiment status. A
checkpoint is written after every origin. The forecast CSV's SHA-256 is
`83cb8f37206af9a3a85f14c5d5875aca93a9a7442cb6d572024bd0b0c241b26e`.

```python
from independent_path_experiment import forecast_origin

result = forecast_origin(
    released_headline, eurczk_monthly_levels, target_month,
    aware_as_of, h0=independent_nowcast,
    vintage_path="data/vintages/unemployment.csv.gz",
)
# result['paths'][model][h] is m/m percent for target_month+h, h=0..12.
# native_paths preserves each model's unmodified h0.
# diagnostics, inputs and history retain the calculation evidence.
```

The caller must screen headline by its release calendar before passing it. The
API then also removes target-month/future CPI, freezes completed FX months and
selects archived unemployment at the explicit aware clock. It reads no database,
survey series or output file internally. Reproduce the historical run without
loading primary data from the database with
`python independent_path_experiment.py --long-extra --frozen-inputs output/independent_path_frozen_inputs.csv`.
`--resume` requires matching exact CPI/FX arrays, reference forecasts, relevant
source/calendar/runtime hashes and the same origin schedule before any saved
inputs or checkpoints are overwritten. Older manifests without these hashes are
rejected. CSV replay preserves floating-point values and interior missing months.

The resume review found that the initial runner had omitted the primary arrays
and stored reference file from its checks. The raw runner is preserved at
`docs/implementation/archive/independent_path_experiment_before_resume_fix.py`,
matching the source hash in `output/independent_path_pre_resume_fix_manifest.json`.
After seven failing regression cases established the gap, all 17 path-input tests
passed. A fresh 223-origin replay from the preserved frozen inputs took 275.2
seconds: all 128,180 numerical values, all other columns, and the forecast CSV
bytes were identical to the original run. Its SHA-256 above is unchanged.
The frozen input CSV now omits its unused leading January 1991 union-padding row.

Validation: **74 combined regression tests passed** across vintage selection,
input boundaries and repaired numerical models. Ten new path-input/harness tests
were observed failing before implementation. Final audit verified all 223 origins,
all thirteen horizon rows per origin/model, unique keys, unchanged input/code
hashes, common primary h0 and exact equality of conditional/ex-ante h12 outcomes.
The optional latest-vintage import challenger was not run; it would require its
own label and cannot convert this comparison into full real-time evidence.
