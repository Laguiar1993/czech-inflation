# R13 core path results, 9 September 2026

The six prespecified series provide no basis for promotion over the independent
component bridge. There is a narrower positive result: explicit category monthly
equations improve some core measures and the h3 path relative to their aggregate
control. The desired persistent h6-h12 improvement is not established. None of
these results says that realised war/oil surprises alone make a model economically
weak; exact headline error attribution is handled separately in the parent report.

## Experiment and coverage

Declaration commit: a74a536f70050968ec594f40400cfa0842e94749. Main factorial:
aggregate/category split crossed with monthly/average cumulative arithmetic core
targets. Fixed mean-loss ridge penalty 1, intercept, expanding complete training
rows, minimum 48, own lags 1/2/12 and destination calendar dummies. Main exogenous
variables are lagged import-price m/m (source r-3) and EUR/CZK m/m (source r-1).
Separate aggregate cumulative unemployment diagnostic has an exactly matched
training-history control. No wages, expectations, surveys, food/energy changes,
post-result parameters or candidate blends.

All 90 origins remain in output. Main fits begin March 2020 at h1, May 2020 at
h3, August 2020 at h6, and February 2021 at h12. With realised outcomes the full
main common panels contain 72 h3, 66 h6, and 54 h12 observations. Thus “full” is
the shared available panel, not all 90 origins and not the old bridge's own panel.
The original bridge's own full h12 RMSE is 5.395 on 75 observations; its correct
R13-main-comparison h12 RMSE is 6.175 on 54. Never compare these as a model change.

Unemployment is available at pseudo-origins only from February 2018 (the archive
release first becomes usable at that origin's March release-eve). Requiring 48
complete past rows delays labour forecasts to March 2022 h1 and February 2023
h12. Both labour series share these gaps; labour never restricts the main panel.
They have 30 scored full h12 observations and 19 recent-origin h12 observations.
All candidate fit failures are insufficient-history cases; no fallback was used.

## Headline annual-inflation error, percentage points

All columns below use the same observations within each panel/horizon.

| Model | Full h3 N72 | Full h6 N66 | Full h12 N54 | Recent-target h12 N31 | Recent-origin h12 N19 |
|---|---:|---:|---:|---:|---:|
| Bridge | 1.638 | 2.767 | 6.175 | 1.892 | 1.347 |
| Aggregate monthly | 1.771 | 3.117 | 6.498 | 2.057 | 1.853 |
| Aggregate cumulative | 1.769 | 3.209 | 6.823 | 2.099 | 1.929 |
| Category monthly | 1.685 | 3.080 | 6.494 | 2.043 | 1.909 |
| Category cumulative | 1.696 | 3.180 | 6.861 | 2.065 | 2.004 |

The category monthly h3 recent-target RMSE is 0.501 versus bridge 0.547, and
recent-origin RMSE is 0.524 versus 0.569. The paired uncertainty against the
bridge still crosses zero improvement. Against its matched aggregate control,
category monthly lowers full h3 annual MSE by 0.296 pp-squared (95% circular
12-month-block interval -0.600 to -0.042), with similar direction in recent panels.
This is limited evidence about that comparison, not a new untouched holdout.

At h12 the cumulative target worsens the matched monthly model: full annual MSE
differences are +4.336 (aggregate, interval +0.340 to +10.242) and +4.903 (split,
+0.322 to +12.212). In recent origins all four main candidates have larger annual
errors than bridge. Their h12 biases are +1.764, +1.850, +1.830 and +1.931 pp,
against bridge +0.730 pp; all 19 candidate errors are positive. Repeated historical
inspection, overlapping targets, few recent origins and unadjusted multiple
comparisons limit inferential force despite block intervals excluding zero.

## Core signal and persistence

These are core rates/sums in core units, not annual headline marginal effects.

| Core metric | Bridge | Aggregate monthly | Category monthly |
|---|---:|---:|---:|
| Full h12 endpoint m/m RMSE, N54 | 0.620 | 0.505 | 0.461 |
| Full h12 cumulative arithmetic RMSE, N54 | 6.190 | 5.104 | 5.044 |
| Recent-origin h12 endpoint m/m RMSE, N19 | 0.218 | 0.226 | 0.208 |
| Recent-origin h12 cumulative arithmetic RMSE, N19 | 1.546 | 1.686 | 1.801 |

Better endpoint estimates do not ensure a better persistent path. Category
monthly's recent-origin cumulative core bias is +1.732 points, versus bridge
-0.274. The cumulative-target variants increase this recent cumulative bias and
generally worsen its RMSE. The full-sample core improvement alongside worse
headline performance deserves an exact weighted annual attribution before any
claim about favourable or unfavourable component error offsets. Arithmetic core
error alone is not that attribution.

The labour addition worsens its matched-history aggregate cumulative control:
recent-origin h12 headline RMSE 3.023 versus 2.396 (bridge 1.347); full common
labour h12 RMSE 2.994 versus 2.503 (bridge 1.740). Full paired labour-minus-control
annual MSE is +2.699, interval +1.671 to +3.696. This does not rule out other
labour measures or transformations; it rejects promotion of this fixed rate-level
addition on the available historical archive.

## Arithmetic target approximation and exact final accounting

Cumulative targets sum arithmetic monthly rates, preserving the exact linear
category-plus-remainder identity at each origin's fixed basket. They are not
cumulative log-price targets. The largest h12 realised core arithmetic versus
compounded discrepancy is 0.883 points (origin September 2021 to September 2022:
13.700 summed versus 14.583 compounded). Among new candidates the largest forecast
discrepancy is 0.464 points (aggregate monthly, August 2022 to August 2023:
9.952 versus 10.415). `core_outcomes.csv` records every divergence.

Headline annual forecasts always compound exact monthly gross factors. Original
bridge noncore contributions and all weights are preserved exactly; its h0 is
also unchanged. Existing saved bridge h0 differs from a round-trip reading of
HARD_BASE by at most 2.22e-16 pp because the original bridge used default CSV
float parsing. Candidate-versus-bridge h0 is checked exactly; only the comparison
between those pre-existing files uses 1e-12 tolerance. No model fit changed for
this serialization issue.

## Reproduction and outputs

Run `python core_path_experiment_r13.py`, then
`python core_path_experiment_r13.py --verify`. The latter refits all 90 origins
with network and database calls blocked and compares deterministic payload hashes.
The manifest records the declaration, consumed inputs/code and package versions.
The operational log is excluded from payload hashing. `verification_receipt.json`
is the authoritative final status for the full replay. Final verification passed:
all 90 origins refitted, 14 output payloads byte-identical, 74 consumed input/code
hashes verified, with network and database calls blocked.

18 new behavioural tests passed, including h1 equivalence, future-outcome and
future-vintage poisoning, complete-window release eligibility, destination
seasonality, origin-weight reconstruction, no fallback, training-only scaling,
exact noncore/h0 preservation and separate labour coverage. The final run of all
18 new tests plus adjacent R12/core input/model tests passed: 94 tests total.

`summary.csv` includes every horizon, all panels, pairwise and own-coverage scores;
`paired_uncertainty.csv` uses 2,000 circular block replicates, block length 12,
seed 1309. `fit_audit.csv`, `fit_diagnostics.json`, `external_source_audit.csv`,
`coverage.csv`, `origin_checks.csv`, `core_summary.csv` and `validation.json`
preserve timing, missing-history and accounting evidence. Prospective observation
is still required before changing the operating model roster.
