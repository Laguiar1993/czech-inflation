# R13 nowcast family declaration — 9 September 2026

Status: declaration before empirical fitting. This experiment cannot promote an
operating model. The first-release survey is evaluation-only. No retailer work,
expectations, ESI, tuned penalties, alternate forest settings, or selected blends.

## Fixed question and forecasts

Compare the unchanged aggregate-core BASE and unchanged simple category-core
TARGET_OWN under raw, half, and full corrections learned from each family's OWN
sequential raw core forecast errors. Error sign is actual core minus raw core
forecast. Add 0, 0.5, or 1 times the predicted core error, multiplied by the
forecast origin's solved core weight, to that family's raw headline forecast.
The non-core headline contribution is identical across every forecast at an
origin. The old TARGET_OWN_HALF is a BASE/category blend and is not used here.

Retain published R9_BASE, R9_HALF, R9_FULL unchanged. CATEGORY_RAW must reproduce
TARGET_OWN at every one of the 90 fixed origins. New CATEGORY_HALF_CORRECTION and
CATEGORY_FULL_CORRECTION use only category errors. BASE_MATCHED_HALF and
BASE_MATCHED_FULL retain BASE raw forecasts and reconstruct BASE's own errors at
the same 23:59 clocks and finite category error dates. These matched controls are required
to separate model architecture from the different historical warmup lengths.

## Clocks and historical reconstruction

Category and scored decisions are the existing first-release calendar eve at
23:59 Prague wall time, matching the saved R9/R10 as_of_eve exactly. The unchanged
legacy BASE sequential-errors helper reconstructs its own historical raw forecasts
at 09:00 on release eve; keep that inherited convention for legacy parity and
disclose it separately. New matched BASE histories instead use 23:59, identical
to the category clocks. Legacy-versus-matched comparisons can therefore reflect
both clock convention and history length, not just warmup length.
Detailed core/category outcomes become eligible only
at their detailed CPI release at 09:00. Ordinary first release is the outcome
before 2025; flash is the first-release outcome from January 2025. Unknown modern
release dates fail closed. The existing conservative pre-calendar twentieth-day
rule is retained only for the legacy aggregate error replay.

Rebuild every feasible historical category raw forecast in chronological order.
At historical origin u, independently solve headline component weights using
only outcomes detailed-released by that origin's decision time. Select the five
category basket fractions effective and available at that same historical time.
Reconstruct the category/remainder training targets with those u weights, and
fit the same six expanding ridge equations (alpha 3, 48 prior common labels,
own lags 1/2/12, month dummies). Never use a later origin's weights to recompute
an earlier forecast. The remainder remains a statistical core/tax/reconciliation
projection, not an official category. Save all attempted historical dates,
forecast/error, release date, origin weights, fit training bounds and statuses.

The frozen category levels begin January 2015; m/m rates begin February 2015.
With the unchanged 48-observation requirement, the earliest feasible forecast
is February 2019. Thus there is no category pre-evaluation forecast history.
The fixed residual forest needs 40 released errors, so the expected first 40
scored origins return a documented zero correction for both matched families.
Do not shorten either warmup or substitute fitted/in-sample residuals.

Correction predictors are the existing availability-masked hard feature frame,
with all expectation columns and ESI removed. Every historical error retains its
own origin forecast. The residual learner is the existing residual_correction
API: 200 trees, minimum leaf 3, max_features 1, seed 42, validation length
min(12, max(floor(n_errors/5), 4)) (8 at 40 errors; capped at 12 from 60),
half-life 6, quantiles .10/.25/.50/.75/.90 and existing constrained quantile bounds.
No search or category-specific forest change. Preserve the legacy feature-history
convention (latest-vintage publication-shifted feature rows, origin row masking).
Insufficient errors or forest failure return zero with distinct audit statuses;
never drop a scored origin to improve coverage. BASE matched and category error
dates must match before each correction fit, including release eligibility.

## Fixed scoring and diagnostics

