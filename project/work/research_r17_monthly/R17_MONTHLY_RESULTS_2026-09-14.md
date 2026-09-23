# R17 monthly category transmission results

The shared category autoregression reduces the covered pressure proxy's measured
forecast error, but adding the declared domestic/imported hard signals does not
improve that full-history comparison. None of the five generated-signal core
mappings improves FAST's pooled monthly core error. These negative results are
retained without changing the fixed penalties, features or model roster.

## Scope and lineage

The experiment uses five frozen tax-including national service groups: actual
rent, imputed rent, catering, accommodation and package holidays. No exact
monthly goods partition, tax-adjusted core membership, or official current
category contribution shares were available. The normalized weighted category
aggregate is a pressure proxy. Its base-weight contribution diagnostic and the
statistical difference core-minus-pressure are explicit; neither is labelled an
official tax-adjusted core partition.

All 126 own-origin snapshots February 2016–July 2026 were constructed using their
own release-eve clocks, endpoint-gated log changes, seasonal means/scales and
dated basket regimes. The first stage pools the five normalized category rows
with shared lag coefficients, comparing persistence, AR, domestic, imported and
both groups. Own penalties are 0.1 and macro penalties 1, fixed throughout.
Domestic inputs are unemployment changes, IP growth and ULC growth. Imported
inputs are FX3 and the preserved import-price/industrial-PPI transformations.
All six are saved own-origin R15 hard inputs; there are no surveys or confidence
variables and no future actual category features.

The second stage reads the saved first-stage pressure forecasts from disk and
maps their log-rate increments relative to own-origin persistence into residuals
against saved FAST core forecasts. Own penalties are 1 and generated-signal
penalties 10. Own-origin fallback forecasts remain legitimate generated
forecasts, with their status and counts visible. For example, February 2019 h12
has 24 mature second-stage training origins but zero actually fitted first-stage
forecast origins in that training set. Its generated increment is zero, so the
model reduces to the own-input control. This early limitation is not hidden by
dropping origins or substituting future actual category pressure.

Both stages retain all 90 original outer origins and h1..12; the five native
headline paths additionally retain unchanged HARD_BASE h0. There are no missing
or fallback outer predictions in this frozen input run. All category/core
training families share their declared historical support.

## First-stage component comparisons

Pooled h1..12 monthly RMSE in percentage points, same 1,002 realised rows:

| Category/proxy | Persistence | Shared AR | Domestic | Imported | Both |
|---|---:|---:|---:|---:|---:|
| Actual rent | 0.2585 | 0.2653 | 0.2683 | 0.2983 | 0.3016 |
| Imputed rent | 0.7013 | 0.6172 | 0.6481 | 0.6742 | 0.6884 |
| Catering | 0.7884 | 0.7343 | 0.7742 | 0.8037 | 0.8387 |
| Accommodation | 0.9258 | 0.8823 | 0.8815 | 0.9691 | 0.9713 |
| Package holidays | 2.7695 | 2.5962 | 2.8430 | 3.0470 | 3.2138 |
| Covered pressure | 0.5673 | 0.5307 | 0.5864 | 0.6457 | 0.6785 |

Covered-pressure monthly and cumulative comparisons retain the same calendar
within each column:

| Model | Full monthly N1,002 | Origins2024+ monthly N294 | Targets2024+ monthly N372 | Full h12 cumulative% N78 |
|---|---:|---:|---:|---:|
| Persistence | 0.5673 | 0.2711 | 0.2925 | 5.7912 |
| Shared AR | 0.5307 | 0.2500 | 0.2772 | 5.0898 |
| Domestic | 0.5864 | 0.3334 | 0.4248 | 5.6846 |
| Imported | 0.6457 | 0.2540 | 0.2891 | 6.0638 |
| Both | 0.6785 | 0.3355 | 0.4164 | 6.2602 |

Imported pressure has a smaller recent-origin h12 cumulative RMSE than AR
(0.9413 versus 1.0922 on 19 origins), but its full-history error is worse. That
narrow observation does not establish the intended general transmission result.
These are measured point errors, not significance claims.

## Second-stage core comparisons

| Model | Full monthly N1,002 | Origins2024+ monthly N294 | Targets2024+ monthly N372 | Full h12 cumulative% N78 |
|---|---:|---:|---:|---:|
| Preserved FAST | 0.43279 | 0.13693 | 0.19650 | 4.53390 |
| Own inputs | 0.43606 | 0.13762 | 0.20565 | 4.59772 |
| Generated AR | 0.43567 | 0.13749 | 0.20522 | 4.59964 |
| Generated domestic | 0.43605 | 0.13771 | 0.20830 | 4.59652 |
| Generated imported | 0.43971 | 0.13762 | 0.20563 | 4.66406 |
| Generated both | 0.43663 | 0.13777 | 0.20628 | 4.62294 |

