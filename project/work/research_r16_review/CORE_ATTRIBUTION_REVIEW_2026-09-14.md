# R16 independent matched-sample core attribution receipt

The post-run attribution passes this bounded independent check. No shared code or original output was edited. The independent script imports neither the attribution module nor its evaluator helpers.

`audit_core_attribution.py` verifies all 19 attribution input/output hashes, independently constructs the original fifteen-model finite headline support, and rebuilds 2,907 FAST/.95-.001/.95-.010 rows across h1–h12. The h12 support is exactly the original 75 origins for all three models. It uses raw native component contributions, the original core actuals, and frozen headline monthly history. Products of monthly gross factors provide a separate arithmetic route from the implementation's sums of logs.

For h1 onward, the oracle combines the sum of retained noncore contributions with `weight_core * observed_core_mm`. The original h0 and known pre-origin headline history are preserved. The annual window includes h0 at h1–h11 and excludes it at h12; every exported window flag agrees. No future headline actual is substituted into the oracle forecast. No missing intermediate month is filled or dropped from the original support.

Maximum row-level difference from the production export is 2.00e−13 annual-log percentage points. The independently rebuilt retained remainder is exactly identical across the three models. The maximum h12 mean-square identity residual is 1.42e−14.

On the identical 75 h12 observations, the exact decomposition is:

| Model | Total headline-log MSE | Weighted core-effect MSE | Common retained MSE | Twice uncentered cross moment |
|---|---:|---:|---:|---:|
| FAST | 19.809119 | 5.581139 | 9.631210 | 4.596770 |
| .95 / .001 | 19.342990 | 6.631634 | 9.631210 | 3.080147 |
| .95 / .010 | 16.822084 | 7.784620 | 9.631210 | −0.593746 |

Each row satisfies `E(total²) = E(core_effect²) + E(retained²) + 2E(core_effect*retained)`. Units are squared **annual-log headline percentage points**, not ordinary headline y/y percentage-point MSE. The weighted core effect is the exact headline-log difference induced by the oracle replacement; it is distinct from unweighted cumulative-core error.

Relative to FAST, .95/.001 increases weighted core-effect MSE by 1.050495, outweighed by a −1.516623 cross-term change. Its cross term remains positive: the errors reinforce each other less. The .95/.010 variant increases weighted core-effect MSE by 2.203481, outweighed by a −5.190516 cross-term change; its aggregate cross term becomes negative. Retained MSE is common. These arithmetic comparisons support error compensation as the source of the aggregate gain, rather than improved own-core accuracy; they do not identify causal mechanisms.

The same-date unweighted cumulative-core RMSE is 4.278485 for FAST, 4.658800 for .95/.001, and 5.037961 for .95/.010. These figures use the same 75 headline dates, removing the larger 78-date core-score sample as an explanation.

The cross term is explicitly **uncentered**. Twice the product of component biases is nonzero (−0.022142, −0.149795 and −0.010894 respectively), so substituting centered covariance would break the stated MSE identity.

Evidence: `attribution/audit_summary.json`, `attribution/h12_independent_rows.csv` and `attribution/h12_independent_scoreboard.csv`. Reproduce with:

```powershell
$env:PYTHONPATH='../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r16_review/audit_core_attribution.py
```

This is a hindsight accounting diagnostic. Observed future core is unavailable at forecast time. Nothing here is a new usable forecast, a tuning target, or a reason to revise the frozen parameter choices.
