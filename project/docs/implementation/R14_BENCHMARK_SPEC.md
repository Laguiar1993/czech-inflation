# R14 benchmark protocol

9 September 2026. Declared before scoring any R14 model against these benchmarks.
The benchmark audit has inspected only source definitions and saved legacy clock
metadata; it has not selected a protocol using new R14 forecast errors.

## Independent forecasts and external benchmarks

FMIE and CNB forecasts are evaluation-only. They do not enter features, trend
estimation, tuning losses, model selection, mixtures or path construction. Every
R14 model retains its independent predictors and frozen numerical specification.
Benchmark availability determines comparison eligibility, never a forecast value.

The official FMIE source has monthly analyst **mean** headline CPI YoY forecasts at
12 and 36 months. The 12-month target is survey_month+12. It is not an average
inflation rate over the next year. No six-month CPI survey exists in this source;
neither 1Y/3Y interpolation nor a shifted endpoint may be called a 6M survey.

## Fixed dated FMIE panel

Use every survey month August 2023-July 2025, giving 24 consecutive twelve-month
targets August 2024-July 2026. These dates were chosen before scoring because all
target outcomes can be available in the frozen evaluation span. Do not remove
months because of errors, delayed English reports or unsupported model horizons.

Source evidence is the corresponding 24 CNB English PDFs and their printed Prague
issue dates. Define `available_from` as **00:00 Europe/Prague on the next calendar
day after the PDF issue date**, localizing after calendar arithmetic. Label this
`DOCUMENT_DATE_NEXT_DAY_RECONSTRUCTED`. It is not an observed website publication
instant, nor proof of the earliest availability of a Czech-language edition.
Survey-month labels and report issue dates remain separate fields. Some reports
are dated in the following month; do not coerce them back to month-end.

Use `fmie_official_panel.csv` as the benchmark value authority: the **published
one-decimal 1Y mean in each report's CPI table on PDF page 4**, independently
extracted and visually verified. The database snapshot has additional digits of
unverified derivation. All 24 1Y and all 24 3Y DB values agree after rounding to
published precision; the largest raw 1Y difference is 0.049776 percentage points.
This does not establish either an official unrounded mean or synthetic data.
Preserve the raw DB values and differences for audit, but do not silently use
their extra precision for primary or bracket scores. Earlier date-calendar and
FIRST_AFTER-only files contain DB values and are metadata/provenance artifacts,
not scoring authorities.

## Primary: custom issue-clock twelve-month comparison

This pre-score addendum supersedes the initially declared LAST_BEFORE primary.
The change follows source-clock reconciliation alone: 22 of 24 archived
LAST_BEFORE paths would require unsupported h13. No new benchmark errors were
inspected to choose this amendment. Archived brackets below remain descriptive.

For each of the 24 surveys, set model origin **t=survey_month**, decision clock
to the report's reconstructed `available_from`, and target to **t+12**. Re-run
`INDEPENDENT_BRIDGE` and exactly the three already declared combined pipelines:
`PIPELINE_FOOD_FUEL_R14`, `PIPELINE_GAP_RIDGE_R14` and `PIPELINE_GAP_RF_R14`.
No new estimator, parameter choice, blend or selected winner is introduced.

Rebuild every current feature and component forecast at that custom clock. A
same-origin saved release-eve state may occur later and must not be reused as the
current state. Historical training states and stored inner candidate forecasts
retain their own historical decision clocks; only states generated before the
custom decision clock may be consumed. Training and selection outcomes must have
all required detail releases available by that clock and target months <=t-1,
even if a delayed report happens to be issued after another CPI release. Apply
the declared source-reference lags and missing-data rules unchanged.

Deliver **h12 annual YoY only** from these custom paths. Its exact compounding
window is t+1,...,t+12, so it excludes h0 mathematically. The bridge API may receive
an explicit h0 placeholder of zero solely to construct its internal path. Before
scoring, prove that changing this placeholder over several materially different
finite valid monthly rates leaves every h1..12 component/monthly forecast and the
h12 annual result unchanged. Independently check annual h12 as
100*(product over h1..12 of (1+headline_monthly[h]/100)-1). If future legs depend
on the placeholder, the comparison fails validation and cannot be scored.
Do not publish or interpret custom h0..11 forecasts derived from this placeholder.

Use identical finite model/survey/outcome rows across all four models. Report all
24 intended rows, own and common coverage, every missing reason, exact targets,
RMSE, MAE and signed bias in YoY percentage points. No report is dropped for a
large error. The source survey has a one-year nominal horizon even when its
document is dated in the following month; retain its survey label and report date
separately. The custom model uses the same reconstructed report clock, but the
survey respondents' earlier information cutoff and actual website posting time
are unknown. Thus this is a **document-date-convention comparison**, not proof of
identical information sets. No significance inference is prescribed for 24
overlapping monthly outcomes. Surveys never enter fitting or inner selection.

