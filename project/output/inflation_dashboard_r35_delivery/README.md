# R35: category momentum first

The dashboard now opens on a compact nine-category table: seasonally adjusted 3m/6m annualised inflation, change versus the preceding three months, y/y and a twelve-month sparkline. Category clicks open charts and all 37 underlying groups. A heatmap switches between pace and acceleration; weighted drivers show which categories matter most. The current path and historical CNB rounds remain accessible. Longer narrative and the former July overview sit under detail/data views.

## Read this snapshot

Observed category data end in August 2026. The unchanged forecast starts in September 2026. These are different clocks, shown separately. The four headline cards give official August inflation, the September m/m nowcast, December model y/y, and the Q4 gap to the August CNB forecast.

- Cooling means a lower recent pace; it does not necessarily mean falling prices. Actual rents still rise at around 5.1% annualised over three months, down from the preceding pace.
- Food is running at around -6.5% on the same measure. Other services and mixed categories are around 3.6%; catering/accommodation around 4.0%.
- Approximately 64% of basket weight is cooling, 27% picking up, and 9% little changed under the fixed +/-0.25 pp rule.
- Vehicle-operation deceleration dominates the weighted change, but its seasonal endpoint is sensitive. It includes fuel, parts and repairs. Its very large 6m pace also reflects earlier sharp movements; do not treat it as a clean persistent-pressure signal.

These are current-vintage descriptive estimates, not new forecast results or evidence for promoting a model.

## Source and method limits

Fresh official CZSO CEN0101E index levels cover January 2015-August 2026 for 37 groups. No values changed across the 5,143 cells shared with the old July file. Fixed 2026 weights sum to 1000 permille. All data, requests, retrieval clocks and X-13 files are archived under output/momentum_r35_inputs and output/momentum_r35/final.

Each series uses the declared Census X-13 log/autoARIMA/AO-LS-TC/X11 D11 specification. Shocks remain in the adjusted series. There is no explicit Easter regressor. Heatmap history uses the latest estimated seasonal factors and can revise. Six underlying groups have July 3m revisions larger than 0.5 pp when August is added; residual-seasonality warnings are exposed in category detail. A successful software run is not proof of economic adjustment quality.

Displayed categories are analytical fixed-weight geometric aggregates, not official CNB core partitions. Contributions use additive annualised log pp, separately from the arithmetic annualised pace. Missing constituents would remove the entire category from driver coverage, with a partial total explicitly labelled. Published y/y can differ slightly because captured index levels are rounded (for example actual rents: index-derived 6.0% versus the official rounded 6.1%).

## Open and reproduce

The self-contained output/inflation_dashboard_r35/index.html can be opened locally or served by a static HTTP server. It is a dated snapshot, not a new automatic Bloomberg refresh service. The existing Bloomberg forecast/input lane is unchanged.

Use the create-only commands in tools/momentum_r35/README.md and tools/inflation_dashboard_r35/README.md with new directories. Do not overwrite this or earlier sealed outputs. verify.py in this delivery directory is read-only and checks source/code/output hashes, semantic analysis consistency, forecast preservation and browser evidence. DELIVERY_MANIFEST.json records the final source and artifact hashes.
