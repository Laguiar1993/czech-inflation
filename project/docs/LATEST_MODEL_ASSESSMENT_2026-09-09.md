# CZK Cpi Forecasting - Latest models

R11 assessment, 9 September 2026. This review closes the bounded category
remainder experiment and investigates the existing independent inflation path.
It does not replace any operating forecast or refit the path models.

## The decision: two nowcast families, four named forecasts

Keep **BASE as the main release nowcast** and **the simple category model as the
research accuracy challenger**. Retain HALF and FULL as the established error
correction comparisons. This is a decision about stability and evidence, not a
claim that BASE has the lowest historical error. The category model wins several
accuracy measures; FULL is stronger on the conditional large-surprise objective.

The names are easier to understand as two families:

- Aggregate-core family: BASE forecasts core as one block. FULL adds a correction
  learned from this model's own earlier forecast errors; HALF applies half that
  correction. HALF is exactly the midpoint of BASE and FULL. Both corrections
  remain independent of the current release consensus.
- Category-core family: TARGET_OWN separately forecasts actual rent, imputed
  rent, catering, accommodation and package holidays, plus the remaining
  core/tax/reconciliation contribution. Food, fuel, administered and alcohol
  blocks remain shared with BASE.

The research label TARGET_OWN_HALF means a separate 50/50 BASE/category blend.
It is **not** the established HALF correction. It stays in the experimental
tables; there is no reason to add it to the ordinary operating display now.

| Forecast | Role | Headline RMSE, all 90 | Headline MAE, all 90 | RMSE, 2024+ | MAE, 23 large surprises | Material wins / losses on large surprises |
|---|---|---:|---:|---:|---:|---:|
| BASE | Main forecast and stable reference | 0.4180 | 0.2625 | 0.2190 | 0.4846 | 7 / 3 |
| Categories | Research accuracy challenger | **0.4089** | **0.2565** | **0.1978** | 0.5120 | 8 / 2 |
| HALF | Conservative error-correction comparison | 0.4137 | 0.2644 | 0.2196 | 0.4794 | 7 / 1 |
| FULL | Surprise-capture challenger | 0.4139 | 0.2696 | 0.2253 | **0.4761** | **9 / 2** |
| Consensus | Scoring benchmark, never an input | 0.3815 | 0.2533 | 0.2410 | 0.5783 | — |

All errors are percentage points of monthly CPI inflation. First-release
outcomes and matching surveys are used: ordinary releases before 2025, flash
from January 2025. Large surprise means absolute print-minus-consensus >=0.4pp;
material means reducing/increasing absolute error by >=0.15pp. Recent N=31.

The category model's full-window RMSE advantage reverses if October 2022 is
omitted, and its paired full-window uncertainty interval crosses no improvement.
That is a reason to collect prospective evidence before promotion. It is not a
reason to discard its substantial core-forecast improvement. FULL improves the
large-event score but worsens overall MAE versus BASE. Neither objective should
be hidden by choosing whichever statistic flatters one forecast.

Conditional big-event results are not a rule for deciding in advance when to
trade. Across all releases, deviations >=0.2pp produce 20/21/22/23 alerts for
BASE/categories/HALF/FULL; only 7/9/7/7 coincide with >=0.4pp actual surprises.
An alert on a smaller surprise is not automatically a losing trade, but it must
remain in the evaluation. Do not select a different winning model after each
print, or use a distribution belonging to another model to size a position.

Today `forecast_independent.py` already produces BASE/HALF/FULL. The category
challenger is an offline research experiment and still needs integration into
the timestamped input archive and live output before prospective side-by-side
calls. No calibrated uncertainty or demonstrated rates-trading rule is claimed.

## What the new diagnostic tests establish

The approved hypothesis was that splitting core removed useful economic
information. We therefore kept all five category equations fixed and changed
only the remaining-core equation:

1. Restore the aggregate independent predictors, excluding expectations, ESI
   and the incorrectly named legacy services proxy. This restores aggregate
   core lags as well as FX, imports, state, interactions and calendar terms.
2. Retain the remainder's own lags and calendar, adding only FX/import/state
   terms. This is the existing channel experiment's remainder with the category
   equations returned to their simple form.

