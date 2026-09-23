# R21: learning from released forecast errors

**Declared before new fits, 2026-09-15.** User has authorized continued model research and tests. Research-only additions; no existing formula, live default, or frozen output is replaced. No untouched holdout exists. Historical availability is reconstructed and input histories revised. All results, including failures, must be published.

## Questions and specifications

1. Does directly targeting the first headline release improve the nowcast beyond correcting core alone? Use the saved HARD_BASE forecast as the offset, with the actual first-release monthly CPI minus that forecast as the label. Never use consensus as a feature, label, or selection objective. Fit on up to 60 earlier, published labels, minimum 24. Compare a recency-weighted mean (12-month half-life, shrunk by n/(n+24)) and elastic net (alpha .05, l1_ratio .5, same recency weighting). ENET uses the existing hard-only feature frame plus the saved BASE forecast and lagged headline errors (last and last-three mean, assembled separately at each historical decision). Impute/scale on training rows only. Shrink the intercept by n/(n+24). Until 24 labels, return BASE.

2. Is legacy quantile weighting helping the core error correction? On the existing released, sequential hard-core errors, minimum 40 and expanding history, fit a 200-tree random forest with leaf 8, all features, seed 42, two workers. Compare its conditional mean and a quantile forest median with the same parameters. Add the predicted error times the known core weight to BASE. Use the same hard-only, decision-masked features. No hyperparameter search this round. Preserve existing HALF/FULL as archived controls; runtime differences are not claimed as model improvements.

3. Can a coherent path combination adapt sooner? Three experts: FAST R15, current core R14B, gentle slope R16. Same weights at all h1–h12; h0 unchanged. Compare a fixed prior (.5,.25,.25), a full-path-maturity pool, and a partially-matured pool. Both learned pools use exactly the same objective and bounds, so the difference isolates label maturity. Eligible training origins must predate the current origin; all constituent outcomes through a horizon must be released and precede the current target month. Restrict scored target months to the preceding 36 months. Require six labels at each h1–h12, otherwise use the prior. Full pool additionally requires every h1–h12 outcome for an origin. Partial pool uses each released prefix independently. Weight loss by target recency (half-life 12 months), balance horizons equally, normalize each horizon by the prior pool's past MSE with floor .01 squared log-percentage-points. Minimize exact compounded cumulative headline log loss plus .05 times squared distance from the prior. Weights sum to one; FAST weight >= .25; all nonnegative. Deterministic SLSQP must succeed or fail loudly. This is a forecast combination experiment, not a replication of ECB WP1972.

4. Does persistent component forecast bias contain information beyond the state itself? For FAST's core and food separately, measure released earlier h1 errors in monthly log points. Latest 24 eligible errors, 12-month target half-life, mean shrunk by n/(n+24), minimum 12. Apply that offset to that component's log monthly forecast with decay .9^(h-1). Test core alone, food alone, and both. No admin/January mapping adjustment. All weights/non-adjusted components/h0 remain unchanged.

## Evaluation and decisions

Fixed 90 origins February 2019–July 2026. Path: existing 969 primary keys, all monthly horizons, full and 2024+; same report/cutoff CNB clocks, leave-one-report omissions, strict and sustained core turns, component scores, bootstrap descriptive uncertainty. Nowcast: same first-release actual/consensus rows, full90, common post-24-label66, recent, ex-January, big surprises >=.4pp, and ALL ex-ante abs(forecast-consensus)>=.2pp calls. Material improvement means absolute-error gain >=.15pp; overshoots receive ordinary loss. Include thresholds exactly with numerical epsilon. Publish release-level rows. No new threshold tuning or winner selected by the big-surprise subset.

Promotion to live is not automatic. A research challenger should improve both RMSE and MAE overall without material recent deterioration, retain surprise performance, and not rely on one event. Report compromises rather than manufacture a composite winner. All training diagnostics include maximum label release and training keys.

## Implementation plan

- [ ] Tests first: poison future/unpublished labels; equal experts; exact monthly/contribution compounding; correction decays; missing availability excluded; first-release headline label gating; train-only preprocessing.
- [ ] Implement pure functions in models/released_error_research_r21.py; runners in tools/research_r21/ with explicit output paths and hashed inputs/spec.
- [ ] Run every declared candidate, reuse the existing evaluator with corrected R21 artifact descriptions, preserve controls and old outputs.
- [ ] Independently review timing/arithmetic and verify scoreboards, then publish R21_RESULTS_2026-09-15.md and a compact comparison chart.

Primary motivation: Hubrich & Skudelny, ECB WP1972 (2016), https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1972.en.pdf. Their evidence motivates recent-performance combinations; neither their empirical result nor their model design is claimed as our result. The direct offset models and partial-label objective here are new project-specific hypotheses.
