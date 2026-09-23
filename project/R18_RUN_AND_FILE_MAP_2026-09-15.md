# R18 run and file map

Start with [R18 results and decisions](R18_RESULTS_2026-09-15.md). This work is in the isolated `work/cpi-independent` checkout on `codex/independent-cpi-20260909`; the older Claude checkout was not modified. The new research remains in the working tree. No commit, merge or deployment was performed in this batch.

## Canonical outputs: use these versions

| Product | Final evidence directory | Generating code |
|---|---|---|
| Official category source package | `data/research_r18/categories/` | `tools/research_r18/category_inputs.py` |
| Category paths | `output/research_r18_category_verified/` | `category_trend_experiment_r18_verified.py`, `models/category_trend_r18.py` |
| Food paths | `output/research_r18_food/` | `food_h0_experiment_r18.py`, `models/food_h0_r18.py` |
| Four nowcast distributions/alerts | `output/research_r18_nowcast_final/` | `nowcast_reliability_experiment_r18_final.py`, `models/nowcast_reliability_r18_final.py` |
| Eleven-model path/CNB comparison | `output/research_r18/path_v2/` | `tools/research_r18/evaluate.py` |
| Joint path-error bands | `output/research_r18/uncertainty_final/` | `tools/research_r18/path_uncertainty_final.py`, `models/path_uncertainty_r18.py` |
| Energy source/field inventory | `data/research_r18/energy/` | `work/research_r18_energy/build_source_ledger.py` |
| Conditional energy illustrations | `work/research_r18_energy/output/` | `tools/research_r18/energy_exposure.py`, `models/energy_exposure_r18.py` |
| Forecast archive API | Tested interface; no live forecast added | `tools/research_r18/forecast_archive.py` |
| Static accuracy chart | `output/research_r18/presentation/` | `work/research_r18_final/build_chart.py` |

Each model output includes declared inputs, source hashes and a completion manifest. The category/food/path runs preserve the old model sources as dependencies. A new filename does not imply a different fit: the verified category runner has exactly the original forecast values, with corrected fallback handling and history metadata.

The final quantile module deliberately imports unchanged distribution/probability functions from `models/nowcast_reliability_r18.py`; that original file is an explicit hashed dependency. Both live model callers limit empirical support to at most 60 observations. The final quantile function is verified for those model supports and requested probabilities, not certified as an arbitrary-size general-purpose statistical library.

## Superseded runs retained for audit

- `output/research_r18_category/`: original numerical result, superseded by the verified runner's fallback and metadata corrections. Point forecasts match exactly.
- `output/research_r18/path/`: interrupted initial integration, no final evaluation. Use `path_v2`.
- `output/research_r18_nowcast/`: original quantile-boundary implementation; do not use its median/band scores. Laws, point forecasts, probabilities and alert outcomes remain unchanged.
- `output/research_r18_nowcast_verified/`: corrected requested quantiles; final adds a p=1 endpoint guard. Requested output tables are byte-identical to final.
- `output/research_r18/uncertainty/`: initial implementation, superseded while score-count reporting was being corrected. Not a final frozen result.
- `output/research_r18/uncertainty_verified/`: corrected quantiles and score counts on the wider native-outcome calendar. Final restores the original 969 intended keys; all actually scored intervals and metrics are identical, while intended/missing counts change.
- Smoke outputs are engineering checks, not additional evaluation samples.

Preserve these as history. Do not automatically pick the newest directory or average every model found under `output/`.

## Working model roster

- **Next release:** BASE, HALF, FULL and Category Raw remain the established display. HALF/FULL scale a learned core-error correction, not a survey adjustment. Category Raw is a point-accuracy challenger. This batch makes no operating point-model change.
- **Path:** FAST is the responsive reference; current core is the recent-period comparison; gentle slope is the existing slope sensitivity. The shared headline h0 remains HARD_BASE.
- **Research diagnostics:** the R18 fast category trend and hard-signal version. Their turns and short-horizon gains do not justify automatic model switching.
- **Conditional assumptions:** the existing annual-index fuel comparator and the new household-electricity cohort scenarios. These are not certified futures curves or national energy forecasts.
- **Rejected operating additions:** food-news propagation, the tested nowcast probability gate and the raw joint-error path bands. Retain their evidence.

## Reproduce without overwriting evidence

Use an unused destination; runners reject existing output directories. Run from the repository root. The historical model runs below consume saved inputs and do not refresh live sources.

```powershell
$env:PYTHONPATH='../pythonlibs'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython category_trend_experiment_r18_verified.py --output output/r18_replay/category
& $cpiPython food_h0_experiment_r18.py --output output/r18_replay/food
& $cpiPython nowcast_reliability_experiment_r18_final.py --output output/r18_replay/nowcast
& $cpiPython tools/research_r18/evaluate.py --output output/r18_replay/path
& $cpiPython tools/research_r18/path_uncertainty_final.py --experiment output/r18_replay/path --output output/r18_replay/uncertainty
```

The integration command intentionally reads the **canonical frozen child directories** listed above, not the replay directories produced by the first two commands. The child replays independently check those frozen runs. This avoids silently mixing a new child experiment into an old scoreboard. Compare numerical payloads with the canonical outputs; execution timestamps and path-dependent manifests will differ.

For the complete tested regression selection, see `work/research_r18_final/test_command_final.json`. In this machine's recorded runtime, legacy bridge imports additionally need:

```powershell
$env:PYTHONPATH='work/audit_fixes_20260914/runtime_deps;../pythonlibs'
& $cpiPython work/research_r18_final/run_tests.py
```

That last helper is the local verification runner and writes a test log; it is not a forecast command. The existing dependency directory required an approved offline sandbox escalation here. Another computer needs the recorded compatible Python/dependencies and source files; copying this command's machine-specific Python path is insufficient. No Bloomberg session is required to replay these frozen experiments.

## Before the first prospective run

The archive's `archive_forecast(...)` and `verify_bundle(...)` interfaces are ready and tested. Read [the schema and gates](docs/implementation/R18_ARCHIVE_SPEC_2026-09-15.md) before integrating them with the normal refresh command.

For a real forecast, acquire and save the input bytes first, record the actual observed availability dates, compute the forecast, then archive it before the correct first-release deadline. Declare the forecast's units and target in metadata; the generic archive does not infer whether a number is monthly or annual inflation. Archive h0 and the chronological monthly path together with the actual code/input/source-manifest files. Do not fill in historical availability using file modification times or call a reconstructed replay prospective.

The interface does not itself fetch data, schedule refreshes, certify source availability, verify that a declared point was generated by the attached engine, or supply an external timestamp. Those remain operational integration tasks. The new energy scenarios also cannot become a national forecast until exposure and baseline fields are identified.

## Verification and handoff evidence

- `work/research_r18_category_review/`: independent filter/regression and exact runner parity.
- `work/research_r18_food/`: food coefficients, training chronology and input/output hashes.
- `work/research_r18_nowcast_review/`: independently reconstructed distributions, exact quantiles, correction history and final parity.
- `work/research_r18_integration_review/`: headline/components/CNB/revisions/uncertainty reconstruction.
- `work/research_r18_final/`: fresh 523-test log, replay behavior, chart and final integrity receipt.
- `output/research_r18/DELIVERY_MANIFEST.json`: delivery file hashes and canonical entry points.

The final receipt checks the earlier frozen manifests as well as this delivery. A successful audit establishes the implementation's consistency with its declared specification; it does not create an untouched holdout or validate a profitable rates-trading strategy.
