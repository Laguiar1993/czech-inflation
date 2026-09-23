import importlib
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from models.energy_ledger import Bill, PolicyEvent


def api():
    return importlib.import_module('models.energy_exposure_r18')


def clock(value='2025-12-31T00:00:00+00:00'):
    return datetime.fromisoformat(value)


def bill(product='a', quantity=1, commodity=100, levy=0):
    return Bill(product, 'electricity', quantity, commodity, 0, 0, levy, .21,
                ('commodity', 'distribution', 'fixed', 'levy'), 'test assumption')


def cohort(product='a', share=1, quantity=1, new=80, window=('2026-01', '2026-01'), **kwargs):
    return api().Cohort(product, share, bill(product, quantity), new, window, clock(),
                        'assumption', 'test reset assumption', **kwargs)


def evidence(status='observed', archived=True, available=None, comparable=True):
    return api().Evidence('test', status, available or clock(), '2025-12',
                          'CPI household electricity', comparable, archived)


def test_household_mass_is_converted_to_expenditure_weights():
    c = [cohort('a', .5, 1), cohort('b', .5, 3, new=100)]
    result = api().cohort_relative(c, '2025-12', '2026-01', clock())
    assert result.conditional_point == pytest.approx(.95)
    assert result.observed_mass == 0
    assert result.national_point is None


def test_mass_not_renormalized_and_missing_mass_requires_bounds():
    c = [cohort(share=.5)]
    result = api().cohort_relative(c, '2025-12', '2026-01', clock())
    assert result.lower is None and result.modeled_mass == .5
    bounds = api().MissingBills((100, 200), (50, 250), 'explicit bound')
    result = api().cohort_relative(c, '2025-12', '2026-01', clock(), missing=bounds)
    assert result.conditional_point is None
    assert result.lower == pytest.approx((.5 * 96.8 + .5 * 50) / (.5 * 121 + .5 * 200))
    assert result.upper == pytest.approx((.5 * 96.8 + .5 * 250) / (.5 * 121 + .5 * 100))
    with pytest.raises(ValueError, match='mass'):
        api().cohort_relative([cohort('a', .7), cohort('b', .7)], '2025-12', '2026-01', clock())


def test_duplicate_cohort_is_rejected():
    with pytest.raises(ValueError, match='unique'):
        api().cohort_relative([cohort(share=.5), cohort(share=.5)], '2025-12', '2026-01', clock())


def test_reset_window_bounds_persist_as_levels():
    c = [cohort(window=('2026-04', '2026-07'))]
    before = api().cohort_relative(c, '2025-12', '2026-03', clock())
    during = api().cohort_relative(c, '2025-12', '2026-04', clock())
    after = api().cohort_relative(c, '2025-12', '2026-08', clock())
    assert before.conditional_point == 1
    assert during.conditional_point is None
    assert (during.lower, during.upper) == pytest.approx((.8, 1))
    assert after.conditional_point == pytest.approx(.8)
    assert api().cohort_relative(c, '2026-08', '2026-09', clock()).conditional_point == 1


def test_unknown_reset_or_future_input_is_unavailable():
    result = api().cohort_relative([cohort(window=None)], '2025-12', '2026-01', clock())
    assert result.lower is None and 'reset' in result.status
    result = api().cohort_relative([replace(cohort(), available_from=clock('2026-01-01T00:00:00+00:00'))],
                                    '2025-12', '2026-01', clock())
    assert result.lower is None and 'unavailable_input' in result.status


def test_vat_onset_expiry_are_inverse_without_repeated_step():
    start = PolicyEvent('v_start', 'v', 'start', '2026-01', 'electricity', (),
                        'vat_rate', 0, 'fraction', clock(), clock(), clock(), 'test', 'test')
    end = replace(start, event_id='v_end', action='expiry', effective_month='2026-03', value=None, unit=None)
    c = [cohort(new=100)]
    drop = api().cohort_relative(c, '2025-12', '2026-01', clock(), (start, end))
    rise = api().cohort_relative(c, '2026-02', '2026-03', clock(), (start, end))
    stable = api().cohort_relative(c, '2026-03', '2026-04', clock(), (start, end))
    assert drop.conditional_point == pytest.approx(1 / 1.21)
    assert rise.conditional_point == pytest.approx(1.21)
    assert drop.conditional_point * rise.conditional_point == pytest.approx(1)
    assert stable.conditional_point == 1


def test_unknown_cpi_policy_treatment_does_not_become_no_change():
    event = PolicyEvent('v', 'v', 'start', '2026-01', 'electricity', (), 'vat_rate', 0,
                        'fraction', clock(), None, clock(), 'test', 'unknown treatment')
    result = api().cohort_relative([cohort(new=100)], '2025-12', '2026-01', clock(), (event,))
    assert result.lower is None and 'treatment' in result.status


