# R31 specification: the Bloomberg input lane for the roster models

22 September 2026, Claude. Declared before the code; committed before the runs. Not a modelling round: no model changes, only the source of its inputs. The question it answers is the user's: with the good Bloomberg series in place of ours, how different are the roster's results?

## What is promoted

Every input of the roster models that the register (`MODEL_REGISTER_2026-09-21.md`) found on Bloomberg as *exact* or *rounding-only* is read from Bloomberg in this lane. The series that Bloomberg does not hold stay where they are. One series that Bloomberg holds as a *different survey* (the nowcast's weekly pump prices) is run as a variant, not promoted by default.

| Input | Bloomberg series, transform | Class |
|---|---|---|
| CNB core m/m (and lags) | `CZCIXM Index`, published m/m | exact |
| CNB regulated m/m | `CZCIRM Index` | exact |
| Weekly pump prices (path fuel block) | `ECOBETCZ`, `ECOBOTCZ Index` ÷ 1000, Friday stamp → ISO-week Monday | exact |
| Headline CPI m/m (nowcast target and wedge; path compounding from 2007) | `CZCPMOM Index` (2015–), `CZCIPM Index` (2007–2014) | rounding |
| Food CPI m/m and lags | `CZCPFMOM Index` | rounding |
| Food CPI level (path food system, R24 drift, R27 gap) | `100·ln(CZCPF / CZCPF_2015-01)` | rounding |
| Alcohol and tobacco m/m | `CZCPAMOM Index` | rounding |
| Import prices m/m, lag 2 | `CZEIIMOM Index` | rounding |
| Food-products PPI m/m, lag 1 | `CZPPA10M Index` | rounding |
| EUR/CZK monthly-average m/m | monthly mean of `EURCZK CNB Curncy`, rounded to 3 dp | rounding |
| Regime state (trailing y/y > 4%) | `CZCPYOY` (2015–), `CZCIPY` (2007–2014) | rounding |
| **Variant B only**: nowcast weekly pump prices | `ECOBETCZ`, `ECOBOTCZ` (EC bulletin) in place of the CZSO CENPHMT survey | different survey |

Stay as they are: the fuel item m/m (weights, wedge), the services proxy, the farm prices, the food-products PPI level, the CPI categories (Category Raw), the 1995–2014 food history, the basket weights, the release calendar, the announcement ledger. The manufacturing PPI (R29B, research line) is not part of the roster.

## What is built

- `data/bloomberg_inputs_20260922/`: a frozen bundle of input frames in the models' own schemas, built by `tools/bloomberg_lane/build_bundle.py` from the 12 and 22 September snapshots (`data/market_snapshots/`), with `provenance.json` (column → ticker, transform, snapshot, coverage, largest gap against the previous source) and `MANIFEST.json` (hashes). Where Bloomberg does not cover a month that the previous source did (before 2007 for the headline history; before 2015 for the CZSO CPI m/m tickers), the previous source's value is kept and the provenance says so.
- `tools/bloomberg_lane/run_nowcast.py`: BASE, HALF and FULL at the 90 recorded release-eve clocks (`forecast_independent.calculate`, the recorded code path) on the bundle; variant A (CZSO pump survey kept) and variant B (EC bulletin). Scores against the same actuals and consensus as the 14 September scoreboards.
- `tools/bloomberg_lane/run_path.py`: the R27 research path at the 90 origins on the bundle: FAST core and administered blocks reused from the recorded run (identical inputs give identical outputs; the register's T1 and T2 are the proof), fuel and alcohol blocks re-run on the bundle, the food block re-run through the R14B system, the R24 drift and the R27 correction on the bundle's food level, h0 from the lane's own BASE (variant A), annual rates compounded on the bundle's headline history. Scored on the 969-key primary support against the previous truth (the unrounded CZSO compounded annual rate, so the numbers are comparable with R27) and, as a second column, against the annual rate compounded from the Bloomberg history; and on the 34 matched CNB pairs from 2024.
- `R31_RESULTS_2026-09-22.md`: the comparison; then the register's "same results" column is updated to the lane's numbers and the lane becomes the declared source for the roster.

## Expectations, written before the runs

From the register's tests: nowcast BASE within 0.05 pp on every print and RMSE within 0.005 in every sample; FULL within 0.08 pp; no large-surprise or alert outcome flips beyond the one or two already seen in the parity test. Path: core, administered and fuel blocks identical; food block within 0.1 pp a month; the R27 h12 RMSE within 0.02 of 4.769 on the full sample and within 0.03 of 0.659 from 2024 against the previous truth; CNB-pair RMSE within 0.01 of 0.405. Variant B: nowcast fuel block RMSE 0.201 against 0.217 over the 90 prints and the headline within 0.001 pp.

## Rules kept

Specification committed before code; code committed before the runs; no hash-frozen file edited; the recorded runs are read only; every number in the results document comes from an exported file.
