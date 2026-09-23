# Predeclared experiment (stage 1): same-month foreign flash components in the food and core blocks

Declared 7 September 2026, BEFORE running. One run, frozen rules. Approved
by the user as the next feature idea after the food and core tests closed.

## Mechanism

Germany's flash CPI (last days of month M), the euro-area flash and the
Polish flash (first working days of M+1) are public before the Czech first
release (day 4-6 of M+1 in the flash era, day 8-15 before 2025). They carry
same-month food, goods, services and energy moves. Common shocks (2022
food and goods) reached those prints in the same month; the Czech blocks
see them only through lagged farmgate and producer prices. This is the one
remaining feature idea whose information the current inputs lack.

## Data (stage 1) and its two caveats

- Source: ECB Data Portal mirror of Eurostat HICP (dataset ICP), monthly
  indices, areas DE and U2 (euro area), items FOODUN (unprocessed food),
  FOODPR (processed food incl. alcohol and tobacco), IGXE00 (non-energy
  industrial goods), SERV00 (services); 2014-01 to 2025-12. Poland and
  Austria are excluded: the Austrian flash carries the headline only and
  the Polish flash's food aggregate does not map to these items.
- Caveat 1, vintage: the series are FINAL values used as a proxy for the
  flash values that were public at the time. Flash-to-final revisions of
  these aggregates are typically within 0.1 pp; the true flash archive is
  stage-2 work if this stage passes.
- Caveat 2, coverage: the mirror is frozen at December 2025 (EU 2016/792
  re-cut). The seven 2026 origins carry NaN foreign features, which the
  ridge mean-imputes, so at those origins the challenger equals the
  incumbent. National sources for 2026 onward are stage-2 work.
- Clock: release eve (B) only. At month-end (A) the euro-area and most
  German flashes are not yet out, and a mixed panel would need exact German
  release dates; A is reported as the incumbent by construction.

## Features (declared; none added or removed after the run)

For month M, same-month m/m in percent of the index: `de_foodun`,
`de_foodpr`, `ea_foodun`, `ea_foodpr` enter the FOOD ridge; `de_neig`,
`de_serv`, `ea_neig`, `ea_serv` enter the CORE ridge. Training rows use
the same-month value too (the same information the origin has at B).
Everything else in both blocks unchanged (alpha 3, minimum 48 rows,
eligibility, X-13 for food, month dummies and state for core).

## Evaluation

The 90 origins of `output/cz_struct_backtest.csv` at clock B. Harness:
the incumbent food and core recomputed by the driver must equal
`food_pred_eve` and `core_pred_eve` to 1e-9 (stop otherwise). Block RMSE
and MAE vs realised block m/m on all 90, ex-January, 2024+, 2024+ ex-Jan,
2025+, and on the 83 origins with data; headline effect through the
origin's solved block weights (`STRUCT_EVE + w_food*(food' - food) +
w_core*(core' - core)`), scored against the first release, with the
gate-closed comparison irrelevant here (admin untouched). Big-surprise
MAE and W-L at 0.15 for information. Ridge coefficients on the foreign
features at the last origin as a diagnostic.

## Adoption rule (frozen; stage 1 is necessary, not sufficient)

Each block separately: the foreign features are carried to stage 2 only
if, at clock B, the block RMSE improves by at least 5% on all 90 AND on
2024+, and the headline RMSE is not worse on either. Stage 2 (flash
vintages, 2026 national sources, availability dates per release) must
then reproduce the gain before anything enters the operating model. A
block that fails here is closed; no feature subset search, no lag search.

## RESULTS (7 September 2026, single run; log `output/flash_run.log`) -- CLOSED AT STAGE 1

Harness: incumbent food and core equal the backtest to 2.2e-16 / 4.4e-16.
Foreign data 2014-02..2025-12; 83 of 90 origins carry it.

| split | n | food inc | food + fx | d | core inc | core + fx | d | headline inc | + food | + core | survey |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all 90 | 90 | 0.913 | 0.820 | −10.2% | 0.308 | 0.311 | +0.9% | 0.4068 | 0.4035 | 0.4100 | 0.3815 |
| 83 with data | 83 | 0.936 | 0.828 | −11.5% | 0.319 | 0.321 | +0.6% | 0.4211 | 0.4174 | 0.4243 | 0.3942 |
| ex-January | 83 | 0.782 | 0.726 | −7.2% | 0.306 | 0.300 | −1.7% | 0.4041 | 0.4072 | 0.4040 | 0.3801 |
| 2024+ | 31 | 0.780 | 0.830 | +6.4% | 0.182 | 0.178 | −2.0% | 0.2166 | 0.2113 | 0.2162 | 0.2410 |
| 2024+ ex-Jan | 28 | 0.682 | 0.680 | −0.3% | 0.184 | 0.180 | −2.1% | 0.1983 | 0.1987 | 0.1988 | 0.2315 |
| 2025+ flash era | 19 | 0.567 | 0.656 | +15.6% | 0.140 | 0.145 | +3.9% | 0.1697 | 0.1829 | 0.1717 | 0.1947 |

Big surprises (23): incumbent 0.504 / 7-1; + food 0.477 / 6-1; + core 0.512
/ 7-3. Same-month correlations with the Czech block m/m: euro-area
processed food +0.60, German processed food +0.55, unprocessed +0.39 to
+0.51; euro-area goods −0.47 and services +0.45 against Czech core (the
two cancel in the ridge; coefficients at the last origin are all near
zero). Mean absolute change of the forecast: food 0.34 pp, core 0.03 pp.

### Decision

- **Food: fails the stage-1 rule** (all 90 −10% passes, 2024+ +6% fails,
  headline 2024+ better but the block is the criterion). Not carried to
  stage 2. The information is real and concentrated: the foreign food
  prints capture the 2022 surge months that the Czech farmgate and PPI lags
  missed, which is where the all-90 gain comes from; in 2024-2025 the Czech
  food m/m decoupled from the euro-area path and the four correlated
  features add noise (the flash-era block is 16% worse). The vintage
  caveat would only weaken a pass, not rescue a fail.
- **Core: fails** (no effect either way).
- Not run, recorded as the possible follow-up: a single euro-area food
  aggregate instead of four correlated features, or a shock-gated use of
  the foreign food print. Each would be a new declared spec; nothing was
  tried here.
- Stage 2 (flash vintages, 2026 national sources) is not built.
