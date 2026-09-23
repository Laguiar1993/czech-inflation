# R17 energy independent implementation review

## Full-run addendum, 2026-09-14

**Full run PASS:** `output/research_r17_energy` was independently checked across all 90 origins. All 266 source/output hashes pass. Independent weekly prices agree within 2.14e-14 CZK/litre and monthly fuel within 3.74e-14 percentage points. Original constant-spot replay, predecision oil, poisoning of unreleased oil/FX/pump observations, tax/VAT reconciliation, missing-annual-quote fallback, h0 and unchanged components all agree exactly. All 27 illustrative bill rows now explicitly label the 2024 capacity-rate carry-forward and uncertified 2025 tariff, resolving the documentation caveat below. Receipts: `energy_full_verified_review.json` and `ENERGY_FULL_REVIEW_RECEIPT.json`.

The original smoke review below remains as the chronological review record.

Reviewed 2026-09-14. Scope: `docs/implementation/R17_ENERGY_SPEC_2026-09-14.md`, `models/energy_path_r17.py`, `energy_path_experiment_r17.py`, reused R14 fuel/R9 bill arithmetic, six R17 tests, and `work/research_r17_energy/smoke2`. No numerical implementation, existing data, or scoring output was changed by this reviewer.

**Disposition: no substantive blocker to the full fuel scenario run.** The two-origin smoke passes independent daily-cost/weekly-price/monthly-relative reconstruction. All 90 decision clocks pass quote gating and policy knowledge checks. One illustration source-year clarification is recommended below; it does not change the fuel candidates or the current illustration numbers.

## Findings and limits

