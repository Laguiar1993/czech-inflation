# R33 explanatory dashboard

This additive dashboard keeps the CNB rounds replay and adds:

- A dated official-release briefing, with a separate comparison for the saved 37-group panel.
- Actual and imputed rents separately in the pressure table; rows still partition the basket.
- Component gaps to the CNB, following the selected report, information clock and model, with the unexplained residual retained.
- Food, core and January energy scenario controls in headline m/m contribution points, compounded exactly through the annual window.
- First/repeat visit messages based on an embedded data fingerprint.
- A watch list with sourced CPI dates and explicit missing dates for other releases.
- Optional component forecast revisions from two validated immutable R33 runs.

The front page uses the official August release published 10 September 2026. The full 37-group analytical panel remains July, as does the archived model origin. The archived goods/services series are ARAD other tradables excluding food/fuel and nontradables excluding regulated prices, with first-round taxes retained. They differ from the broad CZSO aggregates; R33 corrects their labels and explains the scope. Official observations are recorded in official_release.json with direct source URLs; they do not silently overwrite model inputs.

## Reproduce

Use the project's bundled Python from the repository root:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest tools.inflation_dashboard_r33.test_analysis -v
python -m tools.inflation_dashboard_r33.build --output work/my_new_r33_snapshot
node tools/inflation_dashboard_r33/browser_check.cjs http://127.0.0.1:8769 work/my_browser_checks
```

Choose a new output directory every time. The single index.html opens offline in Chrome and embeds its data, CSS and JavaScript. Opening it does not refresh Bloomberg.

To embed a real forecast revision, pass `--old-run` and `--new-run` directories produced by tools.forecast_updates_r33. The builder revalidates their manifests and calls compare_runs; it rejects invalid, reversed or non-comparable pairs. Historical pairs remain labelled replay revisions. It does not infer a revision from the latest CPI change.

The R32 renderer is imported without editing its sealed files. R33's output manifest includes both source directories, the consumed exports and any comparison runs. Review source_issues and each panel's information date before using this as a current monitor.

## Verification

Fourteen Python checks cover component reconciliation, report/cutoff separation, non-overlapping housing weights, scenario neutrality, January timing, exact compounding, twelve-month expiry and forecast support. Browser checks exercise desktop/mobile layouts, source definitions, first/repeat visit messages, scenario controls, CNB selections and existing R32 controls. Scenario outputs are also compared between browser JavaScript and Python.

A recorded current nowcast can be embedded with `--current-run <validated-run-directory>`. The builder revalidates it, requires prospective mode and the expected next-release target, and displays its exact as-of and component contributions. This updates the nowcast card, not the archived monthly path. A historical revision pair is displayed only inside an explicitly labelled working-example disclosure.


## Recorded September run

The delivered snapshot embeds the prospective HARD_BASE run recorded on 22 September 2026 at 17:50:01 UTC: -0.2042311894% m/m for September. Its six contributions reconcile exactly. First release is 6 October at 09:00 Prague. The run uses the successful Bloomberg pull plus the official August ARAD monthly core (+0.3%) and regulated (0.0%) observations, and a separate sourced release calendar. The validated archive is `output/forecast_updates_r33/runs/20260922T175001527361Z_7c5389d7016a`.

No second prospective run exists, so the revision panel keeps the July working example separate. This is the first record, not evidence of prospective forecast skill. The current monthly inflation path has not yet been re-estimated; it remains the dated July-origin research path with actual prints substituted.

The user-requested Bloomberg recheck is archived in `output/bloomberg_core_check_r33/`: latest-value BDP and daily BDH both ended at 31 July for CZCIXM (1.0) and CZCIRM (0.2). Security searches confirmed the mappings and identified nearby annual/contribution variants, not another exact monthly series. This establishes the missing observations in those feeds at retrieval time, not the reason for Bloomberg's update delay.
