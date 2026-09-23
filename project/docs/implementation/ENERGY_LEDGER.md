# ENERGY_LEDGER_R9: household monetary bill challenger

Status: implemented research accounting challenger. It is not a production replacement, a validated reconstruction of Czech household CPI, or a retrospectively selected winner. The old `energy_ledger.py`, `energy_accounting.py`, announcement history and production nowcast are not modified by this implementation.

## Purpose and declared experiment

The 9 September review, section 5, asks for monetary bill levels, separate policy start/expiry, all-month availability gating, exposure uncertainty and explicit removal of embedded baseline energy. This specification was fixed before producing the new sensitivity output. No observed CPI outcome enters the computation, no error metric is optimized, and none of the sensitivity points is promoted. A future comparative forecast trial needs a frozen origin set, comparator, source vintage and acceptance rule; this accounting exercise supplies none of that evidence.

The source set is limited to the repository's existing material about 2021–23: energy parameters and policy/announcement archives, the archived June-2022 MPO announcement, 2021 household connection/billed-volume statistics quoted in the parameter notes, and the published 2020/2022 CPI baskets. The experiment reads their values directly and records hashes. Source economic facts and scenario mapping assumptions remain distinct. In particular, a parameter historically labelled `sourced` does not make its household-to-CPI mapping verified.

## Bill and policy arithmetic

For each item/product/household exposure, hold the comparison quantity fixed. With `q` in MWh/month, commodity `c`, distribution `d`, and levy `l` in CZK/MWh **excluding VAT**, and fixed charge `f` in CZK/month **excluding VAT**:

```
charges = {commodity: q*c, distribution: q*d, fixed: f, levy: q*l}
paid_bill = sum(charges) + vat_rate * sum(explicitly_taxable_charges)
            - fixed_credit_CZK_per_month
```

A monetary credit therefore reverses additively. A VAT change acts multiplicatively on its explicitly declared taxable scope. The commodity cap applies to the commodity rate before VAT; distribution, fixed charges and levies remain separate. Source cap prices including VAT must be converted explicitly before entry. The 2023 electricity ceiling of 6,050 CZK/MWh including 21% VAT maps to a 5,000 CZK/MWh commodity ceiling. The API tests this arithmetic; the historical sensitivity does not invent the missing distribution of uncapped contract prices to claim an aggregate cap effect.

`PolicyEvent` contains event ID, policy ID, start/expiry, effective month, item/product targets, kind/value/unit, source publication, CPI-treatment knowledge, `available_from`, source and a mandatory mapping assumption. Start and expiry are separate public events. `policy_intervals` builds `[effective_from, effective_to)` only from events visible by the same cutoff. Expiry can be known in advance; an unavailable expiry cannot silently terminate a visible start. A continuing policy uses an open interval until its known expiry. Multiple incompatible VAT overrides, duplicate events, orphan expiries and mismatched policy targets fail validation. Amendments should receive explicit new policy/event IDs; overwriting or resolving contradictory revisions is outside this bounded version.

Dates include time zones. For archived sources giving only a date, the experiment conservatively uses 23:59:59 UTC on that day. This convention does not claim exact intraday release timing. Missing treatment knowledge excludes the event; callers must distinguish ineligible mapping from an economic zero. The experiment exports `mapping_unavailable` and an empty contribution for these cases.

There is no month-of-year gate or effect-size activation threshold. October-2022 credit onset and January-2023 credit expiry are different events. The MPO announcement of 23 June 2022 explicitly says the renewable-energy fee waiver continues from October through the end of the following year. The scenario keeps this POZE waiver throughout 2023; removing the saving credit never removes POZE relief. The already archived October CPI methodology publication on 10 November 2022 supplies the earliest treatment date used here. This is a declared application of that treatment, not a claim that the archived ledger's later January methodology confirmation was available in November.

## Exposure aggregation and baseline replacement

`ExposurePortfolio` contains normalized **household shares within one energy item**, not headline expenditure weights. For complete coverage:

```
item_relative = sum(household_share * current_bill)
                / sum(household_share * previous_bill)
gross_headline_pp = 100 * sum(published_item_basket_share * (item_relative - 1))
baseline_energy_pp = 100 * sum(published_item_basket_share * (baseline_relative - 1))
incremental_headline_pp = gross_headline_pp - baseline_energy_pp
```

This ratio uses fixed product quantities and household shares, so changing quantity is not mistaken for changing price. Distinct consumption assumptions are distinct scenario portfolios. The quantity allocated to a Q4 month is held constant across September, October, December and January comparisons within each scenario.

`headline_increment` requires a `BaselineEnergy` object for precisely the same items and months. A flat energy counterfactual must be stated explicitly. If the existing headline baseline embeds normal energy repricing, its corresponding item relatives must be supplied: add **only** the returned incremental contribution. The January-2022 experiment illustrates a hypothetical embedded 2% increase; it is not an estimated seasonal energy baseline. There is no division by the fitted administered coefficient.

Published basket shares come from the exact `E04.510` electricity and `E04.521` network-gas rows, divided by 1,000. Availability uses the repository's detailed January CPI release calendar: 14 February 2020 and 14 February 2022. The January-2022 cutoff therefore uses the 2020 basket. The later 2022–23 calculations use the 2022 basket. These are conventional published-share contribution approximations; exact official chain-linked CPI contributions would additionally need price-updated aggregation weights.

