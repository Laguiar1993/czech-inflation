# R23 review and proposed next steps — Claude to Codex

17 September 2026. Reviewed: `HANDOFF_TO_CLAUDE_R23_2026-09-16.md`, the R23 results, specification, independent review, code, tests and `output/research_r23/final`. Nothing in the existing tree was edited. This file and `work/research_r23_claude_review/` (three read-only probes) are the only additions.

## Verdict

**The delivery is executed correctly and reproduces exactly. The decision not to promote anything is right. The diagnosis of why R23 found nothing needs to change.** R23 did not really test the cost channels it names:

- The imported-cost coefficients sat on their zero bound in 82–98% of fits, so that channel never operated.
- The labour-cost input is not seasonally adjusted, and 44% of the `ulc_gap` feature's variance is a fixed quarter-of-year pattern.
- What remained active was a penalized intercept. Because labels mature 13–15 months late, the correction it applied has a correlation of −0.58 with the correction FAST actually needed.

Separately, a block attribution of the path errors shows that core is now the smallest error source in the regime we are in. Food is the largest.

## What I verified

| Check | Result |
|---|---|
| 25 targeted tests (R23, R22, R21) | 25 passed |
| Three review probes (`probes.py`, `output_checks.py`, `evaluation_checks.py`) | all pass; 206 manifest hashes, 7,084 lead rows, 176 summary rows, 1,360 episode rows |
| Delivery manifests R18–R23 (1,479 file hashes) | 0 mismatches, 0 missing |
| Full replay of `tools.research_r23.run` and `evaluate` into a directory outside the repo | 54 of 55 files byte-identical to `final`; the one difference is `evaluation/input_manifest.json`, which stores absolute input paths (same digests, same outputs) |
| Pre-declaration | The specification (07:21) predates the first run (07:28). Its hash, the model code and the runner are identical in the `full`, `verified` and `final` manifests. Only `data/cost_gaps_r23.py` changed (the provenance fixes). Features, fits and forecasts are byte-identical across the three runs |
| Accuracy table in the results document | all 66 RMSE cells and the 84/81/75 and 28/25/19 counts recomputed from `primary_rows.csv`; exact match |
| CNB lead table | every count matches at both clocks, both thresholds, and the 2024+ cut |
| Matched CNB pairs | joint 1.9949 against CNB 2.2955 (RMSE, 66 pairs), MAE 1.2875 against 1.0605; 2024+: 0.4927 against 0.3718; all match |
| Training sets | rebuilt independently for all 90 origins (latest 40 eligible quarter-ends, fully matured, published by the clock); all match |
| Bootstrap, leave-one-year-out, strict core-turn test | as reported |

I found no look-ahead. Features are masked before transformation, labels and inner folds are fully matured at their own clocks, and scalers use training rows only.

## Findings

### 1. The ULC input is not seasonally adjusted, and the gap construction keeps the seasonal (high)

`LCTQCZI Index` is "Index NSA" in the frozen Bloomberg metadata (`data/market_snapshots/20260911_bloomberg_full_refresh/raw/nominal_ulc_quarterly_bdp.csv`). The A6 audit and the R15 specification both say so, and R15 and R22 avoided the problem by using annual growth. R23 instead takes the log level against the median of the previous twelve quarters. The median is seasonally neutral; the current quarter is not.

| Reference quarter | Mean `ulc_gap` (R23) | Same-quarter variant |
|---|---:|---:|
| Q1 | +4.50 | +1.87 |
| Q2 | +0.45 | +1.85 |
| Q3 | −2.58 | +1.63 |
| Q4 | +2.92 | +1.68 |

Quarter-of-year alone explains 43.8% of the feature's variance. For a variant that compares each quarter with the same quarter of the three previous years, it explains 0.1%. The live readings show the artefact directly: −2.61 at the December 2025 origin, +4.93 at March 2026, +7.77 at June 2026.

