# Current monthly path implementation plan

The user approved R19's next step: connect FAST/current-core/gentle-slope to live calculation and verify all h0–h12 values. This is integration, not new parameter selection. Existing frozen research files are retained byte-for-byte. Work remains in the existing independent checkout because its uncommitted research files are required inputs.

## Design

Create `models/current_path.py`: `forecast_current_path(frames, food_levels, food_available, pump, origin, as_of, h0, h0_contributions=None)` computes the full roster. Core uses the existing R15 fast filter, R14 local twelve-month trend and R16 p95_q001 damped slope. All share the existing stable food VAR, constant-pump path, announced administered prices, alcohol seasonal model, released basket weights and wedge. Reuse existing numerical functions; reproduce the shared noncore arithmetic explicitly without calculating discarded legacy ridge/X13 forecasts. Forecasts contain h0–h12, monthly changes, compounded YoY, contributions, weights and availability diagnostics. No consensus, CNB or outcome table is read by this function.

Create `tools/current_path/run.py`: one entry point for `--fixture`, `--live`, `--replay`. It calls the existing independent nowcast and the shared path function. It snapshots numerical frames, extra food/pump inputs, source files, code, runtime and outputs. Fresh-source capture and retrospective fixture are explicit. `--live` requires an explicitly supplied refreshed path-input directory with the documented CSV names, hashes and units; it cannot silently reuse the historical food/fuel research directory. A stale/unknown required history prevents a prospective-ready label. No unsupported future release date is guessed.

Alternatives rejected: editing the old runner would invalidate frozen source manifests; copying historical path output into a live run would not forecast a new origin; retuning while migrating would obscure parity. A new named command preserves old replay and provides a clear current entry point.

## Implementation and verification

- [x] Add failing tests for constant-pump relative-change arithmetic, source dates, future-data invariance, core horizon alignment, contribution totals, h0 preservation, missing core, duplicate keys and invalid clocks.
- [x] Implement the shared function using existing filters and food model. Retain exact model IDs: STATE_FAST_R15, STABLE_LOCAL_CORE_R14B, DAMPED_P95_Q001_R16.
- [x] Compare the new function against all 90 original origins: each of three models, all thirteen horizons; compare finite masks, monthly and YoY values, future block values, weights and contributions to tolerance 1e-8. Record each difference. Do not fit to the differences.
- [x] Add snapshot and runner tests: explicit live input source requirement, hash changes, unsupported runtime, stale food/pump, missing calendar, immutable directories, offline replay and independent model identities.
- [x] Run the new CLI on the latest historical fixture and replay it without network. Preserve this as historical output, not September issuance.
- [x] Build one clearly labelled HTML view of the resulting thirteen-month paths and contributions with links to the run identity; show actual issue/capture and simulated decision dates.
- [x] Request an independent code review of the shared function/runner while completing parity evidence; fix material findings and rerun affected tests.
- [x] Verify old R18/R19 hashes, write R20 results and precise refresh/use instructions, and seal new files in a new manifest. Receipt is `output/research_r20/DELIVERY_MANIFEST.json`; the final seal command must pass before delivery.

Implementation outcome: shared numerical core plus `tools/current_path/run.py`, `record.py`, `view.py` and `seal_inputs.py`. The new entry automatically records eligible runs and builds a chart. Full parity: 3510 rows, zero finite-mask mismatches, maximum 5.329e-15. Tests: 189 integration/regression plus 2 packaging. Four development review findings were corrected; no model parameter or old research result was changed. Operational source refresh and a future sourced calendar remain outside the numerical migration, as anticipated above.

Scientific limitations remain the existing reconstructed availability, revised input histories and repeated historical selection. The connection itself makes no new claim of forecast accuracy. The current source refresh and first-release calendar may prevent a genuine new live target; report that concretely instead of manufacturing readiness.
