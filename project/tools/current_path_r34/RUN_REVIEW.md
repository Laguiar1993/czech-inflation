# R34 runner independent review

Reviewed the additive runner against `docs/implementation/dashboard_r34/PLAN.md` at HEAD `a9e304d75a6148f48bf66ff621c5a44ab1c0d8a3`. Reviewed `run.py` SHA-256: `d50d9ddc3f34ee43d39c96f7f40f5e98822380350893868d3ae1b877217a2f16`.

**One P1 execution blocker and three P2 findings. No formula mismatch identified in the supplied July parity evidence.**

## P1 - Actual recording datetime breaks valid input loading

`tools/current_path_r34/run.py:135`, calling `load_inputs`; the failing operation is at line 111.

`record` passes `stamp`, an aware Python datetime, into `load_inputs`. For normal provenance containing `as_of` or `prepared_at`, the loader calls `workflow.clock(as_of)`. That R33 parser expects an ISO string and invokes `.replace('Z', '+00:00')`; datetime.replace takes calendar fields instead, so it raises and becomes `ValueError: timestamp must have an explicit timezone`. Every normal timestamped prepared bundle therefore fails before model calculation, despite a valid aware clock.

Reproduced with an in-memory hash-valid input fixture and `datetime(2026,9,22,18,5,tzinfo=timezone.utc)`. Passing the equivalent ISO string succeeds. Pass `stamp.isoformat()` at the call boundary or normalize the loader argument once; add a regression through the recording/loader boundary using its actual argument type. No model execution is needed for this test.

## P2 - Due upstream food inputs can be stale without rejection

`tools/current_path_r34/run.py:114-119` and the pre-computation checks in `record`.

The loader checks the last two consumer-food levels but never checks the latest usable farm/PPI rate against each source's publication clock. The subsequent R33 readiness check covers the separate h0 bundle, not these path food levels. The inherited food system supports a ragged edge, so successful estimation is not a freshness check.

An in-memory September input panel with consumer food through August but both agri4 and food_ppi ending in December 2025 passes `load_inputs`. The existing `tools.current_path.run.input_freshness` on the same panel reports not ready: agri4 is due through July 2026 and food PPI through August. Without a gate, stale upstream inputs can be presented as a fresh path.

Apply the existing source-specific freshness check, or an equivalent verified prepared-input contract, before computation; retain its last-usable/expected-month diagnosis. Preserve legitimate publication lags. Add a stale-PPI/farm regression with current consumer-food observations.

## P2 - load_record does not bind metadata and h0 back to evidence

`tools/current_path_r34/run.py:177-190`.

The loader verifies whatever hashes are listed, the path's arithmetic against its own `meta['h0']`, and completion before `meta['first_release']`. It does not revalidate the referenced R33 h0, require matching origin/contributions, or check the decision/recording/completion clocks and source availability. Hash consistency alone does not establish these cross-file invariants.

A fully hash-consistent synthetic record, represented only in memory, referenced the actual September R33 run but used h0 `+0.2` instead of `-0.2042311894134946`, with internally conserving/recompounded rows. It also claimed as-of `2099-01-01` while recording/completion were in September 2026. `load_record` accepted it. This is a negative validator probe, not a claim that the parent produced such a record.

Revalidate the referenced, pinned h0 evidence with `workflow.load_run`; match its target, point, six h0 contributions, decision clock and release boundary. Enforce supported mode/schema, consistent metadata/table identity, aware ordered clocks, actual-time limits and source availability at the archived path clock. Add negative load-record tests for wrong h0 and future/reversed clocks. Keep valid rehearsal clocks distinguishable from prospective records.

## P2 - R24 long food-history source is outside the recorded hashes

`tools/current_path_r34/run.py:80` and source capture at lines 142-149.

`long_food_rates` reads `data/research_r14/food/coverage_extension/czso_cpi_1995_2025.csv` directly. Its pre-2015 observations affect `mu_long`, hence the adopted R24 drift and future food path. `tools.current_path.run.source_hashes()` includes top-level data CSVs, not this nested CSV; enumeration of bundle/path-input/h0 directories does not cover it either. Confirmed that its exact key is absent from the source-hash map.

Pin this file explicitly before computation, verify the same hash afterward, and include it in the archived source evidence and reload validation. Otherwise changing a numerically influential source is undetected and the saved source list cannot identify the calculated path completely.

## Evidence and limits

- All seven existing `test_run.py` accounting tests passed in 0.021 seconds. They cover h0 point preservation, unchanged other contributions, complete horizons, conservation, target labels, future-history exclusion and missing compounding months.
- Read the matching-input July parity result: maximum absolute difference `2.220446049250313e-16`, annual rates exactly equal, and weights/non-food components equal. No parity model was rerun.
- Traced the unchanged base engine and R24/R27 calls: the runner applies the accepted FOOD_NORM_SHIFT_R24 baseline plus FOOD_ECM_R27 future-food correction; h0 remains outside that replacement. Annual compounding excludes realised origin/future observations.
- The negative probes were bounded in-memory fixtures using real loader/validation functions. No network or forecasting/model-estimation calls were made. No temporary files, source edits, commits or delivery seals were created; this report is the only write.
- `inputs.py` and a ready R34 prepared bundle were not present at the inspection point. Their eventual contract/output needs only a limited follow-up against these findings. The current review does not certify unavailable inputs or a not-yet-produced September path.


## Focused fix review and resolution - 2026-09-22

**All four reported findings are resolved in the reviewed runner. No outstanding blocker from this focused review before the canonical commit.**

Updated only `test_review.py` fixtures to satisfy the real prepared-input contract: January-2015 zero-based food levels, matched availability, exact headline index ratios, gross Monday pump observations, complete source provenance, hash-checked raw capture bytes and the original R33 h0/bundle evidence. The tests mock filesystem byte transport only; `inputs.load_prepared`, source hashing, clock checks, freshness gates and archive revalidation execute normally.

The failure-first suite previously produced 9 expected failures and one successful complete-record control. After the parent fixes and schema-complete fixture update, `python -B -m unittest tools.current_path_r34.test_review -v` passed all 10 tests in 2.184 seconds. Each archive negative test first loads the valid positive control, then reseals only the intended mutation; wrong h0 point, changed h0 contribution split, future decision time and reversed completion all reject specifically. Aware datetime input now loads identically to its ISO string. Overdue farm/PPI inputs reject while the legitimate July-farm/August-PPI September information set remains accepted. The exact long-history CSV hash is present in `record_sources()`.

Static follow-up confirmed `record` invokes prepared-source validation and the calendar-scoped freshness gate before computation, uses `record_sources()` before the model and verifies the hashes afterward. `load_record` checks schema/mode, ordered actual clocks, referenced pinned manifests, revalidated R33 h0 point/contributions/origin/release, row clocks/model identity, prepared-source availability/freshness and the long-history hash. The unchanged model formulas were not rerun.

Reviewed `run.py` SHA-256: `fd4401c49446366a5f310ce63ad8406f437a4d192f07e93bc7764ae53ca4fe24`. Reviewed `test_review.py` SHA-256: `1e7716ad45f31348382ae6d0c0dba3ac858868aae3672b77e0ae0632f4289fc3`. This follow-up modified only the authorized regression file and appended this report; no runner/input-worker edits, model/network calls, commits or delivery seals. It verifies the fixes and their validator behavior, not an as-yet unreviewed final September path artifact.
