# R19 verified nowcast recording and operational preflight

The user asked to continue after the R18 recommendation to prioritize prospective recording and household-energy data. This bounded continuation connects the existing independent nowcast output to the R18 archive. The forecasting formulas and historical results stay frozen.

**Goal:** validate and record a real engine-produced run without implying that an older bridge is the currently audited path model.

**Architecture:** a standard-library adapter checks snapshot/receipt/code hashes, clocks, supported point names and contribution arithmetic before calling the existing archive API. Explicit replay/prospective mode is mandatory. A replay is historical reconstruction; prospective requires the existing live capture, its positive readiness flags, first-release eligibility and a freshly completed calculation. The new code lives under `tools/recording/`; no old hashed source is edited.

**Alternatives considered:** modifying the old forecaster directly would invalidate many frozen source manifests; treating every legacy path as current would mislabel models; a validation/recording adapter preserves the current numerical engine and makes the remaining path gap explicit. The adapter is the chosen bounded step. It does not supply the missing live FAST/current/gentle noncore pipeline.

## Checks and tasks

- [x] Tests first: absent adapter; receipt/frame/code tampering; path traversal; inconsistent target/clocks; nonfinite point; contribution mismatch; stale completion; fixture presented as prospective; missing first-release calendar; archive publication time and supported model.
- [x] Implement `tools/recording/verified_nowcast.py` with `inspect_run`, `record_run` and CLI accepting an existing `--run` directory and explicit `--mode`. Dry-run checks do not write a forecast bundle.
- [x] Declare units explicitly: monthly CPI percent for points, percentage points for contributions. BASE is the archived primary; HALF/FULL remain independent comparison values. Unsupported path models are reported, never silently relabelled.
- [x] Validate a real archived/fixture engine run, then create a clearly labelled replay bundle and verify all bound artifacts. No historical run is called prospective.
- [x] Investigate and preserve raw ERU sources and their metadata. Product horizons/reference dates verified; CSV unit denominator is not explicit, so no bill-calculator integration is made. This narrower retention scope supersedes the original plan's conditional model-input retention. Indicative offer bounds are not paid-price means, CPI forecasts or confidence intervals.
- [x] Run focused tests and the existing archive/forecast-bundle regression tests; recheck frozen R18 hashes; publish a concrete operational gap report and usage command.

Source availability in a prospective archive is stamped when this adapter actually reads/verifies the saved artifacts; the engine's earlier decision/capture clock is preserved separately. This proves acquisition of those bytes by archive time, not the original publication time or completeness of source-loader refreshes. Replay uses the original simulated decision clock as a explicitly labelled historical-availability assumption, alongside the actual current verification clock. The two must not be confused.

The frozen release calendar presently ends at August 2026. A subsequent live target requires an explicit sourced calendar row; this adapter will not invent the next date or fall back to a generic day. The local DuckDB exists, but existence does not prove that its data are current.

Review clarification: the engine completion must be within 120 seconds at archive handoff. The archive has its own 120-second issue-to-publication clock. The combined bound can be 240 seconds; both are now recorded in metadata and boundary-tested. No claim of a single 120-second completion-to-publication limit is made. The archived point must still precede the release.

Completed evidence and remaining integration gaps: `R19_RESULTS_2026-09-15.md`. 56 tests passed; same-runtime fixture replay matched; 643 R18 delivery hashes unchanged. Current-runtime HALF/FULL differ slightly from the original R9-runtime result; this is explicitly documented, not hidden by overwriting the earlier scoreboard.
