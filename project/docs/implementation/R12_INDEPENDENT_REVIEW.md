# Independent R12 review — 9 September 2026

Scope: specification first, then forecast timing, units, numerical implementation,
baseline replay, saved arithmetic, scoring samples and artifact integrity. The
reviewer did not edit estimator/runner code, rerun runners into saved output
directories, change frozen baselines, or select variants from their results.
Implementation fixes were sent to their owners. This is a research correctness
review, not an operating-model promotion decision.

## Category pooling

No actionable correctness or specification finding remains in the reviewed
pooling implementation.

- Raw category/core histories are publication-masked before feature creation.
  The current and future target months cannot enter targets, own lags, common
  core lags, imputation, or standardisation. The common finite-label calendar
  and immediately previous published target requirement are applied jointly.
- The remainder is reconstructed using fixed origin weights and divided by the
  positive residual weight before target standardisation. Predictions are
  returned to rate units and weighted back to headline contributions correctly.
- The separate control uses the same features and training rows as the pooled
  variants. Dynamic common coefficients have penalty 3, equation deviations
  12/48, and equation-specific seasonal slopes 3. The intercept is recovered
  through equation-specific centring. No fitted selection enters forecasts.
- TARGET_OWN is replayed before scoring, references and the noncore contribution
  are frozen, and forecasts are saved before the evaluation survey is parsed.
  R10/R11 assessment/attribution helpers are reused unchanged.

Independent evidence:

- Pooling plus R10/R11 scoring tests: **46 passed**.
- All **65 input and 14 output hashes** matched the saved pooling manifest.
- All **90 TARGET_OWN replay differences are exactly zero**.
- Largest historical target identity error: **1.1102e-16**.
- Largest saved forecast/contribution recombination error: **5.5511e-16**.
- All **1,620 fit records** share their origin's training calendar; training
  sample sizes are **48–137**, with no entirely missing predictor columns.
- An independent solution profiled out the common slopes and solved the
  resulting 90-slope penalised least-squares problem using an augmented SVD
  solve. Across penalties 12 and 48, forecasts matched within **1.8874e-15**
  and dynamic coefficients within **8.0491e-16**.
- Scoring counts: all 90; recent 31; flash 19; ex-January 83; large events 23,
  comprising 13 upward and 10 downward surprises. Signed capture is correctly
  `(forecast - consensus) / (actual - consensus)` on large events; saved
  values matched independent calculation within **5.5511e-16**.

Interpretation: POOL_12 headline RMSE is 0.406533 versus TARGET_OWN 0.408947,
but the separate control already reaches 0.407212. The marginal RMSE gain from
sharing is therefore only 0.000679 percentage points. Recent RMSE worsens from
0.197798 for TARGET_OWN and 0.197405 for the separate control to 0.198264.
Large-event MAE improves from 0.511988 to 0.497043 but remains above FULL's
0.476061. Against TARGET_OWN, the mean headline squared-error gain of 0.001968
is decomposed into a **negative weighted-core gain of -0.000218** and a
**positive cross-term gain of 0.002187**. The modest headline improvement is
associated with favorable core/noncore error offsets, not a cleaner core signal.

## Food and cumulative paths

Two actionable findings were reproduced and sent to the path implementer:

1. **P2 — numeric constant columns produced false regression signals.**
   `ridge_zero_prior` replaced exactly zero SDs but missed floating-point
   constants. With 60 or 137 rows of a predictor equal to 0.3, a residual target
   equal to 1, and current predictor 0.3, the helper returned a correction of
   **0.5** because its computed SD was **5.5511e-17**. The specification requires
   scale one for constants. The owner added explicit constant detection and
   two regression tests; the reviewed fix sets constant SD to one.
2. **P2 — the manifest hashed an actively changing stdout log.**
   The runner initially hashed every file in its output directory before its
   final summary print, including the redirected `run.log`. The saved log hash
   immediately disagreed with its manifest. The owner now hashes an explicit
   list of stable CSV/JSON deliverables, excluding operational logs. Runtime
  dependencies controlling historical clocks, fixtures, and validation were
  also added to the source fingerprints after review.

The path implementer subsequently identified and fixed a publication timestamp issue:
adding elapsed days after localising month start can shift the reconstructed
calendar day by one hour across daylight-saving transitions. The agreed fix is
calendar-day arithmetic before localisation, for both cost source series, with
exact-boundary tests. The r-2 source cap puts these publications weeks before the
actual forecast cutoffs, protecting the historical predictor choices. The reviewer
independently ran the final regression covering autumn-2015 and spring-2018 local
midnight, rejection one second before release, and admission exactly at release:
**one targeted test passed**. The final stable-source rerun includes this fix.

The model specification and forecast timing otherwise agree:

- Historical trend/seasonal states use only observations through r-1. Seasonal
  estimation is causal at each pseudo-origin and effects are equal-weight
  centred. Cost regressors use the exact three source months r-4 through r-2,
  with both historical and current availability checks.
