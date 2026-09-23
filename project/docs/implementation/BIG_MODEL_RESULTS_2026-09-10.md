# Big-model pilot results — 10 September 2026

The run in `output/big_model_all_20260910d/` requests an OOS start of January
2019 and evaluates through July 2026 on the common clock.  Because the direct
h-step fit requires 60 usable labels plus its h-month label delay, the effective
first target is March 2020 (h1), July 2020 (h3), January 2021 (h6), July 2021
(h9) and January 2022 (h12).  It uses 50 trees and 10 BBIM rounds to keep the
local run practical.  Because this checkout's Aguiar
environment does not have `quantile-forest`, the `TVW_QRF` rows use the
explicit `_SklearnQuantileForest` tree-quantile fallback.  They are useful for
screening, but they are not an exact reproduction of the CNB TVW-QRF.

| Horizon | Best model/policy | RMSE | MAE | Bias | n |
|---:|---|---:|---:|---:|---:|
| 1 | full TVW-QRF | 0.892 | 0.505 | -0.008 | 77 |
| 3 | full TVW-QRF | 0.991 | 0.593 | +0.009 | 73 |
| 6 | sentiment TVW-QRF | 1.072 | 0.671 | -0.092 | 67 |
| 9 | independent TVW-QRF | 1.083 | 0.736 | -0.127 | 61 |
| 12 | independent TVW-QRF | 1.068 | 0.743 | -0.003 | 55 |

The policy differences are small and unstable.  The hard-data independent
QRF is within a few hundredths of the best policy at h1–h6 and is the best at
h9–h12.  Adding sentiment does not produce a consistent gain.  Adding FMIE
expectations gives a small h1/h3 improvement in this sample but worsens h6–h12;
that is an information-value result for the optional diagnostic, not a reason
to put surveys into the independent forecast.

BBIM-lite is below the QRF and usually below AR3 on RMSE in this run.  Its MAE
is sometimes competitive, but its negative bias is persistent.  It remains a
research challenger rather than a production candidate.

The scalar benchmarks were:

| Horizon | AR3 RMSE | RW RMSE |
|---:|---:|---:|
| 1 | 1.062 | 1.323 |
| 3 | 1.106 | 1.413 |
| 6 | 1.129 | 1.292 |
| 9 | 1.205 | 1.488 |
| 12 | 1.295 | 1.134 |

These figures should not be read as a claim that the big model beats the
operating h0 model or the survey.  They use a 2015-onward target history,
latest-vintage local data and reconstructed release lags.  A common-window
comparison with the frozen independent nowcast, a material-surprise table and
the exact `quantile-forest` environment are still required.  The full forecast
and input rows, selected columns and engine labels are preserved in the output
directory so the run can be rechecked.

The `directional_hit` column is only a sign-of-the-m/m-rate diagnostic.  Czech
monthly CPI is positive in most observations, so this is not a surprise-
direction score and should not drive selection.  The project's material
surprise-capture table remains the relevant trading-oriented test.

The `d` run is identical to `b` and `c` numerically.  It corrects one
data-contract ambiguity: the Czech PPI source is a same-period-year-ago index,
so the panel columns are now named `*_ppi_yoy` rather than `*_ppi_mm`.  It also
keeps the BBIM lag setting explicit at the wrapper boundary.  No forecast values
or release clock changed.

## Monthly path grid

The independent policy was also run at every direct horizon h=1 through h=12
in `output/big_model_independent_h1_h12_20260910/`.  This is the monthly grid
that can feed a later path-reconciliation layer; it is not yet a chained CPI
index forecast.  The table reports the same fallback QRF and the two scalar
benchmarks on each horizon.

| h | QRF RMSE | QRF MAE | AR3 RMSE | RW RMSE | n |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.898 | 0.499 | 1.062 | 1.323 | 77 |
| 2 | 0.967 | 0.586 | 1.095 | 1.269 | 75 |
| 3 | 0.999 | 0.597 | 1.106 | 1.413 | 73 |
| 4 | 1.037 | 0.634 | 1.126 | 1.397 | 71 |
| 5 | 1.024 | 0.624 | 1.167 | 1.399 | 69 |
| 6 | 1.073 | 0.666 | 1.129 | 1.292 | 67 |
| 7 | 1.013 | 0.627 | 1.148 | 1.434 | 65 |
| 8 | 1.094 | 0.711 | 1.193 | 1.500 | 63 |
| 9 | 1.083 | 0.736 | 1.205 | 1.488 | 61 |
| 10 | 1.116 | 0.751 | 1.250 | 1.491 | 59 |
| 11 | 1.123 | 0.763 | 1.232 | 1.567 | 57 |
| 12 | 1.068 | 0.743 | 1.295 | 1.134 | 55 |

The effective first target moves later with h for the same 60-label rule.  The
grid gives us a consistent set of direct monthly conditional forecasts, but
independent rows at different horizons can imply an incoherent future path.
The next path step should therefore reconcile these rows to a level/index path
and score both monthly errors and path-level y/y errors.

## Practical decision

Keep `forecast_independent.py`/`HARD_BASE` as the next-release operating
nowcast.  Use the independent big-panel TVW-QRF as a path and h1–h12 research
challenger after installing the locked dependencies.  Keep sentiment and full
as side-by-side information lines.  Do not average the three policies or
promote BBIM from this result.  The next useful work is a common-window,
exact-QRF run and a compact comparison against the current component/path
models; additional hyperparameter searching is lower priority than better
release clocks, food/admin persistence, seasonal encoding and a proper
uncertainty score.