Shares must sum to one unless missing household coverage is explicitly declared. Partial coverage is never automatically renormalized. Without missing-household bill bounds there is neither a point nor a range. Explicit positive CZK/month bounds propagate through numerator and denominator to an assumption envelope, with **no point estimate**. These bounds are not confidence intervals. The API similarly rejects mixed units, total national credits passed as household credits, missing assumptions, nonfinite inputs, negative charges and zero/negative paid bills. It never clips a negative household price to manufacture a usable relative.

## Source gaps and sensitivity results

The first measured run produces 60 rows in `output/energy_ledger_scenarios.csv`; full precision is retained. `output/energy_ledger_manifest.json` records the fixed scenario grid, sources, hashes, visible intervals, timing convention and explicit non-promotion status. `output/energy_ledger_summary.json` contains concise numeric results.

| Diagnostic | Declared variation | Result |
| --- | --- | --- |
| November 2021 VAT | Full pass-through arithmetic assumed | Electricity/gas bill factor `1/1.21`; the source-gated case remains unavailable because the existing ledger has no treatment date |
| January 2022 | Household supplier-repricing exposure 0%, 50%, 100%; electricity commodity share 47.7% or 59.4%; fixed fee 0 or 100 CZK ex VAT/month | Gross energy headline contribution **+1.315 to +3.267 pp**; subtract **0.121 pp** for the explicitly assumed embedded 2% baseline |
| October 2022 | National allocation per connection versus 3,500/2,000 CZK decree amounts; Q4 quantity share 25% or 28% | Electricity-only headline contribution **−3.058 to −1.753 pp** |
| January 2023 | Credit expiry under exactly those same bill/exposure assumptions; POZE remains waived; no underlying repricing | Electricity-only headline contribution **+2.436 to +11.649 pp** |
| Low-consumption D01d | Literal 3,500 CZK credit spread across three proxy monthly bills | **Rejected:** the implied monthly net bill is negative |
| Missing households | 50% covered; explicit bill envelope for the remainder | Contribution range retained, point estimate absent |

For the national allocation mapping, the source's 17,400 **million CZK in total** becomes `17,400 × 1,000,000 / 5,363,859 connection points / 3 months`, approximately 1,081.31 CZK per household/month. This is an explicit hypothetical equal-per-connection allocation, not a measured household credit. At 25% Q4 quantity share it implies October electricity −72.22% and January credit-only reversal +224.16%; at 28% it implies −65.54% and +161.38%. The large variation is evidence that the averaging and credit mapping are economically consequential. It is not a reason to choose a value by closeness to the known CPI release.

The D01d diagnostic uses the existing ERU note's 557,279 MWh divided by 719,625 points. Applying a fixed credit to this low proxy quantity produces a negative price. A real annual bill can carry a credit balance, whereas a positive monthly CPI price relative needs the correct expenditure allocation methodology. The rejected scenario exposes that distinction; it does not invalidate the policy itself.

The 36-month `monthly_path` group carries one explicitly flat proxy bill through January 2021–December 2023, with separate October onset and January expiry. It isolates the policy arithmetic. It is **not** a reconstruction of the full historical supplier-price path, VAT episode or cap cohort. The sensitivity uses a 2022 H1 Eurostat band-average price, 6,026.9 CZK/MWh, as a flat comparison proxy. Calling it a September CPI bill would be unjustified.

Primary inputs still missing:

- Historical product/contract price lists and household exposure shares, including fixed-price contracts and supplier-of-last-resort cohorts.
- Dated fixed charges, distribution/consumption tariff bands, levy-capacity rules and explicit VAT coverage for comparable household bills.
- The denominator and date underlying the ERU commodity/regulated shares and the supplier percentage changes; the old 47.7% and later 59.4% are sensitivity choices, not a reconciled December-2021 bill split.
- The CPI population, product/expenditure weights and saving-credit allocation base. ERU billed quantity and calendar consumption differ; a single Eurostat consumption-band average does not close that gap.
- A verified 2021 VAT CPI-treatment knowledge date and complete archived input vintages. Event gating alone cannot establish historical availability of every bill/exposure assumption.
- The baseline energy contribution embedded in a deployable seasonal nowcast and exact price-update weights if official CPI contribution replication is required.

## API and verification

The pure arithmetic API is in `models/energy_ledger.py`: `Bill`, `PolicyEvent`, `Exposure`, `ExposurePortfolio`, `MissingExposureBounds`, `BasketWeights`, `BaselineEnergy`, `paid_bill`, `policy_intervals`, `item_relative`, and `headline_increment`. It uses the Python standard library. The scenario harness uses pandas/openpyxl to read the existing published baskets; no network, database, forecast model or actual CPI outcome is required.

```
python -m pytest test_energy_ledger_r9.py -q
python energy_ledger_experiment.py
```

Test-first evidence: 23 API cases initially failed for the absent API, then passed. Three scenario contracts were added and failed for the absent experiment, then passed. The resulting 26 passing tests cover additive monetary credits, multiplicative VAT and scope, exact information cutoffs, separate expiry/continuing POZE, household expenditure denominators, commodity-cap scope, baseline replacement, invalid inputs and partial-coverage uncertainty. Source gaps are retained in the manifest, and the rejected low-consumption mapping is retained in the output.