- Direct monthly/cumulative fits use the same predictor states and eligibility
  `r+h <= t-1`. The cumulative target deliberately excludes r; HARD_BASE is
  supplied at h0. Cumulative differencing reconstructs monthly rates, and the
  h12 annual window uses h1 through h12 without realised future observations.
- The runner checks actual CPI publication availability before passing history
  to the models and checks the prior CPI edge at historical pseudo-origins.
  Food replacement is restricted to h4–12; h0–3 and nonfood legs are preserved.
- Scoring distinguishes recent target months from recent origin months and
  retains the hard years, horizon-specific common samples, paired panels and
  circular block uncertainty. The separately identified last-YoY benchmark
  uses its own h0; including it in the displayed roster does not alter any
  common horizon sample in these data.

Independent checks of saved path data:

- Corrected path plus new/R9 energy tests: **85 passed**.
- All 90 released history edges end at t-1. All **2,160** direct-horizon
  diagnostic records satisfy `last_training_origin+h == last_training_target
  <= t-1`. Maximum seasonal-effect sum magnitude is **6.1062e-16**.
- There are no model fallbacks in the reviewed 90-origin diagnostics.
- Independent product-based annual compounding agrees with **10,431 finite
  annual forecast rows** within **1.3101e-13**; finite masks also agree. The
  last-YoY benchmark is flat across horizons within **1.3323e-15**.
- Baseline validation records 1,170 points; maximum monthly replay error
  2.2204e-16, unchanged component contributions and long-food values, annual
  replay difference 5.3291e-15, and exact matched-model h1 equality.

The final stable-source path run completed at **2026-09-09 11:48:18 UTC**. The
reviewer independently confirmed all **40 source and 8 payload hashes**, with no
amendment to the executed-source fingerprint. The final native monthly forecasts
are unchanged from the prereview snapshot (**maximum difference 0; changed rows
0**), so the numerical and timestamp fixes do not change this sample's findings.
All **684 score rows**, **144 paired-bootstrap rows** and **220 CNB comparison
score rows** replayed within **1e-12**. The CSV representation of the mixed
`all`/integer quarter grouping was normalised to text for comparison. There are
**10,530 unique origin/horizon/model forecast rows** covering all **90 origins**.
No actionable path finding remains.

## Energy/admin evidence

No actionable correctness or specification finding remains in the reviewed
energy wrapper/integration/scorer.

- Explicit known evidence is required for bills, complete exposure, relevant
  policy source/methodology, weights and embedded baseline. Future/unavailable
  events and inputs cannot produce a usable point contribution. Partial
  exposure produces an unavailable point, with no artificial renormalisation.
- The unchanged monetary engine aggregates fixed-quantity expenditure levels,
  handles credit expiry separately from continuing waivers, and subtracts the
  embedded contribution. Incremental mode compares with/without-policy bills
  on identical exposure and weights without double subtracting the seasonal
  baseline. The integration preserves January as prespecified.
- Candidate effect is null when unevidenced; the applied adjustment is then
  zero and BASE is retained. These are correctly distinguished. Source audit
  text treats current extracts and conservative confirmation dates as evidence
  limitations, and no realised source-document inflation magnitude enters the
  new candidate forecasts.

Independent final artifact evidence:

- All **39 source and 13 output hashes** match the final energy manifest.
- All **90** administered/core-weight replay deltas are exactly zero.
- All 90 strict forecasts equal BASE, with **zero eligible additions** and
  **null candidate effects**. The **1,350** origin-event records preserve the
  evidence gaps and clocks.
- The **60-row** scenario replay is byte-identical to the frozen R9 file.
- Every paired strict-minus-BASE delta and interval endpoint is exactly zero.
- Independently recalculated all-frame RMSE/MAE, direction denominators,
  direction successes and alert counts match the saved release/scoring rows.
- The parent subsequently identified a portability issue in unconditional Git
  metadata collection. The reviewed fix skips Git for extracted snapshots,
  explicitly scopes checkout metadata to the local `.git`, and treats missing,
  failed or timed-out Git as optional metadata. **Five additional targeted
  portability tests passed** independently. All energy hashes were rechecked
  after that change; the forecast hash remained
  `2481430ed75c9950a7f1f5bd78256a0beb575796938f0b1ff4aaa88941fd9ce2`.

The unchanged strict forecast is a documented evidence limitation, not a test
showing zero economic effect or a validated improvement. All experiments retain
the stated latest-vintage/reconstructed-clock and repeatedly inspected-history
limitations.

## Report consistency and closure

The reviewer also checked `R12_RESULTS_2026-09-09.md` and
`RESEARCH_R12_START_HERE.md`. The headline/core attribution, large-event metrics,
recent-target versus recent-origin distinction, bootstrap statements, and 2023
origin bias comparison agree with saved evidence. The nowcast table's material
win/loss heading was clarified to identify the large-event frame. No scientific
interpretation blocker remains. A parent's larger integration test suite and
portable extracted-package checks are separate from the independent checks
recorded above.

Review closed with no unresolved actionable correctness/specification finding.
Operating promotion remains unsupported for the reasons stated in the results
report; passing integrity and timing checks is not evidence of forecast superiority.
