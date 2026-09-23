# R18 forecast archive implementation plan and contract

Declared before implementation. This follows the authorized append-only archive design.

**Goal:** Record immutable forecast bundles with honest replay/prospective labels,
issue clocks, forecast values and source/code/input provenance.

**Architecture:** Standard-library Python module, one reserved UUID directory per
bundle, exclusive payload creation and an atomic commit seal. No update, deletion,
relabeling, historical backdating or overwrite API. This is an append-only software
contract and integrity check, not an external trusted timestamp, signature or OS WORM store.

**Files:** `tools/research_r18/forecast_archive.py`,
`tests/test_r18_forecast_archive.py`. Fixtures only; no live forecast is generated.

## Fixed schema

Every bundle has schema version, UUID, explicit mode (`replay` or `prospective`),
actual `archived_at_utc`, caller's `issued_at_utc`, target origin `YYYY-MM`,
timezone-aware target first-release timestamp, forecast model name, point forecast
and optional monthly path (`target_month`, `point`). All numbers must be finite;
path months must be unique, chronological and no earlier than the target origin.

The required artifact groups are `model_code`, `inputs`, `source_manifests`, each
nonempty. The archiver reads actual local regular files and records path, byte count
and SHA256; it does not trust caller-supplied hashes. Each declared input/source
manifest must have an explicit timezone-aware availability timestamp keyed by its
path; optional metadata records source/reference period and an availability note.
The bundle records source and target clock assumptions honestly. Issue/reference
and replay mode are never inferred from file creation dates.

The supplied source availability declaration is checked but cannot certify its
truth, establish that a historical vintage existed, or prove the inputs were used
by the forecast engine. Artifact hashes freeze exact bytes that the caller supplies.

## Timing gates

Prospective: `actual_now - 120 seconds <= issued_at <= actual_now`, using a private
UTC wall-clock function and no caller-configurable clock/window. Also require
`issued_at < target_first_release_at` and every data `available_from <= issued_at`.
A forecast issued at or after the first-release timestamp is ineligible. Reject
naive or missing timestamps. Date-only midnight is not an implicit time zone.
The actual archive/commit clock must also precede first release, preventing a
within-window backdate after the outcome was released. Recheck after hashing and
again before the commit marker; record commit time in the seal.

Replay: historical issue timestamps are allowed and are labeled replay. All modes
still require declared source availability no later than the simulated issue and
issue strictly before the declared first release. Replay never demonstrates a
prospective live issuance or a real-time historical source vintage. Backdated
`issued_at` cannot obtain a prospective label by setting another argument.

The target first-release clock is declared input, not fetched or inferred; callers
must supply the real official timestamp. Archive code never converts a detailed
release deadline into an earlier first release automatically.

## Append-only commit and verification

Validate timing, forecasts and artifacts before reserving a UUID directory.
Reserve with atomic exclusive `mkdir`; an existing directory is a collision and
is never opened for writing. Write `bundle.json` exclusively (`xb`), flush and
fsync. Write a complete temporary seal exclusively; publish `COMMITTED.json`
atomically using a same-directory hard link that cannot replace an existing path,
then remove only that temporary seal. The seal holds the SHA256 and byte size of
the complete payload. A reader accepts only committed bundles with correct bytes,
schema, ID, mode and structural timing checks. Incomplete/crashed reservations
remain visibly uncommitted and cannot be reused. Nothing is silently cleaned up.

Payload/commit files have no mutation API. Filesystem users with write access can
still alter or delete files; hash verification detects a changed payload against
its seal, but this is not a signed adversarial audit trail. Optional verification
of present artifact files detects changed source/code/input bytes after issuance.
Bundle verification does not require the current date to equal the original issue
window; otherwise a valid prospective bundle would become unreadable with age.

## Validation steps

- [x] Write fixture tests first and observe missing implementation failures.
- [x] Implement standard-library archive, validation and verification APIs.
- [x] Test valid replay and prospective fixture bundles with a monkeypatched private clock.
- [x] Test collision, payload tamper, source artifact mutation and incomplete bundle rejection.
- [x] Test stale/future issue times, issue at/after first release, future/missing source availability and naive timestamps.
- [x] Test replay cannot claim prospective, nonfinite forecasts, duplicate/misordered path months and absence of partial directories after validation failures.
- [x] Run focused tests and write the independent nowcast arithmetic audit separately.

No original dataset, manifest, forecast, parent engine or existing output is changed.
