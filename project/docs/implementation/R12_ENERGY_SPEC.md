# R12 all-month energy/admin evidence experiment

Specification written on 2026-09-09 before implementation, fitting or scoring.
Parent must commit this file before the first experiment run. Frozen baseline:
`c1dacdf4ec946bd5d59d0d7f96876ad9efd1f0a3`. Parent plan: R12_EXPERIMENT_PLAN_2026-09-09.md.

## Question and bounded candidates

Can independently dated energy events improve the existing release-eve administered
forecast outside January without importing realised price shocks or assuming unknown
household exposure? The existing January forecast is preserved as the comparator;
this experiment does not certify its retrospective mappings as strict evidence.

1. BASE: exactly the frozen HARD_BASE and its administered forecast.
2. STRICT_ALL_MONTH_ADDITIONS: BASE plus only a fully evidenced incremental energy
   contribution for a target outside January. Zero eligible additions means BASE is
   retained, with an unavailable candidate effect recorded as null, never disguised
   as a measured zero. January remains unchanged to avoid replacing its existing
   overlapping event treatment without an item-level baseline decomposition.
3. SCENARIO_ONLY: rerun the complete existing R9 monetary scenario grid unchanged,
   including all exposure/split/credit/quantity choices, incomplete exposures and
   rejected negative bills. No fit, CPI-outcome score, best-scenario choice or
   promotion is allowed. No new numeric shock grid will be searched.

There is no event-size threshold or calendar gate in the new accounting API. A
separate experimental integration rule restricts *additions* to non-January targets.
The generic API can handle every month, including January. No retailer collection.

## Exact accounting and eligibility

Reuse `models/energy_ledger.py` for fixed-quantity household bills, policy intervals,
normalised household exposure, ratio of aggregate expenditure levels, cap-before-VAT,
after-tax fixed credits and published basket contribution arithmetic. Do not copy
the engine or modify it. A credit expiry removes only that credit; a continuing levy
waiver remains active. A late or unknown expiry cannot close an earlier interval.

The new wrapper requires explicit evidence records for (a) each baseline bill,
(b) the product/household exposure portfolio, (c) any missing-exposure bounds,
(d) each policy start/expiry's source and treatment methodology, (e) basket weights,
and (f) the embedded energy baseline. Each record contains source identifiers,
SHA-256 snapshot identifiers, a publication/availability timestamp or explicit
unknown, and status `verified` or `scenario_only`. No generic website root, date
invented from retrieval, unsourced assumption, or a label `sourced` alone proves
historical availability. Source audit text will state what a document establishes.

All event source, methodology, bill/input, exposure, baseline and weight clocks must
be known and no later than the forecast cutoff for a strict point contribution.
Snapshots retrieved now establish evidence contents, not archived historical
vintages; `verified` additionally requires a defensible historical publication date.
Date-only source evidence is conservatively available at 23:59:59 UTC. Existing
naive release-eve timestamps are Europe/Prague local time, converted to UTC.
Unknown or late required inputs return an unavailable contribution and reason codes.
Partial household coverage cannot manufacture a point estimate or renormalise the
observed share. Existing explicit bounds may support a scenario envelope only.

Only information visible at the cutoff may construct policy intervals. Unknown
methodology excludes a policy. Future event values cannot alter an earlier usable
forecast. The independent event audit may flag missing evidence for a subsequently
known event, but audit metadata is never a magnitude predictor. A wrapper result
distinguishes no visible transition, unavailable mapping, scenario and strict usable
adjustment. Inputs are immutable; target and previous month must be adjacent.

The integration must state the embedded energy contribution being replaced:
`increment = gross_energy_pp - embedded_energy_pp`. It must not add a gross shock
on top of a seasonal forecast that already contains energy repricing. For a genuine
incremental policy counterfactual, both with-policy and without-policy bills are
needed on the same quantities, exposure and weights; subtract their contributions.
The current aggregate administered seasonal median does not identify item-level
electricity/gas seasonality. Missing decomposition blocks replacement. An explicit
flat or 2% baseline in R9 remains a scenario assumption, not a strict mapping.
Published static basket weights provide a contribution approximation, not exact
official chain-linked CPI accounting; this limitation remains in every result.

