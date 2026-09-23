# R22: domestic and imported inflation transmission

**Declared before fitting/scoring.** User approved the proposed small joint economic system and nonlinear challenger. This research tests seven fixed candidates; no existing model or saved output is changed. Current-vintage data and reconstructed availability persist. No survey, confidence, CNB projection or future realised predictor enters. Sources and all transforms are frozen locally.

## Hypothesis and measurement

Earlier models appended released macro signals to core forecast errors. R22 instead forecasts an endogenous monthly system and uses the predicted evolution of upstream variables to propagate inflation pressure. This is a predictive system, not an identified causal supply/demand model. Inspiration: ECB WP1972 AppendixII component VAR/BVAR systems (https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1972.en.pdf). It is not a replication and does not borrow their projected assumptions.

Twelve measurements, in fixed order:

1. CNB core:100log(1+monthly percent/100).
2. Services pressure: equal mean monthly log change of six R18 national groups (ICT services, recreation services, cultural services, package holidays, catering, accommodation).
3. Housing pressure: equal mean monthly log change of actual and imputed rent.
4. Goods pressure: equal mean monthly log change of R18's ten primary goods groups.
5. Unemployment: Eurostat Czech SA unemployment level, A6 row11.
6. ULC pressure:100log(index_q/index_q-4) from the user-selected quarterly nominal unit-labour-cost index. Represent each quarterly growth observation from its quarter-end month through the following two reference months. All three carry the SAME maximum endpoint publication date and source-quarter identifier. This is an explicitly piecewise-constant quarterly-pressure proxy, not three independently observed monthly labour costs. No interpolation using a future quarter; forecasts of this proxy are latent monthly pressure forecasts, not official quarterly ULC projections.
7. Industrial production:100log(level_m/level_m-3), official SA/calendar-adjusted fixed-base index, A6 row12.
8. Import costs:100log(1+published monthly import-price change/100), A6 row26.
9. Manufactured PPI:100log(level_m/level_m-1), A6 row47, domestic manufactured-product producer-price index.
10. FX:100log(EURCZK_m/EURCZK_m-1), frozen monthly EURCZK levels.
11. Brent:100log(level_m/level_m-1), Bloomberg front-reference monthly mean selected earlier by user, A6 row60.
12. Industrial metals:100log(level_m/level_m-1), BCOMINSP monthly mean, A6 row62.

The service/goods/housing measurements are incomplete national CPI proxies including taxes; never relabel their average as an official core subindex or use today's weights to aggregate history. The separately measured CNB core is the forecast target. Source frequency, units, sample, source id, reference dates and availability are exported. Every multi-period transform requires all used endpoints to be finite and published. Missing availability fails closed. CPI release gates use existing calendar, prior-period fallback only where already defined by the repo. Monthly FX is available next-month day1; its earlier endpoint must also be available. No full-sample X13, PCA or Chow-Lin is used.

## Information and fitting

Common monthly calendar February2015 onward. At origin t use reference months strictly before t for parameter estimation, individually masked by the original forecast clock. Core/category outcomes at t are excluded. Market/macro month t observations may condition the internal h0 state only when actually available by that clock; headline HARD_BASE h0 remains fixed.

Training dates are the last96 responses with all12 measurements and their six lag blocks finite; minimum36. All families use these same dates to isolate information content. Record the number of distinct ULC quarters. When common history is insufficient, explicitly use unchanged FAST core for all12 horizons; do not drop an origin.

For each measurement, estimate destination-season effects on common training response dates using r_m minus its trailing12-reference-month mean, then month-of-year means demeaned over twelve seasons. Known SA unemployment and IP, and annual ULC pressure, have seasonal effect0. Center each series on the mean of its latest12 released de-seasonalized observations strictly before t. Scale by standard deviation over common training responses, floor.05. These choices permit a recent equilibrium reference without a hidden2% anchor. Fit all equations using six monthly lags plus a constant, on standardized centered data.

