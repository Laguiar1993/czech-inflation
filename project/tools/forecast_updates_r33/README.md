# Independent refresh and revision sidecar (R33)

Wraps the unchanged tools.live_bundle_r32 in an isolated, bounded subprocess.
Owns only tools/forecast_updates_r33/ and output/forecast_updates_r33/, each
with local "* -text". No frozen code, data, calendar, or UI edits; no commits.

## CLI and runtime

Run from the repository root:

~~~powershell
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$env:PYTHONPATH='C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs'
$env:PYTHONDONTWRITEBYTECODE='1'
$cpiClock=[DateTimeOffset]::UtcNow.ToString('o')

& $cpiPython -B -m tools.forecast_updates_r33 readiness --bundle output/forecast_updates_r33/current_bundle_20260922_v2 --target 2026-09 --as-of $cpiClock --mode prospective --live-calendar output/forecast_updates_r33/live_calendar_cz_cpi_20260922.csv --timeout 30

# Only after sourced inputs and release clocks have passed readiness:
$cpiClock=[DateTimeOffset]::UtcNow.ToString('o')
& $cpiPython -B -m tools.forecast_updates_r33 run --bundle <prepared-bundle> --target 2026-09 --as-of $cpiClock --mode prospective --live-calendar <sourced-calendar.csv>

# Historical replay, never a current/prospective forecast:
& $cpiPython -B -m tools.forecast_updates_r33 run --bundle data/bloomberg_inputs_20260922_foodppi --target 2026-07 --as-of 2026-08-04T23:59:00+02:00 --mode replay
~~~

Bundle, target, aware as-of, and mode are mandatory. The wrapper's default
store is output/forecast_updates_r33; --store may select a subdirectory there.
No implicit "latest bundle", clock or target is used.

--timeout defaults to 120 seconds and must be in (0,300]. Timed-out owned
process trees are terminated, including model descendants such as X13.
Cleanup waits are bounded separately. There are no retry loops, network calls
or detached jobs in the forecast wrapper.

Stdout is JSON. Exit 0 means a successful calculation or ready inspection.
Exit 2 means blocked/invalid, unavailable comparison or publication failure.
Inspection never creates a forecast or moves a successful pointer.
Invalid CLI syntax returns JSON; a parsed refresh request is archived even
when clock, data, runtime or execution validation fails.

Optional --live-calendar uses R32's append-only sourced CSV contract:

~~~text
target_month,first_release_dt,detail_release_dt,available_from,source
~~~

All three timestamps require explicit timezones and source is mandatory.
Frozen targets cannot be replaced. The file is copied into the attempt and
that immutable copy is supplied to R32. Date-only official schedules are
insufficient for this timestamp contract. No release time is guessed.

## Immutable attempts and publication

Each attempt creates runs/<actual-UTC-recording-time>_<random>/ containing
request.json before work, inputs.json, adapter stdout/stderr and JSON when
reached, result.json, and MANIFEST.json with all sealed file hashes.
Optional calendar/path input copies and scoped model temporary files are retained.
The normalized result carries status (successful/ready/blocked), actual
recorded_at and completed_at, mode, target, model, units, forecast or null, and reason.

Files are create-only. Hashes attest local integrity relative to the manifest,
not an external signature. A crash can leave an inspectable incomplete attempt;
such an attempt cannot be compared or published.

publication.json is a separate create-only post-seal receipt, outside the run's
manifest. It records published, retained, not_applicable or failed. A publication
failure preserves the validated calculation but returns CLI exit 2.

latest_successful.json is the only replaceable shared document. Its entries
are keyed by mode, target, model, units and model implementation identity.
Different modes, months and models do not replace one another. A newly sealed
and revalidated result is published by fsyncing a new sibling pointer file and
atomically replacing the pointer with os.replace. Failed or older/equal-clock
attempts retain the previous successful pointer byte-for-byte.

A single-writer lock prevents races and fails promptly if already held; the busy
attempt is still recorded. If a killed host leaves a stale lock, inspect its
referenced attempt before removing it. Do not choose the newest attempted
directory as the published forecast; follow the validated successful pointer.

Any future as-of is rejected in both modes. Prospective recording must start
within 300 seconds of its explicit as-of. This is an engineering freshness guard,
not a guarantee of tick-by-tick input vintage. The actual completion and publication
must still precede the sourced first release. An archived July adapter ready flag
cannot masquerade as a live September result. Latest-vintage and static-input
limitations remain explicit. Historical clocks use replay.

