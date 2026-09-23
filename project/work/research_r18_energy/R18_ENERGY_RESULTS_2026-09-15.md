# R18 household energy: exposure audit and conditional cohort calculator

R18 improves the exposure research and the scenario mechanics, but does **not** establish a national household-energy point forecast. The audit contains **20 newly archived primary-source files**, references an existing R17 adopted decree and specification, and records **25 facts, 124 ERU schema fields and 15 item/field gaps**. No observed national CPI cohort row was obtained. All national forecast and headline-score fields remain empty.

The specification was frozen before scenarios: `docs/implementation/R18_ENERGY_SPEC_2026-09-15.md`, SHA-256 `e7501e245f6f8cffd690247b91cd6ecbbb8d5d14af061862998c752c65f1037e`. No realised CPI, forecast scores or baseline model paths were read by the new scenario runner. All prior files were preserved.

## What the primary sources now establish

ERU's new retail monitoring scheme starts with **H1 2026**, with first submission due **25 August 2026**. Public pages provide reporting templates and schemas; the submission deadline does not establish that populated results are publicly available. This bounded audit did not locate a populated public exposure extract. [Electricity templates](https://eru.gov.cz/vzory-sablon-xlsx-json-souboru-pro-predkladani-souhrnnych-informaci-podle-monitorovaci-vyhlasky), [gas templates](https://eru.gov.cz/vzory-sablon-xlsx-json-souboru-pro-predkladani-souhrnnych-informaci-podle-monitorovaci-vyhlasky-0).

