"""R12 evidence contracts: tests written before the new wrapper/runner."""
from dataclasses import replace
from datetime import datetime, timezone
from importlib import import_module, util

import pytest

from models.energy_ledger import (BaselineEnergy, BasketWeights, Bill, Exposure,
                                 ExposurePortfolio, PolicyEvent)


def api():
    assert util.find_spec('models.admin_events_r12') is not None, 'R12 evidence wrapper missing'
    return import_module('models.admin_events_r12')


def at(day):
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


def fixture(month='2022-10', previous='2022-09'):
    m = api()
    bill = Bill('p1', 'electricity', 1., 600., 200., 100., 100., .21,
                ('commodity', 'distribution', 'fixed', 'levy'), 'Test known bill')
    p = ExposurePortfolio((Exposure(bill, 1.),), 'Test complete observed exposure')
    e = PolicyEvent('credit:start', 'credit', 'start', '2022-10', 'electricity', (),
                    'credit', 300., 'CZK/month', at('2022-08-01'), at('2022-09-01'),
                    at('2022-09-01'), 'official/credit', 'Test verified mapping')
    evidence = {k: m.Evidence(k, 'official/document', 'a'*64, at('2022-09-01'), 'verified')
                for k in ('bill:electricity:p1', 'exposure:electricity', 'baseline',
                          'weights', 'event:credit:start:source', 'event:credit:start:methodology')}
    return dict(portfolios={'electricity': p}, previous_month=previous, month=month,
                as_of=at('2022-10-31'), events=(e,),
                basket=BasketWeights({'electricity': .04}, at('2022-01-01'), 'official/basket'),
                baseline=BaselineEnergy(previous, month, {'electricity': 1.02}, 'Test baseline'),
                evidence=evidence, mode='replacement')


def test_levels_first_all_month_replacement_subtracts_embedded_energy():
    r = api().assess(**fixture())
    assert r.status == 'strict_eligible'
    assert r.gross_pp == pytest.approx(4*(910/1210-1))
    assert r.embedded_pp == pytest.approx(.08)
    assert r.incremental_pp == pytest.approx(4*(910/1210-1.02))


@pytest.mark.parametrize('key', ['bill:electricity:p1', 'exposure:electricity', 'baseline',
                                  'weights', 'event:credit:start:source',
                                  'event:credit:start:methodology'])
@pytest.mark.parametrize('state', ['unknown', 'late', 'scenario', 'missing'])
def test_every_required_evidence_clock_fails_closed(key, state):
    args = fixture()
    if state == 'missing':
        del args['evidence'][key]
    else:
        args['evidence'][key] = replace(args['evidence'][key],
            available_at=None if state == 'unknown' else
                at('2022-11-01') if state == 'late' else at('2022-09-01'),
            status='scenario_only' if state == 'scenario' else 'verified')
    r = api().assess(**args)
    assert r.status == 'mapping_unavailable' and r.incremental_pp is None
    assert any(key in s for s in r.reasons)


def test_input_exact_boundary_and_poisoned_future_value_are_safe():
    args = fixture()
    key = 'bill:electricity:p1'
    args['evidence'][key] = replace(args['evidence'][key], available_at=at('2022-11-01'))
    first = api().assess(**args)
    p = args['portfolios']['electricity']
    args['portfolios']['electricity'] = replace(p, exposures=(replace(p.exposures[0],
        bill=replace(p.exposures[0].bill, commodity=999999.)),))
    assert api().assess(**args) == first
    args['as_of'] = at('2022-11-01')
    assert api().assess(**args).status == 'strict_eligible'


def test_unpublished_future_event_cannot_poison_an_earlier_forecast():
    args = fixture()
    late = replace(args['events'][0], event_id='later:start', policy_id='later',
        published_at=at('2023-01-01'), treatment_known_at=at('2023-01-01'),
        available_from=at('2023-01-01'), value=10000000.)
    before = api().assess(**args)
    args['events'] += (late,)
    assert api().assess(**args) == before