## Comparison API and exact JSON schema

~~~python
from tools.forecast_updates_r33.workflow import compare_runs

comparison = compare_runs(old_run, new_run)
if comparison["status"] == "ok":
    # Display kind, target and both decision clocks with the bridge.
    pass
~~~

Arguments may be archive directories or result.json paths. The public function
revalidates hashes, request/adapter identity, normalization, clocks, fallback
diagnostics, optional path evidence and component conservation. Do not use the
internal compare_records helper for untrusted input.

~~~powershell
& $cpiPython -B -m tools.forecast_updates_r33 compare --old <old-run> --new <new-run> --output output/forecast_updates_r33/<new-name>.json
~~~

Optional comparison output is create-only. The UI can import it or call compare_runs
at build time. See comparison.schema.json for the formal JSON Schema.

The exact keys are:

~~~text
status, kind, target, model, old_as_of, new_as_of, old_point, new_point,
delta, components[{name,old,new,delta}], residual,
path_changes[{target_month,old,new,delta}], reason
~~~

- status is ok or blocked. Successful kind is forecast_revision for two prospective
  archives, or replay_revision for two replay archives.
- Invalid pairs return kind unavailable, null identity/clocks/points/delta/residual,
  empty component/path lists, and a reason. Missing, corrupted, malformed, failed,
  mixed-mode or incomplete runs never produce a revision.
- Both runs must have the same target, model, source-code model identity, units and
  component definitions. The new clock must be strictly newer. Different months
  or models, equal/reversed clocks and future recording clocks fail closed.
- Only HARD_BASE is supported: R32 exposes its complete contribution bridge.
  Points are CPI m/m percent; contributions, changes and residual are percentage points.
- Each component set sums to its point within 1e-9 pp. Component deltas plus residual
  reconcile to new_point minus old_point. Residual is explicitly unexplained numerical
  reconciliation. No rounding is applied before validation.
- These are changes in model component contributions, not causal effects of individual
  news releases. No controlled release-by-release reruns are claimed.
- Optional paths align the union of calendar target months, never horizon indices.
  Unmatched months have a null missing endpoint and null delta. If either path is
  absent, path_changes is empty and the reason explains that.

--path accepts external JSON with target, model HARD_BASE, units mm_pct, aware as_of,
nonempty source, and points [{target_month,point}]. Identity and clock must match
the run. Duplicate months, nonfinite values and pre-origin months fail. The original
input is archived. This does not fabricate an extended path or certify the external
path's economic model; the R32 adapter itself computes h0 only.

## Current bundle preparation

The frozen upstream builder replaces existing fixture cells and does not extend
frames. current_bundle.py adds a separate extension path using the unchanged pure
cz_struct.assemble_feature_frames function. It preserves historical training rows,
the R31C services exclusion and historical fuel/pump source identities. New observed
months are appended; missing inputs remain NaN. FX MTD is left to R32's as-of gate.
No source loader that writes or fetches shared data is called.

~~~powershell
$cpiClock=[DateTimeOffset]::UtcNow.ToString('o')
& $cpiPython -B -m tools.forecast_updates_r33.current_bundle --base-bundle data/bloomberg_inputs_20260922_foodppi --snapshot output/forecast_updates_r33/bloomberg_capture_20260922_activated/snapshot --target 2026-09 --as-of $cpiClock --output output/forecast_updates_r33/<new-bundle-name>
~~~

The explicit snapshot is hash-verified before parsing and must have completed by the
as-of. The output must be new and under this R33 output directory. The existing local
CZSO national seven-product farm-price loader is read-only and its raw source is
hashed. The new bundle carries source provenance, frames, portable market/history_long.csv,
and a manifest. It is h0-only; no stale path files are relabelled current. Preparation
status is not forecast readiness: always call the wrapper's readiness/run afterward.

Optional --manual-inputs accepts CSV:

~~~text
series,observation_month,value,units,source,available_from
~~~

Supported series are core and regulated, in CNB m/m percent (units mm_pct).
Each row must cite its source and have an aware availability timestamp no later
than as-of. Only observations after the base history and before target are permitted.
Duplicate rows, unsupported units, unavailable observations and conflicts with an
existing Bloomberg value fail. Rounded y/y observations are never converted to m/m.
A later sourced completion should be prepared into another NEW bundle directory.

