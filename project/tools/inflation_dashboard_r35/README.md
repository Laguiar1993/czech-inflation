# R35 compact inflation overview

The overview leads with category 3m/6m annualised momentum, changes in pace, y/y context, twelve-month sparklines and weighted breadth. Click a category for its chart and constituent selector. The heatmap toggles pace/change; weighted drivers identify the largest contributors. Methods sit behind a button, and the former July overview is retained under Data & reliability.

The current path, live nowcast, forecast context, historical CNB replay and July archive are copied exactly from the verified R34 record. Their separate recorded clocks are retained. No forecast is rerun by this build.

The output index.html is self-contained and can be opened as a local file or served by any static HTTP server. No backend or Bloomberg connection is needed to view this snapshot. This change does not implement a new live refresh scheduler.

```
python -B -m tools.inflation_dashboard_r35.build --analysis output/momentum_r35/final --output output/inflation_dashboard_r35
node tools/inflation_dashboard_r35/browser_check.cjs file:///ABSOLUTE/PATH/index.html work/new-r35-browser-check
```

Use new output directories. Rehearsal analysis requires --rehearsal on the dashboard build. The loader verifies source/code/output hashes and analysis semantics before exporting. Browser checks exercise desktop/mobile rendering, category/group selection, sorting, heatmap accessibility, current forecast/CNB replay and unchanged scenario baseline.
