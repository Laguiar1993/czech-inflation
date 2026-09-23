# R14B core: controlled historical-input extension

Declared after R14 scores and their independent audit, before any extended-history
fit. This is explicitly an outcome-informed research extension, not a fresh test.
The audit found that requiring twelve complete import-price sources reduced R14
learned states to March2016 onward despite core history from2007. Testing only
short-history regressions did not establish whether richer independent models
with adequate training history can work.

## One change, independently verified data

Use the immutable extension in data/research_r14b/imports/core_feature_extension.csv
and its manifest. Exactly84 previously missing import_l2 cells are supplied from
official CZSO CEN0303 national total import prices, source January2008--December2014.
Its overlap with the frozen CPA-total series is exact to floating precision on
all137 existing observations. Fresh official CEN0303 and CEN0301 totals agree on
all138 common observations. Never replace a finite original input, another column,
or a later missing observation; no June2026 addition. Keep the current predictor
values, target data, original forecasts, weights and nowcast unchanged.

The additional sources have a conservative reconstructed available_from at00:00
Prague on the start of source+3. One documented January2014 release occurred on
17March, contradicting a universal16th-day rule. The longer clock still precedes
every declared r-3 source's forecast origin r, and is explicitly enforced and
reported. These are latest-vintage series, not a historical revision archive.

## Identical recipes, paired history experiment

Rerun all six R14 core recipes from R14_CORE_DESIGN.md, with exactly the same
targets, seasonal construction, predictors, alpha/window grid, forest settings,
historical clocks, delayed error selection, current trend, missing-value rules
and scoring. Only eligible historical import observations change. Core local
forecasts at the90 outer origins must be numerically unchanged. Other learned
forecasts may change because the training/validation sample grows.

Implementation reuses core_learning_experiment_r14.py with an explicit optional
--feature-extension directory and --declaration parameter. Hash the loader,
extension, its manifest and declared source/preparer files. Apply the extension to
a copy only for core state construction, after the original bridge replay. Verify
the saved feature policy during --verify; no silent default/extended switch.
Source publication overrides are explicit; default None preserves old calculations.
Store outputs in output/research_r14b/core/. Recipe model IDs within that folder
remain identical to R14 for direct paired comparison; combined reporting labels
them CORE_*_EXT_R14B to distinguish data policies. Do not overwrite short-history
R14 forecasts. Refresh their metadata/fingerprint only with verified unchanged
forecast values when the shared runner's optional interface is added.

Report the first historical state and fit, intended/finite/common counts, selected
configurations and default frequency by band, short-versus-long paired errors,
all six algorithms versus original bridge on full/recent-target/recent-origin
panels. Include core errors and final headline errors, not a preferred horizon only.
No further alpha/window/feature or blending change after this run.

Additional combined paths fixed before extended fits:

- STABLE_LONG_CORE_R14B: stable food pipeline + constant-pump fuel + extended-history
  CORE_LEVEL_RIDGE_R14, all other original bridge contributions and h0 unchanged.
- STABLE_LONG_GAP_R14B: same, with extended-history CORE_GAP_RIDGE_R14.

Preserve the earlier two R14B combinations and all original R14 failures. Compare
new combinations on the same90 clocks and external CNB report panel. Add the same
two combinations to the already declared24 custom FMIE issue-clock h12 comparisons;
rebuild current extended state and train on original historical clocks, never use
FMIE values to pick coefficients. Keep all earlier comparison models in the tables.

Tests before fits: fill-only policy, no new rows/columns/finite overwrites, strict
value and timestamp validation, actual extension/source/preparer hash verification,
unreleased extra-source poisoning, old-policy numerical equivalence, no changes to
original frames, and direct h12/validation maturity tests. Independently reconstruct
selected extended fits and sample counts; rerun both policies offline. Report
research limitations and retain evidence rather than claiming promotion from a
repeatedly inspected small historical evaluation.
