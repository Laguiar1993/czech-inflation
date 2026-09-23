# R17 monthly category signals and saved-forecast transmission

Prepared 14 September 2026 before any fitted outcomes in this child experiment.
The hypothesis is that released monthly category pressure and hard domestic or
import-price information forecast future core inflation. This is exploratory
research, not a new holdout or an identified causal supply chain. No tuning after
the full fitted outcomes is permitted.

## Sources, definitions and dates

Use the complete hash-verified `data/core_split` frozen package: monthly levels
for actual rent, imputed rent, catering, accommodation and package holidays,
January 2015–July 2026; and the five category base basket weights and their
declared availability dates. These are current retrieved NSA national service
histories including tax effects, with no exact CNB-core or regulated membership
flags. Catering includes canteens; accommodation includes dormitories. Historical
package-holiday basket 09.6 maps to 09.8 in the 2026 basket as previously audited.
No monthly goods partition is available. Neither broad annual goods/services nor
the old mixed-division service proxy is relabelled as a monthly core category.

Use saved R15 own-origin clocks, FAST core forecasts, two core-state predictors,
and the six frozen hard macro features below. Current-vintage and reconstructed
availability limitations remain visible. No new source, survey, sentiment,
confidence measure, future observed market input or future category input enters.
Verify all original R15/R16 manifest inputs and outputs before and after fitting.

Levels become monthly log rates 100*log(L[m]/L[m−1]); both endpoint detail-CPI
release dates must be known and no later than the origin clock, with both months
strictly before t. Use the saved Czech detail release calendar at 09:00 local
time. January 2015 has no usable change. Missing endpoints remain missing and
calendar gaps are rejected. Detailed release timing is an availability proxy,
not an archived vintage. Weight regimes follow the existing validated
`weights_at` rule: effective year <= origin year, assumption date known at the
clock, date-only assumptions at midnight Prague time. Freeze these weights over
the entire own-origin forecast path; do not borrow future regime weights.

Snapshots cover February 2016–July 2026, 126 own origins. The first origin has
twelve food-independent category monthly changes, one per destination season.
Outer comparisons retain the original 90 monthly origins February 2019–July 2026.
h1 is t+1 with the latest permitted observed category/core month t−1. HARD_BASE
headline h0 and every untouched component stay exact.

## Stage one: pooled category equations

At each own origin s, use the last 96 calendar months of released category log
rates, all if fewer. Separately for each of the five categories calculate its
twelve month-of-year means and sigma=max(0.05, ddof0 standard deviation after
subtracting those means). Save the means, sigma, eligible reference dates and
clock. All twelve seasons must exist for every category; otherwise all category
predictions are explicitly unavailable. Own predictors for each category are
its last one and mean last three contiguous deviations from those own-origin
means, divided by its saved sigma. These transformed predictors are frozen.

Fixed first-stage roster: category persistence, shared AR, domestic, imported,
both. Persistence is destination seasonal mean plus the last-three mean
deviation. Missing own3 explicitly falls back to the seasonal mean. The four
estimated families share coefficients across all five categories:

- AR: two category own predictors.
- Domestic: own plus R15 unemployment_change3, ip_growth3, ulc_growth12.
- Imported: own plus R15 fx3, cost_26_mean3 (import-price input),
  cost_45_mean3 (industrial PPI input).
- Both: own plus all six macro features.

The saved R15 macro transformations and own-origin release gating are preserved;
their different units are handled only by training scaling. All are hard
information; no annual goods/services inflation enters these groups.

For each direct horizon h1..12 pool the five category rows per eligible
historical origin s. Response is (actual log rate[s+h,j]−SAVED seasonal[s,j,
destination month])/SAVED sigma[s,j]. Eligible labels have s+h<t and both
endpoint releases <= the current clock. Every historical feature is the saved
own-origin predictor, not reconstructed with a current fit. For common support
all five own feature pairs and all six macro values must be finite; all five
category responses must be released and finite. Use the latest 96 eligible
origins, minimum 24 origins (120 category rows). Category row order is fixed.

There is no intercept. Scale each pooled regressor by training-only RMS (use 1
when RMS<=1e-12), then minimize mean squared normalized-category response error
plus diagonal ridge penalties. Own coefficients have penalty 0.1; every macro
coefficient has penalty 1. There is no parameter grid or selected penalty. The
shared coefficients avoid unrestricted category-by-category fitting. Convert
each predicted normalized residual back with its current saved category sigma,
then add the destination mean. Missing current predictors or insufficient
history explicitly use the own-origin category persistence path. The current
feature-completeness gate is also common: unavailable current macro inputs make
AR and all macro variants fall back together. No row is
silently dropped. All fallback reasons and training samples are exported.

