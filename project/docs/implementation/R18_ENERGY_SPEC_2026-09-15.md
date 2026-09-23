# R18 household energy exposure research: frozen specification

Frozen 2026-09-15 before scenario outputs. This implements the approved next-stage energy research and does not edit any frozen forecast, fit, score or prior file.

## Decision and scope

Investigate official ERU contract reporting, CZSO expenditure surveys and statistical treatment. A published reporting schema is evidence of fields collected, not an observed exposure dataset. A 2026 retrieval is not a historical publication vintage. No realised CPI or headline outcome may identify missing exposures, prices, denominators or reset months. No national point forecast or national score is produced if any required field remains unsupported.

R17's scalar reset sensitivities become an explicit constant-quantity cohort path: each cohort has its own household mass, base bill, new commodity price and earliest/latest reset month. Household mass is converted into expenditure weighting through its base bill; household counts are never substituted directly for expenditure weights. Policy applies to all eligible contracts while commodity resets apply only to each specified cohort. A single cohort's new commodity price persists after its reset. Missing reset timing is not interpreted as zero repricing.

## Data contracts and gates

`Evidence` records source ID, observed/assumption/unavailable status, source availability timestamp, reference period, population, mapping qualification and whether the source is an archived historical vintage. The gate returns every missing or disqualifying field. Requirements: cohort shares, reset schedule, fixed quantities, tariff components, CPI mapping, item weights and identifiable baseline energy. Aggregate credit additionally requires the comparable fixed expenditure denominator. Historical gates require archived vintage evidence; a current/revised page never retroactively qualifies. A present-day scenario can use a retrieved source fact with its explicit retrieval clock, but assumed exposures still fail the national gate.

`Cohort` contains a unique identifier, household mass in (0,1], a fixed-quantity R9 Bill, replacement commodity price, reset-month interval (or explicit unknown), source availability, evidence status and assumption text. The cohort list must cover one item and unique products; mass cannot exceed one. Incomplete mass is retained. Full synthetic mass still means only a complete assumed portfolio. Source inputs unavailable at the cutoff are excluded by returning unavailable, never by renormalizing the remaining cohorts.

Bill arithmetic reuses `models.energy_ledger`: commodity caps apply to commodity, VAT once to its declared base, policy onset/expiry through levels. Product-level saving credits are rejected in this calculator because CZSO's 2022 treatment requires one national expenditure subtraction. A separate aggregate-credit function requires a comparable denominator and subtracts compensation once. A flag rejects a separate POZE charge or waiver when the supplied regulated component already includes POZE.

Each monthly output includes conditional relative lower/upper bounds to the fixed base month, conditional point only when all specified reset states are known, modeled mass, observed mass and status. Bounds over reset windows are marginal monthly bounds, not a probability interval or a joint worst-case trajectory. Unknown reset timing yields unavailable. Missing household mass can produce only a bounded result when explicit positive bill bounds are provided; no missing mass is set to zero. Baseline replacement uses the scenario-minus-baseline relative once and is unavailable without an identified same-period, same-item baseline and weights.

## Frozen scenario grid

Purpose: demonstrate contract timing and expenditure weighting with sourced supplier commodity levels, not estimate national inflation. Use the CEZ December 30 2025 release's electricity D02 commodity prices 3430 and 3190 CZK/MWh excluding VAT. Gas is not assigned an equivalent CEZ cohort because the R17 audit flags inconsistent product wording. The source's combined 1.6 million electricity/gas customer count never becomes a fuel-specific or national weight.

Fixed assumed electricity cohorts each have one third of household mass; annual quantities 1, 3.5 and 10 MWh. Each uses a constant 1500 CZK/MWh distribution component, 100 CZK monthly fixed fees and 21% VAT. These denominator components and all household shares are assumptions. POZE has a 495 CZK/MWh assumed cap-binding base bill; the sourced January 2026 zero schedule is applied as a levy waiver known December 29 2025. This is a policy-only cap-binding illustration, not a complete 2025-to-2026 tariff replacement: other regulated prices are explicitly held constant. The source gate for the combined supplier scenario is December 30 2025 end-of-day UTC; the earliest runner cutoff is December 31 2025.

Output months January-December 2026 relative to December 2025. Scenario A resets every cohort January 2026. Scenario B resets cohorts January/April/July 2026 respectively. Scenario C allows each cohort to reset from January through December 2026, producing an envelope without choosing a midpoint. Scenario D leaves timing unknown and produces unavailable. Scenario E uses only the first two cohorts (two-thirds modeled mass) with explicitly assumed missing-cohort base monthly bills [1000,6000] CZK and target monthly bills [900,6600] CZK, producing conservative bounds only. These grids are frozen before computation, with no outcome fitting or selection.

## Implementation and verification plan

1. Archive public official source pages, ERU schemas and methodological manual under `work/research_r18_energy/sources`; record URLs, retrieval dates and SHA-256 hashes. Extract the field inventory and keep schema availability separate from actual observations.
2. Create source/evidence and exact-field-gap CSVs under `data/research_r18/energy`. Preserve unknown numeric values as empty fields. Report any exposure counts only with the precise source population and period.
3. Write tests in `tests/test_energy_exposure_r18.py` before the model. Test inverse VAT/credit policy factors, count-to-expenditure weighting, cohort mass, reset persistence/windows/unknowns, unsupported source gating, incomplete mass bounds, no POZE double counting and baseline replacement.
4. Implement `models/energy_exposure_r18.py` and the reproducible `tools/research_r18/energy_exposure.py` runner. Run the tests then the frozen scenarios. Record the specification hash with outputs; write only within assigned R18 paths.
5. Verify outputs and publish the bounded research result, concrete data acquisition fields and remaining national eligibility failure. No emails or external messages are sent.

## Expected research limitation

ERU 2026 schema data can improve future supplier/contract aggregation if an actual extract is available. It does not contain individual contract expiry dates. CZSO turnover/MWh surveys describe realised expenditure with changing consumption, not automatically the fixed CPI expenditure base used for the 2022 saving tariff. HICP inventory describes turnover-based tariff provider weights, but those are not a released historical national CPI cohort matrix. All three mappings require explicit evidence before national use.
