# R18 category-based persistent pressure and smooth-horizon signal correction

Declared before numerical model execution. This is a small statistical common-trend model inspired by multivariate trend inflation, not a replication of the NY Fed estimator or an exact Czech core partition. Category source roster is selected by published definitions before model fits. No surveys, confidence or inflation expectations enter.

## Measurements, clocks and targets

Use the 18 primary CZSO groups in data/research_r18/categories/primary_monthly_levels.csv, plus the separately sourced CNB core monthly target tests/fixtures/cleanup/cnb_core_mm.csv. The ten goods groups, six services and two housing groups are measurements, not exhaustive headline components or official core expenditure weights. Do not aggregate them as an official core basket. Historical classification is the current official recoded history; availability dates are reconstructed release gates, not recorded vintages.

Monthly log rates are100*log(level_t/level_t-1), requiring both endpoints. Core is100*log1p(core_mm/100). At each origin use only reference months before t whose detail publications are known by the saved R15 decision clock. Require complete contiguous joint history through t-1 and at least48 months. Use at most96 last calendar months. If source/clock coverage fails, use the exact unchanged FAST core path with an explicit reason on all12 horizons; never silently discard an origin. Origin-fitted states/seasonality/parameters are saved.

## Two fixed multivariate filters

For series j, destination mean S_j,m is the training-window mean of released monthly log rates in month-of-year m. Let z_jt=r_jt-S_j,month(t). The observation model is z_jt=mu_t+v_t+a_jt+epsilon_jt. mu is the common persistent random walk; v is a common temporary AR(0.3); each a_j is sector-specific persistent AR(0.95). Core is one separate measurement and has its own a_core. These are statistical components, not identified supply/demand shocks.

Observation variance R_j=max(0.05,1.4826*median(abs(diff(z_j)-median(diff(z_j))))/sqrt(2))^2. This is estimated only in the current training window. Process variances: common trend q_mu=.0025 for MCT_SLOW_R18 and .01 for MCT_FAST_R18; common temporary q_v=.04; sector q_j=.05*R_j. Initial mean0; covariance diagonal [1,1,R_1,...,R_N]. Standard Gaussian Kalman updates, simultaneous measurements, Joseph covariance update and explicit PSD checks. No clipping or parameter search.

Core h1..12 forecast is S_core,destination+mu_end+.3^(h+1)*v_end+.95^(h+1)*a_core,end. There are h+1 transitions from the last observed t-1; h0 is never used as realised information or changed in headline output. Save all measurement seasonal means, observation variances, states and transitions. Common positive-vs-negative breadth is the fraction of noncore category residuals above0.05 minus fraction below-0.05, averaged over the last three released months. Goods-minus-services persistent pressure is the unweighted difference of group mean a_j states; these are statistical predictors, not expenditure contributions.

## Chronological signal correction to MCT_FAST_R18

After saving all own-origin MCT_FAST forecasts, create MCT_SIGNALS_R18 using eight fixed predictors: original R15 unemployment_change3, ip_growth3, ulc_growth12, fx3, cost_26_mean3, cost_45_mean3, plus saved own-origin breadth3 and goods-minus-services sector pressure. All original hard-data transformations and publication lags remain. Predict the actual future core log rate minus the SAVED MCT_FAST prediction.

Fit twelve direct equations jointly, one coefficient vector B_h per horizon. Each h uses its latest96 eligible own-origin rows with target s+h<t and published by current clock, min24 rows; incomplete predictors are excluded with counts. Unlike selection requiring whole paths to mature, each equation may consume its own newly matured labels. No future label can enter another horizon through smoothing. If any horizon lacks24 rows or the current predictor is missing, the entire signal correction is zero and visibly flagged.

Training scale each feature by its pooled eligible-row RMS with floor1e-8 (use1 for belowfloor); no imputation, no intercept. Objective: mean_h(mean_i((y_ih-x_ih B_h)^2)) + mean_h(||B_h||^2) + mean_h=2..12(||B_h-B_h-1||^2). Both penalty constants1, fixed before fitting. Solve the strictly convex block normal equations; scale back current features consistently. The smoothness penalty discourages artificial monthly jumps in coefficients; it neither guarantees a monotonic path nor inserts unobserved targets. No post-result selection, sign constraints or CNB anchoring.

## Integration and tests

Replace only h1..12 core values in saved FAST native rows, preserving headline h0 and all other components/weights bit-exactly. Recompound annual CPI. Compare component monthly/cumulative errors and headline h1..12 on original R16 dates, with current-core/gentle/FAST controls. Keep original core-turn and CNB-clock tests and report every false call. Only an improvement supported on both component and aggregate layers supports a better-core-mechanism claim; aggregate-only changes are labelled error compensation.

Meaningful tests: common shock vs one category shock, positive covariance, exact transition power, future-reference rejection/release poisoning, zero-noise boundary, current/future targets excluded from smooth equations, strong regularization and absence of horizon jumps for a common synthetic signal. Candidate grids and output manifest are frozen before the full fit; all results remain exploratory given repeated earlier research.