All recent-origin cumulative h12 core errors also exceed FAST: both 0.6656
versus FAST 0.6022 on 19 origins. Stage-one AR's lower proxy error therefore
does not translate into a better core path here. Further mechanism or promotion
claims are unsupported by these diagnostics.

The separate prior-model comparison retains frozen CORE_SPLIT_MONTHLY_R13 and
TRANSMISSION_BOTH_R16. On their common 780 pooled monthly core observations,
FAST RMSE is 0.44190, generated-both R17 0.44980, R13 0.46903 and R16 0.47468.
Their early missing dates do not shrink the primary R17/FAST 1,002-row panel.
Endpoint-only h12 comparisons can differ: on the common 54 h12 observations,
R13 has lower endpoint error than both R17 and FAST. Neither endpoint result is
a statement about compounded headline performance.

The parent R17 evaluation owns headline annual/CNB comparisons, uncertainty,
fixed combinations and constrained chronological whole-path selection. No
standalone component promotion follows from this child experiment.

## Verification

Fifteen contract tests pass. The initial model and runner tests were observed
failing before implementation. Pre-full-run synthetic tests also exposed and
fixed two boundary issues: a missing macro input must not relabel an otherwise
valid persistence control, and a null generated forecast must remain unavailable
instead of triggering arithmetic on JSON null. No features, penalties or source
choices changed in response to full fitted outcomes.

The separate numerical checker reconstructed all 4,584 fitted first-stage
equations and all 5,730 fitted second-stage equations. Coefficients matched
exactly; first-stage predictions differed by at most 7.11e-15 and second-stage
predictions matched exactly. It checked 1,020,240 publication comparisons, all
generated-file hashes, pressure arithmetic and the statistical reconciliation.
An additional checker independently reconstructs every one of the 126 snapshots,
seasonal/scaling/own features, basket regimes, macro values and FAST baselines
from original inputs with zero discrepancy.

All 94 source/control hashes and 21 saved output hashes verify. Independent
annual direct-product calculations differ by at most 1.01e-13, including the
conditional annual field; cumulative headline log fields differ by at most
3.55e-15. h0, noncore values/contributions and weights remain exact. Original
food-native derived fields were also rechecked without modifying the frozen
food output: cumulative discrepancy 2.66e-15, conditional annual discrepancy 0.

## Deliverables

- Frozen specification: `docs/implementation/R17_MONTHLY_SPEC_2026-09-14.md`.
- Model, runner and tests: `models/monthly_transmission_r17.py`,
  `monthly_transmission_experiment_r17.py`, `tests/test_monthly_transmission_r17.py`.
- `output/research_r17_monthly/firststage_predictions.csv`: 45,360 rows across
  126 own origins, five families and six category/proxy series; the original
  outer subset has 32,400 rows.
- `output/research_r17_monthly/core_predictions.csv`: 7,560 rows; all five
  candidates include every own-origin h1..12 forecast.
- `output/research_r17_monthly/native_forecasts.csv`: 5,850 rows, five models ×
  90 origins × h0..12; all derived headline fields recomputed.
- `output/research_r17_monthly/forecasts.csv`: candidate headline forecasts plus
  unchanged R16 FAST control.
- `snapshots.json`, `core_states.json`, `generated_signals.json`,
  `generated_status.json`, both stage fit files and shared training calendars.
- Both stage summaries/outcomes, separate prior-core comparison scores,
  statistical reconciliation, pre-fit and pre-second-stage declarations,
  validation and final manifest in the same output directory.
- `work/research_r17_monthly/independent_verification.json`,
  `snapshot_lineage_verification.json`, `smoke_verification.json`, and the two
  reusable checker scripts. `food_derived_followup.json` preserves the separate
  food-field audit receipt.

With the approved runtime and `PYTHONPATH=../pythonlibs`:

```text
python -m pytest tests/test_monthly_transmission_r17.py -q -p no:cacheprovider --basetemp work/pytest_r17_monthly_new_unique
python work/research_r17_monthly/verify_independent.py
python work/research_r17_monthly/verify_snapshot_lineage.py
python monthly_transmission_experiment_r17.py --output work/research_r17_monthly/new_replay_directory
```

Replay destinations must not exist. Earlier sources/results were preserved and
no commit was created.
