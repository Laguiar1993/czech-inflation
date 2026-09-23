# CNB tables, gap attribution and the revision tracker — results

17 September 2026, Claude. This is a **conditioned lane**: it uses CNB forecasts. Nothing here enters the independent forecast. Specification: `docs/implementation/CNB_TRACKER_SPEC_2026-09-17.md`, committed before any regression.

**Outcome: two tools worth keeping, one model that is not established.** The archive of CNB tables and the block attribution of our gaps against CNB work and are already informative. The regression tracker of CNB revisions does not meet its declared bar and should not be used as a forecast of revisions.

## 1. CNB forecast tables, archived

`data/cnb_mpr_tables_20260917/` holds the macro-indicator spreadsheet of all 19 reports (February 2022 to August 2026) with SHA-256 hashes, and `cnb_mpr_indicators_long.csv` with every row: headline CPI, core, food including alcohol and tobacco, fuel and administered prices with their basket weights, wages, unit labour costs, the repo rate, 3M PRIBOR, CZK/EUR, and the external assumptions (3M EURIBOR, foreign GDP, HICP and PPI, Brent). A cell is a CNB forecast when it is bold, as the table's footnote says.

Checks: the parsed quarterly CPI equals `data/cnb_mpr_cpi_quarterly.csv` exactly for every report; the bold flag agrees with that file's date rule in every cell; the four block weights sum to 100% in every report. Rebuild with `python -m tools.cnb_tracker.fetch_tables --output <new directory>`.

## 2. Which block drives our gap against CNB

`tools/cnb_tracker/component_gaps.py` splits model-minus-CNB for a target quarter into CNB's own blocks: `w_model * model_rate - w_cnb * cnb_rate` per block, with whatever the blocks do not explain (the nowcast month, the wedge, weight differences) reported as `unexplained` and never forced into a block. Output: `output/cnb_tracker_20260917/component_gaps/`.

Mean contribution gap of FAST against CNB three to four quarters ahead, report clock, percentage points of headline:

| Report year | Core | Food incl. alcohol, tobacco | Fuel | Administered | Unexplained |
|---|---:|---:|---:|---:|---:|
| 2022 | +2.64 | +0.58 | 0.00 | −1.67 | +0.16 |
| 2023 | +1.35 | +0.87 | +0.04 | −1.11 | −0.01 |
| 2024 | −0.08 | **+0.49** | +0.07 | −0.03 | −0.30 |
| 2025 | −0.05 | **+0.52** | +0.07 | −0.02 | −0.21 |
| 2026 | +0.27 | −0.02 | +0.24 | −0.09 | −0.29 |

In 2022–23 the disagreement was core (we were far more persistent than CNB) against administered prices (CNB assumed more regulated-price inflation than our seasonal baseline). **In 2024–25 the whole systematic gap was food**, the block whose drift R24 found biased. With the R24 food drift the 2024 and 2025 food gaps fall to +0.20 and +0.25. The unexplained term has an RMS of 0.57pp over all rows and about −0.2 to −0.3 on average since 2024; it is an accounting limit, stated rather than hidden.

The lead test's calls can now be labelled by driver (`first_calls_with_driver.csv`). For FAST at the report clock and 0.30pp: core-driven calls 3 gains and 6 losses; food-driven 1 gain, 2 immaterial, 2 losses; administered-driven 0 and 2; unexplained-driven 0 and 3.

## 3. The revision tracker: not established

18 consecutive report pairs. Predictors known by the next cutoff: CNB's own forecast error for the quarter of the previous report (`cpi_news`, also split into core and noncore contributions), the koruna against the assumed path, Brent against the assumed path. Targets: the revision of the CPI forecast for the quarter of the next report and the three after it (j = 0 to 3). Ordinary least squares without an intercept; leave-one-pair-out and an expanding window from the ninth pair.

| Scheme | Model | RMSE j=2 | RMSE j=3 | Zero-revision RMSE j=2 / j=3 | Sign hits j=2 | Sign hits j=3 |
|---|---|---:|---:|---:|---:|---:|
| Leave one out (18) | CPI news | 2.86 | 3.00 | 2.49 / 2.32 | 67% of 15 | 25% of 12 |
| Leave one out (18) | CPI, koruna, oil | 2.83 | 2.94 | 2.49 / 2.32 | 67% of 15 | 58% of 12 |
| Expanding (10) | CPI news | 0.484 | 0.524 | 0.488 / 0.491 | 67% of 9 | 40% of 5 |
| Expanding (10) | CPI, koruna, oil | 1.64 | 1.70 | 0.488 / 0.491 | 78% of 9 | 80% of 5 |

Sign hits count revisions of at least 0.15pp. **The declared bar required an RMSE below the zero-revision benchmark under both schemes. No model meets it.** The reason is visible in the coefficients: the four 2022 pairs carry revisions of +6 to +8pp alongside an oil surprise of +37%, so the estimated oil coefficient (+0.06pp per 1%) is several times any plausible pass-through, and it wrecks out-of-sample predictions in calm periods (RMSE 1.4 to 1.7 on pairs from 2023 against 0.44 to 0.46 for zero revision).

What can be said, descriptively and on very few rows:

- CNB's own near-term error does carry into its next forecast: the full-sample coefficient on `cpi_news` is 0.9 to 1.3 for j = 0 to 2 (t about 2.1 to 2.3) and 0.4 at j = 3.
- On the lead-test rows with a material revision, the tracker's sign was right in 67% (15 rows, leave one out) and 78% (9 rows, expanding). The FAST gap's sign was right in 60% and 44% of the same rows; the R24 food-norm gap in 67% and 67%.
- When the independent gap and the tracker agreed in sign, the direction was right in 5 of 6 rows for FAST and 7 of 9 for the food-norm path (leave one out), and in 2 of 2 and 4 of 4 (expanding). This is the "defensible call" idea. It is encouraging and far too small to rely on.

**Use.** Keep the news variables as a descriptive panel next to the disagreement ledger: CNB's error on its own current quarter, the koruna against its assumption, oil against its assumption. Do not publish predicted revisions from these regressions. The natural next declared variant replaces estimated coefficients with pass-through elasticities taken from CNB's own published sensitivity scenarios, which removes the 2022 contamination; it needs those documents opened and cited first, and it has not been run.

## 4. News since the August 2026 cutoff (frozen repository data only)

Against the Summer 2026 report, with data in the repository through 11 September 2026: July inflation was 0.17pp below CNB's forecast for 2026 Q3 (one month of three, so partial), of which core +0.08 and noncore −0.26; the koruna is 0.4% stronger than assumed for 2026 Q4; August Brent was 8.7% above the assumption for 2026 Q4. Prices and the koruna point to a lower CNB path, oil to a higher one. August CPI is not in the frozen inputs. This is a reading of the inputs, not a call.

## Reproduce

```powershell
$env:PYTHONPATH='../pythonlibs'
$cpiPython='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $cpiPython -m pytest tests/test_cnb_tracker.py tests/test_cnb_ledger.py -q -p no:cacheprovider
& $cpiPython -m tools.cnb_tracker.run_component_gaps --root output/research_r24/final --tables data/cnb_mpr_tables_20260917 --output <new directory>
& $cpiPython -m tools.cnb_tracker.revisions --tables data/cnb_mpr_tables_20260917 --lead output/research_r24/final/evaluation --output <new directory>
```

One mechanical defect was fixed between the committed tracker code and its only run: unkeyed table rows made the lookup index non-unique. No result had been produced before the fix.
