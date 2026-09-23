"""Materialize the manually verified R18 evidence register and ERU field inventory."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/research_r18/energy'
SOURCES = Path(__file__).parent / 'sources'


def write_csv(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


manifest = json.loads((SOURCES / 'retrieval_manifest.json').read_text())
publication = {
    'ERU_E_templates': ('2026-04-17', '2026-06-25'),
    'ERU_G_templates': ('2026-04-17', '2026-06-25'),
    'ERU_E_schema': ('', '2026-04-27'), 'ERU_G_schema': ('', '2026-04-27'),
    'ERU_reporting_manual': ('', '2026-04-17'),
    'CZSO_energy_method': ('2023-11-10', ''),
    'CZSO_Elek_2025': ('', '2024-11-12'), 'CZSO_gas_2026': ('', '2025-11-06'),
    'EUROSTAT_hicp_CZ': ('2025-08-26', '2025-08-26'),
    'EUROSTAT_electricity_CZ': ('2025-06-24', '2025-06-24'),
    'EUROSTAT_gas_CZ': ('2025-06-25', '2025-06-25'),
    'CEZ_2026_price_release': ('2025-12-30', ''),
    'CZSO_saving_treatment': ('2022-11-10', '2022-11-09'),
    'ERU_contract_types': ('2026-05-18', '2026-08-04'),
    'ERU_contract_B': ('2026-05-18', '2026-08-04'),
    'ERU_commodity_mean': ('2026-08-11', '2026-08-11'),
    'ERU_fixed_mean': ('2026-08-11', '2026-08-11'),
    'ERU_joint_building_population': ('2026-06-17', '2026-08-04'),
    'ERU_exemptions': ('2026-05-18', '2026-08-04'),
}
register = []
urls = {}
for row in manifest:
    assert 'error' not in row, row
    raw = (SOURCES / row['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    key = Path(row['file']).stem
    urls[key] = row['url']
    pub, update = publication.get(key, ('', ''))
    register.append(dict(source_id=key, url=row['url'], file=str((SOURCES / row['file']).relative_to(ROOT)),
                         publication_date_evidence=pub, content_update_evidence=update,
                         retrieved_at=row['retrieved_at'], strict_snapshot_available_from='2026-09-15T23:59:59+00:00',
                         archived_historical_vintage=False, sha256=row['sha256'],
                         publication_note='Displayed source date is not an archived historical content vintage'))
for key, filename, url, pub, retrieved in (
    ('R17_POZE_2026_decree', 'work/research_r17_policy/sources/ERU_erv192025_adopted_2025-12-29.pdf',
     'https://eru.gov.cz/kopie-z-energeticky-regulacni-vestnik-192025', '2025-12-29', '2026-09-14'),
    ('R17_energy_spec', 'docs/implementation/R17_ENERGY_SPEC_2026-09-14.md',
     'local:docs/implementation/R17_ENERGY_SPEC_2026-09-14.md', '2026-09-14', '2026-09-14'),
):
    urls[key] = url
    register.append(dict(source_id=key, url=url, file=filename,
        publication_date_evidence=pub, content_update_evidence=pub,
        retrieved_at=retrieved, strict_snapshot_available_from=retrieved+'T23:59:59+00:00',
        archived_historical_vintage=False, sha256=hashlib.sha256((ROOT/filename).read_bytes()).hexdigest(),
        publication_note='Existing R17 artifact reused read-only; dated legal fact or research specification; not a cohort vintage'))
write_csv('source_register.csv', register)

facts = []


def fact(key, source, field, value, unit, period, population, kind, implication):
    facts.append(dict(fact_id=key, source_id=source, field=field, value=value, unit=unit,
                      reference_period=period, population=population, evidence_kind=kind,
                      national_weight_eligible=False, implication=implication, url=urls[source]))


fact('ERU_first_period', 'ERU_E_templates', 'first_reporting_period', '2026-H1', 'half-year', '2026-H1',
     'qualifying electricity suppliers', 'reporting_rule', 'No historical 2019-2025 contract data supplied by this scheme')
fact('ERU_deadline', 'ERU_E_templates', 'first_submission_deadline', '2026-08-25', 'date', '2026-H1',
     'qualifying electricity suppliers', 'reporting_rule', 'Submission deadline is not public data publication date')
fact('ERU_portfolio_threshold', 'ERU_reporting_manual', 'minimum_supplier_supply_points', 1000, 'supply points', '2026-H1',
     'qualifying electricity/gas retail customers', 'reporting_rule', 'Excludes smaller suppliers; legal entities and points do not identify unique CPI households')
fact('ERU_E_revenue_threshold', 'ERU_reporting_manual', 'minimum_supplier_supply_points', 15000, 'supply points', '2026-H1',
     'electricity revenue survey mvE2', 'reporting_rule', 'Page 8: revenue coverage differs from portfolio coverage')
fact('ERU_G_revenue_threshold', 'ERU_reporting_manual', 'minimum_supplier_supply_points', 10000, 'supply points', '2026-H1',
     'gas revenue survey mvG6', 'reporting_rule', 'Page 12: revenue coverage differs from portfolio coverage')
fact('ERU_period_semantics', 'ERU_reporting_manual', 'obdobi', 'YYYY-01=H1;YYYY-02=H2', 'half-year', 'all reporting periods',
     'all ERU monitoring forms', 'methodology', 'Pages 3 and 13: never parse 2026-01 as January monthly exposure')
fact('ERU_quantity_semantics', 'ERU_reporting_manual', 'planovanaSpotrebaMwh', '', 'planned/predicted annual MWh', 'snapshot end of half-year',
     'mvE1/mvG5 supply points', 'methodology', 'Page 6: contract or prior-12-month fallback possible; not fixed CPI reference quantities')
fact('ERU_price_semantics', 'ERU_commodity_mean', 'obchodniSlozkaCenyPrumer', '', 'CZK/MWh at snapshot date', 'June 30 or December 31',
     'reported portfolio', 'methodology', 'For monthly products the June/December price; not the semester average price')
fact('ERU_fee_semantics', 'ERU_fixed_mean', 'stalyPlatPrumer', 'daily_rate*365/12', 'CZK/point/month', 'June 30 or December 31',
     'reported portfolio', 'methodology', 'Daily fees converted using 365/12; snapshot fee not half-year paid revenue')
fact('ERU_SVJ', 'ERU_joint_building_population', 'category_D_includes_SVJ', True, 'boolean', '2026 reporting',
     'apartment-owner associations with tariff D', 'methodology', 'One supply point may serve shared building use; cannot equate point count with household count')
fact('ERU_B', 'ERU_contract_B', 'contract_type_B', 'fixed term with non-fixed price; excludes A and E', 'category', '2026 reporting',
     'electricity/gas contract classifications', 'methodology', 'Fixed term does not mean fixed price; A dynamic; E formula-based')
fact('ERU_fixed_price_steps', 'ERU_contract_types', 'fixed_price_contract', 'can have pre-agreed annual price steps', 'contract feature', '2026 clarification',
     'electricity/gas customers', 'methodology', 'Contract expiry and pre-agreed price reset dates are different required fields')
fact('EU_E_legacy_coverage', 'EUROSTAT_electricity_CZ', 'stated_household_sample_coverage', .90, 'customer fraction',
     'reference period unspecified in metadata section 3.6', '7 of 50 electricity suppliers; methodology transition noted',
     'observed_metadata_only', 'Do not assign 90 percent CPI coverage or carry across history')
fact('EU_G_legacy_coverage', 'EUROSTAT_gas_CZ', 'stated_household_sample_coverage', .60, 'customer fraction',
     'reference period unspecified in metadata section 3.6', '3 of 50 gas suppliers; section 18.5 also describes seven main energy retailers',
     'observed_metadata_only', 'Different legacy/new sample statements; cannot identify current fuel-specific coverage')
fact('HICP_tariff_weights', 'EUROSTAT_hicp_CZ', 'tariff_provider_weight_basis', 'turnover', 'expenditure basis', '2025 metadata',
     'Czech HICP tariff index', 'methodology', 'Provider turnover weights are not household counts; national CPI detailed weights still require mapping')
fact('CZSO_E_survey', 'CZSO_Elek_2025', 'collected_household_fields', 'revenue_components;MWh;customers_by_band', 'mixed units', '2025 survey design',
     'sampled low-voltage households/businesses', 'reporting_rule', 'Quarterly household detail does not directly release monthly fixed CPI expenditure')
fact('CZSO_G_survey', 'CZSO_gas_2026', 'collected_household_fields', 'revenue_components;MWh;customers_by_group', 'mixed units', '2026 survey design',
     'sampled gas customers', 'reporting_rule', 'Quarterly survey due 30 days after quarter; reporting deadline not dissemination date')
fact('CZSO_accrual', 'CZSO_energy_method', 'measurement_period', 'consumption period', 'accrual', '2023 explanation',
     'CPI and average household energy prices', 'methodology', 'Advances/settlements are not the CPI price timing rule')
fact('CZSO_revision', 'CZSO_energy_method', 'reference_2022_energy_average', 'new method only in Eurostat', 'revision warning', '2022 data revised in 2023',
     'household realized energy average', 'methodology', 'Current H1-2022 averages cannot be relabeled as 2022-origin vintages')
fact('CZSO_credit_allocation', 'CZSO_saving_treatment', 'saving_compensation_allocation', 'one third each Oct/Nov/Dec', 'national aggregate subtraction', '2022-Q4',
     'all households fixed electricity expenditure', 'methodology', 'Need national comparable pre-credit expenditure; no per-bill equal subsidy; no CPI inversion')
fact('CEZ_commodity_old', 'CEZ_2026_price_release', 'D02_commodity_before', 3430, 'CZK/MWh excluding VAT', 'before 2026-01 repricing',
     'CEZ announced electricity product', 'observed_tariff_fact', 'Product price, not complete bill or CPI exposure')
fact('CEZ_commodity_new', 'CEZ_2026_price_release', 'D02_commodity_after', 3190, 'CZK/MWh excluding VAT', '2026-01',
     'CEZ announced electricity product', 'observed_tariff_fact', 'Only reset at January for actual eligible product; later resets in R18 are assumptions')
fact('CEZ_count', 'CEZ_2026_price_release', 'announced_affected_customer_count', 1600000, 'customers', '2026-01',
     'combined electricity and gas products', 'observed_exposure_context', 'No fuel split, national denominator or contract/consumption joint distribution')
fact('POZE_zero_2026', 'R17_POZE_2026_decree', 'adopted_capacity_rate', 0, 'CZK/A/month', 'from 2026-01-01',
     'covered electricity supply points', 'observed_policy_fact', 'R17 verified decree page 2; zero levy; base cap binding and other regulated components in scenarios are assumptions')
fact('CNB_firm_fix', 'CNB_2023_energy', 'survey_fixed_contract_share', 'about two thirds', 'firm fraction', '2022 survey',
     'industrial firms', 'observed_exposure_context', 'Business exposure cannot be used as household contract share')
write_csv('exposure_source_ledger.csv', facts)

inventory = []
for file, item in (('ERU_E_schema.txt', 'electricity'), ('ERU_G_schema.txt', 'gas')):
    schema = json.loads((SOURCES / file).read_text(encoding='utf-8-sig'))
    for form, definition in schema['properties']['vykazy']['items']['properties'].items():
        if not form.startswith('mv'):
            continue
        for field, metadata in definition['items']['properties'].items():
            inventory.append(dict(item=item, form=form, field=field,
                title=metadata.get('title', ''), description=metadata.get('description', ''),
                type=json.dumps(metadata.get('type', metadata.get('allOf', ''))),
                categories=json.dumps(metadata.get('enum', [])),
                actual_observations_available=False, source_id=Path(file).stem,
                time_semantics='obdobi is HALF-YEAR; not monthly; price fields are end-period snapshots'))
write_csv('eru_schema_field_inventory.csv', inventory)

gaps = [
 ('cohort_shares', 'ERU_E_schema;ERU_G_schema', 'actual mvE1/mvG5 rows by supplier;household category;tariff/band;contract type plus excluded-population totals',
  'Reporting structure located; no published populated dataset found in inspected sources; supply points not unique households'),
 ('reset_schedule', 'ERU_contract_types;ERU_E_schema;ERU_G_schema', 'remaining price-fix expiry month and every pre-agreed price step by joint contract/consumption cohort; not original contract duration',
  'No individual expiry/reset date field; semiannual flows cannot identify monthly remaining maturity'),
 ('fixed_quantities', 'ERU_reporting_manual;CZSO_Elek_2025;CZSO_gas_2026', 'fixed CPI quantity and tax-inclusive base expenditure by joint cohort; annual consumption and VT/NT split with reference year',
  'Planned/recent annual MWh and realized volumes differ from fixed CPI quantities'),
 ('tariff_components', 'CEZ_2026_price_release;ERU_E_schema;ERU_G_schema', 'full supplier/DSO/product vintage tariff panel;fixed fees;breaker/phases;energy taxes;discounts;VAT base;POZE inclusion flag',
  'One commodity tariff fact and summary fields do not close the nationwide bill schedule'),
 ('cpi_mapping', 'EUROSTAT_hicp_CZ;CZSO_energy_method', 'Czech national CPI provider/product weights and turnover linkage;household/point bridge;scope/chain-link confirmation',
  'HICP methodology context available; national CPI historical matrix and comparability proof missing'),
 ('item_weights', 'EUROSTAT_hicp_CZ', 'origin-available national CPI electricity/gas weights plus price-update/chain-link basis at every required date',
  'Published basket levels in older repository not re-certified here as historical chain-link vintages'),
 ('baseline_energy', 'R17_energy_spec', 'baseline item-level energy relative for exactly the same origin target and index level base',
  'Baseline has no identified household electricity/gas subpath for replacement'),
 ('credit_denominator', 'CZSO_saving_treatment;CZSO_Elek_2025', 'Oct/Nov/Dec 2022 national pre-credit fixed-quantity electricity expenditure;total compensation;coverage and VAT treatment;original availability date',
  'Realized quarterly revenues and revised band prices cannot substitute or identify denominator from observed CPI'),
]
rows = []
for item in ('electricity', 'gas'):
    for field, source, required, reason in gaps:
        if field == 'credit_denominator' and item == 'gas':
            continue
        rows.append(dict(item=item, field=field, evidence_status='unavailable', value='',
                         available_from='', archived_vintage=False, cpi_comparable=False,
                         candidate_source_ids=source, exact_required_data=required, remaining_gap=reason))
write_csv('national_field_gaps.csv', rows)
print(json.dumps(dict(sources=len(register), source_facts=len(facts), schema_fields=len(inventory),
                      missing_item_fields=len(rows), observed_CPI_cohort_rows=0), indent=2))
