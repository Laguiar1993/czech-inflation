# R18 national CPI category measurements

Frozen CZSO CEN0101E national-CPI data: **139 months, January 2015–July 2026**,
37 nonoverlapping reported groups/divisions; **18 primary measurements** consisting
of ten goods, two housing and six service groups. These are statistical inputs for
a common/sector trend model. They are not an exhaustive partition of CNB adjusted
core inflation. They retain taxes and have no CNB regulation/membership filter.

## Files and recommended use

`primary_monthly_levels.csv` contains the 18 definition-selected inputs. Start with
these and keep the 19 broader/excluded groups in `monthly_levels.csv` for diagnostics.
`series_metadata.csv` defines every column, the source code, sector, inclusion decision
and scope. Housing should have its own factor because imputed rent represents owner
housing costs. Recreation services include gambling; caterers include school canteens;
accommodation includes student dormitories. These composition issues remain relevant
even though the categories are services. No category was selected using realised
inflation, model performance, likelihood, correlation or later forecast errors.

## Source and definitions

The [official CZSO time-series page](https://csu.gov.cz/produkty/isc_ts) links the
[CEN0101E CSV](https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv). The complete previously audited raw file is retained,
byte for byte after gzip decompression, in `raw/CEN0101E.csv.gz`. Its SHA256 is
`e81dc0dece758d0e89adc88e6f8c31f3ba97f8a68dfa67795a794dbe3b858880`. The original cache is dated September 7, 2026 and was audited on
September 9; its retrieval timestamp is not a historical release vintage. We reused
this frozen file to keep the existing July endpoint, rather than replacing data.
All 695 cells of the old five-group package match exactly.

Selection: indicator 6134, household 0, geography CZ, index type IZ2015, calendar
monthly codes YYYY-MM. Values are NSA index levels with 2015=100; despite the raw
unit symbol %, these rows are index levels, not monthly percentage changes.
No interpolation, rebase, seasonal adjustment or tax adjustment was applied. Convert
after gating with `100*(level_t/level_(t-1)-1)` or an explicitly documented log change.
The level series are rounded; derived monthly changes need not equal published IM.

The frozen source already carries **current COICOP2018 categories back to 2015**.
This is current recoded history, not proof that current group composition was
historically observable. Old 096 was holidays; current 096 is cultural services and
current 098 is holidays. ICT and recreation were rearranged across groups/divisions.
Do not connect old and new numeric codes by equality. No historical item-level
concordance or first-release vintages have been reconstructed. The live schema now
has different time/geography columns, so refresh requires a reviewed schema adapter.

## Availability and leakage limits

`availability.csv` repeats the existing calendar's **detailed** CPI date, never its
earlier flash date. A level is eligible only when `available_from <= origin` in
Europe/Prague, and its reference month is strictly before the origin month. The
existing experiment's approved midnight date convention is preserved. Source
calendar rows are retained, including their Bloomberg/CZSO provenance; these are
historical availability assumptions, not archived releases. Missing gates fail
closed. `load_categories()` verifies all package hashes; then call `levels_asof()`
before transforming or fitting. Latest-vintage history can still contain revisions
and later classification recoding: a calendar gate is not a true real-time vintage.

## Weights and mapping limits

Official [basket archive](https://csu.gov.cz/spotrebni_kos_archiv) workbooks for even
years 2014–2026 are saved unchanged. `basket_weights_long.csv` extracts original
division/group/class labels and weights with sheet/cell references. Headers identify
constant weights from effective year minus two. Pre-2026 canonical mappings are
provided only for the five previously audited groups. Other historical codes remain
native and unmapped; 2026 codes match the current classification. Odd-year files
were not acquired, and historical workbook publication dates are unverified.
Their availability field is the existing January detailed-release proxy (February
15 fallback); only regimes effective no later than an origin year and published
by that origin could be used for a later diagnostic. The primary 2026 base weights
sum to 400.908236 per mille of headline CPI;
this is context only, not core coverage or historical/current expenditure shares.
No weights enter the primary measurement recommendation or loader.

Base weights cannot directly reconstruct monthly official contributions: this
requires price updating, validated regime/concordance selection and tax/regulation
reconciliation. The CNB adjusted-core target must remain a separate measurement
with explicit mapping/residual error. HICP is not substituted for national CPI;
in particular national CPI owner housing differs. No exact weighted core total
is offered by this package.

## Reproducibility and alternatives

`manifest.json` hashes every frozen file. `metadata.json` records coverage, gates,
transformation, validation and alternatives. `raw/online_verification/` contains
public source-page/schema/manual snapshots and a URL/retrieval/hash log when the
direct download succeeded. The web tool confirmed official CSV/XLSX links but does
not render those binary formats; the DataStat information page needed JavaScript;
the Firecrawl CLI was unavailable. Eurostat HICP was unnecessary after locating
the fuller national dataset; ARAD broad year-on-year rates cannot replace monthly
category levels. No existing package, manifest, fit or model path was modified.

Build a *new* destination using `tools/research_r18/category_inputs.py --raw PATH
--output NEW_PATH`. It requires the exact previously audited raw checksum and
refuses to overwrite a package. All raw/package paths are portable after freezing.
