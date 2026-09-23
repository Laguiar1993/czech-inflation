# R14 fuel path design — 9 September 2026

Draft for pre-fit freeze. No R14 model has been fitted. Proposed fixed primary
fuel component: **FUEL_ECM_R14**, the weekly cost/error-correction model below.
Parent must declare the chosen primary before any empirical scoring. No futures,
survey forecasts, inflation expectations or selected combinations enter this work.

## What previous work already ruled out

The existing independent bridge forecasts future monthly fuel inflation with
the median of the last eight observations for the destination calendar month
(last24 median if fewer than three same-month observations). This rule has no
current oil-to-pump transmission. R12 changed food; R13 changed core; neither
estimated a replacement future fuel equation.

FUEL_SPEC_v23.md documents an earlier failed **h0** Brent extrapolation: a fixed
monthly beta0.35 was applied to a ten-business-day window, worsening measured
pump-price accuracy. R14 retains the current h0 untouched. Its new estimates
use weekly targets, weekly oil changes and weekly lag coefficients throughout;
the old short-window fixed-beta overlay is not restored. The weekly petrol/diesel
pair is a proxy for the CPI fuel block and excludes LPG/lubricants.

## Primary sources and files already retrieved

1. European Commission Weekly Oil Bulletin historical workbook, 1,082 weekly
   dates January2005–August2026, with one missing Czech gross-price row observed
   at schema inspection. Czech petrol95 and diesel prices with/without taxes,
   exchange-rate conversion, VAT and dated excise schedules are supplied.
   https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en
   Download: https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx
   Local: data/research_r14/fuel/raw/ec_weekly_oil_history.xlsx
2. EIA daily Europe Brent **spot**, USD/barrel, since1987:
   https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls
   Local: data/research_r14/fuel/raw/eia_brent_daily.xls
3. CNB daily CZK/USD and CZK/EUR fixing, downloaded as23 annual TXT files,
   2004–2026, one request per year. No monthly-FX approximation.
   https://www.cnb.cz/en/faq/Format-of-the-foreign-exchange-market-rates/
   Endpoint: https://www.cnb.cz/en/financial-markets/foreign-exchange-market/central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/year.txt?year=YYYY
4. EC Czech survey methodology, saved as raw/ec_czech_methodology.pdf:
   https://energy.ec.europa.eu/document/download/2b6efb04-9c48-4ef5-a5b1-c2e8183d3c08_en?filename=CZECHIA+2022.pdf
   Monday pump observations; Czech Statistical Office reporting; arithmetic
   survey averages. EC reports national submission Wednesday/publication Thursday.

All are current retrieved histories, not archived real-time vintages. The EC
historical workbook can incorporate corrections. Retain raw bytes, URLs, fetch
UTC, hashes, unit conversion and observed coverage in a new R14 manifest. Never
overwrite the old weekly pump fixture or any old statistical input. Compare
overlapping converted Czech gross prices against the frozen CZSO weekly fixture
as a data audit, not as an estimator-selection exercise.

Economic motivation: the CNB's historical retail-fuel decomposition identifies
koruna crude costs, refining/distribution margins, excise and VAT separately:
https://www.cnb.cz/en/monetary-policy/inflation-reports/boxes-and-annexes-contained-in-inflation-reports/Factors-affecting-retail-fuel-prices
This motivates a mechanism; it is not a parameter source or future-price forecast.

## Availability, currencies and future assumptions

Decision clocks are the saved baseline release-eve clocks, converted to Prague.
Weekly pump records and their observed tax state enter only from observation
Monday+7 calendar days at00:00 Prague, preserving the existing conservative pump
rule despite EC's usual Thursday publication. Missing weekly labels stay missing;
do not interpolate a missing target using later observations.

CNB fixing is available on its reference business date at14:30 Prague. EIA spot
observation dates do not prove publication dates: use observation+14 calendar
days at00:00 Prague as an explicit conservative reconstruction. EIA's weekly
spot-price publication motivates a lag;14days is an assumption, not a certified
historical timestamp. Save it explicitly and poison-test it. No fitting against
an oil observation that is unavailable at the actual origin.

For model training, a weekly pump target and every daily input entering its
weekly crude-cost average must both be published by the origin. Crude cost C_w
is the prior Monday–Sunday mean of daily BrentUSD * same-day available CNB
CZK/USD /158.987294928 litres/barrel. Carry only earlier FX fixings across its
holidays. Oil's missing non-trading days use the last earlier observation.

For every unknown daily oil or FX value along the forward path, hold each source
at its own latest origin-observable value. Known daily observations retain their
actual values. Do not pull realised future oil/FX from the newly downloaded full
history. This is a constant latest-observable oil-and-FX **scenario**, not a
prediction of war, supply shocks, the oil market or the currency.

EC price columns are EUR/1000litres; CZ_exchange_rate is EUR per CZK. Recover
CZK/litre as quoted price / CZ_exchange_rate /1000. Verify recovered levels against
the old Czech fixture. Use the same row's conversion for gross and net prices.
VAT and excise dates in the workbook are effective dates, not announcement dates.
At each origin use the effective tax/reconciliation wedge revealed by already
eligible pump observations, then hold it unchanged into the future. Define
T_w=G_w/(1+VAT_w)-N_w from observed gross and tax-exclusive net prices. This
includes statistical/currency reconciliation and must not be labelled statutory
excise. Never anticipate a later tax schedule row.
The model therefore misses future unannounced tax changes by construction.