The specification was committed before producing these forecasts. Both received
the already-declared fixed half blend; no penalties or blend weights were searched.

| Diagnostic | All RMSE | All MAE | Recent RMSE | Big-event MAE | Big upward-surprise MAE |
|---|---:|---:|---:|---:|---:|
| Simple categories, unchanged | **0.4089** | **0.2565** | **0.1978** | 0.5120 | 0.5062 |
| Aggregate predictors in remainder | 0.4134 | 0.2613 | 0.2097 | 0.5093 | 0.4939 |
| Own remainder lags + macro predictors | 0.4141 | 0.2621 | 0.2038 | 0.5175 | 0.5102 |
| First diagnostic, half blend with BASE | 0.4131 | 0.2594 | 0.2121 | 0.4933 | 0.4461 |
| Second diagnostic, half blend with BASE | 0.4129 | 0.2599 | 0.2094 | 0.4957 | 0.4542 |

The first change recovers a little upward-surprise accuracy but loses ordinary
accuracy. The second does not improve large-event MAE. None warrants replacing
the simple category challenger or expanding the operating roster. This weakens
the hypothesis that restoring those particular variables alone solves the
problem; it does not prove that macro information or category models are useless.

Both diagnostic fits preserve all 900 saved category predictions exactly. All
90 macro-remainder forecasts match the corresponding old channel remainder.
The 90-origin own-category replay also matches. The new models use no survey
expectations or release consensus.

## The more important nowcast finding: errors in the other blocks

The independent audit rebuilt the weights at each actual release-eve timestamp,
then reproduced the frozen non-core contribution and headline error exactly.
Weighted component-error RMSE across all 90 releases is:

| Block | Error RMSE in headline percentage points |
|---|---:|
| Administered prices | 0.3473 |
| Food | 0.1619 |
| Alcohol/tobacco | 0.0803 |
| Measured fuel | 0.0072 |
| Reconciliation error, shown separately | 0.0836 |

These RMSEs cannot be added: the errors can reinforce or offset each other.
Administered prices remain the largest non-core error even excluding October 2022.

The existing administered forecast immediately uses a seasonal median outside
January. It consequently does not incorporate an October credit or a November
repricing into those target months through its January announcement mechanism.
October 2022's admin error alone contributes +2.4361pp to the headline miss;
September and November admin errors contribute -0.6480 and -0.7508pp. This is a
substantive model-coverage limitation, not evidence of a new arithmetic leak.

June 2020 and April 2024 expose alcohol/tobacco misses of -0.2704 and -0.1875pp
of headline. An expanding same-calendar-month mean does not incorporate current
excise or supplier repricing news. Those data establish the misses, not their
precise causal decomposition. Tax and component evidence must come first.

All cheap admin/fuel/alcohol/wedge forecasts reproduce across the 90 origins.
Food forecasts at the eight focus origins reproduce exactly through X-13, with
available origin predictors. There was no X-13 fallback explaining those misses.
The older contribution report mixes month-end weight selection with release-eve
predictions, but the weights are identical at the two clocks in this sample:
zero scored impact. The new audit uses the correct release-eve clock.

The next substantive nowcast development should be dated, all-month energy and
tax events, using the existing monetary ledger with evidenced exposure mapping.
Do not patch an October 2022 row with its realised CPI outcome, and do not assume
all consumers receive a supplier announcement immediately. Keep uncertain
reconstructed magnitudes as scenarios until justified and frozen prospectively.

## The independent path: what exists and what to improve

The path starting point is already the **independent component bridge**:
`BRIDGE_HARD` in the live research output, `INDEPENDENT_BRIDGE` in the backtest.
It uses BASE for h0, direct component forecasts beyond it, and exact compounding
to produce monthly YoY inflation and quarterly averages. It excludes forecast
expectations at every horizon. It is explicitly not production-certified.

The nowcast's month t is h0. Here h1 means month t+1; h12 means t+12. These path
scores concern annual inflation, so their numerical scale differs from the
monthly first-release nowcast scores above. At h12, h0 has left the annual
window: improving the next print alone cannot fix twelve-month-ahead YoY.

