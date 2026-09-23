# R17 household energy policy and forward-source audit

Audit date and retrieval date: 2026-09-14. Scope: read-only inspection of existing model/input files; new audit artifacts only under work/research_r17_policy. No forecast fit, scoring output, CPI outcome calibration, existing policy row or model was changed.

**Decision:** there is enough evidence to correct the policy calendar, VAT treatment gate, POZE rules and several tariff/source labels. There is not enough evidence for a closed national household-bill point forecast across 2019-2026. Keep policy facts, statistical treatment, bill exposures and scenario assumptions separate. The candidate event table deliberately does not pretend that a sourced legal amount closes its CPI contribution.

## Immediate implementation decisions

1. Fill the 2021 VAT treatment date with **2021-12-10 end of day**, using the November CPI release's explicit link to the energy methodology note. The note's “last update” says 9 December; that is not evidence of public availability on release eve. The policy itself and its November-December scope were announced on 20 October. A December origin can therefore anticipate the January return to 21%. The isolated VAT factor is 1/1.21 at onset and 1.21 at expiry; it is not the total item forecast when net tariffs also move. [CZSO note](https://csu.gov.cz/note-to-consumer-prices-of-energy-november-2021), [dated release](https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-november-2021), [MF announcement](https://mf.gov.cz/cs/ministerstvo/media/tiskove-zpravy/2021/nulove-dph-na-elektrickou-energii-a-plyn-43273).

2. Keep **saving credit expiry January 2023** separate from **POZE relief expiry January 2024**. The August 2022 announcement also promised a second 2023 saving subsidy; the October 5 announcement cancelled that subsidy and replaced it with caps. A historical origin before October 5 cannot silently inherit the later cancellation. The cap announcement explicitly covers all 2023, so its default January 2024 expiry was knowable in October 2022, subject to later announced extensions. [August MPO](https://mpo.gov.cz/cz/rozcestnik/pro-media/tiskove-zpravy/vlada-schvalila-konecnou-podobu-usporneho-tarifu-z-dilny-mpo--269504/), [October MPO](https://mpo.gov.cz/cz/rozcestnik/pro-media/tiskove-zpravy/vlada-schvalila-zastropovani-cen-energii--pomuze-jak-domacnostem--tak-firmam--270228/).

3. The January 2024 POZE return has a known end to the temporary waiver and an adopted tariff amount. The 2024 legal decree charges **84.70 CZK/A/month**, with a three-phase multiplier, subject to the **495 CZK/MWh billing-period ceiling**. Therefore a flat 495 per MWh levy is a defensible explicitly stated cap-binding scenario, not the exact formula for every household. The adopted tariff must replace the prior tariff schedule, with no extra POZE addition to a total-regulated multiplier that already includes POZE. [ERU decree 5/2023, published 30 November 2023](https://eru.gov.cz/energeticky-regulacni-vestnik-72023); archived PDF page 22, printed page 21.

4. For 2026 use two announcement versions. The November 28 decision has low-voltage regulated electricity +1.1% and household/small-user gas +4.7%; the larger electricity reduction is conditional. The December 29 **decree 15/2025** adopts zero POZE from January 1 by changing the initial 8.32 CZK/A/month to zero. Its publication and document dates are both December 29. The press release's later January 6 update is unnecessary to establish adoption. Do not backdate the adopted waiver to November. December 16 is cited in the later decree as the government/consultation decision, but no contemporaneous December 16 artifact was archived in this audit; use December 29 for the strict adopted-event gate. [Initial announcement](https://eru.gov.cz/eru-vydal-cenove-vymery-kterymi-stanovi-regulovane-ceny-elektriny-plynu-na-rok-2026-0), [adopted decree](https://eru.gov.cz/kopie-z-energeticky-regulacni-vestnik-192025).

5. The final ERU low-voltage average is -15.1%, 2,772 to 2,352 CZK/MWh. This already includes POZE removal. Its population includes households and small businesses; it is not an exact national CPI electricity-bill relative. Do not splice the average regulated rate and a separate 495 reduction onto different populations. All contract types receive the regulated change, while commodity repricing remains contract-specific. [ERU final summary](https://eru.gov.cz/eru-vydal-zmenovy-cenovy-vymer-kterym-upravuje-regulovane-ceny-na-rok-2026).

## What can enter each historical information set

A source publication date supports an announcement fact. It does not prove a downloaded-in-2026 webpage has never been revised. The source register labels the distinction; original dated decrees are the strongest archived evidence. Use end-of-day UTC when only a date is known. Preserve the actual as-of timestamp, never gate by target month.

| Origin cutoff | Newly usable information | Remaining gap |
|---|---|---|
| 2019 origins | Existing retrospective annual tariff notes are context; no closed 2019 product/exposure panel was found | Exact 2018 publication artifact for 2019 tariffs; contract/DSO mix; dated baseline |
| From 2019-11-28 | 2020 announcement: household regulated electricity +1.3%, gas +0.53% | This source is dated November 28, not decree-signing day November 26; 55%/20% bill shares in old rows are assumptions |
| From 2020-11-30 | 2021 regulated LV electricity -1.7%, household/small-user gas -1.6% | These are network/regulated averages; supplier changes and comparable bill levels remain missing |
| 2021-10-20 to 2021-12-09 | VAT waiver and expiry are legal facts | Event-specific CPI treatment unavailable under conservative sourced-treatment protocol |
| From 2021-12-10 | VAT treatment closes; January VAT reversal can be forecast | Supplier net-price repricing and CPI household exposure remain unresolved |
| 2022-06-23 onward | Public plan for POZE relief October 2022 through December 2023 | Separate legal adoption, credit amount and CPI mapping gates remain required |
| 2022-08-25 to 2022-10-04 | Saving amounts and tariff eligibility; announced later 2023 support | Do not insert the subsequent cancellation or assume complete household coverage |
| From 2022-10-05 | Caps for January-December 2023; cancellation of planned 2023 saving subsidy | Capped share of contracts and fixed fee treatment |
| From 2022-11-10 | CZSO national saving-credit allocation and POZE price treatment | National fixed expenditure denominator; no inference from observed electricity CPI |
| From 2022-11-16 | 2023 regulated price announcement and continuing POZE | Its -16.7% electricity is annual comparison, not a fresh December-to-January drop |
| 2023 origins before final tariffs | Scheduled end of temporary POZE/caps can appear in horizons | Future regulated schedule and uncapped contracts unavailable; retain scenario uncertainty |
| From 2023-11-30 | Adopted 2024 regulated/POZE rates | National supplier/contract exposure and CPI spending base |
| From 2024-11-29 | 2025 regulated electricity +1.4%, household gas +8.6% | Headline -10%/-8.5% bill statements are conditional averages, not exact January m/m |
| 2025-11-28 to 2025-12-28 | Initial 2026 tariffs, conditional full-POZE scenario | Final adopted tariff unavailable under conservative adoption gate |
| From 2025-12-29 | Adopted POZE zero from January 2026 | Full bill exposure still missing; no sourced automatic January-2027 reversal |
| 2026 origins | Apply known zero POZE schedule and subsequently known changes | Beyond known tariff period: explicit unchanged-policy assumption or unavailable, never invented expiry |

For every origin, the forecast horizon is the target month minus that origin's month. Calculate the whole sequence of forecast **levels** from one frozen information set. A December 2025 origin can apply the known January 2026 step at h1. A January 2026 origin should not repeat it at h1; it may already belong in h0. Y/y persistence and roll-out follow from levels and the lagged comparison level, not from adding a one-off contribution every forecast month.

Sources for calm-year facts: [2020 announcement](https://eru.gov.cz/eru-vydava-cenova-rozhodnuti-stanovujici-regulovane-ceny-v-elektroenergetice-a-plynarenstvi-pro-pristi-rok), [2021 announcement](https://eru.gov.cz/eru-oznamuje-regulovane-ceny-elektriny-a-plynu-pro-rok-2021-0). A current MF retrospective history disagrees with some gas summaries and cannot replace contemporaneous announcements.

## Treatment and exposure audit

The October 2022 CZSO note describes a **national aggregate expenditure subtraction**: total saving compensation is divided equally across three months and deducted once from expenditure for all households. Constant consumption follows CPI relative weights. It is not a credit deducted independently from every sampled low-use bill. The R9 product-credit API is useful arithmetic, but that route cannot claim exact Czech CPI treatment; it can create negative artificial bills. The note's numerical CPI outcomes must never identify the unknown credit denominator. Keep the existing conservative **November 10** publication gate despite the page's November 9 update metadata. [CZSO October note](https://csu.gov.cz/note-to-consumer-prices-of-energy-october-2022).

The published tariff credit values do not close an aggregate exposure table. The legal eligibility snapshot is August 23, 2022; the existing 2021 DSO connection counts are a different date and population. Connection points are not necessarily unique households; billed volume is not fixed CPI consumption. The 17.4bn state allocation is a national amount, not a measured equal per-household payment. Keep the recorded arithmetic check but do not promote its 25%-28% Q4 volume choices.

The 2021 ERU commodity shares have dates: 47.7% refers to the **end of 2020**; 59.4% is described as current in the December 1, 2021 release. Neither automatically reconstructs the complete December 2021 sample bill. Gas regulated shares similarly move from 30% to 18.5%. Do not call 52.3% an established December 2021 regulated denominator. [ERU 2022 announcement](https://eru.gov.cz/regulovane-slozky-cen-energii-neprekroci-inflaci).

**Critical vintage failure:** CZSO says its energy-average methodology changed in September 2023 and Eurostat reference-year-2022 data now contain only the new method. Therefore today's H1-2022 band-DC average cannot be labelled an October-2022-publication vintage. Current 2021 full-year averages also cannot be used at January 2021 and lack archived release gates for January 2022. A band average is not the CPI household portfolio even when truly known. [CZSO methodology explanation, 10 November 2023](https://statistikaamy.csu.gov.cz/statistika-cen-energii).

Use published electricity/network-gas/heat basket rows directly, with their own as-of release gates. Do not divide a headline contribution by a fitted administered coefficient or reuse 2022 shares throughout 2019-2026. The existing repo holds 2018/2020/2022/2024/2026 baskets, but presence on disk is not proof of their earlier availability. R9 already gates 2020 and 2022 to the relevant detailed CPI release; retain that convention. This bounded audit did not validate exact 2024/2026 basket release hours or chain-link price-update weights.

**Existing-row corrections:** 2024 +65.7% electricity and +38.8% household gas refer to regulated components. The near-flat electricity statement refers to customers previously at the cap; gas -4% refers to smaller use, with a larger fall for heating. 2025 +8.2% gas is medium/large users; household/small-user is +8.6%. Do not turn “over a tenth” into an exact total CPI m/m. [2024 ERU](https://eru.gov.cz/eru-zverejnil-regulovane-ceny-elektriny-plynu-na-rok-2024), [2025 ERU](https://eru.gov.cz/eru-zverejnil-regulovane-slozky-cen-elektriny-plynu-na-rok-2025).

**CEZ 2026:** the December 30 source supports D02 commodity 3,430 to 3,190 CZK/MWh ex VAT and gas 1,359 to 1,289 ex VAT. It states 1.6m customers across products/fuels; this is not a national CPI exposure weight. Its reported 840 total combines a 240 ex-VAT commodity decrease with a 599 VAT-inclusive POZE decrease. Unit-consistent isolated components give 735 ex VAT / 889.35 incl VAT before other changes. Reject the old -14.8898% national mapping and do not silently resolve the source's inconsistent gas fixed/indefinite wording. [CEZ release](https://www.cez.cz/cs/pro-media/tiskove-zpravy/cez-prodej-od-1.-ledna-zlevnuje-elektrinu-i-plyn-pro-16-milionu-domacnosti.-zalohy-se-snizuji-i-diky-poklesu-regulovane-slozky-230772).

## Closed implementation recipe

- Create an immutable fact/event layer with policy_id, version_id, source_pub_date, source_content_version_date, valid_from, valid_to_if_explicit, publication evidence, supersedes, quantity, unit, taxable scope, product/population scope and CPI treatment basis.
- Keep a separately dated exposure table keyed by item, supplier, contract product, vintage/expiry cohort, DSO, tariff, breaker/phases, fixed reference quantities and CPI population weight. Every price/fixed fee and weight requires its own source and availability date.
- Build each constant-quantity bill as commodity plus distribution, separate fixed supplier and regulated fees, relevant energy taxes/levies, then VAT over the declared base. Caps use min(contract commodity, legal cap); preserve cheaper contracts. The 2023 announcement also contains a 130 CZK/month supplier-fee provision, missing from the current cap API. Its contractual implementation needs the dated decree/product terms before use.
- Apply full tariff schedules once. For POZE, use the legally relevant capacity/volume minimum over a consistent billing period, then allocate to fixed reference monthly consumption. For saving credit, subtract the national monthly compensation from a comparable national expenditure denominator; fail closed if that denominator is unavailable.
- Reconcile the energy path with the baseline using the same items, weights and level base. Replace the baseline's energy contribution with the scenario's contribution. If the baseline lacks an identifiable energy subpath, adding the gross policy effect is not a documented replacement.
- Prevent repeated steps: an expiry removes only its policy, the post-change level persists, revisions supersede rather than stack, and forecast y/y is recalculated from the level path. No January-only gate, magnitude threshold or CPI-result-based credit inversion.
- Output unavailable with reason when a necessary exposure or baseline is absent. A separate named assumption scenario can produce a range. Do not automatically renormalize uncovered households; require bounds. Distinguish zero new announced change from unknown future policy.

## Forward energy metadata and scenarios

Local snapshot 20260909_bloomberg_y1 metadata verifies **FSBTY1 Index** as Bloomberg Fair Value/ICE Brent, USD/barrel, and **TTFGCY1 Index** as Netherlands TTF forward, EUR/MWh. Histories start 2013-07-17 and 2013-04-02 respectively and cover the requested 2019-2026 origins. FSBTY1 is a modelled fair-value series; gas metadata describes calendar-year January-December and gas-year October-September contracts and rolling generic links. Exact ticker-specific delivery/roll mapping and a constant-twelve-month maturity are not established. User selection of these tickers does not establish those missing facts.

The snapshot's availability rule explicitly assumes next-calendar-day usability in Prague and labels histories as retrospectively downloaded, without documented publication vintages. Keep that limitation. Current BDP PX_LAST/update metadata must never enter old origins. Use the latest eligible observed quote separately for each series; preserve its observation date, staleness, same-date USD/CZK or EUR/CZK conversion, and missing FX. Do not use a monthly mean before that month finishes.

Scenario-only mappings can be implemented now: a frozen eligible spot control; a log-linear transition from eligible spot to the annual-index level over a declared number of months; and symmetric high/low annual-index shocks. Those are alternative conditioning paths, not a recovered futures curve. Do not treat Brent as an electricity forward or translate TTF one-for-one into electricity bills. Pass-through and contract reset exposure remain distinct, calibrated only on matured past data in the numerical parent's lane. The suggested assumption CSV does not claim any best model.

## Files and verification

- candidate_policy_events.csv: legal/treatment candidate facts, conservative gates and per-event eligibility reasons.
- exposure_field_audit.csv: missing quantities/weights, what is supported, and acceptable scenario substitutions.
- scenario_assumptions.csv: declared numerical scenario defaults, separate from source facts.
- source_register.csv: official URLs, dates, retrieval date and content-version caveats.
- sources/: original ERU 2024 and 2026 PDFs, extracted text and inspected relevant page images.
- web_retrieval_log.json: retrieved web evidence used in this audit; text can contain realised releases and must never be treated as modelling inputs.
- verification.json and SHA256SUMS.csv: file/schema/date/source-reference validation and archived input hashes.

No national bill point candidate is certified complete. The VAT policy factor is the narrow exception that does not require an unknown contract mix when the entire comparable pre-tax bill is taxable; its total CPI impact still needs the baseline item path and eligible basket. The practical next step is to implement the corrected event semantics and explicit scenarios, while the price/exposure layer remains fail closed.