def test_unknown_event_methodology_is_not_a_measured_zero():
    args = fixture()
    args['events'] = (replace(args['events'][0], treatment_known_at=None),)
    r = api().assess(**args)
    assert r.status == 'mapping_unavailable' and r.incremental_pp is None


def test_unpublished_or_not_effective_event_has_no_visible_transition():
    args = fixture(month='2022-09', previous='2022-08')
    assert api().assess(**args).status == 'no_visible_transition'
    args = fixture()
    args['as_of'] = at('2022-07-31')
    assert api().assess(**args).status == 'no_visible_transition'


def test_credit_expiry_in_january_keeps_separate_poze_waiver():
    args = fixture('2023-01', '2022-12')
    e = args['events'][0]
    args['events'] += (replace(e, event_id='credit:expiry', action='expiry',
        effective_month='2023-01', value=None, unit=None),
        replace(e, event_id='poze:start', policy_id='poze', kind='levy_waiver', value=1., unit='fraction'))
    for event in args['events']:
        for kind in ('source', 'methodology'):
            key = f'event:{event.event_id}:{kind}'
            args['evidence'][key] = replace(args['evidence']['baseline'], subject=key)
    r = api().assess(**args)
    assert r.incremental_pp == pytest.approx(4*(1089/789-1.02))


def test_late_expiry_cannot_end_visible_start():
    args = fixture('2023-01', '2022-12')
    e = args['events'][0]
    args['events'] += (replace(e, event_id='credit:expiry', action='expiry',
        effective_month='2023-01', value=None, unit=None, published_at=at('2023-01-01'),
        treatment_known_at=at('2023-01-01'), available_from=at('2023-01-01')),)
    assert api().assess(**args).status == 'no_visible_transition'


def test_partial_exposure_has_no_point_estimate():
    args = fixture()
    p = args['portfolios']['electricity']
    args['portfolios']['electricity'] = replace(p, exposures=(replace(p.exposures[0],
        household_share=.5),), complete=False)
    r = api().assess(**args)
    assert r.status == 'mapping_unavailable' and r.incremental_pp is None
    assert 'incomplete_exposure:electricity' in r.reasons


def test_incremental_mode_compares_same_bills_with_without_new_policy():
    args = fixture()
    args['mode'] = 'incremental'
    # The with-policy level is 910 and without-policy is 1210; the 2% embedded
    # seasonal input must not also be subtracted for an incremental counterfactual.
    r = api().assess(**args, counterfactual_events=())
    assert r.incremental_pp == pytest.approx(4*(910/1210-1))
    assert r.embedded_pp == 0.


def test_incremental_counterfactual_evidence_is_also_required():
    args = fixture()
    args['mode'] = 'incremental'
    e = replace(args['events'][0], event_id='normal:start', policy_id='normal', value=20.)
    r = api().assess(**args, counterfactual_events=(e,))
    assert r.incremental_pp is None
    assert any('event:normal:start:' in reason for reason in r.reasons)


def test_nonadjacent_comparison_is_rejected():
    with pytest.raises(ValueError, match='adjacent'):
        api().assess(**fixture(previous='2022-08'))


def test_evidence_rejects_missing_hash_and_subject_mismatch():
    m = api()
    with pytest.raises(ValueError, match='hash'):
        m.Evidence('x', 'source', '', at('2022-01-01'), 'verified')
    args = fixture()
    args['evidence']['weights'] = replace(args['evidence']['weights'], subject='wrong')
    with pytest.raises(ValueError, match='subject'):
        m.assess(**args)


def test_unknown_baseline_and_unpublished_basket_cannot_override_metadata():
    args = fixture()
    args['baseline'] = None
    assert api().assess(**args).incremental_pp is None


def experiment():
    assert util.find_spec('admin_events_experiment_r12') is not None, 'R12 runner missing'
    return import_module('admin_events_experiment_r12')


