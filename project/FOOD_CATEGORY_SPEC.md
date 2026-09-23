# Predeclared experiment: category-level food forecasts with pooled information

Declared 7 September 2026, BEFORE running, as the second food project after
`FOOD_SZIF_SPEC.md`. Motivation (user brief): forecast a few food categories
separately while sharing information across them so small samples do not
produce unstable models; the Chicago Fed's "Microforecasting Inflation"
(Giacomini and Levin, Economic Perspectives 2023-3) combines
category-specific and pooled forecasts with inverse recent-MSFE weights.
Their US PCE results motivate the test; they promise nothing for Czech CPI.

## 1. Data (checked for consistency, no forecast comparison made)

- Classes: ECOICOP 0111-0119 and 012 (10 classes), CZSO `cpi_long` division
  01, base 2015 = 100, monthly 2015-01 -> m/m from 2015-02 (138 months to
  2026-07). Class m/m standard deviations 2015+: bread 1.0, meat 1.4, fish
  2.4, dairy 1.6, oils & fats 2.8, fruit 3.4, vegetables 5.4, sugar 1.9,
  other food 1.5, beverages 1.7.
- Weights: CZSO basket files `data/baskets/spot_kos{2014..2026}.xlsx`, class
  rows (per mille of the total basket), regime = the even start year of the
  two-year window (`cz_struct._regime`), Laspeyres price-updated shares
  (weight times the class price relative since the December before the
  regime, normalised over the ten classes). Check: aggregating the class
  m/m with these shares reproduces the published food m/m with RMSE 0.047
  pp, max 0.15 pp (2015-2017), mean +0.001 -- adequate.

## 2. Models (all on seasonally adjusted class m/m, per origin, one-sided)

- Seasonal adjustment per class as the incumbent does for the aggregate:
  one-sided X-13 on the class history released at the clock, target-month
  factor = mean of the last three same-month fitted factors; fallback on
  X-13 failure = same-month mean deviation from the expanding mean.
