# Tuning and vintage review — 9 September 2026

Scope: `models/core_tuning.py`, `core_tuning_experiment.py`,
`forest_tuning_experiment.py`, `data/vintages.py`, their focused tests and saved
evidence. Reviewed against the approved implementation plan, `TUNING.md`,
`FOREST_TUNING.md` and `VINTAGE_FINDINGS.md`. This is a code and reproducibility
review; it does not reclassify the historical experiments as an untouched holdout.

## Stage 1: specification compliance

**Core ridge tuning complies with the declared bounded experiment.** Its twelve
configurations are the fixed alpha grid 0.3/3/30/300 crossed with 60/120/expanding
calendar windows. At least 48 published, strictly earlier core outcomes are
required. Training-only imputation and scaling cannot see the forecast row or
future rows. Each candidate is fitted sequentially at its own decision date;
selection uses the last 36 common published prior core errors and requires 24.
The default and numerical tie rules match the declaration. The selector receives
neither consensus nor headline loss. Although the exported prediction table
contains future actuals for scoring, both the origin and publication filters
exclude them from each decision. All 90 saved selections replay exactly.

Headline attribution holds the noncore reference fixed. It is evaluated against
the same 90 first-release headline outcomes, with separate core/headline and
calendar split scores. The alpha-3 expanding parity checks support the comparison.
The hard policy excludes all four expectation columns and ESI. The estimator
explicitly leaves feature vintages to its caller; applying the existing release
mask at every sourced release eve changes no hard-feature value in this frozen
fixture. This confirms the actual fixture comparison, without granting the API
a general feature-vintage guarantee.

**Forest tuning complies with its separate, fixed experiment.** Its four
leaf/feature configurations, 200 trees, two workers, 12 chronological validation
errors and six-month decay match the declared settings. At least 40 prior
published independent errors are required. Imputation/scaling for the quantile
validation step are fitted on the initial subset, then refitted on the full
eligible history for the forecast. The last twelve errors are reserved even at
the minimum training size. Outer selection minimizes full core residual MSE for
the fixed 0/0.5/1 multipliers over prior common published forecasts; headline,
consensus and alert scores do not enter it. The 18 early insufficient-validation
origins use zero correction. Failed forests remain explicit zero-correction
strategy outcomes rather than disappearing from the comparison.

The forest experiment intentionally uses the independent alpha-3 expanding
ridge's own sequential errors; it is not a joint retuning of the earlier selected
ridge and forest. All **135 supplied error values** independently reproduce at
their historical release-eve clocks with **maximum difference 0.0**. All **90
saved forest selections** replay exactly. Configuration selection is repeated
using only earlier released outcomes; no implicit best-on-all-90 selection was
found. The report appropriately labels this as a follow-on research search and
does not promote it automatically.

**The vintage selector meets the declared release contract.** It requires
timezone-aware clocks and row timestamps, canonical monthly periods, complete
metadata, finite values and full digests. It selects the last eligible vintage
per series/reference month, including exact timestamp equality. Ambiguous keys,
including equivalent UTC timestamps, reject. Date-only archival evidence becomes
available at the next Prague midnight; publication is not inferred from the
reference month. The unemployment API rejects latest-only snapshots and keeps
NSA separate from adjusted data. The delivered archive changes from seasonally
adjusted to then-published trend-cycle history at the documented 2025 release.

## Stage 2: correctness, fixes and evidence

The review found two cache weaknesses and the owner authorized narrow fixes:

1. **Runtime was absent from the forest cache key.** An environment upgrade could
   reuse corrections fitted with older numerical libraries while a new manifest
   reported only the current versions. The recorded original run had zero cache
   hits, so its measured performance was unaffected. The key and cached record
   now include Python plus NumPy, pandas, SciPy, quantile-forest and scikit-learn
   versions. The manifest uses the same runtime-identity function. A regression
   test changes the quantile-forest version and requires a new key and cold fit.
2. **Cached corrections bypassed the finite-result guard.** Fresh fits rejected
   nonfinite results, but JSON cache loading accepted NaN or infinity. Cached
   corrections now undergo the same finite check before return. Three regression
   cases cover NaN and both signs of infinity. Cache loading also checks the
   source and runtime fingerprints in the payload.

All four new cases were observed failing before the fix. All **11 forest tests**
passed afterward. Before these additions, the combined core/forest/vintage/path
input checks passed **54 tests**. The original forest script is preserved byte
for byte at `archive/forest_tuning_before_runtime_fix.py`; its SHA-256 matches the
original experiment manifest's source entry.

Before the cache change, independent verification found:

- All **24 core** and **29 forest** input/source/output hashes matched the saved
  manifests; all 544 forest cache corrections and statuses matched their saved
  prediction rows.
- Both 90-origin selection schedules matched direct selector replay, including
  the exact validation-origin strings and reasons.
- The vintage tests verified all **103 release pages** and their archived table
  hashes. All **42,584 normalized observations** referenced a table digest in
  that manifest. The historical CSV and separately tagged latest snapshot also
  matched the hashes in `source_notes.json`.

The runtime-key cold rerun completed at **08:20:27 UTC in 157.1 seconds**, with
**zero cache hits**, **384 fitted forecasts**, **zero failures** and zero timing
violations. All **544 corrections** and every original prediction field apart
from changed cache metadata matched exactly. The **90-row schedule**, **90-row
release table**, **1,440 event rows**, **112 headline-score rows** and **six core
score rows** were also byte-for-byte unchanged. The fresh manifest records the
current source/runtime hashes. `output/forest_tuning_runtime_verification.json`
retains both sets of artifact hashes and the exact comparison results.

Final isolated verification passed **48 tests** across
`test_core_tuning_r9.py`, `test_forest_tuning_r9.py` and `test_vintages_r9.py`
in 8.51 seconds. After the cold rerun, all **24 core** and **29 forest** hashes
matched again, and all **544 current cache records** matched their saved
corrections and manifest runtime. The scoped whitespace check passed. The path
resume tests are owned by the concurrent path task and are outside this final
test count.

## Interpretation and remaining limits

No remaining target-chronology or selection-leakage finding was identified in
the declared experiment. Core tuning worsens all-sample core RMSE from 0.299717
to 0.312035 and headline RMSE from 0.417952 to 0.419449. Forest selection changes
headline RMSE from 0.417952 to 0.413013, with mixed later-window results. These
match the saved reports and support keeping both searches as research evidence.
The forest alert report distinguishes realized large surprises from alerts:
23 alerts include 8 large surprises and 15 false alarms, with 15 large surprises
missed. These are absolute-error diagnostics, not trading returns.

Historical feature inputs remain reconstructed/latest-vintage research data.
The recovered unemployment archive covers forecast origins from March 2018,
not 2008, despite containing earlier reference observations. The September 2026
download hashes establish the bytes recovered now; they do not prove the source
website never replaced an older attachment. The selector does not cache a
latest-vintage series across decision clocks or substitute one when coverage is
missing. These limits are explicit in the reports and do not require inventing
older vintage coverage.

Tuning manifests generated on Windows use Windows separators in some relative
path keys. A cross-platform evidence reader should normalize those separators;
the vintage archive itself has tested portable paths. Final source/runtime and
run-bundle integrity still need the owner's coordinated freeze after integration.