This matters because ULC is the only cost feature that did anything. From January 2024, the ULC term is essentially all of the joint candidate's departure from FAST (ratio of absolute contributions 1.04). 73.6% of that term's variance is explained by the reference quarter: +0.17 when the latest quarter is Q1, −0.16 when it is Q3. In the recent sample, joint minus FAST is mostly a seasonal sawtooth.

### 2. The sign restrictions switched the imported channel off (high)

| Feature | On the zero bound, joint | Negative in the unrestricted ridge |
|---|---:|---:|
| `import_gap` | 97.5% | 99.2% |
| `ppi_gap` | 83.6% | 73.6% |
| `fx_news` | 82.2% | 83.1% |
| `tightening` | 63.3% | 74.4% |
| `ulc_gap` | 31.1% | 41.9% |

Shares are of the 360 origin-and-band cells. The "Imported gaps" candidate is in effect a second intercept-only calibration: its mean absolute 12-month contribution is 0.287 from the intercept and 0.011 from the three features together.

The unrestricted sign is informative, not noise. `import_gap` is negative in at least 94% of cells in every origin year from 2019 to 2026. A level gap is a late-cycle measure. By the time import prices stand high relative to core prices, FAST's adaptive trend already carries the pass-through, and core then decelerates faster than FAST expects. Exploratory in-sample correlations with the R23 targets point the same way (about 60 overlapping quarterly rows, one cycle, so descriptive only):

| Measure | Correlation with 12-month FAST error |
|---|---:|
| Twelve-month import and PPI inflation | −0.38 |
| Core's own twelve-month momentum | −0.54 (−0.68 for origins from 2020) |
| PPI acceleration (six-month momentum less the previous six months) | +0.40 |
| PPI minus core six-month momentum, against the h1–3 band only | +0.38 |

The results document says "removing sign restrictions hurts". The more useful statement is that the declared sign prior was rejected by the training data at almost every origin.

### 3. The corrections were a delayed echo (high)

Mean absolute 12-month log-core contribution in the joint candidate: intercept 0.245, `ulc_gap` 0.129, everything else at most 0.014. With a 13–15 month label delay the intercept switches on a year after it was needed:

| Origins | Correction FAST needed | Joint applied | Calibration applied |
|---|---:|---:|---:|
| 2019-02 to 2020-12 | +0.90 | +0.20 | +0.23 |
| 2021-01 to 2022-04 | +4.85 | +0.09 | +0.22 |
| 2022-05 to 2023-08 | −5.78 | +0.58 | +0.48 |
| 2023-09 to 2025-07 | −0.26 | −0.01 | +0.17 |

"Needed" is realised minus FAST, cumulative 12-month log core. Across the 78 matured origins the correlation between needed and applied is −0.58 for joint and −0.60 for calibration. With an inflation cycle of two to three years, a signal delayed by more than a year is close to anti-phase. Band-specific maturity (your question 2) helps h1–3. It cannot help h7–12, where the delay is structural. I would stop learning long-horizon corrections from matured errors altogether.

### 4. The third joint success is not robust (medium)

August 2024 report, target 2025 Q2: FAST's revision-distance gain is 0.1209 (fails the 0.15 bar) and joint's is 0.2272 (passes). Joint differs from FAST by +0.053pp. About two thirds of that comes from the ULC term, read at +3.40 for reference quarter 2024 Q1, the seasonal peak. The same-quarter definition gives +1.90 and a four-quarter-average definition gives −0.71. The handoff already treats this case cautiously; it should not be counted as evidence for R23.

### 5. The lead test's calls are mostly a structural gap, not news (medium)

FAST minus CNB rises with horizon in every year. In 2023 the mean gap is −0.76 one quarter ahead, −0.21 two ahead, +0.69 three ahead and +1.61 four ahead. At four quarters ahead the gap is positive in 100% of rounds in 2022, 2023 and 2025. Seventeen of the 21 first calls are upward (15 of the 19 matured ones). The model mean-reverts more slowly than CNB's, so a 0.30pp level threshold three to four quarters ahead fires in one direction for years.

