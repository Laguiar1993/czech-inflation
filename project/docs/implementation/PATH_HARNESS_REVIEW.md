# Independent path harness review — 9 September 2026

The saved path evidence supports the reported horizon comparisons, subject to
the vintage and information-set limits below. No remaining forecast-target or
compounding error was found. A material resume reproducibility gap was reproduced
and repaired; a fresh full replay then produced the same forecast CSV byte for
byte. This review does not turn the comparison into an untouched holdout.

## Scope and verified evidence

Reviewed `independent_path_experiment.py`, `models/path_inputs.py`, their numerical
model interfaces, the release selector, frozen inputs, forecast rows, diagnostics
and score tables. The later component bridge and CNB matching functions received
a separate bounded review. No production forecasting mathematics was changed in
this review. Authorized implementation was limited to runner resume handling and
its regression tests; the bridge author separately fixed an API calendar check.

The complete run contains 90 primary release-eve origins and 133 older control
origins, 986 origin/model paths and 12,818 monthly rows. Each path has h0 through
h12. The primary independent intersection contains 89/87/84/78 observed YoY
targets at h1/h3/h6/h12; adding stored references reduces it to 88/84/78/66.
Missing reference coverage is not silently used to improve a model's score.

The review independently reconstructed 25,168 finite ex-ante/conditional YoY
cells from the monthly paths and frozen history, including their missingness,
and checked 4,048 numeric/count cells in the common-sample summaries. All agreed
with the recorded calculations. No primary path was lost to fit failure: the
403 ML fits include one successful prescribed retry and no fallback. Reference
convergence remains unknown. The common-score regression test demonstrates that
a failed model remains visible in own coverage while scores use the intersection.

## Horizon and label boundaries

At origin t, the caller screens headline observations by the release calendar,
and `prepare_origin` additionally removes every value at or after t. The history
must be finite, monthly and contiguous, and end at t−1. The underlying model's
forecast horizon h+1 therefore corresponds to the reported target t+h; h0 is the
next unobserved CPI month. The exact h1 geometric-growth regression in the model
tests protects the direct BVAR alignment.

For direct RF, a training origin r maps to label y[r+h]. Its regressors contain
headline lags, trailing released inflation, destination calendar dummies and
source drivers at r−1. The final eligible training label is y[t−1], so the last
training origin is t−1−h. Across all 90 primary origins and h1/h3/h6/h12, all 360
last-label checks matched t−1 exactly. Future-outcome poisoning leaves the
origin inputs unchanged. No core outcome is fitted by this path harness: the
independent h0 is an explicit input from the separately evaluated HARD_BASE run.

The target-anchored model uses the fixed target schedule in `target_path`.
Pre-2002, including the pre-1998 history retained here, is approximated by 4%.
This is a declared modeling convention, not archived target-announcement data.

## Unemployment vintages and FX information

Unemployment is selected from the actual historical release archive at the
timezone-aware origin clock. The selector returns the whole historical series
then available, including its then-published adjustments and revisions. All 90
selected series were contiguous, and every selected provenance timestamp was
at or before its decision clock. There was no substitution of today's full
unemployment history into earlier origins. The series follows published SA and
then the 2025 transition to trend-cycle; that change in concept remains labeled.

The state-space transition uses source row s for destination s+1. The U-change
driver at s therefore has destination lag one. FX12[s−2] has destination lag
three. There is no second wrapper lag. At release eve in the month after t,
completed FX month t is available under the declared month-close assumption and
can affect ML destination t+3. Unobserved future FX levels are held flat, rather
than immediately forcing their twelve-month changes to zero; unpublished future
U changes are zero. Missing initial driver history is explicitly neutral and
counted in metadata.

**The future FX scenario is used only by the ML paths.** BVAR truncates its panel
to the last headline month, and RF uses the source drivers at t−1. Neither direct
benchmark consumes the extended future-driver rows. In a controlled February
2024 probe, a 1% increase in the known February FX level left BVAR's input panel
and all RF training/prediction inputs unchanged, while changing the ML source
driver for destination t+3 by 1.064103 pp. With a fixed coefficient of one and
zero gap persistence, the ML forecast changed by exactly that amount. This probe
checks wiring; it is not an estimated economic effect. Results compare these
specified procedures, not model families under identical terminal information.

## Compounding and outcome-vintage interpretation

