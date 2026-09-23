# R16 independent evaluator and interpretation review

The final frozen numerical experiment and its evaluator pass this bounded independent review. No model, source data, forecast output, evaluator code or scoring definition was edited by this reviewer. All reviewer writes are confined to `work/research_r16_review`. Parent-owned browser/JavaScript checks and presentation review remain separate from these arithmetic and artifact-data checks.

## What was independently checked

The final evaluator receipt verifies 108 hashes: 64 input/source files and 44 output artifacts. `audit_evaluation.py` recomputes all 21,300 scoreboard rows, including the full fifteen-model intersection and every separate pair against FAST and the pipeline. Every count, RMSE, MAE and bias matches exactly. All five retained controls have exactly their R15 common-support scores, and every metric/horizon/era support set in the R15 comparison is unchanged. Metrics with different underlying outcome coverage still retain different samples; in particular h12 headline annual CPI has 75 origins while h12 cumulative core has 78.

The source wrapper passes explicit R16 model lists into the frozen R15 helpers. It retains only each helper's explicitly selected common result before assigning its R16 scope. The old R15 default roster and its extra pipeline-only scopes therefore do not leak into FAST comparisons. No shared helper global or default is mutated.

Raw monthly-core forecasts and the original monthly-core outcome file independently reproduce all four annualized, seasonally adjusted bands. Every origin uses the same own-origin R15 seasonal vector for its forecast and actual paths. Maximum band-value difference is 7.11e−15; all peak/trough labels, eligibility indicators, hits, false calls and misses match exactly. All 159 full-sample common turn opportunities are retained. Actual outcomes are neither inferred from headline annual inflation nor replaced by the broad annual services/goods series.

The CNB comparison was rebuilt directly from frozen monthly-origin forecasts, raw CNB forecast quarters and the frozen headline monthly outcome history. Both report-day and cutoff-day snapshot clocks, all common quarter inclusion decisions, quarter averages, forecasts, gains/losses and every-report omission result match exactly. The five retained controls and CNB reproduce their original R15 pairs exactly. Report-clock snapshots are strictly before Prague report-day midnight; cutoff snapshots include the whole cutoff day. Known pre-origin annual rates and subsequent forecasts from one origin supply each quarterly mean; later-origin forecasts are never borrowed.

The first-stage scoreboard contains only the 90 scored outer origins: 720 intended signal/origin/band rows. Its outcome is the mean of three transformed annual inflation observations, `mean(100*log1p(yoy/100))`, in annual log percentage points. The comparator is each origin's current annual-log signal held constant. Complete-band availability, identical projection/persistence support, every actual value, error and score match independent calculation. No /12 conversion is applied to these scored outcomes; /12 remains a second-stage predictor rescaling only.

All 15,987 raw revision pairs match independent same-target, consecutive-origin differencing. These include 990 pairs without a realised annual-CPI outcome. Outcome availability therefore does not incorrectly gate forecast stability.

The final HTML's decoded embedded `DATA`, apart from its intentional convenience `reports` copy, equals the UTF-8 `replay_data.json` exactly. All fifteen model IDs and distinct labels are present. All 7,980 monthly path points, quarter points, common score-quarter lists and displayed MAE values reconcile to saved forecasts and CNB score pairs. Each clock contains 19 replay rounds, including the final unscored round. Checkbox visibility does not change the common score inputs.

An initial suspected label-encoding mismatch was withdrawn: the reviewer read the JSON with the Windows default encoding while reading HTML explicitly as UTF-8. Explicit UTF-8 reads of both files give exact equality, and the HTML contains no Unicode replacement characters. No artifact correction was necessary for that concern. A separate evaluator hardening pass added raw/native headline parity, origin-calendar and clock checks without changing scores; the final receipt and audit use the refreshed evaluator. Independently, all 11,700 new raw headline monthly predictions equal their native counterparts exactly.

Evidence: `evaluation/audit_summary.json`, the `evaluation/reference_*.csv` tables, `audit_evaluation.py` and `reference_diagnostics.py`. Successful audit command:

```powershell
$env:PYTHONPATH='../pythonlibs'
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r16_review/reference_diagnostics.py
& 'C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' work/research_r16_review/audit_evaluation.py
```

