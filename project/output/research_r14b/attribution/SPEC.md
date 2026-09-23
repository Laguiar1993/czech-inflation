# Evaluation-only path component attribution

Declared before reading the new R14B stable-combination errors. No fits,
forecast changes, configuration choice or new observation download occurs.

Models: original INDEPENDENT_BRIDGE and STABLE_PIPELINE_R14B,
STABLE_LOCAL_CORE_R14B, STABLE_LONG_CORE_R14B, STABLE_LONG_GAP_R14B. Use all 90
saved origins and horizons 1..12, retaining unavailable predictions/outcomes.
The original baseline is loaded independently; integration supplies only its
declared stable models with identical origin/horizon keys and saved weights.

Actual component concepts come exclusively from the verified cleanup fixture:
CNB core and regulated m/m; CZSO COICOP01 food,0722 fuel and02 alcohol/tobacco.
Use each saved forecast's component weight (alcohol uses weight_alc). These
are model projection weights frozen at the origin, not realized expenditure
weights. Leave the forecast reconciliation wedge unchanged; do not manufacture
a realized wedge or claim the component basket exactly explains headline CPI.

For each block and h, retain destination-month error and weight times that
error. Over future h1..h report sum of component log-change errors in 100 log
points, and sum of monthly weighted arithmetic errors in CPI percentage points.
Any missing intermediate input makes the corresponding cumulative diagnostic
missing; no partial summation. These quantities are not headline annual errors.

Separately create a single-block future oracle: replace that block's h1..h
contributions by saved weights times actual block m/m; retain h0, all other
forecasts and the wedge. Recompound the exact twelve-month headline window,
using actual history only before origin. For actual future headline use the
same frozen headline series. Define e=forecast annual-actual annual,
b=forecast annual-oracle annual, o=oracle annual-actual annual. Check e=b+o
and e²=b²+o²+2bo. Report oracle MSE gain e²-o²=b²+2bo. Its sign can be negative
when errors offset. Single-block effects are conditional on the other forecast
blocks; do not add them across blocks or describe them as causal shares.

Report full, recent-target2024+ and recent-origin2024+ summaries at every
horizon, highlighting6/12. Coverage scopes: each model/block's own finite
observations, joint finite observations for all five blocks within model, and
joint finite observations for all five blocks/all five models. Separate masks
for each diagnostic; retain counts, RMSE,MAE,bias and exact MSE decomposition.
Save every row, coverage table, and the complete h6/h12 event table rather
than only selected examples. No uncertainty or causal claims from ranks alone.

Implementation/tests are path_attribution_r14.py and test_path_attribution_r14.py.
Inputs and deterministic outputs are hashed. Offline --verify recomputes the
diagnostics into a temporary folder and requires output hashes to match.
--baseline-only permits development against the old bridge in a separate
baseline_only subfolder; final default execution requires all four new models.
