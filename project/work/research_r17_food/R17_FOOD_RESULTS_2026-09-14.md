# R17 food experiment results

The declared asymmetric cost model does not improve the preserved FAST food
component on full-history monthly or cumulative errors. Symmetric costs are
slightly better than the own-food control on pooled monthly errors, but still
worse than FAST. No parameter was changed after the full fit, and these results
do not support replacing the production food component on their own.

## Scope and implementation

The six declared models were replayed over 126 own-origin snapshots from February
2016 through July 2026. All 90 original outer origins February 2019–July 2026
have all twelve food forecasts. The early snapshots used for later training and
selection preserve explicit fallback flags; none of the 6,480 outer candidate
food rows uses a fallback or lacks a finite forecast. The first outer h12 fit
has exactly 24 eligible shared training origins, as declared.

Monthly log-rate features use both released level endpoints and calendar-exact
lags. Frozen food seasonality and own1/own3 controls are augmented with average
agri4 and food-PPI changes in lag windows 1..3 and 4..6. The asymmetric version
splits each raw change into positive and negative parts before averaging. Every
historical feature and destination seasonal offset is saved at its own clock;
direct monthly targets must precede the current origin and have released
endpoints. Own and cost fits share the same complete historical feature calendar.

Ridge uses fixed own penalty 0.1 and cost penalties 0.1, 1, 10. One penalty is
selected for the whole path, using only previously saved fixed-candidate paths
with all twelve outcomes matured. Default penalty 1 remains explicit for the
first 24 outer origins. Among the 66 later outer selections, the asymmetric
model chooses penalty 10 at 58 origins and 1 at 8; the symmetric model chooses
10 at 51, 1 at 14 and 0.1 at one. Strong shrinkage is usually preferred.

## Component results on identical realised calendars

Pooled h1..12 food m/m RMSE, in percentage points:

| Model | Full: 1,002 rows | Origins 2024+: 294 | Targets 2024+: 372 |
|---|---:|---:|---:|
| Preserved FAST food | 1.1381 | 0.8325 | 0.9092 |
| Seasonal | 1.1695 | 0.8552 | 0.9375 |
| Persistence | 1.3062 | 0.9935 | 1.0702 |
| Own-food ridge | 1.1701 | 0.8626 | 0.9316 |
| Symmetric costs | 1.1686 | 0.8584 | 0.9236 |
| Asymmetric costs | 1.1847 | 0.8674 | 0.9588 |
| Half correction | 1.1987 | 0.8878 | 0.9648 |

Compounded h1..12 food percentage-change RMSE, in percentage points:

| Model | Full: 78 origins | Origins 2024+: 19 | Targets 2024+: 31 |
|---|---:|---:|---:|
| Preserved FAST food | 8.5962 | 4.2037 | 5.6790 |
| Seasonal | 8.9903 | 4.1006 | 5.7797 |
| Persistence | 12.1565 | 8.6725 | 10.3133 |
| Own-food ridge | 9.1902 | 4.4148 | 6.3852 |
| Symmetric costs | 9.1801 | 4.4612 | 6.1851 |
| Asymmetric costs | 9.4496 | 4.4340 | 7.2668 |
| Half correction | 10.0492 | 6.0429 | 8.0988 |

The small seasonal improvement on recent-origin cumulative errors does not erase
the negative full-history comparison. These are point estimates, not evidence of
statistical significance. The parent R17 evaluator owns annual-headline common
support, block uncertainty, CNB clock comparisons and combination selection.

The historical inputs are stored current-vintage levels with reconstructed
availability. This is an origin-gated direct cost-lag forecasting association,
not a recovered projected upstream supply chain or an identified causal effect.
No new historical source, future cost series, survey or expectations input was
introduced.

## Verification evidence

Seventeen tests passed, including signed lag decomposition, endpoint publication
gates, future poisoning, own-origin seasonality, common training support,
train-only scales, direct-target maturity, explicit fallbacks, chronological
whole-path selection, half correction and exact monthly/annual arithmetic.
Tests were written and observed failing before their implementations. One
pre-full-run edge correction made an incomplete seasonal calendar disable the
whole path, exactly as already specified; both initial smoke paths were unchanged.

The independent saved-output checker rebuilds all 8,022 fitted equations from
the stored own-origin features, original response levels and saved historical
seasonal offsets. Maximum coefficient discrepancy is 1.89e-15; maximum fixed
forecast discrepancy is 8.22e-15. It checks 1,512 shared training calendars,
163,584 response endpoint timestamps and all 252 symmetric/asymmetric
whole-path penalty decisions. Independent direct-product annual recomputation
differs by at most 1.07e-13 and six-component monthly sums by 8.88e-16.

All original h0 forecasts, nonfood component values/contributions and weights
are exact. R15 FAST monthly paths equal the preserved R16 FAST control. Seventy-five
source/control hashes and fourteen completed output hashes verify. The runner
saved its source/specification/parameter declaration before fitting, refuses to
overwrite a destination, and checks the source hashes again before completion.

## Deliverables and replay

- `models/food_transmission_r17.py`: released-input snapshots and direct models.
- `food_transmission_experiment_r17.py`: frozen declaration, replay, integration,
  outcomes and score export.
- `tests/test_food_transmission_r17.py`: 17 contract tests.
- `docs/implementation/R17_FOOD_SPEC_2026-09-14.md`: frozen child specification.
- `output/research_r17_food/food_predictions.csv`: 9,072 standalone monthly rows
  for all 126 own origins; `outer_origin` identifies the original 90.
- `output/research_r17_food/native_forecasts.csv`: 7,020 FAST-with-food native
  h0..12 rows, six candidates × 90 origins × 13 horizons.
- `output/research_r17_food/forecasts.csv`: same annual/monthly candidate panel
  plus unchanged R16 FAST control for parent evaluation.
- `output/research_r17_food/fixed_candidates.csv`, `snapshots.json`,
  `fits.json`, `training_calendars.json`, `selections.json`: complete lineage.
- `output/research_r17_food/food_summary.csv`, `food_outcomes.csv`,
  `coverage.csv`, `validation.json`, `declaration.json`, `manifest.json`.
- `work/research_r17_food/independent_verification.json` and
  `verify_independent.py`: standalone numerical/source audit and receipt.
- `work/research_r17_food/smoke_checks.json`: independent pre-full smoke receipt.

With the approved Python runtime and `PYTHONPATH=../pythonlibs`, rerun:

```text
python -m pytest tests/test_food_transmission_r17.py -q -p no:cacheprovider --basetemp work/pytest_r17_food_new_unique
python work/research_r17_food/verify_independent.py
python food_transmission_experiment_r17.py --output work/research_r17_food/new_replay_directory
```

The replay destination must not already exist. No earlier source, model or output
was rewritten; no commit was created.
