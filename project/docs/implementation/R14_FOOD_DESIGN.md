# R14 food: domestic price-pipeline design, before new fits

Prepared 9 September 2026 for parent integration and declaration freeze. No new
forecast fits or outcome-based choices have been made. Primary integration model:
**FOOD_DOMESTIC_PIPELINE_R14**. Matched control: **FOOD_OWN_LEVEL_AR_R14**. Parent
must approve/freeze this design before any empirical fit. No additional food
candidate, blend, hyperparameter search or winning-variant substitution is planned.

## Economic hypothesis and primary evidence

The present bridge applies a five-year same-calendar-month average to food h4-h12.
R12 instead extrapolates an EWMA food trend and adds a two-variable correction
with an imposed three-month half-life. Neither explicitly propagates the levels
of earlier farm and food-industry costs through the production chain. R14 models
that chain jointly, allowing cost pressures to emerge over several future months.

[CNB, What drives food prices? (2020)](https://www.cnb.cz/en/monetary-policy/inflation-reports/boxes-and-annexes-contained-in-inflation-reports/What-drives-food-prices/)
uses agricultural, food-producer, consumer and imported food prices in a trend-cycle
system, and stresses that consumer prices can grow persistently faster than
producer prices. Consequently R14 does not impose a fixed consumer/producer ratio,
unit long-run pass-through or a stationary margin. It is a forecast experiment,
not a structural identification of margins or demand.

[Ferrucci, Jimenez-Rodriguez and Onorante, ECB WP1168 (2010)](https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1168.pdf)
find that domestic/EU farm-gate data and delayed transmission matter; globally
traded commodity prices alone can poorly describe European input costs. This
motivates prioritising the domestic chain. Their nonlinear results are not copied
as calibrated Czech elasticities. [ECB's 2024 food-price analysis](https://www.ecb.europa.eu/press/economic-bulletin/focus/2024/html/ecb.ebbox202402_04~9b36bced23.en.html)
also models a sequence through food commodities, farm-gate, food-industry producer
and consumer prices. Unexplained wage, energy and distribution effects remain.

World Bank and FAO public data were researched. The World Bank publishes observed
monthly food commodity indices; FAO releases monthly indices on published dates.
They are not an automatic substitute for local farm prices, need a USD/CZK
conversion and a historical release/revision audit, and do not remove the local
margin problem. No global series is included in these two fitted candidates.
This exclusion is fixed before scores. Existing Bloomberg commodity futures,
all futures curves, retailer data, surveys and expectations are excluded.

Primary downloaded documents and hashes are in data/research_r14/food/; sourcing
script tools/r14_food/collect_sources.py performs no estimation.

## Frozen input levels and exact concepts

All inputs are latest stored histories with explicit reconstructed publication
gates, not archived statistical vintages. Reuse frozen headline food m/m rather
than silently substitute an HICP series or already fully-sample-adjusted series.

1. `food`: tests/fixtures/cleanup/component_food_fuel_mm.csv, column food. Create
   log level L[m]=sum_{u<=m} 100*log1p(food_mm[u]/100), using January 2015 as an
   arbitrary zero. Consecutive levels reproduce the original monthly rate exactly.
   Original first month is only a normalization; no level from future data enters.
2. `food_ppi`: data/cz_ppi_product_raw.csv, national CZ-CPA division 10, no lower
   group, TYPUDAJE5A=IZ2015, exact monthly CASMKMQRM12 labels. Positive producer
   index, 2015=100, January 2015 through July 2026 (139 monthly levels). Transform
   100*log(level/January-2015 level), no seasonal adjustment from the full sample.
3. `agri4`: fixed equal-weight geometric index of four physical Czech national
   farm-gate prices from data/cz_agri_prices_raw.csv (national rows only):
   `Pšenice potravinářská [t]`, `Mléko kravské Q. tř. j. [tis. l.]`,
   `Prasata jatečná  j.tř. SEU v JUT [t]`, `Kuřata jatečná v živém I.tř.j [t]`.
   Define log index as the mean of 100*log(price_j[m]/price_j[2015-01]). The four
   series all have zero missing months over January 2015-July 2026. This is a
   stable physical-cost proxy, not an official weighted agricultural index and
   not a CPI contribution share. Fixed equal weights do not follow basket regimes.
   The previous seven-product average had changing support (potatoes 11 missing
   months and apples 2 over this interval); neither missing-value averaging nor
   substitution is used here. All four observed prices must be finite/positive.

These definitions are frozen on input coverage/economic grounds, not forecast
performance. All source extraction, units and provenance are saved before fits.

Publication policy per source observation m, with Europe/Prague clocks:

- Food CPI: existing detailed CPI release calendar; unknown dates unavailable,
  existing pre-calendar conservative day-20 convention retained.
- Agri4: day 26 of m+1, the existing raw national average-price publication rule.
- Food PPI: day 16 of m+1 plus existing reference-month exceptions (January +9,
  March/April +4, June/December +1). Calendar arithmetic precedes localization.

For every outer t, require month m<t AND publication timestamp <= saved origin
clock, separately for each series. This generally admits t-1 farm/PPI at the
release-eve of CPI(t); R12's extra source r-2 cap is not carried over silently.
Do not admit t itself just because an input happens to appear in the current
file. Save last reference month and release timestamp per variable and origin.

## Matched recursive log-level estimators

Both models use the same 2015-01 start, the same complete-row training cutoff,
the same estimator, 12 monthly lags and deterministic destination-month dummies
(February-December, January omitted) plus an intercept. Primary variable order
is agri4, food_ppi, food. The control has food only but uses the primary complete
training calendar, so the comparison isolates the extra cost-chain information.

Expanding training, minimum 36 complete response rows after all 12 lags; this
requires at least 48 consecutive levels. There are only 139 levels in the current
common source snapshot, not 200. All 90 original forecast origins are intended;
the earliest February 2019 origin has sufficient nominal history, subject to
actual release eligibility. Missing fits stay missing with their reasons.

Use independent-equation Gaussian Minnesota posterior means, random-walk prior:
own first level lag mean 1, every other lag coefficient mean 0. No cointegration
rank or fixed relative-price restriction. Let sigma_j be the training-only SD of
first log differences of variable j (ddof=0); reject a zero/nonfinite sigma.
Prior SD for variable j at lag l in equation i:

    (0.2 / l) * (sigma_i / sigma_j) * (1 if i==j else 0.5).

This fixes global tightness 0.2, lag-decay exponent 1 and cross-variable shrinkage
0.5 before results. Intercept and seasonal dummy means are zero; their prior SD
is 10*sigma_i (weak compared with innovation scale). Solve the penalised Gaussian
least squares objective SSE_i/sigma_i^2 plus the sum of squared coefficient
deviations divided by their prior variances. No residual-based outer tuning,
window/lag search, clipping, cap, manually decaying cost correction or re-fit
after looking at errors. Output all coefficients and companion spectral radius;
do not reject near-unit-root level models solely for radius >=1 or silently
stabilize coefficients. Numerical failures are explicit.

Estimate the innovation covariance from the final fit's training residuals only:
Q = 0.9*(E'E/n) + 0.1*diag(E'E/n), plus diagonal 1e-10*mean(diag(E'E/n)) for
numerical conditioning. This is fixed covariance shrinkage for ragged-edge
conditioning, not a structural shock ordering or causally identified IRF.

## Released ragged edge and forecast reconstruction

Initialize the companion state at the latest month with 12 complete released
lagged level vectors, with zero covariance for observed state. Advance month by
month to t-1. When any series value is known at the outer clock, condition that
month's Gaussian state on its exact observed level using the standard Kalman
measurement update with zero measurement error. Use only released coordinates;
unknown upstream values retain their model prediction/covariance. If all three
last observations end at t-1, this simply uses the fully observed last state.
All conditioning uses Q from the eligible training sample. No interpolation
through future observations and no measured t or later value may enter.

Then forecast unconditionally through t+12, carrying agri and PPI endogenously.
Model food(t) is an internal state forecast used to generate later food levels;
it does NOT replace HARD_BASE headline h0. Forecast food m/m at t+h from the
successive forecast log levels at t+h-1 and t+h, h1..12:

    food_hat_mm[h] = 100*expm1((L_hat[t+h]-L_hat[t+h-1])/100).

These are conditional-median level paths; no lognormal mean adjustment or
simulated-shock recentering is introduced. Preserve the original food h0 and
all headline h0 values. For h1..12 replace only value_food, contribution_food
(original destination weight times new food rate), and headline mm_forecast.
All nonfood contributions, all weights and labels remain exactly the bridge's.
Recompound annual headline paths exactly using released pre-origin history and
the supplied HARD_BASE h0. Output native_forecasts.csv retains original baseline
columns and all component/weight fields, with only those declared fields/model
names/status metadata changed. Save predictions before outcome scoring.

## Evaluation, tests, and acceptance

Report both candidates, original bridge and stored R12 food variants on own,
paired and common panels at every h1..12; full origins, targets >=2024-01 and
origins >=2024-01 remain separate. Include intended/finite/scored counts; food
monthly, cumulative log food and exactly compounded annual headline RMSE/MAE/bias.
Paired circular origin-block bootstrap length 12, 2,000 draws, seed 1409. Parent
handles combined-core/fuel path and exact annual component-error attribution.
No automatic promotion from a small favourable window; economic consistency,
bad periods and prospective evidence remain relevant.

Tests precede implementation: input extraction/rebase invariance, exact original
food monthly reconstruction, common-calendar estimator control, train-only
sigma/Q, random-walk prior limiting case, synthetic cost shock delayed recursive
pass-through, conditional-state observed-coordinate equality, uncertain unobserved
coordinates, future-value and future-date poisoning, delayed/unknown releases,
destination seasonality, full-horizon cumulative/log-product identity, preserved
HARD_BASE/nonfood/weights, and missing/no-fallback coverage. Full offline replay
must re-estimate every origin and compare outputs; source/code/payload hashes and
runtime versions accompany output. No existing models/data/results are edited.