## Evidence inventory and permitted source work

Inventory every row of `data/energy_policy_ledger.csv`, preserving start, expiry and
extension links and source/methodology dates. Also explicitly audit the missing
September/November 2022 supplier-repricing evidence and October-2022 saving-tariff
onset. The known problem months justify evidence searches, never shock magnitudes.
Read existing hashed source archives and optionally verify primary public documents
(CZSO, ERU, ministries). Store new source captures only below
`output/research_r12/energy/sources/`, with source URL, retrieval time, historical
publication support, hash and narrowly stated evidentiary role. Numerical outcomes
appearing in source documents must not become same-month predictors.

Known unresolved constraints before running: no complete dated household contract
exposure; no CPI credit-spreading denominator; no baseline energy decomposition;
2021 VAT treatment date absent in current ledger; October-2022 treatment listed as
2022-11-10, the release day; supplier repricing cannot be inferred from realised
regulated inflation. Finding no strict eligible additions is a valid bounded result
and must not be replaced with a retrospective reconstruction to obtain a score gain.

## Replay, scoring and output order

Use all 90 frozen R9 first-release clocks and preserve row order. Recompute the
administered forecasts with `admin_forecast(..., as_of=clock, announce_mode='documented')`
and release-eve solved administered/core weights using frozen cleanup fixtures.
Compare replay with `output/cz_struct_backtest.csv` to tolerance 1e-10. Read only
released histories for computations; test mutation of current/future observations.
Full core/food refitting is unnecessary: their frozen forecasts are reused unchanged.
Write forecast values, addition status/reasons and replay checks before loading the
survey/first-release outcome file for evaluation. Target actuals and consensus are
evaluation-only. Keep BASE, category TARGET_OWN, HARD_HALF and HARD_FULL references.

Report all, recent (target >= 2024-01), ex-January, flash, and large-surprise
(absolute actual-minus-consensus >= 0.4pp, tolerance 1e-9) frames. Within frames:
bias, MAE, RMSE, direction of forecast-minus-consensus relative to realised surprise,
upward/downward large events, material absolute-error gain/loss >= 0.15pp,
and every absolute forecast-minus-consensus alert >= 0.2pp. Direction excludes
exact zero surprises and counts zero forecasts as not directional. Paired uncertainty
is strict-minus-BASE MAE/RMSE using 2,000 circular moving-block resamples of length
6, seed 1209, 2.5/97.5 percentiles. With identical forecasts this is necessarily
[0,0] and is not evidence that an unevaluated event mechanism has no economic value.

All outputs below `output/research_r12/energy/`: forecasts, baseline replay,
event evidence/eligibility audit, scenario replay, scores, release-level alerts,
paired uncertainty, summary/notes and portable source/code/fixture hashes. Store
complete gaps and fallback counts. No existing output or numerical code is edited.
No parameters are fitted and no scenario is selected on historical CPI error.

## Tests first and acceptance

Before implementation, observe failures for the missing new API. Tests must cover
unknown/late publication, methodology, bill, exposure, baseline and weight clocks;
exact timestamp boundaries; future-event and future-input poisoning; target month
adjacency; October start and January credit expiry while POZE persists; exposure
denominators; no point from partial coverage; unavailable vs zero; replacement
and incremental arithmetic; no baseline double-counting; strict rejection of R9
scenario inputs; all-90 admin replay; unchanged strict candidate when evidence is
missing; forecast construction independent of outcome/survey values; and byte/numeric
scenario replay parity. Run existing `test_energy_ledger_r9.py` with new tests.

This is inspected pseudo-OOS history with frozen latest-vintage components, not
a vintage-certified or untouched holdout. Do not describe an unchanged fallback as
a new validated forecaster or claim that closing the calendar gate fixes the misses.
