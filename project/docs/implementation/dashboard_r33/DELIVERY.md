# R33 delivery: explanatory monitor and first prospective nowcast

The user approved the briefing/revision improvements and then connected Bloomberg. The current snapshot contains a real prospective September BASE nowcast, the explanatory monitor, and the preserved historical CNB rounds replay.

## What is new

- First-screen August official-release briefing: what changed, what it implies, what to watch.
- Headline, observed CNB core, broad CZSO services and imputed rent cards, with dates.
- Actual versus imputed rents in a non-overlapping detailed pressure table.
- Explicit correction of the earlier monitor's generic goods/services labels: the saved ARAD series are other tradables excluding food/fuel and nontradables excluding regulated prices, retaining first-round tax effects. They are not the CZSO broad aggregates.
- CNB gap attribution follows model, quarter and report/cutoff clock; residual and h0 caveats remain visible.
- User food/core/January-energy assumptions in headline monthly contribution points, exactly compounded.
- Revision workflow with immutable runs, component conservation, comparable identities and a retained last-successful pointer. The page includes a separately labelled July replay example; one prospective record cannot establish a prospective revision.

## First current forecast

Target September 2026; HARD_BASE -0.2042311894134946% m/m. Recorded at 2026-09-22T17:50:01.527361+00:00; completed at 17:50:14.588539+00:00. Its six components sum exactly to the point. Archive: output/forecast_updates_r33/runs/20260922T175001527361Z_7c5389d7016a.

Bloomberg supplied fresh headline, food, alcohol, fuel, pumps, FX and pipeline inputs. The two monthly CNB Bloomberg feeds (CZCIXM and CZCIRM) still ended in July. A direct latest-value/daily-history/mapping check confirmed this; evidence is output/bloomberg_core_check_r33. Official ARAD supplied the same observed August core +0.3% m/m and regulated 0.0% m/m. No CNB forecast entered the independent model. The separate live calendar uses official October 6 flash / October 13 detail dates and CZSO's 09:00 Prague publication rule.

## Limits and next step

The h0 nowcast is current. The monthly path remains the July-origin research model with actual July/August prints substituted; its future monthly forecasts were not re-estimated. The 37-group analysis panel remains July. These dates appear on the page. The first prospective record is an anchor for future evaluation, not evidence of prospective skill.

The next substantive engineering job is the current path runner using the same validated current input bundle, with explicit availability for food producer and farm price inputs. Keep the historical CNB replay at its original clocks and input lane. Do not silently substitute a current path into historical rounds or promote another model from this engineering exercise.

## Open and refresh

The delivered output/inflation_dashboard_r33/index.html is a single offline page; copy it to the other computer and open it in Chrome. It does not pull data merely by opening. tools/forecast_updates_r33/README.md describes Bloomberg capture, new bundle preparation, sourced supplements, readiness/run and recorded comparisons. tools/inflation_dashboard_r33/README.md describes the snapshot builder and optional --current-run / --old-run / --new-run inputs.

Preserve old snapshots and manifests. The new builders require new output directories. No frozen R32 or earlier file was edited; local directory attributes preserve working bytes under autocrlf.

## Final verification and seal

71 targeted tests passed: 48 refresh/conversion/availability and 23 R32/R33 dashboard checks. Chrome desktop and mobile checks passed, including the current recorded card and its source/path caveats. Independent review cleared both dashboard and refresh findings.

Use output/forecast_updates_r33/FINAL_DELIVERY_MANIFEST.json for the final workflow. The retained worker DELIVERY_MANIFEST.json predates the review fix and has three superseded code/document hashes (workflow.py, README.md and REVIEW.md), explicitly reconciled in the final manifest. No raw observation, prepared bundle or recorded forecast archive changed. The added availability tests and final workflow enforce source timestamps both before execution and when loading a record.
