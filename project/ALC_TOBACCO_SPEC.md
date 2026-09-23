# Predeclared experiment: alcohol-and-tobacco block, recent-window seasonal mean and sub-index split

Declared 7 September 2026, BEFORE running. One run, two clocks, frozen rules.

## Why this block

Attribution on the v2.5 baseline: the alcohol-and-tobacco block carries
18% of the headline squared-error variance 2024+ ex-January, second after
food, with the crudest forecast in the model (an expanding same-month mean
of the division-02 m/m). Diagnostics gathered before this declaration
(sub-index history only, no forecast run):

- Alcohol (021): the January jump, the reversal of December promotions,
  has grown from +5.5% (2016) to +8.9-10.7% (2023-2026); December and
  February mirror it (-2 to -4%). The expanding mean lags a trending
  season: the block under-forecasts January by 1.10 pp on average over
  the 90 origins, about -0.10 pp of headline.
- Tobacco (023): the excise pass-through lands in February to April
  (+1 to +2.5% a month) in every year since 2020; the consolidation
  package legislates steps of +10% (2024) and +5% a year (2025-2027) for
  cigarettes and tobacco, +5% a year for spirits, so the pattern is known
  to continue through 2027. Pre-2020 years had irregular steps, which the
  expanding mean averages in.
- Block RMSE 2024+: 0.846 (MAE 0.703); worst months April, January, May,
  June -- promotion timing around Easter and May, plus January.

## Incumbent

`alc_forecast`: mean of all released same-calendar-month observations of
the division-02 m/m through t-1 (minimum three, else the overall mean).
Reproduced by the driver to 1e-9 against `alc_pred` in the backtest.

## Challengers (both declared now, no others)

- **W5**: same structure, but the mean of the LAST FIVE released
  same-month observations (minimum three; fewer than three falls back to
  the incumbent's rule). Five years: long enough to average promotion
  noise, short enough to follow the rising January reversal and the
  post-2020 excise regime. No other window is run.
- **W5-split**: alcohol (021) and tobacco (023) each forecast by their own
  five-year same-month mean (same minimum rule; a sub-index with fewer
  than three observations uses the W5 block value), aggregated with
  Laspeyres price-updated basket shares of the two sub-indices within
  division 02 (basket files, regime = even start year, publication-gated:
  a January origin uses the previous basket, as the weight solver does).

Dependence stated: W5 presumes the legislated annual excise steps continue
through 2027; a year without a step (2028 onward, or a change in the law)
requires an explicit step calendar before the window rule is trusted.

## Evaluation

The 90 first-release origins at clocks A and B as in `cz_struct.main` (the
inputs are released CPI values, so the clocks are expected to coincide;
both computed). Block RMSE and MAE vs the realised division-02 m/m on all
90, ex-January, 2024+, 2024+ ex-Jan, 2025+, plus January-only and
February-to-April subsets as declared diagnostics. Headline effect
`STRUCT + w_alc(t) * (cell - incumbent)` with the origin's solved
alcohol-tobacco weight, scored against the first release, plus
big-surprise MAE and W-L at 0.15 for information.

## Adoption rule (frozen)

Adopt W5 if, at clock B, block RMSE improves by at least 5% on all 90 AND
on 2024+, headline RMSE is not worse on either, and clock A is not worse
on either window. If W5-split also passes, it replaces W5 only if it
beats W5 by a further 5% on both windows; otherwise the simpler W5 stands.
Anything less: recorded and closed. If adopted, the change is implemented
in `alc_forecast` with the same rule, tested, and the full backtest is
rerun as a new tagged version with the standard gates.

## RESULTS (7 September 2026, single run) -- RECORDED AND CLOSED

Harness: incumbent equals the backtest `alc_pred` to 4.4e-16; clocks A and
B coincide for both challengers (0.0), as expected for released-CPI inputs.

### Block, RMSE (MAE) vs realised division-02 m/m (clock B; A identical)

| split | n | incumbent | W5 | W5-split |
|---|---|---|---|---|
| all 90 | 90 | 0.919 (0.712) | 0.928 (0.705) | 0.928 (0.707) |
| ex-January | 83 | 0.886 (0.680) | 0.921 (0.697) | 0.919 (0.695) |
| 2024+ | 31 | 0.846 (0.703) | 0.882 (0.696) | 0.882 (0.692) |
| 2024+ ex-Jan | 28 | 0.791 (0.647) | 0.896 (0.698) | 0.893 (0.692) |
| 2025+ flash era | 19 | 0.789 (0.682) | 0.746 (0.646) | 0.750 (0.646) |
| January only | 7 | 1.247 (1.096) | 1.005 (0.798) | 1.027 (0.851) |
| Feb-Apr only | 24 | 1.078 (0.901) | 1.140 (0.951) | 1.137 (0.942) |

January bias (forecast minus actual): incumbent -1.10, W5 -0.80, W5-split
-0.85. Headline RMSE (B): all 90 0.7292 / 0.7270 / 0.7278; 2024+ 0.2144 /
0.2142 / 0.2143; 2024+ ex-Jan 0.1983 / 0.2027 / 0.2029; flash era 0.1650 /
0.1624 / 0.1626. Big-surprise MAE 0.642 / 0.646 / 0.648.

### Decision

Neither challenger passes: block RMSE is 1% worse on all 90 and 4% worse
on 2024+ for both. RECORD AND CLOSE. The result is informative rather than
null: the five-year window does what the diagnosis predicted for January
(error down a fifth, bias down a third) and for the flash era, and pays
for it in February-April and the promotion-driven spring months, where
five observations are too few and the expanding mean's stability wins.
The split adds nothing over the block window: the sub-index shares are
stable and the two sub-indices' errors are dominated by the same
promotion timing.

Not run, recorded as the natural follow-up if this block is reopened: a
January-only recent window (the trending December-promotion reversal is
the one systematic error; the rest of the year keeps the expanding mean).
That is a different, narrower spec and would need its own declaration.
The excise calendar was not needed as an explicit input for 2020-2027
because every year in the window carries a step; it becomes necessary the
first year without one.