Every annual forecast uses exactly the twelve calendar months ending at t+h.
Months before t use released history, t uses the supplied independent h0, and
later months use only the model's monthly path. Missing intermediate predictions
produce a missing annual forecast; they are not filled from future actuals.
At h12 the window is t+1 through t+12, so h0 substitution has no effect.

The conditional diagnostic replaces only h0 in this calculation; it does not
condition the estimated state or refit any future monthly path on the release.
Moreover, its `h0_actual` is current stored CPI, not the rounded first-release
print. Comparison with the first non-suspect release table found **86 differences
among 90 origins, maximum 0.0898734177 pp**. May 2026 is 0.189873% in stored CPI
versus a 0.1% first print; January 2026 is 0.837629% versus 0.9%. These differences
include rounding and possibly flash-versus-stored outcomes. They cannot all be
attributed to revisions. The same current stored CPI defines evaluation targets.

The h0 estimates also inherit the independent nowcast's documented cached-driver
limitations. FX is stored history screened by a completed-month assumption.
Consequently, the evidence is retrospective with genuine origin-vintage
unemployment, rather than a fully archived real-time data experiment.

## Resume defect, repair and exact replay

The original runner hashed model files, the U archive and the h0 forecast file,
but omitted the actual CPI/FX arrays and `output/path_step2.csv`. On resume it
could reuse old forecasts while overwriting `frozen_inputs.csv` with changed
database data. That would disconnect the saved forecasts from their advertised
inputs. This was a reproducibility defect even though the present inputs were
stable and the original recorded file hashes matched.

Seven new failing regression cases were observed before the fix. The runner now
hashes exact float64 values, calendar months and missingness in both primary
arrays, and hashes the stored references, relevant source files, release
calendar and numerical package versions. Resume requires the same origin list
and exact fingerprint map before any checkpoint, manifest, diagnostics or frozen
input output is changed. Old manifests fail closed. A test explicitly preserves
all checkpoint bytes on rejection. `--frozen-inputs` loads primary CPI/FX from a
CSV using round-trip float parsing, preserving internal missing months and
rejecting an incomplete monthly grid. This avoids database primary-data reads.

The raw pre-fix runner is retained in
`docs/implementation/archive/independent_path_experiment_before_resume_fix.py`.
Its SHA-256 matches the original manifest's
`55e1513065511632f836fde2f3a5ddc733f3d17e01b44c6857170945a0e2e734`.
Original forecasts, frozen inputs and manifest are saved under
`output/independent_path_pre_resume_fix_*`.

The fresh run used the repaired runner and the preserved frozen input CSV for
all 223 origins. It took 275.2 seconds. **All 128,180 numeric cells, all other
forecast columns, and every forecast CSV byte were identical.** The forecast
SHA-256 remains
`83cb8f37206af9a3a85f14c5d5875aca93a9a7442cb6d572024bd0b0c241b26e`.
The refreshed frozen input CSV only removes the unused leading January 1991
padding row; actual history still starts February 1991. The final receipt is
`output/independent_path_resume_validation.json`. All 17 path-input/resume tests
passed. Final model code and array/reference fingerprints were checked again
against the refreshed manifest.

## Component bridge and CNB extension

The bridge uses hard feature exclusion at every direct core/food horizon and
screens component labels through t−1 at the aware origin clock. Contribution
weights and forecasts sum to the headline path; unknown future basket regimes
retain current weights. Its short-food-history failures are preserved and can
invalidate annual compounding even when a later monthly prediction is finite.
No forecast-expectation feature or legacy future-path prediction enters it.

The CNB matcher chooses the latest generated origin strictly before midnight
Prague on the report date. It computes complete quarterly means of monthly YoY,
using stored actuals only for months preceding that chosen origin and forecasts
thereafter. Incomplete quarters remain missing; scoring uses common report/quarter
rows. Reports have different information timing from the earlier generated
origins, and repeated report/quarter pairs overlap in realized targets. This is
a conservative timing comparison, not a same-instant or independent-sample test.

A reusable bridge API weakness was reproduced: deleting an interior core month
could silently misalign the existing ridge's positional target shift. The bridge
author added a regression and validates the relevant monthly input grids before
calculation, while ignoring irrelevant future grid changes. All actual frozen
bridge monthly frames were independently checked contiguous and duplicate-free,
so the defect did not contaminate the historical run. The bridge author is
responsible for the final run/receipt and its own nine-test verification.
