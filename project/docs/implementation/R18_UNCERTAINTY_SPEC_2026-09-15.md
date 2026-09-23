# R18 joint path-error sensitivity and interval evaluation

Declared before execution. Reuse frozen model points; no new fit or selection. This tests a simple joint historical error law, not calibrated state covariance or probability claims.

For each fixed candidate and origin t, collect that model's saved earlier origin s monthly headline prediction errors in log-percent units, for ALL h0..12: e_s,h=100log1p(actual_mm_s+h/100)-100log1p(forecast_mm_s,h/100). Require all13 actual months/predictions finite, final target s+12<t and every detail release <= current saved decision clock. Current-vintage continuous monthly headline outcomes match the existing path evaluator; these are not the rounded first-release outcomes used by the separate nowcast evaluator.

Use latest60 eligible whole paths, minimum24. With fewer, emit unavailable with n_pool, never a fabricated interval. Equal weights, no mean removal/scaling/regime choice. For current origin, add each historical vector to its frozen current log monthly predictions INCLUDING h0, transform to monthly relatives and compound to annual CPI using only known history before t. Each empirical scenario remains a coherent monthly path; residual vectors preserve historical dependence across months. Do not independently join per-horizon quantiles into a claimed coherent scenario. Save actual pool origin/release membership and all13 error coordinates.

Report marginal 80/90 annual-CPI interval coverage/width and empirical CRPS, full and origins2024+, separately for every h1..12; compare same eligible dates across models and include n_intended and missing distributions. Quantiles use inverse empirical CDF. Small samples, overlapping errors, heavy crisis influence and revised vintages remain limitations. These do not assign probabilities to new geopolitical shocks.

Keep independent point forecasts unchanged. Energy portfolio scenarios remain assumption-conditioned and never use these empirical quantiles as national probability bands. No post-result tuning; operating interval promotion needs coverage/reliability evidence and a prospective record.