## Evidence at delivery

Bloomberg became available after the user connected: the API session started even
though the direct TCP probe timed out. xbbg 0.7.7 and blpapi 3.25.5.1 are installed.
The first pull's Anaconda DLL failure was retained. The repository-documented
process-local Library/bin PATH correction allowed one bounded retry to succeed
in about 10 seconds, with zero errors.

bloomberg_current_config.json contains existing configured tickers only. The existing
tools.market_data.probe_bloomberg_candidates CLI captured data through 21 September
into output/forecast_updates_r33/bloomberg_capture_20260922_activated/snapshot.
Its request, coverage, raw data and manifest are retained. Observation dates are not
publication timestamps. Latest observations are August for headline/food/alcohol/fuel
index/food PPI, July for CNB core/regulated and import prices, 18 September for pumps,
and 21 September for CNB EUR/CZK.

The prepared current_bundle_20260922_v1 passes the real R32 portable-bundle checks.
At 2026-09-22T17:41:42.9865242+00:00, real current readiness has only:
missing September CPI release timestamps; missing August core; missing August regulated;
and missing September core_l1 caused by the same core gap. All other required input
checks pass. Local July farm prices provide September agri_l1; August agri_l0 is
correctly NOT_DUE until the frozen September 26 gate.

Those earlier blocked attempts are preserved. The parent then supplied original
official ARAD m/m observations: August core 0.3 and regulated 0.0, series
SCPIMZM09MOMPECNA and SCPIMZM02MOMPECNA. Raw responses and retrieval hashes were
verified and copied to cnb_observed_20260922; available_from conservatively uses
the actual retrieval time 2026-09-22T17:43:58.430957+00:00.

current_bundle_20260922_v2 incorporates those two observed monthly values. The separate
live_calendar_cz_cpi_20260922.csv uses official next-release dates, 6 and 13 October,
and the CZSO media page's 09:00 local publication rule. Both dates are +02:00 in
Europe/Prague. Source text and hashes are archived in calendar_provenance.json.

The first prospective September run then passed the real model and publication
checks at as-of 2026-09-22T17:50:01.527361+00:00, completed at
2026-09-22T17:50:14.588539+00:00. HARD_BASE is -0.2042311894134946 percent m/m;
the six contributions reconcile with zero residual. Its immutable archive is
runs/20260922T175001527361Z_7c5389d7016a and its convenient result is
first_prospective_result.json. This is the first current baseline, so no prospective
revision bridge is claimed yet. The separate July replay comparison remains valid.

current_refresh_feasibility_v2.json supersedes the earlier dated blocked diagnosis;
earlier evidence files are preserved unchanged. Model latest-vintage/static-input
limitations continue to apply. This h0 does not update or extend an archived path.

Two real historical calculations passed: July 28 12:00 +02:00 and August 4 23:59
+02:00 for target July. comparison_july_replay.json records 0.44602898893387816 to
0.4734274935716145 m/m percent, +0.027398504637736354 pp. It is replay_revision,
not a prospective forecast or causal news decomposition. replay_verification.json
checks frozen model/adapter/calendar/bundle manifest hashes remained unchanged.

## Tests

~~~powershell
& $cpiPython -B -m unittest discover -s tools/forecast_updates_r33 -p 'test_*.py' -q
~~~

The workflow suites have 40 tests (including nine availability regressions); current preparation adds 8. The complete 48-test suite passes. Tests were written and
observed failing before implementation, followed by complete passing runs. Coverage
includes genuine child timeout, release-crossing publication, pointer failure/busy
writer preservation, archive tampering, identity/clock/conservation failures, month
alignment, no-imputation current extension, exact historical preservation, source
corruption and sourced manual-input gates. Test temporary files stay in this new
tools directory and are removed. Workflow unit tests use the standard library;
current preparation uses the real supplied runtime and read-only frozen fixtures.


## Run-clock availability guard

Prospective recording rechecks raw snapshot completion and manual availability against the run's own as-of, not only the preparation clock. The metadata must match its hash in the exact input manifest. New runs archive those manifest/provenance bytes and recheck the gate on load. Earlier prospective records, including the first September forecast, are checked against their retained hash-pinned bundle without editing the record. Replays retain their explicit latest-vintage policy. A rejected refresh leaves the successful pointer intact.
