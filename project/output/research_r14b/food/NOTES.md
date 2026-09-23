# R14B stable food results, 9 September 2026

The stable monthly-change model removes the R14 level model's explosive
extrapolations. Full-sample headline accuracy is broadly unchanged from the
bridge, while recent 12-month paths improve. These are outcome-informed
exploratory results: R14B was designed after seeing R14 fail and is not a fresh
holdout. The predeclared primary remains FOOD_STABLE_PIPELINE_R14B; the own-food
control was not substituted after results.

Annual headline RMSE on the identical seven-model common panel, percentage points:

| Sample | h | N | Bridge | Stable domestic pipeline | Stable own-food AR |
|---|---:|---:|---:|---:|---:|
| Full | 1 | 88 | 0.911 | 0.910 | 0.921 |
| Full | 3 | 84 | 1.537 | 1.534 | 1.559 |
| Full | 6 | 81 | 2.516 | 2.509 | 2.516 |
| Full | 12 | 75 | 5.395 | 5.398 | 5.401 |
| Targets since 2024 | 1 | 31 | 0.365 | 0.356 | 0.359 |
| Targets since 2024 | 3 | 31 | 0.547 | 0.521 | 0.514 |
| Targets since 2024 | 6 | 31 | 0.748 | 0.729 | 0.748 |
| Targets since 2024 | 12 | 31 | 1.892 | 1.764 | 1.780 |
| Origins since 2024 | 1 | 30 | 0.371 | 0.361 | 0.364 |
| Origins since 2024 | 3 | 28 | 0.569 | 0.544 | 0.535 |
| Origins since 2024 | 6 | 25 | 0.678 | 0.674 | 0.663 |
| Origins since 2024 | 12 | 19 | 1.347 | 1.269 | 1.239 |

Food cumulative-log RMSE at h12, log points:

| Sample | N | Bridge | Stable domestic pipeline | Stable own-food AR |
|---|---:|---:|---:|---:|
| Full | 75 | 7.882 | 7.949 | 8.276 |
| Targets since 2024 | 31 | 6.419 | 5.623 | 5.920 |
| Origins since 2024 | 19 | 4.572 | 4.129 | 4.090 |

The recent gains also appear in food cumulative errors, not solely through
offsets against another headline component. The stable pipeline beats the
matched own-food control on full-sample food cumulative RMSE, but not in every
recent comparison. In particular, recent-origin h12 own-food AR has lower food
and headline RMSE than the pipeline. The data therefore do not show a general
advantage from adding the domestic cost chain. Full-sample food cumulative RMSE
remains slightly worse than the bridge, even though point monthly h3/h6 food
RMSE improves (1.100/1.166 versus1.112/1.200).

Paired annual-MSE difference, stable pipeline minus bridge, circular12-origin
block bootstrap with2,000 replicates and seed1410:

| Sample | h | Mean MSE difference | 95% interval |
|---|---:|---:|---:|
| Full | 3 | -0.009 | [-0.188, +0.169] |
| Full | 6 | -0.037 | [-0.374, +0.302] |
| Full | 12 | +0.031 | [-0.857, +1.062] |
| Targets since 2024 | 12 | -0.467 | [-0.861, -0.168] |
| Origins since 2024 | 12 | -0.205 | [-0.333, -0.078] |

These intervals describe the declared retrospective comparisons, not
selection-adjusted significance or proof of prospective gains. Recent-origin
h12 has only19 observations with overlapping annual paths. At that horizon,
the pipeline minus own-food AR MSE difference is+0.074, interval[+0.026,+0.121].
That weakness remains visible rather than choosing the lower-scoring control.

Both models fit all90 origins using42..96 complete monthly responses; each has
90 finite forecast paths at every horizon. Own h12 labels number78, versus75
on the seven-model common panel because the old bridge has additional missing
food predictions. All own/paired/common counts are retained. No new prediction
is an old-bridge fallback. Realised targets after the last observed month remain
missing. Publication gates require both endpoints of every rate; future rows
never enter model fitting, centering, scaling or conditioning.

No estimated model needed the declared root contraction: maximum unconstrained
radius is0.820660 for the pipeline and0.726570 for the own-food AR, across180
fits. Thus the improvement in plausibility comes from modeling centered monthly
changes, not active post-estimation clipping. At June2022 the stable pipeline
predicts10.735% cumulative food growth over h1..12, versus12.036% realised,
15.014% for the bridge and295.112% for the original R14 pipeline. The stable
own-food control predicts4.949%, illustrating useful cost information in that
particular episode without establishing superiority across all episodes.

The source history remains the same139 monthly levels from2015, with stored
latest vintages and reconstructed release gates. A separate official historical
food CPI audit covers1995-2025 and reproduces all131 overlapping monthly changes
within2.22e-16; no older observation was added to this model. Food PPI remains
the currently stored2015-start bottleneck. No futures, surveys, expectations,
retailer prices or additional fitted data enter either food model.

Verification: all15 R14B contract tests,15 original-food tests and15 R12 path
tests pass. The complete offline replay refitted all90 origins, checked60 input/
source/code hashes and reproduced11 deterministic output payloads byte-for-byte,
with network/database access blocked. Original R14 payloads were also checked
before reference reuse. Every nonfood contribution, weight and supplied h0 is
exactly preserved; native annual fields are recomputed. Details are in
verification_receipt.json, validation.json and the source/output manifest.

Scientific judgement: keep this as a plausible stable research candidate for
the predeclared combined-path and prospective evaluation. It solves a clear
economic failure and improves recent cumulative paths, but does not deliver
a broad historical RMSE gain or consistent evidence that costs beat food history.
