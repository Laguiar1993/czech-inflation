# R18 independent nowcast and archive review

No actionable arithmetic or release-gate defect was found in the parent nowcast
engine or its saved run. No parent engine, point forecast, source file or output
manifest was edited by this review.

## Independently reproduced calculations

`audit_nowcast.py` does not import the nowcast engine. It reconstructs the laws and
scores directly from the frozen point forecasts, first-release actuals, release
calendar and original state clocks. It verified:

- 90 origins × four models: all 360 own-origin scales use earlier origins whose
  first release had already passed; current/future errors are excluded.
- All 1,080 law records; 792 are estimated, giving the same 66 eligible dates for
  each model/family. The first 24 dates retain insufficient-history status.
- Signed raw-error pooled laws, own-scale transformations, calendar-age decay,
  training-pool RMS similarity and the prescribed 50% temporal/50% kernel blend.
- Every saved training-origin list and first-release clock, including the source
  evidence's first-release date and the release-eve origin-clock assertion.
- Material-gain probabilities from absolute-error improvement, including a
  same-direction overshoot that loses. Big-event probabilities are separate.
- CRPS via an independent unordered-pair weighted sum, all empirical quantiles,
  intervals, realized gain/error flags and effective sample sizes.
- All 72 score rows and 144 alert comparison rows. The unchanged departure rule
  and probability-gated alerts share identical eligible samples; non-alert dates
  remain in primary scores.

Maximum absolute differences: support `1.78e-15`, weights `5.56e-17`, individual
metrics `9.24e-14`, score summaries `4.45e-16`; alert comparisons match exactly.
All 63 recorded nowcast input hashes and all output hashes were also verified.
Full machine-readable results are in `arithmetic_audit.json`, with independently
reconstructed scored observations in `independent_predictions.csv`.

Interpretation: `n_false` counts alerts on non-big outcomes. It does not mean every
such forecast lost money or even increased forecast error; material wins/losses
and total error reduction are distinct columns. The probabilities and intervals
remain experimental and do not establish calibration, conformal coverage or a
trading signal. Historical release clocks and source vintages remain reconstructed.

## Forecast archive

The preimplementation contract is
`docs/implementation/R18_ARCHIVE_SPEC_2026-09-15.md`; the new module is
`tools/research_r18/forecast_archive.py`.

`archive_forecast(...)` validates all inputs, records actual code/input/source
manifest hashes, reserves a fresh UUID directory exclusively, writes a payload
with exclusive open, and atomically publishes a commit seal. It cannot update or
overwrite an existing bundle. An interrupted attempt remains uncommitted and its
UUID cannot be reused. `verify_bundle(...)` rejects uncommitted, changed or invalid
records; `verify_artifacts=True` additionally checks source files against saved hashes.

Prospective mode requires a supplied issue timestamp within the real UTC clock's
previous 120 seconds, strictly before first release, and no declared source
availability later than the issue. Actual archive/commit time must also precede
first release; checks repeat after input hashing and immediately before commit.
Replay mode permits an earlier issue clock but stays explicitly labeled replay.
Dates must include time zones. Source availability is a checked declaration, not
proof of historical vintage or a certification that an engine consumed those files.

The archive is an append-only software interface and integrity record, not a
signed external timestamp or OS-enforced WORM repository. A filesystem user can
alter both a payload and its seal; no adversarial tamper-proof claim is made.

Only synthetic fixture bundles were created, under review work directories. No
actual live forecast was generated or labeled prospective. Nineteen archive tests
pass, including collision, source/payload tamper, incomplete reservation, invalid
paths, missing/future availability, naive timestamps, stale/future issue clocks,
post-release issue/commit, and delayed hashing/publication. Combined verification:
**28 tests passed** (19 archive, five nowcast reliability, four category inputs).

Run the focused checks with the bundled Python and existing `../pythonlibs`:

```
python -m pytest tests/test_r18_forecast_archive.py tests/test_nowcast_reliability_r18.py tests/test_r18_category_inputs.py -q -p no:cacheprovider
python work/research_r18_nowcast_review/audit_nowcast.py
```