The portfolio forms collect contract category, supply-point count, planned annual MWh, tariff/band, commodity-price summaries and fixed-fee summaries. Revenue forms separate commercial/regulated charges, taxes and, for electricity, POZE. They contain **no individual contract-expiry or price-reset month field**. The published electricity schema also references `typCleneniCeny` and `pocetCenovychUseku` in conditional requirements without declaring them among the form properties; an actual extract requires reconciliation with ERU before automated validation. [Electricity schema](https://eru.gov.cz/sites/default/files/obsah/prilohy/jsonschema-monitorovacivyhlaskaev0json_2.txt), [gas schema](https://eru.gov.cz/sites/default/files/obsah/prilohy/jsonschema-monitorovacivyhlaskagv0json_2.txt).

The methodological manual supplies essential scope and time details. Portfolio reporting begins at **1,000** qualifying supply points, but revenue reporting has thresholds of **15,000 electricity** and **10,000 gas** points. Portfolio MWh can be planned, predicted, contracted or based on the preceding 12 months. `2026-01` denotes January–June, and `2026-02` July–December. The calculator now explicitly decodes these semester identifiers. Manual pages 8 and 12 were rendered and inspected to confirm the higher revenue thresholds. [ERU manual](https://eru.gov.cz/sites/default/files/obsah/prilohy/metodickapriruckavyplnovanisablonv31.pdf).

ERU's August clarifications say the commodity and fixed-fee means describe **30 June or 31 December snapshots**; monthly products use the June/December price. Daily fixed fees are converted with **365/12**. These are not semester-average paid prices. [Commodity mean](https://eru.gov.cz/jak-mame-vypocitat-ukazatel-obchodnislozkacenyprumer), [fixed fee](https://eru.gov.cz/jak-mame-vypocitat-ukazatel-stalyplatprumer).

Fixed-term contracts can have variable prices, while fixed-price contracts can have pre-agreed annual price steps. Both remaining contract maturity and the next scheduled price step matter. ERU also includes apartment-owner associations with tariff D in its reported consumer category. Supply-point counts therefore require a bridge to household expenditure coverage. [Contract types](https://eru.gov.cz/jake-jsou-typy-smluv-pro-elektrinu-plyn-pro-koncoveho-spotrebitele), [type B clarification](https://eru.gov.cz/co-je-smlouva-typu-b-jak-se-odlisuje-zejmena-od-smlouvy-typu-e-ss-5-odst-1-pism-b-vyhlasky), [building associations](https://eru.gov.cz/mame-zapocitavat-mezi-konecne-spotrebitele-nebo-podnikajici-fyzicke-osoby-z-pohledu-monitorovaci).

Czech HICP metadata explicitly derive tariff-provider weights from **turnover**. That supports expenditure weighting rather than equal customer weights, but does not release the historical national CPI supplier/product matrix. Its stated population also differs from national CPI. [HICP inventory](https://ec.europa.eu/eurostat/cache/metadata/EN/prc_hicp_esmshi3_cz.htm).

CZSO collects household electricity/gas revenue components, delivered MWh and customer counts. These surveys provide a concrete acquisition route for energy expenditures. They measure realised quantities and revenues, not automatically the fixed-consumption national denominator required for the 2022 saving tariff. [Electricity survey](https://csu.gov.cz/vykazy/ceny-elek-1-12-mesicni-vykaz-o-cenach-elektricke-energie_psz_2025), [gas survey](https://csu.gov.cz/vykazy/ceny-e-6-04-ctvrtletni-vykaz-o-cenach-zemniho-plynu-pro-konecne-zakazniky_psz_2026).

CPI and structural average energy prices use the consumption period rather than advance-payment timing. Today's 2022 Eurostat averages already embody the methodology introduced in 2023; they cannot be relabeled as historical 2022-origin data. The saving tariff needs one aggregate expenditure subtraction, not the same credit subtracted from each hypothetical bill. [CZSO methods](https://statistikaamy.csu.gov.cz/statistika-cen-energii), [saving-tariff treatment](https://csu.gov.cz/note-to-consumer-prices-of-energy-october-2022).

Two tempting exposure numbers remain unusable as national weights: Eurostat metadata describe 90% electricity and 60% gas household sample coverage alongside a methodology transition, without a precise matching cohort period; CEZ's 1.6 million affected customers combine electricity and gas. They are preserved as source context with eligibility false. [Electricity metadata](https://ec.europa.eu/eurostat/cache/metadata/EN/nrg_pc_204_sims_cz.htm), [gas metadata](https://ec.europa.eu/eurostat/cache/metadata/EN/nrg_pc_202_sims_cz.htm), [CEZ announcement](https://www.cez.cz/cs/pro-media/tiskove-zpravy/cez-prodej-od-1.-ledna-zlevnuje-elektrinu-i-plyn-pro-16-milionu-domacnosti.-zalohy-se-snizuji-i-diky-poklesu-regulovane-slozky-230772).

## Working scenario result

The calculator replaces R17's single reset fraction with explicit cohorts and reset intervals. It converts household mass into expenditure weighting through fixed-quantity bills, applies policy once, persists price levels, retains missing population mass, rejects product-level saving credits, and requires observed comparable historical evidence before national eligibility. Baseline replacement requires matching item/month scope and subtracts the identified embedded baseline once.

The frozen electricity illustration uses CEZ's 3430 to 3190 CZK/MWh commodity change and a cap-binding POZE-removal scenario. Equal cohort masses, annual quantities of 1/3.5/10 MWh, other bill components and delayed reset dates are **assumptions**. Other regulated components are held constant; this is not a full 2026 tariff replacement or a national forecast. Gas is omitted from numeric cohort scenarios because the available CEZ wording does not securely identify an equivalent gas product cohort.

| Assumed reset pattern | January level / December base | Later behaviour |
|---|---:|---|
| All January | 0.870445 | Persists through December |
| January / April / July | 0.909831 | 0.899620 in April; 0.870445 from July |
| Each reset somewhere January–December | [0.870445, 0.912749] | Bounds coincide in December; no midpoint selected |
| Reset timing unknown | unavailable | No assumed zero repricing |
| One third of household mass missing | [0.375717, 2.421996] | Broad assumed missing-bill bounds remain explicit |

These are conditional bill-level results, not percentage-point CPI impacts, forecast errors or probability bands. The wide missing-mass interval demonstrates the information lost when household coverage and spending are not identified. All 60 output rows have empty `national_point` and `baseline_increment_pp`.

## Exact next acquisition request

`data/research_r18/energy/national_field_gaps.csv` records the required fields separately for electricity and gas. Request populated, anonymized ERU mvE1/mvG5 and mvE2/mvG6 extracts with release/vintage information, excluded-supplier totals and household/association distinctions. Add the joint distribution of **remaining monthly reset dates, pre-agreed price steps, contract commodity levels and fixed quantities** from suppliers/CZSO; original contract-duration buckets are insufficient. Obtain the national CPI provider/product turnover weights and the fixed pre-credit October–December 2022 electricity denominator. Finally identify the baseline's same-item energy subpath before replacing its contribution. No external request has been sent.

## Reproduction and verification

From the repository root, with the bundled Python and `PYTHONPATH=.;../pythonlibs`:

```
python work/research_r18_energy/build_source_ledger.py
python -m tools.research_r18.energy_exposure
python -m pytest tests/test_energy_exposure_r18.py tests/test_energy_path_r17.py -q -p no:cacheprovider --basetemp work/research_r18_energy/pytest_verification
```

Verified result: **20 passed** (14 R18 tests plus 6 R17 energy tests). All 22 referenced source hashes were checked. The runner writes 60 scenario rows, 14 explicit cohort-input rows and 10 ineligible item/cutoff rows under `work/research_r18_energy/output`. Spec and output hashes are recorded. The research starts from dated source facts retrieved in 2026 and does not claim an archived historical replay.