Use exactly February 2019–July 2026, N=90, the same first-release survey and
outcomes as R12. Save own/common results, recent 2024+, ex-January, flash 2025+,
large events, large up/down events, and all-release alerts. Large means absolute
actual-minus-survey >=0.4pp; material win/loss means absolute-error improvement or
deterioration versus survey >=0.15pp; alert means absolute forecast-minus-survey
>=0.2pp, with the established 1e-9 threshold tolerance. Show false alarms and
missed large events. Add common post-warmup results when both matched correction
models have >=40 eligible errors and successful fits; save its exact dates and
remaining large-event count. Full90 includes every zero-correction warmup row.

Use paired circular block bootstrap, 5,000 draws, seed42, 95% percentile intervals:
12-month primary with 6/18 sensitivity; full and recent windows, plus the common
post-warmup window. Predetermined pairings: every new forecast against R9_BASE;
category corrections against category raw; corresponding category/matched-BASE
corrections; matched-BASE half/full against legacy R9 half/full. Report RMSE and
MAE differences without selecting a winning block length. No event-subset bootstrap
that mistakes sparse large events for consecutive calendar months.

Retain core RMSE/MAE, exact weighted core versus fixed non-core/reconciliation
error decomposition and all leave-one-origin-out RMSE comparisons against BASE.
Additional within-family pairwise attribution and omission diagnostics cover
category correction versus raw and category correction versus matched BASE.
Headline MSE gains must equal weighted-core gains plus changed cross terms.

## Tests first and implementation sequence

1. Write synthetic failing tests for required APIs before implementation. Cover
   category forecast parity, unavailable/future label poisoning, historical
   weight isolation, 48-label warmup, own-error sign, detailed-versus-flash release
   admission, missing dates, matched error calendars and 40-error fallback.
2. Commit this declaration via the parent before any empirical fit. Synthetic
   tests may be implemented and run while waiting; empirical execution waits
   for the parent's explicit declaration-committed message.
3. Add only models/nowcast_family_r13.py, nowcast_family_experiment_r13.py and
   test_nowcast_family_r13.py. Reuse frozen numerical primitives unchanged.
   The minimal category-only solver must verify exact TARGET_OWN parity at all90.
4. Rebuild the legacy BASE sequential error history and check the saved R9
   error series; retain published comparators and verify correction parity.
   Rebuild category histories and matched BASE raw histories at the same 23:59
   clocks, save forecasts before
   reading survey outcomes, and produce the prespecified diagnostics.
5. Run deterministic offline --verify: block sockets, HTTP and database access,
   freshly refit all histories and forests into a temporary directory, and
   compare every output hash (not merely re-score saved forecasts). Verify
   frozen inputs/fixtures and all numerical dependencies before and after run.
6. Test all90 parity, midpoint/accounting identities, forecast completeness,
   direction/materiality thresholds, a synthetic predictor published between
   09:00 and 23:59, post-warmup sample and error-calendar
   admission. Report fallback counts and substantive limitations to the parent.

## Scope and reproducibility

New outputs are confined to output/research_r13/nowcast/. Old numerical modules,
input snapshots and results remain untouched. Manifest input hashes include the
declaration, new code, reused numerical dependencies, fixed source package,
fixtures, calendar and retained reference outputs. Record deterministic outputs
separately from the timestamped manifest. No live source updates.

The sources are frozen latest-vintage histories with reconstructed availability,
not genuine historical vintages. Both the repeatedly inspected full90 and the
post-warmup subsample are reused research data, not untouched holdouts. The long
category warmup also excludes early shocks from the active-correction comparison.
Conditional large-surprise success does not identify large events in advance.

Pre-score implementation clarification: the first empirical attempt stopped at
the first origin clock assertion before residual forests or scoring. It exposed
the difference between saved 23:59 forecast clocks and the legacy 09:00 helper.
The reconstruction above preserves the saved raw models and uses identical
23:59 clocks for the new matched-family comparison.