## Secondary: archived clock brackets

For each source survey retain both saved model clocks:

1. **LAST_BEFORE, descriptive:** latest model clock strictly before `available_from`.
   This avoids giving the model a more recent information set, while explicitly
   recording its information disadvantage.
2. **FIRST_AFTER, diagnostic:** first model clock at or after `available_from`.
   This represents the closest saved operational update with a potential
   information advantage. Report it separately from the custom-clock comparison.

For both, target stays survey_month+12. Compute model_horizon as the difference
between this target and the selected model origin; do not force it to twelve.
Record signed/model information ages, all source dates and source hashes.
Do not interpolate or extend model values across unsupported horizons.

The declared existing path grid is h0..12. Source-only calendar reconciliation
shows that most LAST_BEFORE comparisons require **h13**, so they must remain
explicit unsupported rows in this experiment. This is a coverage limitation, not
permission to move the survey target, use a later model h0, or select another
clock after inspecting forecast errors. FIRST_AFTER rows have mixed h11/h12.
Report horizon-specific coverage and never describe the whole dated panel as a
uniform twelve-month model forecast comparison. The custom-clock primary above
addresses this coverage problem without extending the path to h13.

Use identical finite model/survey/outcome rows for every submitted R14 model in a
given bracket and horizon. Report intended, supported, available-outcome, own and
common counts; RMSE, MAE and signed bias in YoY percentage points; source target
months and model-origin dates; median/range of clock gaps. Preserve all rows with
an explicit reason for missing comparison. With only two supported LAST_BEFORE rows,
that bracket cannot substantiate a general performance claim. No
significance or bootstrap inference is prescribed for such a tiny panel.

## CNB issue-vintage quarterly path

Reuse the existing dated `data/cnb_mpr_cpi_quarterly.csv` issue vintages and strict
report-clock convention. Select the latest saved model clock strictly before each
report's availability. For every report/target quarter, calculate the simple
average of the model's three exact monthly YoY forecasts; require the complete
quarter and all necessary monthly path steps. Use historically released months
only where the existing matcher permits them. Unavailable future horizons remain
missing. Retain the original realised target definition and one common model
roster per comparison.

Label target quarter, report issue date, model origin/clock, each constituent
monthly horizon and report-to-model age. Report full and recent issue-date panels,
plus horizons/target quarters and coverage. A quarterly-average YoY forecast is a
separate comparison from a monthly h6 or h12 endpoint; do not rename it a six-month
survey. Keep issued-quarter comparisons distinct from the frozen release-eve
6-12 month path scores.

CNB agreement, differences and shared errors are descriptive. CNB error is not an
identified unforeseen shock; model-minus-CNB is not pure misspecification. Repeated
target quarters and different information sets remain visible. No crisis year is
excluded from the declared score panels.

## Frozen artifacts and checks

`data/research_r14/benchmarks/fmie.csv` preserves all 654 raw DB rows plus explicit
survey/target months. Its manifest records the read-only source query, database
file metadata and payload SHA-256. The database was not modified.

`fmie_release_calendar.csv`, `fmie_release_manifest.json` and `fmie_reports/`
retain all 24 document dates and source PDF hashes. `fmie_model_clock_brackets.csv`
and its manifest preserve both protocol clocks and unsupported horizons. The
official panel and `fmie_official_manifest.json` retain published 1Y/3Y means,
database differences and extraction-page/precision evidence. Both-clock brackets
use these official published 1Y means. The
earlier `fmie_model_clock_matches.csv` is the immutable FIRST_AFTER-only extraction,
superseded for protocol purposes by the two-bracket file; it is not another
selected scoring variant. No generic month-end timing sensitivity is needed for
the dated panel.

Before scoring, verify all input hashes, exact survey target/horizon arithmetic,
clock inequalities and timezone handling. After scoring, independently reproduce
metric arithmetic on the same source rows. Freeze benchmark code and report every
declared bracket/coverage outcome without results-driven date adjustments.

### Stable follow-up extension, before its survey-clock scores

When the separately declared R14B food estimator is available, also rerun
STABLE_PIPELINE_R14B and STABLE_LOCAL_CORE_R14B at the same24 clocks, with the
exact combinations fixed in R14B_COMBINATIONS.md. Keep the original four-model
primary table and add matched bridge/new-model/FMIE panels; never replace failed
R14 pipelines in the reported primary table. The stable follow-up was motivated
by observed R14 failures, so its results remain exploratory. Its custom-clock
model uses no survey value and rebuilds food and current core at the issue clock.
