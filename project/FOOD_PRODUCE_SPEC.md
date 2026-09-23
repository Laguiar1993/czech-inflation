# Predeclared experiment: produce split inside the food block

Declared 7 September 2026, BEFORE running. One run, frozen rule. Follows
the finding of `FOOD_CATEGORY_SPEC.md` that vegetables (0117) is the one
class where the naive same-month mean beat every model (4.29 against
4.49-4.64), and that the food block's worst months are April, May,
September and October, the produce months.

## Design

- Split division 01 into PRODUCE = fruit (0116) + vegetables (0117) and
  the REST (0111-0115, 0118, 0119, 012). Class levels from `cpi_long`
  (2015-01 on), Laspeyres price-updated shares from the basket files with
  the January publication gate, as in `data/food_categories.py`.
- REST index: the share-weighted aggregate of the eight non-produce
  classes' m/m, chained from 2015-01; forecast with the incumbent's exact
  recipe (per-origin one-sided X-13, ridge on the food frame features
  `food_l1, food_l12, agri_l0, agri_l1, food_ppi_l1` where the own lags
  are the REST series' lags, seasonal factor added back).
- PRODUCE: for each of the two classes the expanding same-month mean of
  released history (minimum three observations, else the class's expanding
  mean), aggregated by their shares within produce.
- Food forecast = (1 - s_produce) x REST forecast + s_produce x PRODUCE
  forecast, with s_produce the price-updated produce share of the food
  division at the origin.
- Clocks A and B as in `cz_struct.main` (food inputs coincide; both run).

## Evaluation and rule

Harness: the incumbent recomputed equals the backtest `food_pred` to 1e-9.
Block RMSE and MAE vs realised food m/m on all 90, ex-January, 2024+,
2024+ ex-Jan, 2025+, and the produce-month subset (Apr, May, Sep, Oct);
headline effect through the origin's solved food weight. ADOPT only if,
at clock B, the food block RMSE improves by at least 5% on all 90 AND on
2024+, headline not worse on either, and clock A not worse. Otherwise
record and close. No alternative class groupings, windows or models.

## RESULTS (7 September 2026, single run; log `output/food_produce_run.log`) -- RECORDED AND CLOSED

Harness: incumbent equals the backtest `food_pred` to 2.2e-16. Produce
share of the food division averages 0.159. Clocks A and B coincide.

| split | n | incumbent | produce split | d | headline inc (B) | headline split | d |
|---|---|---|---|---|---|---|---|
| all 90 | 90 | 0.913 | 0.902 | −1.2% | 0.4068 | 0.4073 | +0.1% |
| ex-January | 83 | 0.782 | 0.782 | +0.1% | 0.4041 | 0.4040 | 0.0% |
| 2024+ | 31 | 0.780 | 0.777 | −0.4% | 0.2166 | 0.2357 | +8.8% |
| 2024+ ex-Jan | 28 | 0.682 | 0.720 | +5.5% | 0.1983 | 0.2134 | +7.7% |
| 2025+ flash era | 19 | 0.567 | 0.573 | +1.0% | 0.1697 | 0.1783 | +5.1% |
| produce months (Apr, May, Sep, Oct) | 30 | 1.031 | 0.988 | −4.2% | 0.5824 | 0.5809 | −0.3% |

Decision: fails the rule (no 5% gain anywhere; 2024+ ex-January and the
flash era worse; headline worse on the recent windows). The split helps
where it was aimed, the produce months, by 4%, and costs more elsewhere,
because the REST series' own X-13 and ridge lose the smoothing the full
division gave them and the produce mean carries its own noise into every
month. Closed. Together with FOOD_SZIF, FOOD_CATEGORY and the state-space
challenger this is the fourth food experiment to close today; the food
block is at the ceiling of the information it has.