The optional `--skip-integrity` audit switch was used only while the evaluator was being refreshed. The final `audit_summary.json` records `integrity_skipped: false` and all 108 verified hashes.

## Turning-point result

There are 77 actual material turns among 159 matched opportunities. None of the five damped-slope paths calls a material turn in this frozen test, including the two phi=0.95 models whose architecture permits reversals. Architectural capability has not become demonstrated turning-point skill.

| New transmission path | Calls | Exact-band hits | False calls | Missed actual turns |
|---|---:|---:|---:|---:|
| Own | 17 | 1 | 16 | 76 |
| Services | 20 | 1 | 19 | 76 |
| Goods | 25 | 2 | 23 | 75 |
| Both | 29 | 0 | 29 | 77 |
| Fixed damped/transmission blend | 17 | 0 | 17 | 77 |

All ten new models have zero exact hits in the 2024+ origin sample, which contains 41 matched opportunities and 22 actual turns. This does not support a claim that R16 anticipates underlying-core turns, or any comparison against unavailable CNB core-turn forecasts.

The first-stage services forecasts also lose to annual-signal persistence in full-sample RMSE at every band and in the recent-origin sample at every band. Goods improve full-sample h1–3 signal RMSE, but lose at h4–6, h7–9 and h10–12. Their target forecasts therefore provide no general evidence of a successful underlying transmission mechanism, even before assessing the monthly-core mapping.

## CNB-relative gains and their concentration

All report-clock results below use the same 66 report/quarter pairs from 18 scored reports. These are overlapping dependent comparisons.

| Model | MAE | RMSE | Material gains / losses versus CNB |
|---|---:|---:|---:|
| CNB | 1.0605 | 2.2955 | — |
| R15 FAST | 1.2597 | 1.9867 | 15 / 32 |
| Damped .95 / .001 | 1.2462 | 1.9071 | 13 / 29 |
| Damped .95 / .010 | 1.1147 | 1.6786 | 13 / 29 |

Both new .95 paths improve RMSE relative to FAST and CNB, while CNB retains lower MAE. Their identical 13 material gains versus 29 material losses do not establish a frequent, broad disagreement advantage. In the 2024+ report sample, CNB MAE/RMSE is 0.2865/0.3718; .95/.001 gives 0.3616/0.4804 and .95/.010 gives 0.5178/0.7268. The more reactive path is substantially weaker recently.

Both new .95 models retain a full-sample CNB RMSE advantage under 17 of 18 single-report omissions. Omitting the February 2022 report reverses the advantage, just as for FAST. On the remaining 62 report-clock pairs, CNB RMSE is 1.4763, .95/.001 is 1.6907, .95/.010 is 1.6227 and FAST is 1.7391. At cutoff clock the corresponding new-model RMSEs are 1.8276 and 1.7174, again above CNB's 1.4763. The sensitivity is a post-run diagnostic, not a reason to remove the episode from primary scores or retune the models.

Headline improvement should also be separated from core-mechanism accuracy. On their primary h12 cumulative-core support of 78 origins, FAST RMSE is 4.1963 versus 4.5691 for .95/.001 and 4.9447 for .95/.010. Thus better aggregate headline accuracy does not itself establish a better core forecast. The parent's separate same-75-origin accounting analysis can distinguish outcome-support differences from compensation against fixed noncore errors; that accounting must not be presented as causal identification.

## Independent driver reconstruction

`audit_drivers.py` independently expands every fitted second-stage contribution through its first-stage predictors, including both stages' penalized constants and generated-predictor centering. It imports neither driver helper. All 1,440 explained fits and 15,840 exported terms reproduce: maximum component difference is 1.11e−16 and maximum summed-residual difference is 4.44e−16 monthly-log percentage points. The interpretation manifest's eight data hashes and two source/helper hashes also match. Evidence is `evaluation/driver_audit_summary.json`.

These contributions explain fitted arithmetic. They do not identify causal services or import-price pass-through, official component weights, or a monthly partition of the broad annual-rate inputs. No automatic promotion or hindsight-selected blend follows from this review.
