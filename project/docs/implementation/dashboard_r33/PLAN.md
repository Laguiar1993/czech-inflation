# R33 briefing and forecast-change workflow

Approved by the user's "do it" following the five proposed improvements. This is engineering and analysis presentation; no research model promotion, retuning, or invented live forecast.

## Design and implementation plan

Create additive tools/inflation_dashboard_r33/ and tools/forecast_updates_r33/ with local * -text attributes; preserve every R32 and older frozen file. Main UI retains three views and the CNB replay. Main implementation owns the dashboard; one independent worker owns the refresh/revision workflow.

1. Dashboard data:
   - Load the hash-verified R32 exports through its existing builder.
   - Briefing comparisons are explicit: latest detailed CPI month against one or three months earlier, selected by the user. A prior visit baseline can be stored locally, but identical snapshot means no new data; never substitute last-month changes for since-last-visit changes.
   - Split actual and imputed rents using the 37-group panel, and show the other-services-and-mixed and catering blocks distinctly. Do not call the remaining mixed blocks pure services or subtract annual rates without weights.
   - For CNB gaps, consume each replay report's existing model-specific gaps, including unexplained residual and h0 caveats. Reconcile all components to the headline gap. Follow selected model/quarter/clock and keep the older input lane explicit.
   - Add scenarios as user-controlled headline m/m contribution assumptions for food (next three future months), core (next six), and administered energy (next January in support). Compound exactly relative to the archived rebased path; do not pretend these are commodity elasticities, model refits or confidence intervals.

2. Fresh-run and revision workflow:
   - Inspect existing Bloomberg connection and read-only source tools for an authorized fresh pull; save new snapshots only if a real connection is available. No network retries without useful new evidence.
   - Add a tested update entry point wrapping the R32 adapter with explicit bundle, target, timezone-aware as-of, separate sourced calendar, and immutable output/ledger metadata.
   - Only two successful comparable runs (same target/model/units) produce a component revision bridge. Changes sum to the point revision. Path differences align by calendar target month, never h-index across changed origins. Label any unexplained residual.
   - Reject missing/stale/invalid pairs and future-dated/reversed clocks. No current run is fabricated from the archived July calculation. No causal attribution to individual releases unless actually obtained by controlled re-runs.
   - Persist latest successful published snapshot separately from refresh attempts, with atomic replacement only after all checks. Failed refresh retains previous successful snapshot and publishes an inspectable failure report.
   - If current Bloomberg/manual inputs or verified calendar are unavailable, save the real readiness diagnosis. Complete the usable update/compare pathway with tests and portable documentation.

3. Interface:
   - First screen: What changed / What it implies / What to watch, each with evidence dates and observed/model/scenario labels.
   - Revision panel can load a validated comparison export at build time; absent comparables states why. Never relabel historical reconstructions as live.
   - Watch table maps CPI detail, farm/food PPI, pumps/FX, wages/demand, energy decisions to model blocks and qualitative sensitivities. Only show next release dates from sourced clock-valid records; otherwise date unavailable.
   - Scenario controls update the monthly line and quarter summaries, with reset and visible assumption amounts.
   - Retain all R32 track record and replay features, keyboard access, responsive layout, offline single-HTML output.

4. Verification/delivery:
   - Meaningful tests first: date-aligned revisions and failure cases, component conservation, non-overlapping housing split, scenario neutrality/timing/exact compounding, gap reconciliation, first/repeat visit behaviour.
   - Chrome desktop/mobile checks for changed features; independent review of finance semantics and stale-data handling.
   - Commit implementation before final canonical build, verify manifests and byte-exact staged files, preserve dated snapshots, update loopback preview only after checks.

