# R18 independent nowcast error distributions and alert experiment

Declared before fitting. Existing HARD_BASE, HARD_HALF, HARD_FULL and CATEGORY_RAW point forecasts are immutable. Frozen matched first-release evidence supplies 90 releases Feb2019-Jul2026. R15 state clocks are the same release-eve clocks; verify mapping to first-release calendar. Historical information remains reconstructed, not recorded vintages.

## Error law

Response e=first_release_actual-independent_point. For each model and origin t use only earlier origin errors whose FIRST release date has passed. No consensus, actual surprise or outcome-selected big-event label enters the error distribution. Retain latest60 eligible releases and require24 for any distribution. Earlier origins still emit the unchanged point with distribution_status insufficient_history, no fabricated probability.

Three fixed families:

1. POOLED: equal-weight raw past signed errors added to current independent point.
2. SCALE: re-scale past signed errors by scale_current/scale_at_own_origin. Own scale=max(0.05, (n*mean_abs_last12+12*mean_abs_last36)/(n+12)), where n<=12 is past eligible count in the short window. With no past errors use0.25. The current scale never uses the current error. Weight errors by exp(-log(2)*calendar_age_months/24).
3. STATE: SCALE plus similarity conditioning. Two predictors are abs(HARD_FULL-HARD_BASE) and abs(CATEGORY_RAW-HARD_BASE), both known point disagreements, without consensus. Standardise by training pool RMS with floor0.05, compute Gaussian distance exp(-sum((x_i-x_t)^2/scale^2)/2), multiply temporal weights, normalize. Blend 50% temporal-only and50% similarity weights. If kernel total underflows, use temporal-only with explicit flag. This model sees neither outcome errors in distance nor future predictors.

Every law is a finite weighted empirical sample point+error. Save support, weights, each training origin/release, scales, effective sample size, probabilities, quantiles and all fallbacks. Quantiles use the left inverse weighted empirical CDF. These are distribution candidates, not guaranteed conformal intervals or calibrated probability claims. Frozen point need not equal the error-law median; report that median separately without changing the point used for gains.

## Evaluation and alert rule

Consensus first enters this evaluation layer. For each support value y, material_gain(y)=abs(y-consensus)-abs(y-frozen_point)>=0.15-1e-9. Probability is its weighted frequency. Also report probability abs(y-consensus)>=0.4-1e-9. Evaluate Brier scores for those two events, weighted empirical CRPS, 80/90 interval coverage and width.

Primary alert: abs(point-consensus)>=0.20-1e-9 and predicted material-gain probability>=0.65. Sensitivities0.55/0.75 are always shown, not selected. Compare with the unchanged abs-departure alert on precisely the same eligible dates; all eligible release outcomes remain in primary accuracy/distribution scores. Report every alert, large-event coincidence, material gain/loss, total error reduction and false alarms. With small samples no conditional hit-rate claim establishes a trading signal. Full/2024+/flash and January/ex-January results are separate; no subset selected after results.

Future poisoning tests must leave an earlier law unchanged; replacing current actual or consensus must leave the independent law unchanged. All parameters above are fixed and no search follows the run. Original source and output manifests remain unchanged.