def test_runner_inputs_do_not_read_survey_or_actual_forecast_columns(monkeypatch):
    x = experiment()
    original = x.pd.read_csv
    def guarded(path, *args, **kwargs):
        assert 'survey' not in str(path)
        if str(path).endswith('cz_struct_backtest.csv'):
            assert 'actual' not in kwargs['usecols']
        return original(path, *args, **kwargs)
    monkeypatch.setattr(x.pd, 'read_csv', guarded)
    data = x.load_inputs()
    assert len(data['reference']) == 90


def test_all90_admin_replay_and_strict_missing_evidence_fallback():
    x = experiment()
    data = x.load_inputs()
    forecasts, replay = x.build_forecasts(data)
    assert len(forecasts) == len(replay) == 90
    assert replay.admin_replay_delta.abs().max() < 1e-10
    assert replay.coreweight_delta.abs().max() < 1e-10
    assert (forecasts.STRICT_ALL_MONTH_ADDITIONS == forecasts.BASE).all()
    assert forecasts.candidate_effect_pp.isna().all()
    assert not forecasts.strict_eligible.any()


def test_admin_replay_ignores_poisoned_current_future_histories():
    x = experiment()
    data = x.load_inputs()
    t = x.pd.Period('2022-10', freq='M')
    cutoff = x.pd.Timestamp(data['reference'].loc[t, 'as_of_eve'])
    first = x.replay_origin(data, t, cutoff)
    for key in ('headline', 'components', 'core', 'regulated', 'alcohol'):
        v = data[key].copy()
        v.loc[v.index >= t] = 1e8
        data[key] = v
    assert x.replay_origin(data, t, cutoff) == first


def test_scenario_replay_is_byte_identical_to_frozen_csv():
    x = experiment()
    text, manifest = x.scenario_replay()
    assert text.encode('utf-8') == (x.ROOT/'output/energy_ledger_scenarios.csv').read_bytes()
    assert not manifest['outcome_data_used'] and not manifest['fitted_parameters']


def test_evidence_audit_keeps_unknown_magnitudes_and_publication_ambiguity():
    x = experiment()
    audit = x.evidence_audit(x.load_inputs())
    assert len(audit) >= 15
    assert not audit.strict_payload_complete.any()
    assert audit.loc[audit.policy_id.eq('vat_waiver_2021'), 'r12_treatment_confirmation'].eq('2021-12-10').all()
    assert audit.loc[audit.policy_id.eq('saving_tariff'), 'r12_treatment_confirmation'].eq('2022-11-10').all()
    assert audit.bill_available_at.isna().all() and audit.exposure_available_at.isna().all()


def test_scoring_direction_zero_and_paired_identity():
    x = experiment()
    index = x.pd.period_range('2024-01', periods=3, freq='M')
    forecasts = x.pd.DataFrame({'BASE':[0.,1.,1.], 'STRICT_ALL_MONTH_ADDITIONS':[0.,1.,1.]}, index=index)
    targets = x.pd.DataFrame({'actual':[0.,2.,0.], 'survey_median':[0.,0.,2.],
                             'era':['regular']*3}, index=index)
    scores, events, uncertainty = x.score(forecasts, targets)
    row = scores.query("model == 'BASE' and frame == 'all'").iloc[0]
    assert row.direction_n == 2 and row.direction_correct == 2
    assert row.material_win_vs_base == 0 and row.material_loss_vs_base == 0
    assert (uncertainty[['delta','lower','upper']] == 0).all().all()
    assert len(events.query('alert')) == 4