Bayesian-ridge posterior mode: independent Gaussian coefficient prior. Own first lag prior mean .8 (core/price rates) or .95 (unemployment, ULC, IP); all other lags and intercept prior0. Prior SD=.2/lag for own lags, .1/lag for cross lags, .2 for intercept. Gaussian observation variance1 in standardized space. Solve(X'X+precision)B=X'Y+precision*Bprior. This is a fixed-prior point estimate, not a claim of full Bayesian uncertainty.

Companion stability: if spectral radius>.98, multiply lag-l coefficients by c^l, c=.98/radius. Record raw and final radius and coefficient contraction. Residual covariance after contraction: .9 empirical+.1 diagonal, numerical ridge1e-8. Kalman condition the ragged edge from the last six completely observed months using released measurements only. All families initialize at the same reference month. Measurement updates are exact for the defined proxy series; the Gaussian approximation does not erase the quarterly-pressure limitation. Simulate internal month t and h1..h12. At t condition any permitted known macro observations, then propagate; do not substitute HARD_BASE as an observed core reading.

## Fixed roster

- JOINT_OWN_R22: core alone, matched dates/preprocessing/prior.
- JOINT_DOMESTIC_R22: core, services, housing, unemployment, ULC and IP.
- JOINT_IMPORTED_R22: core, goods, import costs, manufactured PPI, FX, Brent, metals.
- JOINT_LINEAR_R22: all12 measurements, same Bayesian ridge.
- JOINT_ENET_R22: all12; fixed ElasticNet alpha.02,l1_ratio.5 fits coefficient departures from the same persistence prior; no unpenalized intercept. Same stability contraction.
- JOINT_RF_R22: linear system plus .5 times a200-tree,leaf8,all-feature,seed42 forest prediction of the core equation's residual; other equations linear. Residuals are in-sample residuals of that origin's fitted linear equation, not claimed OOS errors. Forest only sees six-lag standardized state, excluding constant. This retains linear extrapolation while testing nonlinear residual dynamics. Ragged-edge updates use the linear system; nonlinear recursion begins after conditioning month t. Record that approximation explicitly.
- JOINT_HALF_R22: equal arithmetic mean of JOINT_LINEAR core and saved FAST core; all other components fixed.

No parameter sweep or after-score choice. ENET must converge; failures are surfaced. Nonfinite or nonsensical monthly values fail visibly, not clipped into a competitive score. Any research fallback is reported on original90-origin support.

## Economic diagnostics and evaluation

Export each forecasted driver, coefficient matrix, centering, seasonality, dates, states, covariance and known-h0 observations. At each origin perturb the latest filtered state AFTER internal month-t conditioning, one variable at a time: ULC pressure+2 annual log points; unemployment+.5pp; FX+100log1.05; Brent+100log1.2. Re-run the same forecast with no parameter refit, reporting the change in cumulative core by h3/6/12. These are predictive state perturbations, not causal identified shocks or known future events. Wrong signs or unstable propagation are evidence against an economic interpretation; do not impose post-hoc sign repairs.

Replace only h1..h12 core in frozen FAST paths; preserve all non-core blocks, weights and independent h0. Score full and2024+ original969 keys, all horizons, core as well as headline. Compare controls FAST/current core/gentle slope/R21 core feedback. Retain both CNB clocks, material gains/losses, report omissions, strict interior core turns and sustained movements including false calls. Use fixed-support bootstrap for relevant claims. Show proxy/driver own forecasts separately; historical category proxies never become official expenditure contributions.

## Implementation plan

- [ ] Add tests first for endpoint publication, quarterly bridge timing, future poison, matched histories, h+1 indexing, stability, ragged conditioning and accounting.
- [ ] Implement data/research_transmission_r22.py, models/transmission_r22.py and tools/research_r22/run.py; verify frozen inputs before and after runs.
- [ ] Execute all seven fixed candidates, export diagnostics and score fixed support using a new R22 wrapper around existing evaluators.
- [ ] Independent code/timing review; reproduce candidate outputs and selected driver responses; fix substantive defects and rerun affected artifacts.
- [ ] Publish R22 results, CNB replay, driver/response diagnostics and comparison charts; hash the delivery and verify earlier deliveries unchanged. No automatic operating-model promotion.
