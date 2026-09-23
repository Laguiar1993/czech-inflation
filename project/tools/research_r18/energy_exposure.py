"""Run the frozen R18 energy assumption grid; no forecasts or outcomes are read."""
from __future__ import annotations

import csv
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json
from pathlib import Path

from models.energy_ledger import Bill, PolicyEvent
from models.energy_exposure_r18 import Cohort, Evidence, MissingBills, cohort_relative, national_gate

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / 'docs/implementation/R18_ENERGY_SPEC_2026-09-15.md'
DATA = ROOT / 'data/research_r18/energy'


def _csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir=None):
    out = Path(output_dir) if output_dir else ROOT / 'work/research_r18_energy/output'
    out.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.fromisoformat('2025-12-31T00:00:00+00:00')
    input_clock = datetime.fromisoformat('2025-12-30T23:59:59+00:00')
    policy_clock = datetime.fromisoformat('2025-12-29T23:59:59+00:00')
    spec_hash = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    sources = list(csv.DictReader((DATA / 'source_register.csv').open(encoding='utf-8')))
    source_ids = {row['source_id'] for row in sources}
    assert {'CEZ_2026_price_release', 'ERU_E_schema', 'ERU_G_schema'} <= source_ids
    for source in sources:
        assert hashlib.sha256((ROOT / source['file']).read_bytes()).hexdigest() == source['sha256']
    poze = PolicyEvent('POZE_ZERO_2026', 'POZE_ZERO', 'start', '2026-01', 'electricity', (),
                       'levy_waiver', 1., 'fraction', policy_clock, policy_clock, policy_clock,
                       'https://eru.gov.cz/kopie-z-energeticky-regulacni-vestnik-192025',
                       'Dated adopted zero POZE; R17 original decree archive. Base levy cap binding is assumed.')
    assumptions = ('All masses, fixed quantities, distribution and fixed fees are assumed. '
                   'CEZ D02 3430->3190 ex-VAT commodity is a source fact; timing beyond January '
                   'is hypothetical. Cap-binding POZE only; all other regulated components held '
                   'constant. Not a complete 2026 tariff schedule or national CPI forecast.')
    base = []
    for n, q in enumerate((1., 3.5, 10.)):
        product = f'assumed_cohort_{n + 1}'
        bill = Bill(product, 'electricity', q / 12, 3430., 1500., 100., 495., .21,
                    ('commodity', 'distribution', 'fixed', 'levy'), assumptions)
        base.append(Cohort(product, 1 / 3, bill, 3190., ('2026-01', '2026-01'),
                           input_clock, 'assumption', assumptions))
    scenarios = {
        'A_JANUARY_RESET': base,
        'B_STAGGERED_RESET': [replace(c, reset_window=(m, m)) for c, m in
                              zip(base, ('2026-01', '2026-04', '2026-07'))],
        'C_RESET_WINDOW': [replace(c, reset_window=('2026-01', '2026-12')) for c in base],
        'D_UNKNOWN_RESET': [replace(c, reset_window=None) for c in base],
        'E_MISSING_MASS': base[:2],
    }
    records, inputs = [], []
    for name, cohorts in scenarios.items():
        missing = MissingBills((1000., 6000.), (900., 6600.),
                               'Frozen broad missing-cohort CZK/month bill bounds') if name == 'E_MISSING_MASS' else None
        for c in cohorts:
            inputs.append(dict(scenario=name, cohort_id=c.cohort_id, household_mass=c.household_mass,
                annual_mwh=c.base_bill.quantity_mwh * 12, commodity_old=c.base_bill.commodity,
                commodity_new=c.new_commodity, distribution_czk_mwh=c.base_bill.distribution,
                fixed_czk_month=c.base_bill.fixed, levy_czk_mwh=c.base_bill.levy, vat=c.base_bill.vat_rate,
                reset_earliest=c.reset_window[0] if c.reset_window else '',
                reset_latest=c.reset_window[1] if c.reset_window else '', exposure_status=c.exposure_status,
                source_available_from=c.available_from.isoformat(),
                commodity_source_id='CEZ_2026_price_release',
                input_vintage_status='dated_statement_retrieved_2026_not_archived_origin_vintage',
                missing_previous_bill_bounds='1000;6000' if missing else '',
                missing_current_bill_bounds='900;6600' if missing else '', assumption=assumptions))
        for month in range(1, 13):
            target = f'2026-{month:02d}'
            result = cohort_relative(cohorts, '2025-12', target, cutoff, (poze,), missing=missing)
            record = dict(scenario=name, **asdict(result), cutoff=cutoff.isoformat(),
                          baseline_increment_pp=None, spec_sha256=spec_hash,
                          interpretation='assumption-conditioned marginal bounds; no national score',
                          source_vintage='retrospective source audit; not certified forecast replay')
            records.append(record)
    gaps = list(csv.DictReader((DATA / 'national_field_gaps.csv').open(encoding='utf-8')))
    national_rows = []
    for item in ('electricity', 'gas'):
        evidence = {r['field']: Evidence(r['candidate_source_ids'], 'unavailable', None,
                                        '2019-2026 historical path', item + ' national CPI', False, False)
                    for r in gaps if r['item'] == item}
        for origin in ('2019-12-31', '2021-12-31', '2022-11-30', '2025-12-31', '2026-09-15'):
            gate = national_gate(evidence, datetime.fromisoformat(origin + 'T23:59:59+00:00'),
                                 aggregate_credit=item == 'electricity')
            national_rows.append(dict(item=item, cutoff=origin, eligible=gate.eligible,
                                      national_point=None, reasons=';'.join(gate.reasons)))
    assert not any(row['eligible'] for row in national_rows)
    assert all(row['national_point'] is None for row in records)
    _csv(out / 'cohort_scenarios.csv', records)
    _csv(out / 'assumption_inputs.csv', inputs)
    _csv(out / 'national_eligibility.csv', national_rows)
    _csv(out / 'policy_events.csv', [asdict(poze)])
    summary = dict(scenario_rows=len(records), scenarios=len(scenarios), sources_verified=len(sources),
                   spec_sha256=spec_hash, observed_CPI_cohort_rows=0, national_eligible=False,
                   national_point=None, headline_score=None,
                   interpretation='Conditional cohort scenarios only; frozen model paths untouched',
                   missing_fields=sorted({row['field'] for row in gaps}))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (out / 'output_hashes.json').write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                     for p in sorted(out.glob('*.csv'))}, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
