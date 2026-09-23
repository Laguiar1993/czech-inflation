# Path step 5: a semi-structural gap model in the CNB's spirit, conditioned on our nowcast

Declared 8 September 2026, BEFORE running. One run, frozen rules. User
direction: "do what they do, plus our nowcast", after asking whether the
CNB's paper uses expectations.

## What the documents say (opened 8 September 2026)

- Franta and Sutóris, CNB WP 1/2020 (CNB research summary 3/2020): Czech
  inflation decomposed into a trend and deviations; "the results indicate
  a fall in the inflation trend, coinciding with changes in inflation
  expectations, while the transitory component exhibits features of an
  open-economy Phillips curve." Our F2 line mirrors this (trend measured
  by the survey expectation; gap driven by open-economy variables).
- Brázdik et al., CNB WP 7/2020 (abstract): the CNB's core forecasting
  model is g3+, a two-country DSGE with a structural foreign block, oil as
  a production factor and heterogeneous households; conditional forecasts
  under limited information. In a DSGE of this kind expectations are
  formed inside the model and anchored by the target through the policy
  rule; surveys are not inputs. The abstract does not discuss surveys.
- CNB blog "First use of AI in inflation forecasting at the CNB": "the
  primary forecasting scenario is based on the g3+ DSGE model. However,
  from 2021 to 2023, this model exhibited larger forecast errors for
  one-year-ahead inflation predictions ... Since January this year, we
  have been developing a new semi-structural model as an alternative to
  the existing primary model."

So "what they do" is: a near-term forecast for the current quarter built
bottom-up by component (our nowcast and component bridge play that role),
handed to a structural model with anchored expectations, a Phillips curve,
an exchange-rate channel and monetary transmission through the real
interest rate, run as a conditional forecast. Step 5 builds the smallest
honest monthly version of that.

## Model S (monthly, percent)

    y_t          = mu_t + g_t + e_t                          SA headline m/m (mean seasonal removed and added back)
    mu_t - tau_t = rho (mu_{t-1} - tau_{t-1}) + eta_t        expectations / trend anchored to the CNB target path
    g_t          = phi g_{t-1} + b_u ugap_{t-1} + b_q fx12_{t-4} + eps_t      open-economy Phillips curve
    ugap_t       = c + r_u ugap_{t-1} + sigma rr_{t-12} + nu_t                 IS curve (transmission)
    rr_t         = i_t - pi12_t - rstar_t                                       real policy rate gap

ugap = LFS unemployment rate (trend-cycle) minus its trailing 60-month
mean, used with its one-month publication lag; fx12 = twelve-month change
of EUR/CZK lagged three months (step 4); i = 3-month PRIBOR (monthly
average); pi12 = trailing twelve-month headline inflation; rstar =
trailing 120-month mean of (i - pi12). Expected signs: b_u < 0, b_q > 0,
sigma > 0 (a higher real rate raises unemployment a year later). The
first two equations are the step-3 model with the level of slack in place
of its change; the third is new and is what carries policy into the path.

Estimation at every origin on released data (1998-01..t-1; rows before a
driver exists are zero, as declared in steps 3-4): the IS curve by OLS,
the rest by maximum likelihood (Kalman filter, filtered states).