1. **Documentation caveat, no current numerical effect — distinguish the 2024 capacity tariff from the illustrative December 2025 bill.** `energy_path_experiment_r17.py:62` supplies 84.70 CZK/A/month to a bill labelled December 2025. The source audit establishes that capacity rate for 2024, not 2025. All three declared quantities (1, 3.5, 10 MWh/year), the assumed 25A three-phase connection, and twelve-month interval make the 495 CZK/MWh ceiling bind, so this rate does not affect any of the 27 current illustration numbers. Label the capacity-rate carry-forward explicitly as an assumption, or express this example directly as the declared volume-cap-binding scenario. Do not generalize it to other quantities/breakers as a sourced 2025 bill without the 2025 tariff. Relevant source: [ERU 2024 tariff decree, bulletin 7/2023](https://eru.gov.cz/energeticky-regulacni-vestnik-72023), reviewed in the source audit on 2026-09-14.

2. **Scope boundary — only VAT is presently turned into an origin-indexed policy-factor path.** All 34 policy facts and 3,060 knowledge/eligibility decisions are exported; tariff replacement, capacity/volume POZE, and aggregate-credit routines are separate accounting APIs. The runner does not construct a national bill portfolio from those facts. This is consistent with its explicit ineligibility decision and must remain clear in final claims. An API test for version replacement does not establish a complete historical tariff ledger or closed national exposure.

3. **Scenario interpretation — interpolation time is explicit and economic mapping remains unverified.** Fuel curves begin after the actual decision day and terminate at the end of target month t+12. Because forecasts for origin month t are made in t+1, this is roughly eleven months after the decision, not a verified constant-twelve-month contract. Gas rows use the separately declared h/12 monthly interpolation and remain EUR/MWh commodity scenarios. They do not condition household CPI or electricity prices. Low/high endpoint factors 0.8/1.2 are assumptions, not probabilities or tuned candidate weights. The saved Bloomberg histories use reconstructed next-calendar-day availability; they are not archived real-time vintages.

## Fuel arithmetic and timing

- Each FSBTY1, TTFGCY1 and TTF day-ahead quote is selected as the latest positive finite observation available by the origin clock under the next-calendar-day Prague assumption; age greater than 31 days becomes unavailable. Independently checked all 270 origin/ticker selections against the frozen daily table. Poisoning all not-yet-available quote values leaves every selected quote unchanged.
- Petrol/diesel parameters are the saved R14 origin rows; the source hash checks cover those outputs. Both products exist for all 90 original origins, all original status rows are `estimated`, and the runner rejects fitted labels whose last availability exceeds the decision clock. No new fuel parameter fitting or endpoint tuning occurs.
- Daily EIA oil is gated by observation date plus 14 days, CNB FX by same-day 14:30 Prague, and weekly pump prices by plus seven days. The saved R14 spot/FX/pump endpoints and dated petrol share are reused. Oil and FX stay at their original known/frozen values through the decision date. Only later oil dates change. FX remains at the last eligible R14 FX level thereafter.
- Independently reconstructed seven daily CZK crude costs ending the day before each Monday, then the product ECM recurrence with the saved coefficients. Observed net prices, VAT, and gross/(1+VAT)-net reconciliation wedges match the R14 audit exactly. Weekly gross product prices are averaged into monthly levels; the dated petrol share weights the separate product monthly relatives, as required.
- Poisoning unreleased oil, FX and pump data leaves all four smoke paths exactly unchanged. Missing annual quotes reproduce the constant-spot ECM exactly for annual/base/low/high model labels. Constant-spot replay matches saved R14 fuel monthly values exactly.
- The runner modifies only fuel h1..h12. h0, every nonfuel component/contribution, weights and decision clocks are unchanged. Headline monthly replacement is exactly the frozen fuel weight times the fuel forecast difference. Native annual/cumulative fields agree exactly with recomputed forecast exports; the stale-column issue found during the core review is absent here.

## Policy and bill contracts

- VAT announcement and CPI treatment remain separate. Before 2021-12-10 23:59:59 UTC the treatment is unavailable, including the November VAT start. From that exact cutoff, the November/December factor is 1/1.21, and the January 2022 reversal is 1.21. Events are evaluated from one frozen information set before adjacent level ratios are taken. VAT is not repeatedly charged on later horizons.
- The retained source facts separate January 2023 saving-credit expiry from January 2024 POZE expiry, preserve the 2023 cap expiry, gate the final zero-POZE adoption at December 29, 2025, and leave its end unknown. No January 2027 reversal is invented. See [CZSO November 2021 release](https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-november-2021) and [ERU decree 15/2025](https://eru.gov.cz/kopie-z-energeticky-regulacni-vestnik-192025), retrieved for the source audit on 2026-09-14.
- `visible_rate` chooses a replacement tariff value after effective-date, publication and treatment gates; two versions of the same effective-date/gate are rejected. Unknown treatment does not silently activate a later rate. Policy expiry remains the R9 interval API's responsibility. The API is not currently called to create national CPI adjustments.
- POZE is `min(rate * ceil(breaker_A) * phases * billing_months, quantity_MWh * volume_ceiling)` over one consistent interval. A caller marking the regulated adjustment as already containing POZE is rejected. This guard requires callers to supply that fact truthfully; it does not discover component overlap automatically.
- Aggregate compensation is subtracted once from comparable aggregate expenditure. Missing/nonpositive denominators and credits beyond the positive expenditure balance fail closed. R9 `paid_bill` caps commodity charges before VAT and retains network/fixed charges; it does not implement the unsourced national fixed-fee application of the 2023 cap.
- The 27 January 2026 illustrations use fixed quantity, distribution and fee assumptions. The commodity reset share multiplies only the 240 CZK/MWh ex-VAT CEZ reduction; POZE removal applies across the illustrated portfolio independently. The 21% VAT is applied once to the resulting ex-VAT amounts. Independent arithmetic matches all 27 rows. No household counts, realised CPI or inferred national contract shares enter these numbers. See [CEZ announcement](https://www.cez.cz/cs/pro-media/tiskove-zpravy/cez-prodej-od-1.-ledna-zlevnuje-elektrinu-i-plyn-pro-16-milionu-domacnosti.-zalohy-se-snizuji-i-diky-poklesu-regulovane-slozky-230772), retrieved for the source audit on 2026-09-14.

## Verification receipt

`independent_energy_review.py` writes only this review directory. The successful smoke receipt is `energy_smoke2_review.json`:

| Check | Result |
|---|---:|
| Saved input/output SHA-256 checks | 266 / 266 |
| Independent quote selections, all 90 origins | 270 / 270 exact |
| Weekly gross price max difference | 1.42e-14 CZK/litre |
| Monthly fuel max difference | 2.99e-14 percentage points |
| Original R14 constant-spot replay difference | 0 |
| Predecision oil / future-data poisoning difference | 0 / 0 |
| Tax/VAT reconciliation / missing-quote fallback difference | 0 / 0 |
| Policy fact / all-origin eligibility rows | 34 / 3,060 |
| National policy candidates made eligible | 0 |
| Illustrative bills checked | 27 / 27 |
| R17 energy unit tests | 6 passed in 0.90s |

The initial independent script run used an incorrect review-only CSV column name (`effective_to`); changing it to the existing `effective_to_exclusive_if_known` resolved that reviewer error. No implementation change was required.

The receipt certifies the smoke hashes recorded in its manifest. Re-run verification against the final declared output after a full run, and after any source changes. This review does not assess out-of-sample forecast gains or authorize selecting the assumption endpoints using future outcomes.
