# Predeclared experiment: seasonal treatment of the core block (X-13 vs month dummies) and an Easter dummy

Declared 7 September 2026, BEFORE running. One run, two clocks, frozen rules.

## Question

The core block handles seasonality with eleven calendar-month dummies
inside the expanding ridge: a fixed seasonal pattern. The food block uses
per-origin one-sided X-13 (adopted in v1.1 after it cut food error by a
quarter). Is core better served by X-13 as well, and does a moving-holiday
(Easter) term add anything? Evidence gathered before this declaration
(item indices, no forecast run): airfares show a clear Easter effect
(March +10 with a March Easter vs +1 otherwise) but weigh 0.18% of the
basket; package holidays (2.2%) follow fixed catalogue seasons with no
Easter effect; accommodation none. Expected Easter contribution to the
headline: 0.02-0.04 pp in March/April. Expected X-13 effect: unknown, the
honest reason for the test.

## Incumbent

`_ridge_predict(feats, core, t, as_of)`: expanding ridge (alpha 3, minimum
48 rows, labels released at the clock) on the core frame including
`mon_2..mon_12`, the state dummy and its interactions. Reproduced by the
driver to 1e-9 against `core_pred` in `output/cz_struct_backtest.csv`
(harness check; stop otherwise).

## Challenger S (X-13 core)

Per origin t and clock: history = core m/m released at the clock through
t-1 (`_released_index`, exactly as `food_forecast`); X-13 via
`x13_arima_analysis` with the same settings as the food block (automatic
model, outlier detection on, no calendar regressors); SA series = seasadj;
seasonal factor for t = mean of the last three same-month fitted factors;
ridge on the core frame WITHOUT the month dummies with the SA series as
target (alpha 3, minimum 48, same eligibility); forecast = ridge + factor.
Content-keyed cache as in v2.5. If X-13 fails at an origin the incumbent
value is used and the origin is counted as a fallback (reported; more than
5 fallbacks of 90 voids the comparison).

## Easter term E (tested on both treatments)

One extra ridge feature `easter_m` = 1 in the calendar month containing
Easter Sunday (Gregorian computus), 0 otherwise, on the full frame index.
Four cells are run: incumbent, incumbent+E, S, S+E. No other variant, no
alternative Easter definitions (Good Friday, Easter Monday, the eight-day
X-13 window) are run.

## Evaluation

The 90 first-release origins, clocks A (month-end) and B (first-release eve)
as in `cz_struct.main`; the core inputs are complete-month objects so the
two clocks are expected to coincide, both are still computed. Core-block
RMSE and MAE vs realised core m/m on all 90, ex-January, 2024+, 2024+
ex-Jan, 2025+; headline effect through the origin's solved core weight,
`STRUCT + w_core * (cell - incumbent)`, RMSE vs first release on the same
splits, plus big-surprise MAE and W-L at 0.15 for information. March and
April core errors by Easter regime for all four cells. Only BASE_RIDGE is
recombined; the warm past-error challenger is not re-derived here.

## Adoption rules (frozen)

- S replaces the month dummies only if, at clock B, the core-block RMSE
  improves by at least 5% on all 90 AND on 2024+, headline RMSE is not
  worse on either, AND clock A is not worse on either window.
- E is added (to whichever seasonal treatment stands after the first rule)
  only if it lowers the March+April core RMSE by at least 10% AND does not
  raise the overall core RMSE on all 90 or 2024+ at either clock.
- Anything less: recorded and closed. No parameter search.

## RESULTS (7 September 2026, single run) -- RECORDED AND CLOSED

Harness: incumbent equals the backtest `core_pred` to 4.4e-16. X-13
succeeded at all 90 origins (0 fallbacks). Clocks A and B coincide for S
(max difference 0.0), as expected for complete-month core inputs.

### Core block, RMSE vs realised core m/m (clock B; A identical)

| split | month dummies (inc) | inc + Easter | X-13 (S) | S + Easter |
|---|---|---|---|---|
| all 90 | 0.308 | 0.308 | 0.309 | 0.310 |
| ex-January | 0.306 | 0.305 | 0.311 | 0.311 |
| 2024+ | 0.182 | 0.181 | 0.193 | 0.194 |
| 2024+ ex-Jan | 0.184 | 0.183 | 0.192 | 0.192 |
| 2025+ flash era | 0.140 | 0.141 | 0.149 | 0.149 |
| March + April (16) | 0.265 | 0.265 | 0.226 | 0.225 |

### Headline, RMSE vs first release (clock B; core weight recombination)

| split | inc | inc + E | S | S + E | survey |
|---|---|---|---|---|---|
| all 90 | 0.7292 | 0.7293 | 0.7172 | 0.7172 | 0.3815 |
| ex-January | 0.4041 | 0.4046 | 0.3962 | 0.3968 | 0.3801 |
| 2024+ | 0.2144 | 0.2160 | 0.2148 | 0.2151 | 0.2410 |
| 2024+ ex-Jan | 0.1983 | 0.2002 | 0.2103 | 0.2107 | 0.2315 |
| 2025+ flash era | 0.1650 | 0.1662 | 0.1787 | 0.1792 | 0.1947 |

Big surprises (23): inc MAE 0.642, W-L 6-2; S 0.615, W-L 8-2.

### Decision

- **S fails the first rule**: the core block is not 5% better anywhere; it
  is level on all 90 and 6% worse on 2024+ and the flash era. Month
  dummies stay. Finding for the record, not acted on: S lowers the
  all-90 and ex-January HEADLINE error (-1.7%, -2.0%) and the big-surprise
  MAE (0.615 vs 0.642) because the one-sided X-13 absorbs the 2022-2023
  level shifts differently, while losing accuracy in every calm recent
  window. Under the doctrine that overall recent accuracy is central,
  that trade is not taken; it is logged as a possible surprise-capture
  challenger if the roster is ever reopened for one.
- **E fails the second rule** on both treatments: March+April core RMSE
  unchanged (0.265 vs 0.265 on the incumbent), overall unchanged. The
  item-level Easter effect is real for airfares but too small in the
  basket to reach the core aggregate. No Easter term.
- No variant, no parameter search. Roster unchanged.
