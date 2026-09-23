# R35 observed category inputs

Ready prepared source: `output/momentum_r35_inputs/prepared_20260922_v1`.
Raw source capture: `output/momentum_r35_inputs/capture_20260922`.

These are current-vintage descriptive inputs. They do not update any frozen forecast, perform seasonal adjustment or calculate momentum. Parent modules own those stages.

## Ready snapshot

- Complete January 2015–August 2026: **140 monthly observations × 37 mapped national all-household groups**.
- Source availability: **2026-09-22T21:05:12.058703+00:00**, the actual download completion.
- Preparation: **2026-09-22T21:11:45.368517+00:00**.
- Frozen overlap: **5,143 cells (139 months × 37 groups), zero changed values**. August adds 37 observations.
- The 37 positive fixed 2026 weights sum to **1000 permille**, without normalization.
- All 17 fresh CSV columns match the frozen schema, and every fresh official category label matches its frozen mapping.
- Prepared MANIFEST.json SHA-256: `5cc208aa8bce7139da2f7e8b0e8a185de37938559864d28823483a9606127b7a`.

Pin the prepared `MANIFEST.json` along with its listed files in the parent analysis archive. This input manifest is source-integrity evidence, not a final analysis or delivery seal. No commit was made by this sidecar.

## API

```python
from tools.momentum_r35.inputs import load_prepared, prepare, capture

inputs = load_prepared(
    'output/momentum_r35_inputs/prepared_20260922_v1',
    as_of=analysis_start_iso,
)
# as_of=None uses actual UTC now.

# Reproduce in new directories only:
capture(new_capture_directory)
inputs = prepare(new_capture_directory, new_prepared_directory, as_of=aware_clock)
```

`prepare(capture_dir, output, *, as_of=None, through='2026-08', frozen_package=...)` and `load_prepared(path, as_of=None)` return exactly:

| Key | Type and contract |
| --- | --- |
| `levels` | pandas DataFrame; sorted, unique monthly PeriodIndex named `period`; 37 positive float columns in frozen CATEGORIES order. |
| `metadata` | DataFrame in the same group order; includes `column`, `label_cs`, `scope_note`, code, sector, scope and source/availability fields. |
| `weights` | Float Series named `weight_permille`, indexed by `group`; all 37 names in level-column order, sum 1000. |
| `provenance` | Dictionary with source paths/hashes, actual clocks, coverage, schema and selection rules, frozen workbook-cell references and full overlap revision audit. |

An explicit decision clock must include a timezone and cannot be in the future. The entire current-vintage source, including its historical observations, becomes available only at retrieval completion. No historical release calendar is invented. Preparation time is separately recorded; it is not passed off as a publication time. The source's revision and classification vintage remain explicit.

## Files

- `monthly_levels.csv`: `period` followed by all 37 group columns; positive observed NSA levels, 2015=100.
- `series_metadata.csv`: frozen group definitions retained; current coverage, retrieval availability, vintage and raw hash updated.
- `weights.csv`: exactly `group,weight_permille`.
- `provenance.json`: source and extraction evidence, fixed-weight definition, current-analysis-only scope and overlap audit.
- `MANIFEST.json`: `files` maps relative output file names to SHA-256; includes the four files above and local `.gitattributes`.

All new text uses explicit UTF-8. Local `* -text` attributes preserve byte hashes. The shared tools-directory attributes, already set by the parent, were not edited.

## Official source and frozen evidence

The source is the exact R18 URL: [CZSO CEN0101E CSV](https://data.csu.gov.cz/opendata/sady/CEN0101E/distribuce/csv). The capture stores `CEN0101E.csv.gz`, `request.json` and `MANIFEST.json`. Gzip uses mtime=0; decompressing reproduces the original **66,269,310 response bytes**. Their SHA-256 is:

`da38ba0d08f5de15435df54c1db8d2c3b25baaadd3739f762992dbf649cec56c`.

`request.json` retains the URL, final response URL, response headers, retrieval start/completion, original byte count/hash and compression description. The manifest hashes the compressed archive and request evidence. No data is interpolated or reconstructed.

Preparation verifies every `data/research_r18/categories/manifest.json` entry, the unchanged `tools/research_r18/category_inputs.py` builder hash and decompressed frozen raw hash. It checks the frozen metadata against every CATEGORIES code/name/sector/scope mapping. Each mapped 2026 weight is checked against its retained original `raw/spot_kos2026.xlsx` sheet, label, code and E-column cell. Effective year 2026 and expenditure basis 2024 are required.

Fresh extraction uses the unchanged R18 `extract_levels` only after exact ordered-column comparison. Selection remains indicator **6134**, index type **IZ2015**, household population **0**, geography **CZ**, and monthly `YYYY-MM` codes. Original group/division mappings preserve leading zeros. Every selected label must still match the frozen official label. A changed source schema or scope requires review rather than an automatic adapter.

The source includes other index types and household/geographic populations. These are excluded by the frozen exact selector, never used as substitutes for missing national all-household rows. All 37 mapped series must be contiguous from January 2015 through the declared endpoint; duplicate, nonpositive, nonfinite, missing or extra/future observations fail.

Frozen metadata's primary-measurement flag is retained as historical documentation; it does not restrict this 37-group panel or declare CNB-core membership. Vehicle operation retains its fuel/parts/repairs/service scope. Blocks, rent splitting and analytical aggregation belong to the parent analysis.

## Revisions and loading

`overlap_revision_audit` contains compared cell count, months, changed-cell count, maximum absolute level change, affected groups, and one `{period,group,old,new,delta}` record per changed cell. The current capture has no revisions. A synthetic recorded revision is tested and accepted for current analysis; the frozen snapshot is never overwritten.

Every load validates the prepared hashes and revalidates the original source archives, clocks, frozen parser/metadata and workbook evidence. It re-extracts levels from verified raw bytes and compares them exactly to the prepared matrix, verifies weights/metadata against their definitions, and recomputes the revision audit. Simply rehashing an altered prepared matrix or redistributing weights while retaining a 1000 total cannot bypass these checks.

## CLI and tests

From the repository root:

```powershell
$env:PYTHONPATH='C:/Users/luis_/AppData/Local/Temp/cpi-r32-runtime;../pythonlibs'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$python='C:/Users/luis_/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'

& $python -B -m tools.momentum_r35.inputs verify `
  --prepared output/momentum_r35_inputs/prepared_20260922_v1

& $python -B -m unittest tools.momentum_r35.test_inputs -v

# Optional fresh reproduction: destinations must not exist.
& $python -B -m tools.momentum_r35.inputs capture `
  --output output/momentum_r35_inputs/NEW_CAPTURE
& $python -B -m tools.momentum_r35.inputs prepare `
  --capture output/momentum_r35_inputs/NEW_CAPTURE `
  --output output/momentum_r35_inputs/NEW_PREPARED
```

**20 tests pass.** The suite failed before implementation. A focused label-change regression separately failed before its guard and then passed. Cases cover missing/duplicate/nonpositive observations, wrong populations/geography/indicator/index type, irrelevant-population isolation, schema and scope changes, future months, naive and future/earlier capture clocks, incorrect source URL, compressed/raw/output integrity, overwrite refusal, revision acceptance/audit, exact round-trip shapes, optional as-of, and both invalid weight totals and allocations.

Review confirmed the fresh labels and full frozen-source integrity on the actual capture. The real prepared bundle passed `load_prepared` with its complete source checks. Existing captures, R34/R18 code/data, seasonal, analysis and dashboard modules were not modified; no model, forecast, seasonal or final-analysis call was run.
