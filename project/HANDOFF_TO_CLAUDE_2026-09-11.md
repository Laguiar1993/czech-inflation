# Handoff to Claude — Czech CPI model and CNB-paper replication

Date: 11 September 2026  
Prepared by: Codex  
Purpose: resume the Czech CPI forecasting work without losing the distinction
between the operating independent nowcast, the path model, and the separate
CNB Working Paper 9/2026 replication lane.

## Read this first

The active Codex checkout is:

`C:\Users\luis_\Documents\Codex\2026-09-05\c-users-luis-appdata-local-temp\work\cpi-independent`

Current branch: `codex/independent-cpi-20260909`. The latest committed point
there is `709d4b3`; the working tree contains substantial uncommitted research
and output files. Do not reset or clean the tree. Claude's separate worktree
is:

`C:\Users\luis_\Downloads\czk-cpi-nowcast_extracted\czk-cpi-nowcast`

It is on branch `codex-p0` at `47c0e6f` and also has uncommitted path work. The
two directories are linked worktrees of the same Git repository, but their
working files are different. Review both before merging or committing.

The user asked to remove the invalid `EEUR3CZ Index` ticker. That change is
already made in `tools/market_data/pull_bloomberg.py`; the configuration test
now asserts that it is absent. The valid canonical ticker is `EUR3CZ Index`.
The immutable Bloomberg capture still retains the failed diagnostic row for
audit history; do not edit that old capture.

## Latest Bloomberg capture

The full current-vintage capture is:

