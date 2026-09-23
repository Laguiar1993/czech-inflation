# Deferred refactors touching cz_struct.py's numeric path

The /code-review (2026-09-06) verified these structural findings. They are
NOT applied yet, deliberately: `cz_struct.py` carries the frozen v2.2 spec,
and any edit to its numeric path — even a supposed no-op — risks silently
changing forecasts. Apply them in ONE batch, with this mandatory gate:
**re-run the 90-origin backtest before and after; every output column must
be bit-identical; commit the diff proof alongside the refactor.** A new
SPEC_TAG is NOT needed if bit-identity holds (refactor, not spec change);
if any number moves, stop and treat it as a found bug.

1. **Wedge/recombination block duplicated** between `main()` and
   `struct_live()` (character-for-character, incl. the 5-component
   extension applied twice). Extract one `_weighted_wedge(...)` helper —
   this is the backtest/live-parity risk the module docstring promises
   against.
2. **Trailing-yoy/state defined twice** (`load_all` line ~82 and the band
   loop ~742). The sum→compound audit fix had to be applied in both. One
   `_trailing_yoy(ext)` helper, or reuse `feats["state"]` in the band loop.
3. **Division SQL copied four ways** (`load_headline_cpi_mm`, food/fuel in
   `load_component_targets`, `load_alc_tobacco_mm`, `food_experiment.
   food_levels`) while `local_adapter._cpi_divisions_mm()` already
   generalizes it. One `la.load_division(coicop, levels|mm)`.
4. **`czcpmom_survey_history_extended.csv` parsed in four places** with
   diverging filters (one drops the suspect Aug row, others don't). One
   typed loader; callers choose the filter explicitly.
5. **Train-mean imputation implemented three times** (`_ridge_predict`,
   main's PE block, `restored_pe_correction`). One `_impute_train_means`
   helper; keep the sd-standardize step only in `restored_pe_correction`
   (spec-distinct per PAST_ERROR_QRF_SPEC.md).
6. **`prev` alc seed 0.087 magic number** — derive from
   `_OFFICIAL_ALC[min(_OFFICIAL_ALC)]` so the pre-anchor fallback tracks
   the table. (Affects pre-2016 regimes → numeric path → this batch.)
7. **No-op `[:avail]` slices** in the PE block (lists only ever appended
   together) — drop `avail`, use the lists directly.

Non-numeric findings from the same review were fixed immediately (commit
history): broken ast fixture in test_p0_regressions (AnnAssign globals),
capture_survey manual path always aborting + unverifiable hash + leaked
BBG session, energy_accounting dead branch with literals shadowing the
params CSV, dead `cons` copy in scoreboards, dead `ann` in acceptance
tests, energy_ledger per-call re-parse.
