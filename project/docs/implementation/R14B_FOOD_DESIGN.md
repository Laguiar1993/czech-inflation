# R14B food: stable monthly-change pipeline, second-stage declaration

Prepared 9 September 2026 after viewing the completed R14 level-model results.
This is an outcome-informed exploratory adaptation, not another untouched test.
The original R14 code, input hashes, predictions and failed results remain intact.
No R14B fit is allowed until the parent freezes this specification and integration
roster. The only new food models are **FOOD_STABLE_PIPELINE_R14B** (primary) and
**FOOD_STABLE_OWN_AR_R14B** (same-estimator own-food control). No 3-versus-6 lag,
window, shrinkage, contraction or post-score model selection is planned.

## Observed problem and scope

The R14 primary maximum companion radius is 1.176071 at origin June 2022. All
three inputs were complete through May 2022, with 77 training response months.
The available annual agri/PPI/food increases were 31.96%, 22.33%, and 15.12%.
The model extrapolated a 295.11% cumulative food increase over h1..12, against
12.04% realised. This is excessive propagation of an already observed cost surge,
not merely failure to anticipate the war. The full common h12 headline RMSE is
8.177 versus bridge 5.395; recent-origin h12 is 1.274 versus 1.347. Neither a good
recent window nor the structural plausibility of a pipeline justifies promotion.

R14B changes the modeled stochastic state to stationary monthly inflation around
a causal seasonal mean. It preserves domestic multi-stage, delayed transmission,
but removes unrestricted combinations of integrated price levels. It does not
impose producer-consumer cointegration, constant margins, zero trend inflation,
or fixed future cost paths. All upstream rates are jointly forecast endogenously.

## Inputs, releases and coverage

Use exactly the verified R14 January-2015 to July-2026 `agri4`, `food_ppi`, and
`food` normalized log levels and source-release table. Define rate d[m] as
L[m]-L[m-1], in 100 log points (approximately m/m percent). First rate is February
2015; never invent a January rate. A rate is eligible only when BOTH endpoint
levels are released at the origin clock and both reference months are before t.
Unknown release timestamps make their observations unavailable. No future row is
read to estimate, center, scale, condition, contract, or initialize a model.
Save last released rate/reference month and both endpoint release timestamps.

For each origin, eligible response dates have finite released primary rates at
the response and all six contiguous monthly lags. Use the latest 96 eligible
complete response months, or all if fewer, with a minimum of 36. Calendar gaps
are never collapsed into fictitious adjacent lags. At February 2019, the nominal
first complete response is August 2015, so at least 42 responses are available.
Both primary and own-food control use exactly this primary response calendar.
Missing fits remain missing with a reason; no old-bridge fallback is a candidate.

The historical source audit found the four physical farm series start January
2010 (199 complete months), but the stored national food PPI still starts January
2015. The official CZSO archived food division source offers 1995-2025 levels,
and its documentation states old COICOP/ECOICOP division concepts are comparable.
The source, documentation, hashes and overlap audit are saved separately under
`data/research_r14/food/coverage_extension/`. No older-data splice enters this
round: complete food/PPI concept and release audits would be needed together.

## Fixed seasonal-centered VAR(6) and AR(6)

At each outer origin, compute a separate mean for each variable and each of the
12 calendar months using ONLY selected training response dates. All calendar
months must be represented. These 12 means are the model's explicit seasonal
equilibrium, including any nonzero annual average food inflation. Subtract the
corresponding calendar mean from every response and lag. Those means may use
later observations within this origin's training set when centering earlier
rows; they never use a date outside the outer eligible training window. The
own-food control uses the identical food means and scales.

Fit a zero-intercept VAR(6) to centered monthly rates. Variable order agri4,
food_ppi, food; control food only. All lag prior means are zero, expressing
eventual mean reversion of inflation deviations. Training sigma is the ddof=0
standard deviation of centered response rates, never a full-sample scale. Reject
zero or nonfinite sigma. In equation i, coefficient on variable j at lag l has
prior SD (0.2/l)*(sigma_i/sigma_j)*(1 if i==j else 0.5). Minimize SSE_i/sigma_i^2
plus squared coefficient deviations divided by prior variance. There is NO fitted
intercept or seasonal dummy coefficient on these already centered responses.

Let rho be the fitted companion spectral radius. Set c=min(1,0.98/rho), with c=1
when rho=0. Replace each lag matrix A_l by c^l*A_l. This deterministic stability
map multiplies every companion root by c; hence final radius is <=0.98 within
numerical tolerance. Apply equally to primary and own control. Report original
radius, final radius, c, all coefficients and number of contracted origins.
This is a declared constrained forecast mapping, not a new Gaussian posterior
claim. No forecast clipping, error-based cap, case-specific override or tuning.

Recompute training residuals using the final contracted coefficients. Set Q to
0.9*(E'E/n)+0.1*diag(E'E/n), plus diagonal jitter of
1e-10*mean(diag(E'E/n)). No measurement or forecast outcome enters Q.

## Ragged edge, recursive predictions and exact bridge contract

Initialize from the latest six consecutive fully observed primary rate vectors,
centered using the frozen origin means. Advance through t-1 using the fixed
companion model and Q; when a coordinate's rate is known, condition its centered
state on the observed rate minus its corresponding calendar mean, with zero
measurement noise. Never infer an observed difference from an unreleased level.
Unknown coordinates retain model conditional mean and covariance. The own-food
control starts at the same anchor and is conditioned on eligible food only.

Forecast states t through t+12 recursively. Add the frozen destination-month
seasonal mean to the food coordinate to obtain log rate d_hat[t+h]. Internal
h0 remains model-only; replace original bridge food only at h1..12 with
100*expm1(d_hat[t+h]/100). Cumulative log rates and compounded percent changes
use exactly these predicted rates, with no Jensen correction.

Keep original h0, all nonfood contributions, every weight, forecast labels and
clock. Native output retains original columns, replaces future food values,
food contributions, total monthly forecast and model/status metadata, and
recomputes both ex-ante and conditional annual fields exactly. Failed predictions
remain missing; never hide inherited nonfood missingness by summing fewer parts.

## Evaluation and verification

Use all 90 original origins, h1..12, full / recent targets / recent origins,
and separate own, paired and common coverage. References are the bridge, the
two original R14 food models and two stored R12 food variants. Report food m/m,
cumulative log and compounded-percent errors, and exactly compounded headline
monthly/annual RMSE, MAE and bias. Paired annual-MSE differences use circular
origin-block length12, 2000 replicates, seed1410. All primary/control/bridge
coverage counts must remain visible. Parent declares combined roster separately
before fits; no substitution of a better-scoring variant afterward.

Tests before fits: rates require both released endpoints; first January rate
absent; future values/releases and unavailable old inputs cannot affect model;
identical primary/control response dates and food centering; rolling cap96 and
minimum36; training-only means/scales/Q; no fitted residual intercept; lag-l
root contraction produces exactly scaled roots and preserves seasonal equilibrium;
synthetic delayed cost propagation; ragged observed-state equality and unknown
uncertainty; destination seasonal means; cumulative-rate/product identity;
preserved h0/nonfood/weights, annual recomputation and missing/no-fallback behavior.
Save source/parameter/runtime manifests and native predictions before scoring.
Full offline replay must refit all origins and compare deterministic payloads.

Implementation is new files `models/food_stable_r14b.py`,
`food_stable_experiment_r14b.py`, `test_food_stable_r14b.py`, and
`output/research_r14b/food/`; original R14 files remain unchanged.
