# Predeclared experiment: elastic net in place of ridge in the core and food blocks

Declared 7 September 2026, BEFORE running. One run, frozen rules. User
request: no block uses elastic net today; ridge cannot drop a feature, and
two of today's results (four correlated foreign food series adding noise
in calm months; ESI carried at zero correlation) are the setting where an
L1 component earns its keep.

## Estimator (fixed before the run)

`_enet_predict` mirrors `_ridge_predict` exactly in everything but the
estimator: training rows are targets released at the decision clock
through origin-1 (minimum 48), features mean-imputed on the training slice
and standardised, prediction for the origin row. The estimator is
scikit-learn `ElasticNetCV` with `l1_ratio = 0.5` (fixed, not searched),
the default 50-point penalty path, penalty chosen by 5-fold
`TimeSeriesSplit` INSIDE the training window (expanding folds, no future
rows), intercept on the demeaned target, `max_iter` 20000. The chosen
penalty and the set of non-zero coefficients are recorded per origin.

## Cells (all declared now; nothing added after)

Core block: C0 ridge (incumbent), C1 elastic net on the same 26 features,
C2 elastic net on the 26 features plus the four foreign core series of
`FLASH_SPEC.md` (`de_neig, de_serv, ea_neig, ea_serv`).
Food block: F0 ridge + X-13 (incumbent), F1 elastic net on the same 5
features with the same X-13 target and seasonal factor, F2 elastic net on
the 5 plus the four foreign food series (`de_foodun, de_foodpr,
ea_foodun, ea_foodpr`).
The foreign series are the ECB mirror finals to 2025-12 (FLASH_SPEC
caveats apply: finals as flash proxy, NaN for 2026 origins). Release-eve
clock; the non-foreign cells coincide with month-end by construction.

## Evaluation

The 90 origins. Harness: C0 and F0 equal the backtest `core_pred_eve` and
`food_pred_eve` to 1e-9. Block RMSE and MAE on all 90, ex-January, 2024+,
2024+ ex-Jan, 2025+; headline effect through the origin's solved block
weights against the first release; big-surprise MAE and W-L at 0.15 for
information; per-origin count of non-zero coefficients, the features most
often dropped, and the median chosen penalty.

## Adoption rules (frozen)

- C1 replaces the core ridge only if its block RMSE improves by at least
  5% on all 90 AND on 2024+ with the headline not worse on either; same for
  F1 against the food ridge.
- C2 (F2) is carried to the flash stage 2 only if it beats BOTH the
  incumbent and C1 (F1) by at least 5% on all 90 AND 2024+, headline not
  worse. This is the one way the foreign series can come back: through an
  estimator that can discard them.
- No search over `l1_ratio`, folds, penalty grid or feature subsets. Fail
  means closed.

## RESULTS (7 September 2026, single run; log `output/en_run.log`) -- RECORDED AND CLOSED

Harness: C0 and F0 equal the backtest to 4.4e-16 / 2.2e-16.

| split | n | core ridge | core enet | core enet + fx | food ridge | food enet | food enet + fx | headline: inc / C1 / C2 / F1 / F2 |
|---|---|---|---|---|---|---|---|---|
| all 90 | 90 | 0.308 | 0.313 | 0.313 | 0.913 | 0.943 | 0.855 | 0.4068 / 0.4091 / 0.4105 / 0.4122 / 0.4078 |
| ex-January | 83 | 0.306 | 0.311 | 0.308 | 0.782 | 0.818 | 0.756 | 0.4041 / 0.4072 / 0.4073 / 0.4100 / 0.4103 |
| 2024+ | 31 | 0.182 | 0.185 | 0.178 | 0.780 | 0.795 | 0.854 | 0.2166 / 0.2177 / 0.2165 / 0.2196 / 0.2191 |
| 2024+ ex-Jan | 28 | 0.184 | 0.186 | 0.179 | 0.682 | 0.700 | 0.725 | 0.1983 / 0.1999 / 0.1995 / 0.2021 / 0.2059 |
| 2025+ flash era | 19 | 0.140 | 0.141 | 0.142 | 0.567 | 0.597 | 0.700 | 0.1697 / 0.1712 / 0.1721 / 0.1760 / 0.1919 |

Big surprises (23): incumbent 0.504 / 7-1; C1 0.512 / 7-1; C2 0.516 / 7-3;
F1 0.508 / 7-4; F2 0.487 / 6-1.

Selection diagnostics: the expanding-fold CV chooses a very light penalty
for core (median 0.005 on standardised features; 22 of 26 coefficients
non-zero at the median origin), so C1 behaves like a barely regularised
regression and carries more variance than ridge at alpha 3; the features
it drops most often are `state` (kept in 26% of origins) and `exp12`
(48%). Food keeps all five features at most origins (penalty 0.057). In
F2 the German processed-food series is kept at every origin and the
farmgate lag `agri_l0` is dropped at every origin: the foreign print
substitutes for the farmgate information rather than adding to it, and
the block is still 10% worse in 2024+ and 23% worse in the flash era.

### Decision

All four rules fail: elastic net does not replace ridge in either block,
and the foreign series do not come back through it. Reading: at 130-230
training rows the incumbents' fixed L2 penalty is a better variance
control than a penalty chosen by five expanding folds, and the honest
selection the L1 term offers costs more in stability than it saves in
bias. The estimator is not the constraint on this model; the information
set is. Closed; no search over `l1_ratio`, folds or grids.