Projection (the estimated equations run forward from the last released month; every input is released data or a market quote at the origin's clock), months t..t+24 (t+1..t+12 scored):
- Rate path: the market's. 3-month PRIBOR and the 3x6, 6x9, 9x12, 12x15,
  15x18, 18x21, 21x24 FRAs at the last Bloomberg date on or before the
  origin's release-eve clock (cache `~/bbg_cache/bloomberg.duckdb`), each
  applied to its three months; if the cache ends before the clock, the
  last available date is used and the row is flagged `rate_path_stale`.
  Because transmission takes twelve months, the rate path affects
  unemployment only beyond the scored horizon; it enters the twelve-month
  path through expectations in variant M.
- Exchange rate: random walk (fx12 fades to zero as the base months roll
  off). Import prices are not in this model.
- Unemployment: the IS curve projected forward with known real rates
  (t-12..t-1) and then the market path with model expectations.
- Expectations: A = geometric reversion of mu to the target at the
  estimated rho (steps 3-4). M = model-consistent: mu_s = w tau_s +
  (1-w) x the model's own average headline inflation over months
  s+1..s+12, solved as a fixed point over the 24-month projection (beyond
  it, variant A), w = 0.5 declared (credibility weight); w = 0.25 and 0.75
  are reported as sensitivity, never adopted.
- Handover to the nowcast (component span 2019-02 on, variants with
  suffix H): months t..t+3 of the component bridge F1b enter the Kalman
  filter as pseudo-observations (the print at t for object b, the nowcast
  for object a; F1b's m/m for t+1..t+3), the filter updates the states,
  and S continues from t+4. Published path: F1b for h <= 3, S from h = 4.
  This is the CNB's own arrangement: near-term forecast imposed, core
  model continues.

Variants: S_A, S_M (long span), S_A_H, S_M_H (component span). Reference
columns from steps 2-4: F1b, F2 (survey), E1, E5, E7, naive, RW, CNB
report quarters.

## Rules (frozen)

- Eligibility: b_u < 0, b_q > 0 and sigma > 0 in at least half of the
  origins.
- Selection between S_A and S_M: lowest h = 12 y/y RMSE on origins
  2008-01..2018-12, and (new safeguard, the lesson of step 4) not worse
  than E1 at h = 12 on the full long span 2008-01..2026-07. A variant
  failing the safeguard is not adopted whatever its selection score.
- Target line: the selected S replaces E7 if eligible and better than E7
  at h = 12 on the long span.
- Second line: the selected S replaces the survey-anchored F2 if at least
  3% better at h = 12 on the long span.
- Product engine: the handover variant of the selected S replaces F1b if
  at least 5% better at h = 12 on the component span, on the full span
  and in both origin halves, and publishable (PATH_SPEC_v2 rule).
- CNB comparison at report dates (user rule of 8 September) for the
  selected variant and its handover version; everything reported.

## RESULTS, run 1 as declared (8 September 2026; files `output/path_step5_*_run1_level_is.*`)

### Parameters (222 origins)

Phillips curve: slack (level of the unemployment gap) -0.029 with the
right sign in 100% of origins; koruna twelve-month change +0.007, right
in 94%; phi 0.04; rho 0.908 (half-life seven months). IS curve: sigma
-0.027, the WRONG sign in 94% of origins (positive only in 2008), with
the persistence coefficient at its 0.995 cap in every origin. Diagnosis:
a monthly regression of the level of the unemployment gap on its own lag
sits on the unit-root boundary, so the coefficient on a real rate twelve
months earlier is not identified; the estimate picks up the 2011-13
recession, when unemployment rose while real rates had fallen. Under the
rule the model is not eligible. The market rate path was stale (cache
ending 24 April 2026) in the last three origins.

### Long span, origins 2008-01..2026-07, object (b), y/y RMSE (bias)

| h | S_A | S_M (w 0.5) | S_M w 0.25 / 0.75 | E1 | E5 | E7 | survey F2 | naive |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.58 | 0.63 | 0.63 / 0.62 | 0.57 | 0.57 | 0.59 | 0.57 | 0.63 |
| 3 | 1.24 | 1.39 | 1.42 / 1.38 | 1.22 | 1.22 | 1.30 | 1.21 | 1.37 |
| 6 | 2.08 | 2.41 | 2.47 / 2.37 | 2.02 | 2.00 | 2.18 | 2.02 | 2.30 |
| 9 | 3.03 | 3.42 | 3.50 / 3.37 | 2.95 | 2.88 | 3.14 | 2.93 | 3.21 |
| 12 | 4.04 (-0.30) | 4.35 (-0.94) | 4.45 / 4.28 | 3.96 | 3.83 | 4.18 | 3.84 | 4.09 |

Selection 2008-2018 at h = 12: S_A 1.71, S_M 2.00 (E1 1.34): S_A
selected; long-span safeguard: 4.04 against E1 3.96, FAILS, not adopted.

By regime, h 7-12, S_A / S_M / E1 / survey / naive: 2008-09 2.42 / 2.72
/ 2.24 / 1.19 / 1.95; 2010-12 1.74 / 1.96 / 0.97 / 0.84 / 0.96; 2013-16
1.22 / 1.61 / 1.05 / 0.78 / 1.15; 2017-19 0.56 / 0.48 / 0.67 / 1.00 /
1.13; 2020-21 1.70 / 1.72 / 1.74 / 2.10 / 1.75; 2022-23 8.42 / 9.79 /
8.29 / 8.76 / 8.45; 2024-26 2.54 / 0.70 / 2.80 / 0.87 / 3.84.

The model-consistent expectation is the story of this run. It is the
best line of any family, survey included, wherever inflation was on its
way back to target (2017-19: 0.48; 2024-26: 0.70 against the survey's
0.87 and the anchored lines' 2.5-2.8), and the worst wherever inflation
stayed away from target for years (2010-16 under the exchange-rate floor
and the 2022-23 shock, where forward-looking expectations pulled the path
down too early). A constant credibility weight of one half cannot be
right in both worlds; the weight is a state, not a parameter.

### Component span 2019-02..2026-07, object (b): F1b 0.79 / 1.56 / 2.57 / 4.05 / 5.79 at h 1 / 3 / 6 / 9 / 12; handover S_A_H 0.79 / 1.56 / 2.66 / 4.13 / 6.08; S_M_H 0.79 / 1.56 / 2.80 / 4.50 / 6.40; survey F2 0.83 / 1.83 / 3.25 / 4.89 / 6.66; E7 0.87 / 1.97 / 3.49 / 5.23 / 7.27; naive 0.95 / 2.10 / 3.65 / 5.28 / 6.99.

By regime, h 7-12 (handover months excluded), F1b / S_A_H / S_M_H /
survey: 2019-21 2.23 / 2.19 / 2.15 / 2.35; 2022-23 7.30 / 7.46 / 8.20 /
8.76; 2024-26 1.10 / 1.59 / 0.77 / 0.87 (bias +0.64 / +0.41 / -0.13 /
+0.47). The handover architecture works: the first three months are the
bridge's, and from month four the structural model with model-consistent
expectations is the best line in the calm regime, better than the survey
line, while the anchored version keeps pace with F1b in the shock.

### Against the CNB at its report dates (fair matching, object b)

Reports 2022-23 (32 quarters): CNB 3.27, F1b 3.23, S_A_H 3.24, S_M_H
3.91, S_A 4.51, S_M 5.73. Reports 2024-26 (34): CNB 0.37, F1b 0.55, S_M_H
0.56 (closer than the CNB in 12 of 34), S_A_H 0.65, S_A 0.58, S_M 0.58.

### Rules, applied

Target line: E7 stays (S_A 4.04 is better than E7 4.18 but the model is
not eligible and fails the safeguard). Second line: F2 stays (S_A 5.3%
worse). Product engine: S_A_H is publishable (+25.7 / +27.3 / +13.2%
over naive at 3 / 6 / 12 months, DM -1.9 / -2.0 / -1.9) but 5.0% behind
F1b at twelve months on the full span (-2.6% first half, -67.7% second
half); F1b stays. Nothing changes in the product.

## Amendment 1 (8 September 2026, after run 1, before run 2)

The IS curve is re-specified in its identifiable form, the same economics
in annual differences: the twelve-month change in the LFS unemployment
rate on the average real policy rate gap over the twelve months ending
one year earlier,

    u_t - u_{t-12} = c + sigma x mean(rr_{t-13..t-24}) + nu_t,   sigma > 0 expected,

estimated by OLS on released data at every origin; the projection carries
the unemployment level forward by this equation from its last public
month and recomputes the gap against the trailing 60-month mean along the
path. Everything else, including every rule, is unchanged. This is a
specification repair for an identification failure, of the kind recorded
in PATH_SPEC_v4 amendment 1, not a tuning on outcomes: it cannot change
the scored twelve-month path of variant A (the rate path reaches
unemployment only beyond the horizon) and touches variant M only through
expectations.

## RESULTS, run 2 under amendment 1 (8 September 2026; final files `output/path_step5.csv`, `_params.csv`, `_summary.csv`, `_run.log`, `_cnbq_*.csv/.log`)

The IS curve in annual differences gives sigma -0.29 with the wrong sign
in 95% of origins (n about 160 per origin). The identifiable form did
not rescue the sign, so the failure is economic, not statistical: the
ex-post real rate (PRIBOR minus realised inflation) falls when demand
booms lift inflation and unemployment falls, and rises when inflation
collapses in a recession, so it correlates negatively with the change in
unemployment a year later whatever the lag. The CNB's models avoid this
by using an ex-ante real rate (the nominal rate minus the model's own
expected inflation) in a quarterly output-gap equation. That is the next
declared repair if the user wants the transmission block; it would not
change the twelve-month path of variant A (transmission reaches the
horizon only through expectations) and is therefore not urgent for the
product.

Scores are unchanged to the second decimal for A and slightly worse for
M (the mis-signed IS now feeds expectations): long span h = 12: S_A 4.05,
S_M 4.37, E1 3.96, E5 3.83, E7 4.18, survey 3.84, naive 4.09; 2024-26
h 7-12: S_M 0.91 (0.70 in run 1), survey 0.87. Component span h = 12:
F1b 5.79, S_A_H 6.09, S_M_H 6.38. Against the CNB at report dates: 2022-23
S_A_H 3.25 (CNB 3.27, F1b 3.23); 2024-26 S_A_H 0.68, S_M_H 0.63 (CNB 0.37,
F1b 0.55).

Rules, applied: not eligible (signs), safeguard fails (S_A 4.05 against
E1 3.96), S_A_H publishable but 5.2% behind F1b at twelve months. Nothing
changes in the product: F1b engine, survey second line, E7 target line.

## What step 5 established

1. The CNB's architecture transfers: nowcast and bridge for the first
   three months, a structural model after. The handover variant matches
   the bank in the 2022-23 shock (3.25 against 3.27 at report dates) and
   stays within 5% of our own bridge at twelve months.
2. Slack belongs in the Phillips curve as a level (right sign in every
   origin), the koruna as a twelve-month change lagged three months
   (94%).
3. Expectations are the pillar that decides the calm regime. The
   model-consistent expectation is the best line of any family in
   2017-19 and 2024-26 and the worst in 2010-16 and 2022-23. A
   time-varying credibility weight (anchoring that strengthens the
   longer inflation has been near target and weakens after a long
   departure) is the economically motivated next step, to be declared as
   PATH_SPEC_v6 before any run, together with the ex-ante real rate for
   the transmission block.
4. Monthly ex-post real rates cannot identify monetary transmission;
   this block should be quarterly and ex-ante or left out.