For reports from 2023, the correlation between the gap and CNB's eventual error is −0.32 (n=23), with a 30% sign hit rate. The correlation with the next CNB revision is −0.06. I also tried removing the trailing same-horizon mean from the gap. It does not help (−0.53 against CNB's error), so I do not recommend that fix.

The 19 matured episodes come from 13 reports: losses from 9, gains from 3.

### 6. Smaller points

- **Bootstrap, recent sample.** With 19 observations, 12-month blocks and truncation to 19, the latest five origins are almost never resampled. For three candidates the point estimate lies outside its own 95% interval (joint: mean +0.0228, interval −0.0488 to +0.0183, "probability of improvement" 0.84 for a candidate that is worse). Use a circular or stationary bootstrap, or print no interval at n=19.
- **Support.** The core figures quoted in the results (4.1963 against 4.3554) use 78 origins, while the headline table uses 75. On the 75-origin support they are 4.2785 and 4.4400. The conclusion is unchanged.
- **Clocks.** At the cutoff clock CNB has one more CPI print than our snapshot in all 19 rounds (our snapshot is a median 16 days older). At the report clock that happens in 5 rounds, including both success rounds. A post-release snapshot would make the cutoff comparison fair.
- **Process.** The whole round ran in about 30 minutes, and the independent review checked code against the specification, not the specification against the data. Three cheap gates would have caught findings 1–3 before scoring: variance explained by period-of-year for each feature; share of fits with a binding constraint; correlation of needed against applied correction.
- **Operational.** 280 uncommitted paths carry eight days of work. The user decides on commits; I recommend a checkpoint before any R24.

## Where the path error actually is

RMS of the cumulative weighted block error over h1–h12, in percentage points of headline, FAST path (`call_attribution.py`, section 1):

| Sample | Core | Food | Fuel | Administered | Alcohol, tobacco |
|---|---:|---:|---:|---:|---:|
| Full (78 origins) | 2.33 | 1.41 | 0.59 | 1.98 | 0.27 |
| Origins from 2024 (19) | 0.32 | **0.73** | 0.44 | 0.32 | 0.11 |
| Bias, origins from 2024 | −0.02 | **+0.40** | 0.00 | +0.26 | +0.08 |

R21, R22 and R23 all worked on core. In the current regime core is the smallest of the four large blocks (0.25 for current core).

**Food.** The 12-month food forecast has no skill against a zero-change forecast: RMSE 7.84 against 8.83 on the full sample, and 4.13 against 3.69 from 2024. The correlation between forecast and outcome is −0.14 on the full sample and −0.57 from 2024. The model kept projecting +4.4 to +5.2% a year through 2025 while food prices fell 1–3%. The bias grows about +0.19 a month with horizon, the signature of a drift estimated on a window that contains 2022. At h3 it does have skill (2.20 against 2.82).

**Administered.** The baseline is a constant +1.4 to +1.7% a year. From 2024 a zero-change forecast beats it, 1.15 against 1.85.

**Gentle slope.** Its recent h12 advantage is error cancellation: a core bias of −0.54 offsets food at +0.40 and administered at +0.26.

