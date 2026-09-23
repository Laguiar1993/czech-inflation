# R33 sidecar review

Self-review completed against the approved dashboard_r33 plan; the parent is doing
an independent UI review. No separate subagent tool was available in this task.

- Public compare_runs always validates archived hashes and normalized adapter
  evidence before accounting. Invalid comparisons retain the exact unavailable schema.
- Model identity includes config, model/data Python implementations and frozen adapter
  code; bundle data changes alone are permitted as revisions. Current preparation
  preserves the frozen model and adds source provenance to a new bundle only.
- Failure tests caught command mismatch, malformed manifest handling and the direct
  internal API's missing command. Follow-up tests caught missing process-tree timeout
  and publication-after-release guards. These are fixed.
- Atomic pointer replacement occurs only after a complete sealed calculation and
  revalidation. The separate publication receipt is intentionally outside the seal.
- Replay and prospective pointers cannot replace each other. July calculations are
  replay only. Earlier blocked readiness is retained. The subsequently sourced official ARAD monthly inputs and CZSO calendar pass current readiness and the first prospective calculation.
- Contribution changes are accounting differences. No release-by-release causal
  effects, confidence bands, source publication times or missing core data are inferred.
- Current preparation uses the original pure feature builder, calendar-labelled
  shifts, R31C fuel source and EC pump conversion. All historical training values are
  preserved; missing August core/reg rows remained missing in v1; v2 adds only the separately sourced official ARAD m/m observations, with raw evidence and hashes.
- Optional external paths have an explicit source and matching identity, but are not
  certified as outputs of this adapter. Their limitation is documented.
- No changes to frozen files, shared calendars, existing data, the parent UI or Git
  history were made. Local attributes disable text conversion in both owned trees.


Parent integration fixed the independent P2 run-clock availability issue: hash-bound snapshot/manual availability is checked before invocation and again on load. New runs preserve the evidence internally; the earlier September archive remains byte-exact and validates through its pinned bundle. Nine failure-first regressions cover late sources within the permitted recording window, archive reload, missing original source after evidence capture, legacy archives and the unchanged September record. Full suite: 48 passed.
