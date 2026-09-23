# R35 category momentum analysis

This is a current-vintage descriptive analysis of observed category prices. It does not rerun, update or feed any forecast. August 2026 observations are separate from the existing September-origin forecast and its earlier clocks.

## Run in new directories

Set PYTHONPATH to the R32 runtime plus ../pythonlibs, PYTHONDONTWRITEBYTECODE=1 and PYTHONIOENCODING=utf-8. Use the bundled Python and installed Census X-13 binary documented in SEASONAL_README.md.

```
python -B -m tools.momentum_r35.build --prepared output/momentum_r35_inputs/prepared_20260922_v1 --output work/new-momentum-check --rehearsal
python -B -m tools.inflation_dashboard_r35.build --analysis work/new-momentum-check --output work/new-dashboard-check --rehearsal
```

Canonical outputs are created once, after code commit, by omitting --rehearsal and selecting new output directories. Never overwrite or regenerate a sealed archive. The frozen R35 source selection ends August 2026; a later endpoint needs a separately declared source capture and validation.

## Interpretation

Nine non-overlapping category rows cover 37 groups and 1000 permille of fixed 2026 weights. Each block uses a weighted geometric index. 3m and 6m rates compound endpoint changes to an annual pace; acceleration compares adjacent, non-overlapping three-month windows from the same X-13 vintage. A positive pace with negative acceleration means prices still rise, more slowly.

The +/-0.25 pp direction threshold is descriptive. Group breadth uses full basket weight, keeping missing groups in the denominator. Driver coverage instead counts only complete emitted category contributions. Missing constituents make that category's driver unavailable; incomplete totals are explicitly partial, with no reported full-basket total. Complete log-rate contributions add exactly; they have different units from the arithmetic annualised rates in the main table.

A triangle exposes residual-seasonality or endpoint-sensitivity checks. The endpoint comparison is July 3m pace estimated through July versus estimated through August, with a 0.5 pp flag. Aggregate and constituent sensitivity are distinguished. Generic X-13 warnings remain in group detail and archived diagnostics. There are no explicit Easter regressors, so travel series require caution. Category y/y is calculated from rounded index levels and can differ slightly from the official published annual rate.

The heatmap and historical charts use today's estimated seasonal factors. They are revised history, not a real-time backtest. All actual source, adjustment and completion clocks are recorded. See INPUTS_README.md and SEASONAL_README.md for source selection, exact settings and diagnostic evidence.