## Exact fixed estimator, no grid search

Fit petrol95 and diesel separately to tax-exclusive CZK/litre pump levels N_w.
Use the latest260 complete eligible weekly observations, minimum104 observations.
First estimate the long-run relation N_w = a + b*C_w with constrained least
squares, a>=0 and 0<=b<=3. The intercept captures an average refining/distribution
cost or margin; this is not an identified refinery-margin series.

Then estimate weekly dynamics with the same available sample (and complete lag
rows), zero drift/intercept:

    delta N_w = lambda*(a + b*C_(w-1) - N_(w-1))
                + beta0*delta C_w + beta1*delta C_(w-1)
                + phi*delta N_(w-1)

Constrained least squares bounds: lambda in[0,1], beta0/beta1 in[0,2], phi in[0,.8].
No tuned penalty, alternative lag count, asymmetric variant or fitted blend.
The long-run fit and dynamics are re-estimated at each historical origin from
eligible labels only; standard optimisation tolerances are fixed in code and
audited. Save coefficients, training start/end, maximum source availability,
sample count and boundary hits. If insufficient history, fit failure, or a
nonpositive projected net/gross price occurs, fall back for the complete origin
to the declared constant-pump control and report that status; no silent clipping.

Start from the latest eligible observed net pump levels and changes. Recursively
project missing Mondays through the end of origin+12 using the origin-frozen
daily oil/FX scenario; retain known pump observations. Reconstruct gross prices
with origin-known effective wedge T and VAT: G_w=(N_w+T)*(1+VAT). Keep each known historical
week's own gross price rather than retrospectively applying current taxes.

Average Monday gross prices by month. Compute petrol/diesel monthly relatives
separately and combine using the existing publication-gated petrol share available
at the origin (hold it for future unknown basket regimes). This avoids the old
price-level weighting artefact. Forecast h1..12 fuel CPI with this ratio proxy.
The projected month-t pump mean is only the denominator for h1; headline h0 stays
the saved BASE value. This proxy is not asserted to be an exact official CPI index.

## Fixed comparison roster and integration

- INDEPENDENT_BRIDGE: all existing values remain the frozen reference.
- FUEL_ZERO_R14: literal zero fuel m/m at h1..12; h0 unchanged.
- FUEL_CONSTANT_PUMP_R14: retain eligible observed gross pump weeks, carry each
  petrol/diesel price flat for unobserved weeks, then use the same monthly-relative
  aggregation. h1 can move from the monthly averaging/known-week carry effect;
  distant monthly changes are zero. This distinguishes observed carry from an
  assumed persistent seasonal increase.
- FUEL_ECM_R14: the fixed primary model above, with the same weekly information
  dates and monthly aggregation as the constant-pump control.

Save native_forecasts.csv with the baseline columns. Copy all baseline rows and
replace only value_fuel, contribution_fuel and mm_forecast for h1..12. Recompute
yy_exante (and the explicitly labelled conditional annual diagnostic) by exact
monthly compounding; preserve h0, all other component forecasts, all weights,
origin clocks and evaluation actuals. Keep each proposed model separate. Root
integration will use the declared ECM candidate rather than choosing after scores.

## Fixed evaluation and tests

Use the old90 origins, h1..12, all eligible realised destinations and identical
pairwise/common coverage. Report fuel m/m and accumulated fuel price change,
headline m/m and YoY RMSE/MAE/bias, full, recent-target2024+ and recent-origin2024+
samples with counts, and h1/3/6/12 checkpoints. Report exact changed fuel
contribution versus shared other-block errors, all leave-one-origin-out influence,
and paired circular origin-block bootstrap12 (6/18 sensitivity),5000 draws seed42.
Do not rank models using an unreported favourable horizon or sample.

Before fitting write red tests for unit/currency conversion, tax identity,
missing-week handling, publication cutoffs, future oil/FX/tax/target poisoning,
matched controls, stable constant-cost limit, nonpositive-price fallback, source
regime availability, unchanged h0/nonfuel blocks/weights, and exact compounding.
Data preparation may proceed now. Await the parent's freeze/implementation
message before fitting either estimator or producing empirical model scores.

New ownership only: models/fuel_path_r14.py, fuel_path_experiment_r14.py,
test_fuel_path_r14.py, tools/r14_fuel/, data/research_r14/fuel/ and
output/research_r14/fuel/. No old numerical/result edits and no Git commits here.

## Pre-fit source reconciliation clarification

The data-only audit, before empirical model fitting, found the EC gross/net/VAT
and statutory schedule do not always reconcile. On20July2026, diesel gross is
41.297CZK/litre, while published net plus scheduled8.011CZK/litre excise and21%VAT
reconstruct38.950800. The schedule reports the higher excise one week later.
Other mismatches reach0.188234CZK/litre. These are source conflicts, not verified
legal-timing findings. Preserve the full statutory reconciliation audit, all
source rows and all overlap discrepancies; do not patch or drop selected dates.

The primary ECM retains the published tax-exclusive net price. Its future gross
mapping uses the latest already observable T above, closing G=(N+T)*(1+VAT)
exactly at the initial price state and preventing an artificial seam from source
inconsistency. Future T and VAT remain unchanged until actually observed at a
later origin. Tests cover this identity and future tax/price poisoning. This is
an explicit pre-fit data-definition clarification, not an improvement selected
from forecast scores or a claim that statutory schedules were validated.
