# R14 food results, 9 September 2026

The prespecified domestic log-level pipeline does **not** improve the full
historical path. It has modest recent-origin gains, but severe 2022 extrapolation
failures. It is not suitable for promotion from this evidence. Neither the model
nor any parameter was altered after viewing its scores. The declared primary is
still FOOD_DOMESTIC_PIPELINE_R14; the own-level AR remains the matched control.

Annual headline RMSE, identical five-model common panel (percentage points):

| Sample | h | N | Bridge | Domestic pipeline | Own-level AR |
|---|---:|---:|---:|---:|---:|
| Full | 1 | 88 | 0.911 | 0.908 | 0.925 |
| Full | 3 | 84 | 1.537 | 1.614 | 1.595 |
| Full | 6 | 81 | 2.516 | 2.995 | 2.654 |
| Full | 12 | 75 | 5.395 | 8.177 | 5.992 |
| Targets since 2024 | 6 | 31 | 0.748 | 0.718 | 0.844 |
| Targets since 2024 | 12 | 31 | 1.892 | 2.696 | 2.848 |
| Origins since 2024 | 6 | 25 | 0.678 | 0.691 | 0.772 |
| Origins since 2024 | 12 | 19 | 1.347 | 1.274 | 1.412 |

The recent-origin h12 food cumulative-log RMSE also improves, from 4.572 to
4.222 log points. Thus this particular recent gain is not solely offsetting
another headline component. However, full h12 food cumulative-log RMSE rises
from 7.882 to 24.088; recent-target h12 rises from 6.419 to 10.220. Food point
monthly RMSE over the full h12 panel is 4.509 versus 1.205 for the bridge.

Paired circular 12-origin-block bootstrap (2,000 replicates, seed1409) for annual
MSE difference, pipeline minus bridge: full h12 +37.763, 95% interval
[+0.384,+105.874]; recent-origin h12 -0.192, interval [-0.510,+0.112]. Full h6
difference +2.635, interval [+0.029,+7.162]. These are exploratory retrospective
uncertainty diagnostics, and the small recent panel does not establish a gain.

At June 2022, all three sources are complete through May 2022 and the model has
77 complete training responses. Released annual growth was 31.96% for the fixed
farm proxy, 22.33% food PPI and 15.12% consumer food. The fitted companion radius
is 1.176071, and the conditional median model path forecasts cumulative food
growth of 295.11% over h1..12 versus 12.04% realised. May and July 2022 also have
very large upward extrapolations. This is a model weakness after observing the
cost surge, distinct from an unforeseeable geopolitical shock. The own-level
control also has mildly explosive fits (maximum radius1.046502). The declaration
explicitly prohibited post-score clipping or stabilization, so all remain saved.

Both new models fit all90 original origins. The minimum training sample is37
responses. Headline scoring excludes unavailable original nonfood paths and
unrealised targets; model fits were not silently replaced with the bridge. Own,
paired and common panels plus intended/finite counts remain in the CSV files.
All weights, nonfood contributions and supplied bridge h0 are exact; annual
fields on changed native rows are recomputed. All predictions were saved before
scoring outcomes. Source history is the latest stored vintage with reconstructed
release gates, not a historical statistical vintage archive or fresh holdout.

Verification: 15 new food tests plus15 R12 path tests passed before fits. The
offline replay refitted every one of90 origins and reproduced11 deterministic
payloads byte-for-byte, checking54 source/code/input hashes with network and
database access blocked. See verification_receipt.json and validation.json.

Read-only follow-up research finds official Czech food CPI levels from1995;
131 overlapping monthly changes reproduce this target within2.22e-16. The four
farm inputs extend to2010, while the stored food-PPI history begins2015. These
findings do not alter the R14 model. A separately declared R14B adaptation will
model monthly log changes around causal seasonal means and explicitly limit
dynamic roots. Its outcome-informed origin must remain visible.