def test_poze_and_product_credit_double_counting_rejected():
    c = replace(cohort(), base_bill=bill(levy=495), regulated_includes_poze=True)
    with pytest.raises(ValueError, match='POZE'):
        api().cohort_relative([c], '2025-12', '2026-01', clock())
    event = PolicyEvent('s', 's', 'start', '2026-01', 'electricity', (), 'credit', 10,
                        'CZK/month', clock(), clock(), clock(), 'test', 'saving tariff')
    with pytest.raises(ValueError, match='aggregate'):
        api().cohort_relative([cohort()], '2025-12', '2026-01', clock(), (event,))


def test_national_gate_requires_observations_and_archived_vintages():
    required = {key: evidence() for key in api().NATIONAL_FIELDS}
    assert api().national_gate(required, clock()).eligible
    required['cohort_shares'] = evidence(status='assumption')
    required['reset_schedule'] = evidence(archived=False)
    required['fixed_quantities'] = evidence(comparable=False)
    result = api().national_gate(required, clock())
    assert not result.eligible
    assert any('cohort_shares:assumption' in r for r in result.reasons)
    assert any('reset_schedule:unarchived' in r for r in result.reasons)
    assert any('fixed_quantities:population' in r for r in result.reasons)
    assert not api().national_gate({}, clock()).eligible
    assert not api().national_gate({k: evidence(available=clock('2026-01-02T00:00:00+00:00')) for k in required}, clock()).eligible


def test_credit_uses_comparable_national_denominator_once_and_inverse():
    fn = api().aggregate_credit_relative
    assert fn(100, 100, 0, 20, evidence(), clock()) == .8
    assert fn(100, 100, 20, 0, evidence(), clock()) == 1.25
    assert fn(100, 120, 20, 20, evidence(), clock()) == 1.25
    with pytest.raises(ValueError, match='denominator'):
        fn(100, 100, 0, 20, evidence(comparable=False), clock())
    with pytest.raises(ValueError):
        fn(100, 100, 0, 100, evidence(), clock())


def test_baseline_replacement_cannot_add_gross_twice():
    fn = api().replace_baseline_contribution
    scope = ('electricity', '2025-12', '2026-01')
    assert fn(.9, 1.1, .05, evidence(), clock(), scenario_scope=scope, baseline_scope=scope) == pytest.approx(-1)
    assert fn(.9, .9, .05, evidence(), clock(), scenario_scope=scope, baseline_scope=scope) == 0
    with pytest.raises(ValueError, match='baseline'):
        fn(.9, None, .05, None, clock())
    with pytest.raises(ValueError, match='scope'):
        fn(.9, 1., .05, evidence(), clock(), scenario_scope=scope,
           baseline_scope=('gas', '2025-12', '2026-01'))
    with pytest.raises(ValueError, match='scope'):
        fn(.9, 1., .05, evidence(), clock())


def test_eru_reporting_period_is_half_year_not_month():
    assert api().eru_reporting_period('2026-01') == ('2026-01', '2026-06')
    assert api().eru_reporting_period('2026-02') == ('2026-07', '2026-12')
    with pytest.raises(ValueError):
        api().eru_reporting_period('2026-03')


def test_inputs_reject_nonfinite_negative_or_naive_time():
    with pytest.raises(ValueError):
        cohort(share=float('nan'))
    with pytest.raises(ValueError):
        cohort(new=-1)
    with pytest.raises(ValueError):
        api().Evidence('x', 'observed', datetime(2025, 1, 1), '2024', 'households', True, True)
    with pytest.raises(ValueError):
        cohort(window=('2026-07', '2026-04'))


def test_runner_exports_only_conditional_scenarios_and_ineligible_national_rows(tmp_path):
    import csv
    runner = importlib.import_module('tools.research_r18.energy_exposure')
    summary = runner.run(tmp_path)
    rows = list(csv.DictReader((tmp_path / 'cohort_scenarios.csv').open()))
    assert len(rows) == 60
    assert all(row['national_point'] == '' for row in rows)
    assert summary['national_eligible'] is False
    assert summary['observed_CPI_cohort_rows'] == 0
    unknown = [r for r in rows if r['scenario'] == 'D_UNKNOWN_RESET']
    assert len(unknown) == 12 and all(r['lower'] == '' for r in unknown)
    staggered = [r for r in rows if r['scenario'] == 'B_STAGGERED_RESET']
    assert float(staggered[0]['conditional_point']) > float(staggered[6]['conditional_point'])
    assert len(summary['spec_sha256']) == 64
