# R33 refresh/conversion independent review

Reviewed 2026-09-22 against `docs/implementation/dashboard_r33/PLAN.md`, source HEAD `a7aaca818ffd38cb906a7443722de9e5515084c1`, and the additive worker files. Worker changes were checked again after the successful September run appeared.

**Outcome: one P2 workflow finding; no critical finding. The actual September run passes the capture-clock checks below and this finding does not invalidate that snapshot.**

## P2: Revalidate bundle availability against the run's own as-of

Location: `tools/forecast_updates_r33/workflow.py:310-320` (input capture before invoking R32); corresponding archive revalidation in `load_run`.

`current_bundle.prepare` checks snapshot completion and manual `available_from` against the preparation clock, but `record` accepts another `--as-of` and records only the bundle manifest hash. R32's portable-bundle loader verifies the provenance file's hash without applying its capture/manual timestamps. Neither `validate_adapter` nor `load_run` restores this gate. A prospective as-of can therefore precede a supplement's recorded availability while still being within the permitted 300-second recording window, allowing later inputs into an earlier decision timestamp.

Concrete read-only reproduction with the real v2 bundle: as-of `2026-09-22T17:43:00+00:00` retains August core/regulated values `0.3`/`0.0`, although both manual rows have `available_from=2026-09-22T17:43:58.430957+00:00`. Calling `load_manual` at that earlier clock correctly rejects them; loading the prepared bundle and applying R32 readiness does not. Its only failure is the absent September calendar. Supplying an explicitly synthetic future release calendar in memory makes data readiness true, and `validate_adapter` accepts the prospective readiness report with recording at `17:46:39.265415+00:00`. No model was executed and no archive was created for this probe.

Required correction: before prospective invocation, read hash-verified preparation provenance and reject raw capture completion or any manual availability later than the requested run as-of. Preserve sufficient evidence in the run archive and apply the same condition on `load_run`. Add a regression for an earlier run clock that still passes the 300-second guard. Historical latest-vintage replay can retain its explicitly different policy.

## Actual successful September record

`output/forecast_updates_r33/runs/20260922T175001527361Z_7c5389d7016a` passed the real `load_run` hash/evidence validation. It is prospective, targets September, and has publication receipt `published`.

- Point and contribution sum both equal `-0.2042311894134946` m/m percent.
- Run as-of/recorded-at: `2026-09-22T17:50:01.527361+00:00`; completed `17:50:14.588539+00:00`.
- Raw snapshot completed `17:26:40.547842+00:00`; manual core/regulated availability `17:43:58.430957+00:00`; bundle preparation as-of `17:46:37.568733+00:00`. All precede this run's as-of.
- Archived sourced calendar availability is `17:50:00.528349+00:00`; first release is `2026-10-06T09:00:00+02:00`. Calendar availability precedes the run, and completion precedes release. Source URLs were inspected locally, not re-fetched.

## Verification and scope

Six existing conversion tests passed with their setup replaced only in memory to avoid temporary-file writes: missing inputs, calendar lags, frozen history/services exclusion, missing import month, current FX deferral, and Monday/CZK-per-litre pump conversion. Both real prepared bundles passed R32 manifest/source validation; baseline training rows through July and all existing weekly pump rows matched exactly. V1 keeps August core/regulated missing; V2 adds the supplied observed m/m values. Fuel conversion uses the exact monthly index ratio. Independent HARD input selection excludes survey/expectations columns; no CNB forecast input was introduced by this conversion.

The two existing July archives revalidated and reconciled to a `0.027398504637736354` pp replay revision; reversed order returned unavailable. Static review found no additional material defect in create-only run files, locking, atomic successful-pointer replacement, normal failed-attempt retention, or pair identity/conservation checks. Publication receipts are intentionally outside the sealed manifest. The full I/O test suite was read but not rerun under the read-only restriction. Chrome/UI checks remain the main task's evidence.

No worker files were changed, and no model or network operation was run. This review file is the only write.

Reviewed final `workflow.py` SHA-256: `5aaf210bd6da9ddb10da78f63696ecb221253e95569a1d027e89d5b5c658b9f8`; `current_bundle.py`: `13c33f605ecc3d185f8ee1dd641e373a85e6612493645167ed59aa57b3047fb5`.


## P2 resolution verified - 2026-09-22

**Resolved. No outstanding material finding from this focused review; the September snapshot remains valid for final publication.**

Reviewed the new `bundle_evidence` / `check_bundle_availability` implementation and all nine added `test_availability.py` cases. `record` now binds provenance to the exact bundle manifest and checks prospective source availability before adapter invocation. New archives seal manifest/provenance evidence with `bundle_evidence_version=1`; `load_run` checks those sealed bytes and their source-manifest binding. Legacy prospective records revalidate the original hash-pinned bundle without rewriting the archive. Explicit latest-vintage replay remains permitted.

Independent read-only verification passed 11 focused checks: the original early-manual reproduction and early snapshot clocks now reject; wrong manifest/provenance hashes reject; replay remains allowed; a virtual sealed v1 archive loads without its original bundle; both early clocks and resealed-but-source-mismatched provenance reject on archive reload. The real September record revalidated at -0.2042311894134946, and every file in that archive remained byte-exact. The virtual archive existed only in memory. The parent full test suite was not rerun here.

Reviewed fixed `workflow.py` SHA-256: `2a7cfb66bd91bf9e188b71d697816392146529ebd025b014a78f495629c68fe3`. No worker edits, model execution, network calls, or writes beyond this review-file append.