`data\market_snapshots\20260911_bloomberg_full_refresh\`

It was pulled through 10 September 2026 with Bloomberg Desktop API/xbbg
(`xbbg 0.7.7`, `blpapi 3.25.5.1`, `pandas 1.4.4`). It contains:

- 66 requested tickers;
- 65 successful BDH histories and 65 usable BDP metadata records;
- 65 daily series in `daily.csv`, plus raw BDH/BDP files;
- `coverage.csv`, `metadata.json`, `errors.json`, `request.json` and
  `MANIFEST.json`.

The only error is `EEUR3CZ Index`, with no BDH or BDP response. This is the
known spelling error, not a connection failure. `EUR3CZ Index` returned from
2000-01 through August 2026. `CZIPITS Index` is labelled `Index SA`, and
`CZIPITN Index` is labelled `Index NSA`. Market prices run through 10 September;
monthly survey/statistical series naturally stop at their latest July/August
release. The manifest was independently checked after the pull.

The previous folder
`data\market_snapshots\20260911_bloomberg_full_clean\` is an earlier narrower
capture and remains immutable. The Bloomberg data are current-vintage histories,
not historical publication vintages. Their `ECO_RELEASE_DT` fields are current
next-release metadata, not a historical release archive.

## External Czech data and papers

Not everything is physically inside the checkout. The user's durable external
evidence folder is:

`C:\Users\luis_\OneDrive\Ambiente de Trabalho\Czech\`

It contains the original model-input files (`cz_predictor_panel.parquet`,
`cz_target_and_components.parquet`, weekly fuel, heating oil, HPI, M3,
services CPI, agricultural staples, regulated-price and target files), the
availability notes, and the closed replication packages
`CZ_STRUCT_REPLICATION` and `CZ_STRUCT_REPLICATION_v2`. It also contains the
CNB paper and supporting inflation papers, including the CNB WP 9/2026,
Blockwise Boosted Inflation, Medeiros et al., Hauzenberger et al., and the
other PDFs referenced in the repository notes. These files are inputs/evidence
for the model, not generated code.

The older Claude scratchpad under
`C:\Users\luis_\AppData\Local\Temp\claude\...` is temporary and should not be
treated as the durable source of truth. The repository, its Git history, the
OneDrive Czech folder and the immutable Bloomberg snapshot folders are the
durable locations.

## What the project contains

### Operating independent nowcast

The production independent nowcast is the no-survey lane in
`forecast_independent.py` and the associated `models/`/`data/` files. It is the
user's primary short-term product and deliberately excludes professional or
household inflation expectations and broad confidence balances. HALF/FULL and
survey-conditioned variants remain labelled challengers or comparisons. The
nowcast and the path forecast must not be conflated.

### Big data-style challenger

`big_model_experiment.py` and `models/paper_big.py` build a 41-column
official-data panel and run direct h1/h3/h6/h9/h12 TVW-QRF/BBIM-style
challengers under independent, sentiment and full policies. Results are under
`output/big_model_*`. This is a research challenger, not the paper replication.

### CNB Working Paper 9/2026 replication lane

The paper checklist is
`docs/implementation/CNB_WP9_A6_DATA_REQUEST_2026-09-10.md`. It enumerates all
72 A6 predictors, their transforms and the declared May 2002–September 2025
sample. The runner is `paper_replication_experiment.py`; its current panel is
`data/paper_replication/paper_predictor_panel.csv` and its latest archived
results are under `output/cnb_paper_replication_20260910/`.

The current runner is explicitly a closest-data screening run, not an exact
replication. Its manifest reports 15 exact mappings, 21 proxies and 36 missing
predictors. It still reads the older
`data/market_snapshots/20260909_bloomberg_y1/monthly_complete.csv`; the new
11 September snapshot has not yet been imported into the A6 panel. Do not
interpret the old scoreboard as evidence that the new Bloomberg candidates
have been tested.

## Exact replication gaps after the full Bloomberg pull

The new pull closes ticker discovery for many rows but does not automatically
make them exact paper inputs. Of the 36 rows previously declared missing:

### Candidate histories now exist, but require validation and integration

Twenty-eight rows now have Bloomberg candidate histories. They still require
value-by-value matching with the official EC/Eurostat or statistical-authority
series, correct transformation, seasonal-adjustment treatment and a release
clock:

- detailed Czech BCS questions 1–10;
- German confidence questions 18–21;
- Euro-area price-balance questions 27–28;
- detailed Czech confidence/sentiment questions 29–42;
- Czech industry/construction price expectations 67–68;
- German HICP and unemployment (23–24);
- Czech import-price level (26);
- quarterly nominal ULC (17);
- industrial-metals and food-commodity index candidates (62–63).

The relevant Bloomberg aliases are visible in `pull_bloomberg.py` and the raw
BDP files. A mnemonic is not enough to admit a series. For example, `EUS1CZ`
has a good direct annex match for services business situation, while `EUS2CZ`
does not yet match the intended “past three months” question closely enough.
`EUA2CZ` and `EUA4CZ` must be compared against the official consumer financial-
situation expectation question before choosing one. Several retail balances
are NSA and need the paper's declared X-13 handling; do not double-adjust a
series already SA.

### Still genuinely unavailable as exact inputs

- A6 #15: published CNB LUCI total.
- A6 #16: published CNB LUCI wages-and-labour-costs component.
- A6 #50: official agricultural PPI animal-products aggregate.
- A6 #51: official agricultural PPI plant-products aggregate.
- A6 #52: official agricultural PPI agriculture-and-fish aggregate.
- A6 #71: exact perceived-inflation balance as defined by the paper (the
  available household/Euro-area candidates still require confirmation).

A6 #72 is present only as a labelled household price-trend proxy in the old
panel; it still needs the exact paper geography/question match before being
called exact.

The farm-gate basket and the industrial “vegetable and animal oils and fats”
PPI are useful research proxies, but neither is an automatic replacement for
the three official agricultural aggregates.

### Special resolutions

- A6 #4 (`EUS2CZ`) needs the official question/value match resolved.
- A6 #10 needs a value-by-value choice between `EUA2CZ` and `EUA4CZ`.
- A6 #13 (`CZGRIDX`) needs a final geography, unit and revision-clock check;
  its history behaves like a direct monthly permit count, not a cumulative
  year-to-date series.
- A6 #54 must use three-month PRIBOR at month-end. `PRIB03M` is available,
  whereas the old ARAD panel is a monthly average.
- A6 #58 should retain the ARAD VST total as the baseline perimeter. `LONSCZNF`
  is a close ECB/MFI comparison in EUR millions, not a proven identical
  commercial-bank perimeter.
- A6 #64 still lacks the fourth Czech pump-price series, Petrol 98/Super Plus.
  It is a CZSO CENPHMT retrieval gap, not a Bloomberg ticker gap.
- A6 #61–66 contain useful Bloomberg proxies (`TTFGDAHD BCFV`, `BCOMINSP`,
  `BCOMAGSP`, `TTFGCY1`, `FSBTY1`), but the paper's exact index identities and
  Refinitiv 12-month forward vintages are not identified. Keep proxy labels.

## Structural replication problems independent of missing variables

Even a complete ticker panel would not yet reproduce the published score:

1. The paper says all inputs are seasonally adjusted with X-13 before the
   stationarity transform. The current target is the official NSA Czech CPI
   m/m series, and some inputs are already SA. We need a per-origin, one-sided
   X-13/vintage rule that avoids both under-adjustment and double adjustment.
2. The current files are latest-vintage histories. They do not contain the
   paper's original May 2002–September 2025 publication vintages or exact
   historical availability timestamps.
3. Coverage is shorter than the paper for important inputs: detailed PPI
   subsectors begin in 2015, import prices in 2007, and Rushin in 2008.
4. The current QRF is a leaf-weighted/sklearn approximation with a declared
   tree count, not proof of the paper's exact quantile-forest implementation.
5. The signed Czech trade balance can be negative, so an ordinary log
   difference is undefined. The current signed-log workaround is a documented
   approximation, not a paper-confirmed transform.
6. Quarterly ULC needs prospective one-sided Chow–Lin disaggregation.

## Recommended next work for Claude

1. Build an importer that reads
   `data/market_snapshots/20260911_bloomberg_full_refresh/daily.csv` plus its
   metadata and creates a separate monthly candidate panel. Preserve raw
   aliases, observation dates and explicit assumed availability; do not replace
   the old snapshot.
2. Download the official ECFIN archives with
   `tools/paper_replication/download_public_bcs.ps1` (the current
   `data/paper_replication/raw_bcs` directory is empty), then match each
   question by `geo`, sector, question code, answer type and SA flag. Retain
   publication/revision information.
3. Extend/import Petrol 98 and the three official agricultural PPI aggregates;
   investigate whether CNB can provide the two published LUCI series.
4. Update the A6 audit with separate statuses: exact, validated proxy,
   candidate-unvalidated, unavailable, and historical-coverage gap. Do not
   collapse a downloaded candidate into “exact”.
5. Only after the audit is complete, implement the paper transforms, horizon-
   delayed expanding estimation and TVW/QRF scoring. Reproduce h=3, 6, 9 and
   12 on a common eligible window and keep the operating independent nowcast
   outside this lane.
6. Report the exact remaining gaps and a clean comparison against the paper's
   published TVW3 benchmarks. A result using mixed current vintages and proxies
   must be called a screening/challenger result.

## Verification already performed

- Bloomberg refresh completed through 10 September 2026.
- Snapshot manifest hashes verified locally.
- `tests/test_bloomberg_download.py`: **48 passed** after removing the typo.
- The only Bloomberg error is the invalid `EEUR3CZ Index` diagnostic.

## Suggested message to Claude

> Read `HANDOFF_TO_CLAUDE_2026-09-11.md` first. Work from the Codex checkout
> `C:\Users\luis_\Documents\Codex\2026-09-05\c-users-luis-appdata-local-temp\work\cpi-independent`
> and compare it with the Claude `codex-p0` worktree under
> `C:\Users\luis_\Downloads\czk-cpi-nowcast_extracted\czk-cpi-nowcast`.
> The latest Bloomberg capture is
> `data/market_snapshots/20260911_bloomberg_full_refresh`; `EEUR3CZ Index` is
> invalid and has been removed from the active map, while `EUR3CZ Index` is
> valid. Audit the 72-variable CNB WP9 lane, import the new candidate histories
> without calling them exact, resolve the remaining gaps, and preserve the
> independent nowcast and path lanes. Do not reset or clean either worktree.