- Candidate forecasts of the SA class m/m at origin t:
  - **I1** rolling mean of the last 12 released SA observations (the
    Giacomini-Levin individual intercept model).
  - **I2** class-specific expanding ridge (alpha 3, the model's ridge) on
    `y_l1, y_l12` (own class) and `agri_l0, agri_l1, food_ppi_l1` (the
    incumbent's pipeline features), minimum 48 training rows as everywhere.
  - **P** pooled ridge across the ten classes: class means removed on the
    training sample (class fixed effects), one common slope vector on the
    same five regressors, standardised over the pooled sample, alpha 3,
    minimum 24 months of panel (240 rows). This is the "shared
    information" component.
  - `szif_mm` (FOOD_SZIF_SPEC) is added to I2 and P ONLY if that experiment
    adopts it; otherwise it is absent. Decided by the step-1 rule, not here.
- **Individual Weighting (IW)** per class and origin: weight of candidate k
  proportional to 1 / MSFE_k over its last 24 realised pseudo-out-of-sample
  errors, where an error counts only once the class value for that month is
  released at the clock; a candidate needs at least 12 such errors to be
  weighted, otherwise it is excluded; if none qualifies, equal weights over
  the available candidates. The recursion starts at origin 2017-02 so the
  first evaluated origin (2019-02) has error histories for I1 and P.
- Aggregation: food forecast = sum over classes of share(t) times (combined
  SA forecast + seasonal factor). Two sub-aggregates reported for
  attribution only: I1-only and P-only.

## 3. Evaluation

- The 90 origins of `output/cz_struct_backtest.csv`, clocks A and B as in
  `cz_struct.main` (without `szif_mm` the two clocks carry identical food
  information and the results coincide; both are still tabulated).
- Food-block RMSE and MAE vs realised food m/m: all 90, ex-January, 2024+,
  2024+ ex-Jan, 2025+; headline effect through the origin's solved food
  weight; per-class RMSE of the combined forecast vs I1, I2, P and vs the
  naive same-month mean, for attribution.
- Harness check: the incumbent food block recomputed in the driver equals
  the backtest's `food_pred` to 1e-9.

## 4. Adoption rule (frozen now)

ADOPT the category aggregate as the food block only if, at clock B,
food-block RMSE improves by at least 5% on the full window AND on 2024+,
AND headline RMSE is not worse on either, AND at clock A the block is not
worse on either window. Otherwise record and close. No tuning of the
window (12 / 24), the minimum error count, alpha, the regressor set or the
class list after seeing results. A partial result (some classes better)
is recorded as a finding, not adopted piecemeal.

## RESULTS (7 September 2026, corrected run) -- RECORDED AND CLOSED

`szif_mm` absent (FOOD_SZIF_SPEC closed). Harness: incumbent equals the
backtest `food_pred` to 2.2e-16. Two defects found by Codex (R6) in the
first run were corrected before this run of record: (i) January origins
used the new basket's class weights although that basket is published
only with the January detailed release in mid-February -- the class
shares are now publication-gated per clock, exactly as the model's weight
solver; (ii) the pooled ridge removed class means from the target but not
from the predictors -- it now applies the within transformation to both.
Clocks A and B differ only through the January share gating and give the
same numbers to three decimals. The first run (uncorrected) had all-90
+1.9%, ex-January +7.7%, 2024+ +2.6%; the corrections move nothing that
matters.

### Food block, RMSE vs realised food m/m (all 90 origins forecast)

| split | incumbent | category (IW) | d | I1-only | P-only |
|---|---|---|---|---|---|
| all 90 | 0.913 | 0.928 | +1.6% | 1.131 | 0.921 |
| ex-January | 0.782 | 0.843 | +7.8% | 1.092 | 0.821 |
| 2024+ | 0.780 | 0.796 | +2.0% | 0.953 | 0.752 |
| 2024+ ex-Jan | 0.682 | 0.728 | +6.8% | 0.916 | 0.676 |
| 2025+ flash era | 0.567 | 0.606 | +6.8% | 0.749 | 0.578 |

### Headline, RMSE vs first release

| split | A STRUCT | A category | d | B STRUCT | B category | d |
|---|---|---|---|---|---|---|
| all 90 | 0.7307 | 0.7233 | -1.0% | 0.7292 | 0.7217 | -1.0% |
| ex-January | 0.4048 | 0.4121 | +1.8% | 0.4041 | 0.4114 | +1.8% |
| 2024+ | 0.2141 | 0.2293 | +7.1% | 0.2144 | 0.2298 | +7.2% |
| 2024+ ex-Jan | 0.1973 | 0.2117 | +7.3% | 0.1983 | 0.2128 | +7.3% |
| 2025+ flash era | 0.1659 | 0.1821 | +9.7% | 0.1650 | 0.1814 | +9.9% |

Big surprises (23): category 0.646 vs BASE_RIDGE 0.642, W-L 5-3 vs 6-3 (A)
and 5-3 vs 6-2 (B). The all-90 headline gain is a January artefact (the
class aggregate happens to sit closer in two of the seven Januaries);
every ex-January split is worse.

### Per class (90 origins): RMSE combined | I1 | I2 | P | naive same-month mean

| class | combined | I1 | I2 | P | naive |
|---|---|---|---|---|---|
| 0111 bread & cereals | 0.979 | 1.137 | 0.965 | 1.006 | 1.240 |
| 0112 meat | 1.410 | 1.653 | 1.403 | 1.378 | 1.597 |
| 0113 fish | 2.284 | 2.428 | 2.290 | 2.295 | 2.391 |
| 0114 milk, cheese, eggs | 1.400 | 1.684 | 1.350 | 1.429 | 1.658 |
| 0115 oils & fats | 2.800 | 2.951 | 2.760 | 2.880 | 2.952 |
| 0116 fruit | 3.003 | 3.154 | 3.006 | 2.979 | 3.110 |
| 0117 vegetables | 4.558 | 4.640 | 4.585 | 4.495 | 4.288 |
| 0118 sugar & sweets | 1.687 | 1.855 | 1.685 | 1.681 | 1.817 |
| 0119 other food | 1.357 | 1.504 | 1.345 | 1.377 | 1.463 |
| 012 non-alcoholic beverages | 1.580 | 1.658 | 1.615 | 1.611 | 1.558 |

Mean IW weights are close to equal (I1 0.30-0.34, I2 0.29-0.35, P
0.36-0.39): inverse-MSFE weighting over 24 errors does not separate the
candidates enough to exclude the weak rolling mean.

### Decision and findings

RECORD AND CLOSE under section 4: the combined aggregate is worse than the
incumbent on every window (ex-January +7.8%), and the headline is worse on
every ex-January split. Findings recorded, not acted on: (i) the pooled
ridge alone is roughly level with the incumbent (all 90 0.921 vs 0.913;
2024+ 0.752 vs 0.780; ex-Jan 0.821 vs 0.782) -- information sharing
across classes works, the individual candidates and their equal-ish
weighting are what hurt; (ii) vegetables (share 9-10% of food, standard
deviation 5.4 pp) is the one class where the naive same-month mean (4.29)
beats every model (4.49-4.64), and it is the class behind the block's
April/May/September/October errors -- a seasonal-treatment question for
a separately declared experiment, not a variant here; (iii) for the
remaining nine classes the class ridge or the pooled ridge beats the
naive mean, so the class-level information is not the problem, the
aggregation of noisy class forecasts is. The Chicago Fed result did not
transfer at this sample size (138 class-months, 90 evaluated origins). The
incumbent food block stays.