def test_source_and_methodology_clocks_are_separate_at_each_origin():
    x = experiment()
    assert hasattr(x, 'origin_evidence_clocks'), 'Origin-by-origin source clock audit missing'
    data = x.load_inputs()
    f, replay = x.build_forecasts(data)
    clocks = x.origin_evidence_clocks(x.evidence_audit(data),f,replay)
    october = clocks.query("period == '2022-10' and policy_id == 'saving_tariff' and event == 'start'").iloc[0]
    assert bool(october.source_visible) and not bool(october.treatment_visible)
    assert bool(october.transition_this_month) and not bool(october.strict_eligible)
    november = clocks.query("period == '2022-11' and policy_id == 'saving_tariff' and event == 'start'").iloc[0]
    assert bool(november.treatment_visible) and not bool(november.transition_this_month)


def test_strict_payload_integration_overrides_clock_and_adds_only_increment():
    x = experiment()
    data = x.load_inputs()
    args = fixture()
    args['as_of'] = at('2029-01-01')
    f, _ = x.build_forecasts(data,strict_payloads={'2022-10':args})
    t = x.pd.Period('2022-10',freq='M')
    expected = 4*(910/1210-1.02)
    assert f.loc[t,'candidate_effect_pp'] == pytest.approx(expected)
    assert f.loc[t,'STRICT_ALL_MONTH_ADDITIONS'] == pytest.approx(f.loc[t,'BASE']+expected)
    args['evidence']['weights'] = replace(args['evidence']['weights'],available_at=at('2029-01-01'))
    f, _ = x.build_forecasts(data,strict_payloads={'2022-10':args})
    assert f.loc[t,'status'] == 'mapping_unavailable'
    assert f.loc[t,'STRICT_ALL_MONTH_ADDITIONS'] == f.loc[t,'BASE']
    args = fixture()
    args['basket'] = replace(args['basket'], available_from=at('2022-12-01'))
    assert api().assess(**args).incremental_pp is None


def test_portable_snapshot_never_discovers_parent_git_metadata(tmp_path, monkeypatch):
    x = experiment()
    assert hasattr(x, 'git_provenance'), 'Portable Git provenance helper missing'
    (tmp_path/'.git').mkdir()
    extracted = tmp_path/'extracted'
    extracted.mkdir()
    def forbidden(*args, **kwargs):
        raise AssertionError('An extracted snapshot must not discover the parent Git repository')
    monkeypatch.setattr(x.subprocess, 'check_output', forbidden)
    assert x.git_provenance(extracted) == {
        'git_head':None, 'git_provenance':'portable_snapshot_no_local_git'}


@pytest.mark.parametrize('error_kind', ['missing_git','git_failure','timeout'])
def test_git_metadata_failure_cannot_abort_a_portable_run(tmp_path, monkeypatch, error_kind):
    x = experiment()
    assert hasattr(x, 'git_provenance'), 'Portable Git provenance helper missing'
    (tmp_path/'.git').write_text('gitdir: missing-worktree-location')
    errors = {'missing_git':FileNotFoundError('git'),
        'git_failure':x.subprocess.CalledProcessError(128,['git']),
        'timeout':x.subprocess.TimeoutExpired(['git'],5)}
    def fail(*args, **kwargs):
        raise errors[error_kind]
    monkeypatch.setattr(x.subprocess, 'check_output', fail)
    result = x.git_provenance(tmp_path)
    assert result['git_head'] is None
    assert result['git_provenance'] == 'git_metadata_unavailable'
    assert result['git_error'] == type(errors[error_kind]).__name__


def test_git_provenance_uses_explicit_local_git_directory(tmp_path, monkeypatch):
    x = experiment()
    assert hasattr(x, 'git_provenance'), 'Portable Git provenance helper missing'
    (tmp_path/'.git').write_text('gitdir: linked-worktree-directory')
    def head(command, **kwargs):
        assert command == ['git','--git-dir='+str(tmp_path/'.git'),'rev-parse','HEAD']
        assert kwargs['cwd'] == tmp_path and kwargs['timeout'] == 5
        return 'a'*40+'\n'
    monkeypatch.setattr(x.subprocess, 'check_output', head)
    assert x.git_provenance(tmp_path) == {'git_head':'a'*40, 'git_provenance':'local_checkout'}