## Covered pressure, contribution diagnostic and remainder

Let w_j be the own-origin five base expenditure fractions of headline CPI and
W=sum(w_j). For monthly category forecasts r_j in log percentage points form
q_j=100*expm1(r_j/100), the exact simple monthly percentages. The covered pressure
index P=sum((w_j/W)*q_j) is the change of the normalized weighted gross relatives;
its log rate is 100*log1p(P/100). The unnormalized sum sum(w_j*q_j)=W*P is saved
separately as a fixed-base headline-basket contribution diagnostic. It is not an
official current expenditure contribution and W is not an official core share.
Every constituent is required; missing categories propagate rather than
renormalizing the remaining categories. The own-origin weights also apply to
future actual category relatives for scoring the same target definition.

The explicit remainder is core monthly percent minus P, for forecasts and for
released realised outcomes. This is a statistical reconciliation difference,
not a claimed uncovered core component. Core=P+remainder holds exactly in
monthly percentage units. It does not establish a tax-adjusted core partition.
Cumulative pressure compounds the same monthly P values, requiring every month.

## Stage two: core residuals on saved generated forecasts

Save all own-origin category and covered-pressure forecasts to disk before
stage-two fitting; save a second-stage declaration with their SHA256. Generated
forecasts, including declared first-stage fallback forecasts, retain their own
clock, family and generation status. No realised future category value can
replace a generated regressor.

The five core candidates are MONTHLY_OWN_CORE_R17, MONTHLY_AR_CORE_R17,
MONTHLY_DOMESTIC_CORE_R17, MONTHLY_IMPORTED_CORE_R17, MONTHLY_BOTH_CORE_R17.
The baseline at every source s is its saved R15 FAST log-core h1..12 path.
The two own inputs are R15 core3−FAST_mu and core1−core3 at s. AR/domestic/imported/
both add ONE generated input: their saved pressure log forecast at s+h minus
the same-origin pressure persistence log forecast at s+h. The own candidate uses
only the two own inputs. No category actual enters a feature.

For each h fit actual core log[s+h]−saved FAST log[s,h], requiring s+h<t and
the core detail release <= current clock. Use the latest 96 eligible own origins,
minimum 24. Common support across all five families requires finite own inputs,
all four generated increments and the realised label. Historical first-stage
fallback predictions remain legitimate saved forecasts; report the number of
actually estimated generated forecasts separately. If the generated input is
zero for an early training sample, its coefficient stays zero. No unsupported
sample disappears from headline comparisons.

No intercept; training RMS scaling with the same zero-scale rule. Ridge own
penalties are 1, generated-input penalty is 10. These are fixed before fitting.
Missing predictors or insufficient training imply zero correction to FAST, with
explicit fallback labels. Add the learned correction to FAST log-core and convert
with 100*expm1(log/100). No clipping, sign restriction or retrospective tuning.

## Scoring, integration and evidence

Export all 126 own-origin predictions and all 90 outer paths. First-stage scores
cover every category and the fixed-origin covered pressure index against its
own persistence/shared-AR controls: monthly, cumulative log and cumulative simple
percent RMSE/MAE/bias by h1..12 and pooled, full/origins2024+/targets2024+. Keep
primary persistence calendars and jointly finite calendars, missing forecasts,
unreleased targets, and fallback counts explicit. A mechanism improvement claim
requires beating the first-stage controls; an improved core fit alone is not
evidence of a successful upstream forecast.

Score each second-stage core path against preserved FAST on monthly and
cumulative targets. Parent supplies final headline common-calendar/CNB/uncertainty
and combination evaluation. Preserve the old failed R13/R16 evidence. A separate
common-support comparison includes saved CORE_SPLIT_MONTHLY_R13 and
TRANSMISSION_BOTH_R16 core paths; R13's missing early forecasts remain explicit
and do not shrink the main new-model/FAST comparison. Verify these saved output
hashes and expose their source manifests. Retain FAST as a direct comparator.
Replace only future core values/contributions in FAST, with unchanged weights,
noncore values and h0. Recompute total monthly headline, cumulative headline
fields and both annual fields from the changed own-origin path. Missing
components cannot be concealed by summing fewer values.

Write a complete source/code/spec/parameter declaration before fitting and all
outputs into a new destination that must not exist. Tests must fail first for
endpoint releases, future poisoning, own-origin seasonality/scales, shared
training rows, weights across regime changes, exact pressure/remainder arithmetic,
generated-feature lineage, horizon and publication maturity, visible fallback,
train-only pooled scaling, preserved h0/noncore, and exact recomputed accounting.
Smoke and independent numerical checks precede the full replay; full artifacts
and negative findings are preserved without a new outcome-informed grid.