**The 13 FAST lead-test losses, by block.** Mean contribution in the direction of the miss: core 0.76, food 0.48, h0 nowcast 0.48. For the three 2025 losses: food 0.71, administered 0.35, core 0.12. The May 2025 call on 2026 Q1 (2.95 against CNB's 2.30, outcome 1.62) was a food and administered-price miss. No core correction could have fixed it.

## Answers to the six handoff questions

1. **Information mapping.** The proxies are weak, but the transformation is the larger problem: level gaps are late-cycle. Any measurement system must first pass the three gates above. Do not build a services and goods measurement layer until a block attribution shows core is the binding error again.
2. **Faster learning.** Worth doing for h1–6 only. For h7–12 the delay is structural (finding 3). Long-horizon adjustments should come from contemporaneous state information with parameters estimated outside this sample.
3. **Wages against productivity.** Low priority. One Czech cycle cannot identify two channels where it failed to identify one.
4. **Why disagreements fail.** Answered above: a structural persistence gap against CNB in 2023 (core), then food and administered prices in 2025, plus the h0 nowcast error. `call_attribution.py` gives the per-call table.
5. **Alert test.** Keep it, and add three things. First, naive rows (constant 2%, random-walk annual rate, previous CNB forecast) so the base rate is visible. Second, report-level clustering. Third, a block label on every call. De-meaning the gap does not rescue it. Start the prospective ledger before the next CNB forecast round.
6. **Nowcast measurement.** Agreed. The January 2027 energy repricing is the next real test.

## Proposed order of work

1. **Checkpoint the tree** (the user's decision), then **start the prospective ledger** before the Autumn 2026 CNB forecast round (date to be taken from cnb.cz). Freeze BASE, HALF, FULL and Category Raw before each release; freeze the three paths monthly; write one ledger row per target quarter before each CNB round, recording the named driver, the threshold and abstentions. This is the only evidence that twelve rounds on the same 90 origins cannot contaminate.
2. **Make block attribution and block benchmarks standard output** of every path round: each block against zero-change and seasonal-naive at h3, h6 and h12, full sample and from 2024. Decide what to model from that table.
3. **Noncore path round, food first.** Candidates to declare before fitting:
   - a robust long-run drift for h7–12, in place of the recent-window mean;
   - for h1–6, upstream three-to-six-month momentum and the retail-to-upstream spread gap (in-sample signs are right at h3 and h6: −0.43 and −0.33 for the spread gap, about +0.5 for three-month upstream momentum; nothing predicts h12);
   - futures-curve conditioning as a labelled scenario, not the baseline.

   Then administered prices: split regulated energy (regulator decisions known in late November) from the rest, and test the constant baseline against zero drift. State the full-against-recent trade-off up front. A lower drift would have hurt 2022 origins.
4. **A separate conditioned lane: a CNB revision tracker.** Start from CNB's published assumptions (EUR/CZK, 3M PRIBOR, Brent, euro-area prices) and the CPI prints since its cutoff. Map deviations to an expected revision per target quarter. It uses CNB forecasts, so it stays outside the independent forecast. A defensible call is then one where the independent disagreement and the tracker agree in sign. This is where anticipating CNB revisions is most achievable. The independent path alone has shown no such ability since 2023.
5. **Core persistence from outside the sample.** State-dependent persistence (persistent while upstream pressure builds, mean-reverting once it rolls over) cannot be validated on one Czech cycle. Estimate it on an EU or CEE panel (HICP core, producer and import prices, ULC, by country), or take it from published pass-through estimates, and impose it as a fixed prior. That makes 2019–2026 a genuine out-of-sample test, and it serves the portability goal. If adaptivity is wanted sooner, weight the three existing filters by one-step predictive likelihood. That learns from h1 innovations, which mature in a month, not from h12 bands.
6. **Optional R23b**, only to close the lane cleanly: same-quarter ULC, no intercept, report the unrestricted sign share as a specification test instead of bounding, and corrections for h1–6 only. I expect no promotion.

Items 1, 2 and the evaluation fixes involve no modelling and can start now.

## Reproduce my checks

PowerShell, from the repository root:

```powershell
$env:PYTHONPATH='../pythonlibs'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython work/research_r23_claude_review/feature_checks.py
& $cpiPython work/research_r23_claude_review/correction_audit.py
& $cpiPython work/research_r23_claude_review/call_attribution.py            # default FAST; pass another model id as the argument
```

All three write nothing. `feature_checks.py` first asserts that it rebuilds the delivered `ulc_gap`, `import_gap` and `ppi_gap` exactly. Its part B and the food, gap and correlation figures above are exploratory in-sample description on a sample already studied many times. They motivate hypotheses; they are not evidence of forecast skill and must not select a model.
