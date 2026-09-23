# R12 food and cumulative-path results

9 September 2026. **Retain the existing independent bridge.** None of the four
prespecified variants earns replacement status. They remain recorded research
experiments; no operating formula, baseline data or baseline output changed.

The specification was committed as `abd1342` before fits. FOOD_TREND_R12 replaces
only food h4–12 with a released-data EWMA trend and centred calendar effects.
FOOD_COST_R12 adds the fixed, lagged agricultural/PPI correction. The two separate
headline models have identical features, priors and ridge strength; only their
monthly versus cumulative future log-change labels differ. All use HARD_BASE h0.
See `docs/implementation/R12_PATH_SPEC.md` for every fixed numerical choice.

## Results on the same h12 annual-inflation panel

RMSE, percentage points. Full sample: origins February 2019–July 2026 with an
observed target and complete common forecasts. Recent targets are destinations
from January 2024; recent origins are forecasts made from January 2024. They are
different samples and are not interchangeable.

| Model | Full, N=75 | Recent targets, N=31 | Recent origins, N=19 |
|---|---:|---:|---:|
| Existing independent bridge | 5.3948 | 1.8921 | 1.3473 |
| FOOD_TREND_R12 | 5.6913 | 2.3423 | 1.3132 |
| FOOD_COST_R12 | 5.7148 | 2.3536 | 1.3203 |
| DIRECT_MONTHLY_R12 | 6.5884 | 5.8000 | 1.2523 |
| DIRECT_CUMULATIVE_R12 | 6.5633 | 5.7329 | 1.2539 |
| Existing forest | 5.6016 | 3.4137 | 1.6141 |
| Existing direct Minnesota/BVAR | 6.2234 | 4.0422 | 1.6044 |
| Existing seasonal naive | 6.5719 | 4.6476 | 4.7053 |
| Fixed last-released YoY | 6.9693 | 6.2224 | **1.1747** |

The last-released YoY reference has its own implied h0, rather than HARD_BASE.
Its recursively implied monthly path preserves the fixed annual rate exactly.
Including it in the common roster does not reduce coverage at any horizon.

**Food:** trend and cost variants worsen full-sample annual RMSE at every changed
horizon h4–12. On recent targets they improve h5, h7 and h8 slightly, but worsen
h9–12. On recent origins, trend improves h5 and h8–12; cost improves h8–12.
The food trend reduces recent-origin h12 headline bias from +0.7300 to +0.1129 pp,
but its monthly h12 endpoint RMSE rises from 0.2975 to 0.3044. Bias reduction alone
does not establish a better path. Adding cost pressure improves none of the full
sample h4–12 annual comparisons versus the trend-only specification.

**Cumulative target:** changing labels produces only a small improvement over the
matched monthly model on full/recent-target h12 annual RMSE and a small loss on
recent origins. Both are materially worse than the bridge over the full history.
At recent-origin h12, cumulative future-log RMSE is 1.2178 for the cumulative
model versus 1.2163 for the monthly control. Their h1 forecasts are identical.
This bounded specification provides no convincing benefit from changing targets.

All four recent-origin h12 paired annual MSE confidence intervals include zero.
For food trend, the difference versus bridge is -0.0907 pp², 95% interval
[-0.6135, +0.4296]; cumulative is -0.2429, [-0.8730, +0.3479]. Full-sample food
trend MSE deteriorates by +3.2872, interval [+0.2818, +7.4354]. These are the
prespecified circular 12-origin block bootstrap, 2,000 draws, seed 1209, not
independent observations or an untouched holdout.

## Publication-aligned CNB comparison

The inherited matcher selects the last generated path strictly before the report
publication day, then averages three monthly annual rates. Future observations
never replace forecasts. This is public-availability alignment, not equality of
internal information cutoffs. All report-quarter rows are retained, including
incomplete and not-yet-observed quarters; common scoring requires complete data.

Full common RMSE, 66 report-quarter pairs / 18 distinct quarters: CNB 2.2955,
bridge 2.3624, food trend 2.5250, food cost 2.5476, direct monthly 3.5643 and direct
cumulative 3.5622. For reports from 2024, 34 pairs / 10 distinct quarters: CNB
0.3718, bridge 0.5904, food trend 0.7018, food cost 0.7090, direct monthly 0.5522
and direct cumulative 0.5587. The small recent direct-model advantage over bridge
does not erase its full-history losses or beat the bank on this panel.

## Integrity and limitations

All 90 origin schedules and all 13 path points per model are retained: 10,530
rows over nine models. `summary.csv` contains h1–12 RMSE/MAE/bias, intended and
available counts, own coverage, a shared roster and paired bridge panels, with
separate monthly endpoints, future cumulative logs and exact annual targets.
`paired_uncertainty.csv` retains every declared variant and horizon.

The baseline replay checks 1,170 points and all original source fingerprints.
Every unchanged nonfood contribution and old long-food prediction matches
exactly; maximum monthly difference is 2.22e-16 and annual difference 5.33e-15.
The 270 unchanged X13 h1–3 values are reused only after code/data hash checks;
all other baseline regressions and weights are recomputed. Original monthly and
annual targets agree within 1.78e-15 before the original stored values are used
for scoring. Existing early missing paths and difficult years remain included
in the coverage accounting.

Agriculture's recovered source-month series matches 196 cached raw observations
exactly; food PPI matches 137. Agriculture is a mean of available-product log
price changes; PPI is an arithmetic percentage change. The cost model uses
24–113 complete training rows, while direct models use 300–400. All newly fitted
variants have zero fallbacks. Historical and current source publication clocks
are both enforced, and every training label ends at or before released t-1.
Unknown publication times fail closed. All seasonal sums are numerically zero.

The final regression suite has 78 passing new/relevant existing tests, with two
existing X13 warnings. Review caught a constant-column scaling edge case; the
regression test fails before the fix and passes afterward. Correcting it changes
zero empirical forecast rows (maximum difference zero). Reconstructed publication
dates use calendar arithmetic before timezone localization, with spring/autumn
daylight-saving boundary tests; the conservative r-2 source cap protects the
historical inputs. A separate CSV type normalization in the offline verifier
changes no forecast or score.

These inputs mostly contain latest stored statistical values with reconstructed
publication timing. This is repeatedly inspected pseudo-out-of-sample history,
not new untouched evidence. No surveys, expectations or retailer collection enter
the new models. R11's food attribution remains a useful diagnosis; R12 shows
that this particular local-trend replacement does not recover it reliably.

## Reproduction

From the repository root, with the existing scientific Python dependencies:

```text
python -m pytest test_path_improvements_r12.py test_independent_bridge_r9.py test_path_math_r9.py test_path_inputs_r9.py -q -p no:cacheprovider
python path_improvements_experiment_r12.py --output-dir output/research_r12/path
python path_improvements_experiment_r12.py --output-dir output/research_r12/path --verify
```

To preserve an existing run, choose a child directory such as
`output/research_r12/path/replay`. The runner needs no network or database. It
reuses frozen X13 values and therefore does not need to refit X13; some inherited
tests still exercise the installed X13 executable. The manifest records source,
model and payload hashes. Open operational logs are deliberately excluded from
payload hashes. Offline verification independently recomputes target arithmetic,
scores, bootstrap and CNB summaries, and checks the source/payload hashes.