| YoY RMSE | h1 | h3 | h6 | h12 |
|---|---:|---:|---:|---:|
| Independent bridge, full common sample | 0.911 | 1.537 | 2.516 | 5.395 |
| Fixed forest, same sample | 0.975 | 1.772 | 2.817 | 5.602 |
| Seasonal naive, same sample | 1.040 | 2.123 | 3.633 | 6.572 |
| Bridge, targets from 2024 onward | 0.365 | 0.547 | 0.748 | 1.892 |
| Bridge, forecasts made from 2024 onward | 0.371 | 0.569 | 0.678 | 1.347 |

Full counts are 88/84/81/75. Recent-target N=31 at each displayed horizon;
recent-origin counts are 30/28/25/19. Overlapping paths are not independent trials.

The bridge beats the existing freshly estimated roster at every full-sample
horizon, but that does not establish superiority in every regime. A new no-fit
benchmark check holds the last released YoY number constant. At recent-origin
h12 it scores **1.175 versus the bridge's 1.347**, on the same 19 cases. It is
much worse over the full sample. Add this simple benchmark and both recent
definitions to evaluation rather than picking one favourable period.

The path remains competitive with CNB in some windows but weaker recently:
on matched recent report/quarter pairs, bridge RMSE is 0.590 versus CNB 0.372.
At four quarters ahead the corresponding numbers are 0.927 and 0.426 (only
seven pairs). The model forecast predates each report's publication; the CNB's
internal cutoff is not identical. CNB is a benchmark, not a target to copy.

**The first path improvement to test is food beyond three months.** The current
rule switches from X-13/direct regression at h1–3 to the last five observations
for the destination calendar month at h4–12. Exact annual-error accounting
assigns food +0.9105pp of mean h12 error for recent targets and +0.5760pp for
recent origins. These are accounting allocations, not automatically attainable
improvements. They support testing a forecast that separates a centered seasonal
pattern from an evolving food trend, with its window fixed before scoring.

**Second, test one category-core path challenger.** Extend the current category
definition to direct future-month forecasts while leaving other blocks fixed.
Check accumulated core errors and exact annual losses as well as each monthly
endpoint. Do not assume the nowcast result carries to h6 or h12; do not combine
this change with food, horizon pooling and new penalties in one experiment.

**Third, add dated administered-energy scenarios across all months.** This is
shared infrastructure for nowcast and path. It should distinguish known policy
start/expiry from unknown future shocks, and incorporate exposure and the
embedded seasonal baseline once. A 2021-origin forecast cannot know subsequent
war or policy announcements. An exposure range is preferable to an unsupported
precise point override.

Keep survey-conditioned and CNB paths as clearly separate comparisons. Better
seasonality, economic timing and error accounting should be tested before
restoring expectations simply to pull forecasts toward the bank's path.

## Verification, reproduction and scope

The new R11 experiment passed its independent correctness review. The selected
R9/R10/R11 regression suite passed **262 tests**, with two existing X-13 warnings.
R10 replay reproduced all 15 CSVs and gates exactly; R11 reproduced all 12 saved
outputs exactly with network and database access blocked. No old forecast series
was rewritten. The non-core error identity closes within 6.32e-16pp. The path
review reproduces 84 saved score rows within 8.89e-16 and its annual-error
allocation sums within 1e-10. No new path model was fitted in this review.

From the repository root, using the numerical environment in
`requirements-r9-lock.txt`:

```text
python core_remainder_experiment.py --verify
python core_split_experiment.py --verify
python tools/r11_review/noncore_audit.py
python tools/r11_review/noncore_food_replay.py
python tools/r11_review/path_review.py
```

The targeted food replay needs the existing Census X-13 binary configured via
`CZ_X13_PATH`; the remainder experiment and saved-path analysis do not.
Main R11 scores and audit metadata are in `output/core_remainder/`; supporting
non-core and path evidence is in `output/review_r11/`. Detailed reviews retain
the original audit provenance and limitations. Historical features remain partly
latest-vintage with reconstructed availability. Prospective archives and
calibrated forecast distributions remain necessary before claiming a dependable
trading edge.
