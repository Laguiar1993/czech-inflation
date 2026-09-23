# R32 engineering review

An independent reviewer checked the approved plan, statistical meaning, quarter alignment, forecast vintages, loader integrity and calendar isolation.

- All 216 historical replay MAEs independently reconcile to the source exports.
- Quarterly averages agree with frozen exports. The latest report has no fabricated matured outcome.
- The reviewer found that the replay table stayed on R27 after changing model selection. The table now follows the first selected independent model and names it in its header. With no independent model selected, no model table is shown. A browser regression failed on the original preview and passed after the fix.
- The reviewer found incomplete current-month FX coverage could pass the adapter preflight. Current-month start and interior-gap guards now apply before constructing MTD FX. Both regression cases failed before the fix and pass after it. The independent reviewer confirmed both findings closed.
- No frozen input, historical calendar, production model or old artifact is modified.

The page is a dated snapshot. The new adapter is an explicit alternative entry point, not an automatic Bloomberg refresh service. September forecasts remain unavailable until the missing source observations and release metadata arrive.

Final focused verification: 44 tests passed (9 dashboard, 35 adapter), with no skips. Real-runtime July forecasts match the archive exactly; maximum contribution difference is 8.33e-17 pp. Chrome desktop/mobile interaction checks passed with no JavaScript errors. Initial-anchor scrolling was removed so the page opens at the top.
