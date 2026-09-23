# Predeclared experiment: food block — X-13+ridge vs level state-space

Declared 6 Sep 2026, BEFORE running. One challenger, one comparison, one
adoption rule. All other blocks frozen at v2.2.

**Incumbent**: current food block — per-origin one-sided X-13 on food m/m,
ridge on the pipeline features, seasonal factor added back.

**Challenger (STATE-SPACE, fixed spec, no tuning)**: statsmodels
UnobservedComponents on the LOG PRICE LEVEL of the food index (cpi_long
div-01 levels), local linear trend + stochastic 12-month seasonal
(`level='lltrend'`, `seasonal=12`, `stochastic_seasonal=True`), fitted per
origin on history ≤ origin−1 (same information set as the incumbent), one-
step forecast converted to m/m %. No exogenous regressors in v1 of the
challenger (isolates the seasonality/trend treatment question). MLE with
statsmodels defaults; non-convergence at an origin ⇒ challenger forecast
missing there (counted, not imputed).

**Comparison**: identical origins (the v2.2 backtest's 90), block-level
RMSE/MAE vs realized food m/m, split all/exJan/2024+; plus the headline
effect (recombine challenger food into STRUCT, everything else unchanged).

**Adoption rule (declared now)**: adopt the challenger ONLY if its block
RMSE improves by ≥5% on BOTH the full window and 2024+, AND headline RMSE
does not worsen on either. Anything less: incumbent stays, result recorded.
No third variant, no parameter search, regardless of outcome.
