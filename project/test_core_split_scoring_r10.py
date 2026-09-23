"""Finite coverage, economically meaningful event scores, and paired uncertainty."""
import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest


def evaluate(predictions, survey):
    assert importlib.util.find_spec('evaluation.core_split') is not None, 'R10 evaluator is missing'
    return importlib.import_module('evaluation.core_split').evaluate(predictions, survey)


def sample(actual, forecast, survey=None, start='2024-01'):
    index = pd.period_range(start, periods=len(actual), freq='M')
    sv = pd.DataFrame({'actual': actual, 'survey_median': np.zeros(len(actual)) if survey is None else survey}, index=index)
    predictions = pd.DataFrame({'R9_BASE': np.zeros(len(actual)), 'CANDIDATE': forecast}, index=index)
    return predictions, sv


def score(result, model='CANDIDATE', frame='all', coverage='own'):
    return result['scores'].set_index(['model', 'frame', 'coverage']).loc[model, frame, coverage]


def test_big_alert_and_material_boundaries_use_forecast_loss_not_capture_ratio():
    p, sv = sample([.4, -.4, .4, .4], [.8, -.2, .79, .25])
    result = evaluate(p, sv)
    rows = result['release_rows'].query('model == "CANDIDATE"')
    assert rows.big.tolist() == [True] * 4
    assert rows.alert.tolist() == [True] * 4
    np.testing.assert_allclose(rows.capture_ratio, [2., .5, 1.975, .625])
    np.testing.assert_allclose(rows.gain, [0., .2, .01, .25], atol=1e-12)
    assert score(result).direction == 4
    assert score(result).material_win == 2  # Direction alone, including near-double capture, earns no material win.
    assert score(result).closer == 3
    assert score(result).rmse == pytest.approx(np.sqrt(np.mean([.4**2, .2**2, .39**2, .15**2])))


def test_overshoot_and_material_loss_are_penalized():
    p, sv = sample([.4, -.4, .4], [.95, -.25, .15])
    result = evaluate(p, sv)
    row = score(result)
    assert row.material_win == 2
    assert row.material_loss == 1
    assert row.mean_gain == pytest.approx((-.15 + .25 + .15) / 3)
    assert result['release_rows'].query('model == "CANDIDATE"').iloc[0].capture_ratio > 2


def test_own_and_all_model_common_coverage_retain_baseline_warm_variants():
    p, sv = sample([.5, .5, .5, .5], [.5, np.nan, .3, .3])
    p['R9_HALF'] = [.1, .1, np.nan, .1]
    p['R9_FULL'] = [.2, .2, .2, .2]
    result = evaluate(p, sv)
    assert set(result['scores'].model) == {*p.columns, 'CONSENSUS'}
    assert score(result, 'R9_BASE').n == 4
    assert score(result).n == 3
    assert score(result, 'R9_HALF').n == 3
    assert set(result['scores'].query('frame == "all" and coverage == "common"').n) == {2}
    assert score(result, 'CONSENSUS').n == 4
    assert score(result, 'CONSENSUS', coverage='common').n == 2
    # Bootstrap pairs do not inherit the third model's missing period.
    boot = result['bootstrap'].query('candidate == "CANDIDATE" and frame == "all"')
    assert set(boot.n) == {3}


def test_missing_actual_survey_or_forecast_cannot_count_as_events():
    p, sv = sample([.5, np.nan, .6, .6], [.2, .2, np.nan, .2], survey=[0., 0., 0., np.nan])
    result = evaluate(p, sv)
    row = score(result)
    assert row.n == row.alerts == row.alerted_big == row.direction == row.material_win == 1
    assert score(result, frame='big').n == 1
    assert score(result, frame='alerts').n == 1
    events = result['release_rows'].query('model == "CANDIDATE"')
    assert events.valid.tolist() == [True, False, False, False]
    assert not events.iloc[1:].big.any()
    assert not events.iloc[1:].alert.any()
    assert events.iloc[1:].capture_ratio.isna().all()
    assert set(result['bootstrap'].query('candidate == "CANDIDATE"').n) == {1}


def test_false_alerts_and_missed_big_use_valid_release_denominators():
    p, sv = sample([.1, .39, .4, -.4, 0.], [.2, -.2, .1, -.2, 0.])
    result = evaluate(p, sv)
    row = score(result)
    assert row.false_alarm == 2
    assert row.missed_big == 1
    assert row.alerts == 3
    assert row.alerted_big == 1
    assert row.big_precision == pytest.approx(1 / 3)
    assert row.big_recall == pytest.approx(1 / 2)
    assert result['release_rows'].query('model == "CANDIDATE"').capture_ratio.notna().sum() == 2


def test_all_prespecified_calendar_frames_are_scored():
    p, sv = sample([.4] * 15, [.2] * 15, start='2023-12')
    result = evaluate(p, sv)
    expected = {'all': 15, 'ex_jan': 13, '2024+': 14, 'flash2025+': 2,
                'big': 15, 'big_ex_jan': 13, 'alerts': 15}
    assert {frame: int(score(result, frame=frame).n) for frame in expected} == expected
    assert set(result['scores'].frame) == set(expected)
    assert set(result['scores'].coverage) == {'own', 'common'}


def test_identical_forecast_bootstrap_is_exactly_zero_and_deterministic():
    p, sv = sample(np.linspace(-.3, .7, 30), np.zeros(30), start='2023-01')
    before_p, before_sv = p.copy(deep=True), sv.copy(deep=True)
    a, b = evaluate(p, sv), evaluate(p, sv)
    boot = a['bootstrap']
    assert set(boot.block) == {3, 6, 12}
    assert set(boot.frame) == {'all', '2024+'}
    assert (boot[['delta', 'lower', 'upper']] == 0).all().all()
    assert (boot.draws == 5000).all()
    assert (boot.seed == 42).all()
    pd.testing.assert_frame_equal(boot, b['bootstrap'])
    pd.testing.assert_frame_equal(p, before_p)
    pd.testing.assert_frame_equal(sv, before_sv)
    assert a['gates']['CANDIDATE']['pass'] is False


def test_bootstrap_delta_sign_is_candidate_minus_reference():
    p, sv = sample([1.] * 4, [.5] * 4)
    boot = evaluate(p, sv)['bootstrap']
    np.testing.assert_allclose(boot[['delta', 'lower', 'upper']], -.5)


def test_circular_blocks_preserve_whole_cycles_and_nonconstant_short_block_interval():
    p, sv = sample([0.] * 4, [0.] * 4)
    p['R9_BASE'] = [0., 1., 4., 9.]
    result = evaluate(p, sv)
    boot = result['bootstrap'].query('frame == "all"').set_index('block')
    # A circular block of length >= four contains every release before truncation.
    expected = -np.sqrt((0. + 1. + 16. + 81.) / 4)
    np.testing.assert_allclose(boot.loc[[6, 12], ['delta', 'lower', 'upper']], expected)
    # Three-release blocks need a second start; the 16 possible ordered starts
    # yield endpoint mean squared losses 4.25 and 44.75, each with mass > 2.5%.
    # The largest loss samples errors [1, 4, 9, 9], not [4, 9, 0, 9].
    assert boot.loc[3, 'lower'] == pytest.approx(-np.sqrt(44.75))
    assert boot.loc[3, 'upper'] == pytest.approx(-np.sqrt(4.25))
    pd.testing.assert_frame_equal(result['bootstrap'], evaluate(p, sv)['bootstrap'])


def test_gates_apply_three_fixed_limits_to_common_sample_and_flag_exploration():
    p, sv = sample([1., 1., 1.], [.02, .02, 100.])
    p['R9_HALF'] = [.02, .02, np.nan]
    p['R9_FULL'] = [0., 0., 0.]
    result = evaluate(p, sv)
    gate = result['gates']['CANDIDATE']
    assert gate['pass'] is True
    assert gate['coverage'] == 'common'
    assert gate['rmse_gain_all'] == pytest.approx(.02)
    assert gate['mae_deterioration_all'] == pytest.approx(-.02)
    assert gate['rmse_deterioration_recent'] == pytest.approx(-.02)
    assert gate['n_all'] == gate['n_recent'] == 2
    assert 'exploratory' in gate['selection_status']
    assert 'multiple comparisons' in gate['selection_status']
    assert set(result['gates']) == {'CANDIDATE', 'R9_HALF', 'R9_FULL'}


def test_empty_common_sample_and_absent_recent_sample_do_not_pass_gates():
    p, sv = sample([1., 1.], [np.nan, np.nan], start='2023-01')
    result = evaluate(p, sv)
    assert score(result, coverage='common').n == 0
    assert np.isnan(score(result, coverage='common').rmse)
    assert result['gates']['CANDIDATE']['pass'] is False
    assert result['gates']['CANDIDATE']['n_recent'] == 0
    assert (result['bootstrap'].n == 0).all()
    assert result['bootstrap'][['delta', 'lower', 'upper']].isna().all().all()


def test_gate_rejects_mae_deterioration_even_when_rmse_improves():
    p, sv = sample([0., 0., 0.], [2., 2., 8.])
    p['R9_BASE'] = [0., 0., 10.]
    gate = evaluate(p, sv)['gates']['CANDIDATE']
    assert gate['rmse_gain_pass'] is True
    assert gate['recent_rmse_pass'] is True
    assert gate['mae_pass'] is False
    assert gate['pass'] is False
    assert gate['mae_deterioration_all'] == pytest.approx(.2)


def test_recent_five_percent_guard_is_inclusive_and_independent_of_overall_gain():
    p, sv = sample([0.] * 24, [5.] * 12 + [1.05] * 12, start='2023-01')
    p['R9_BASE'] = [10.] * 12 + [1.] * 12
    p['RECENT_WORSE'] = [5.] * 12 + [1.051] * 12
    gates = evaluate(p, sv)['gates']
    assert gates['CANDIDATE']['pass'] is True
    assert gates['CANDIDATE']['rmse_deterioration_recent'] == pytest.approx(.05)
    assert gates['RECENT_WORSE']['rmse_gain_pass'] is True
    assert gates['RECENT_WORSE']['mae_pass'] is True
    assert gates['RECENT_WORSE']['recent_rmse_pass'] is False
    assert gates['RECENT_WORSE']['pass'] is False


def test_perfect_reference_cannot_show_a_two_percent_rmse_gain():
    p, sv = sample([0., 0.], [0., 0.])
    gate = evaluate(p, sv)['gates']['CANDIDATE']
    assert gate['rmse_gain_all'] == 0.
    assert gate['rmse_gain_pass'] is False
    assert gate['pass'] is False


@pytest.mark.parametrize('invalid', ['duplicate', 'gap', 'reverse', 'daily', 'datetime'])
def test_forecast_index_requires_unique_contiguous_months(invalid):
    p, sv = sample([.1, .2, .3], [.1, .2, .3])
    if invalid == 'duplicate':
        p.index = pd.PeriodIndex(['2024-01', '2024-01', '2024-03'], freq='M')
    elif invalid == 'gap':
        p.index = pd.PeriodIndex(['2024-01', '2024-03', '2024-04'], freq='M')
    elif invalid == 'reverse':
        p = p.iloc[::-1]
    elif invalid == 'daily':
        p.index = pd.period_range('2024-01-01', periods=3, freq='D')
    else:
        p.index = p.index.to_timestamp()
    with pytest.raises(ValueError, match='monthly|contiguous|unique|PeriodIndex'):
        evaluate(p, sv)


@pytest.mark.parametrize('invalid', ['duplicate', 'missing_month', 'extra_month', 'no_actual', 'no_survey'])
def test_survey_requires_unique_matching_labels_and_required_columns(invalid):
    p, sv = sample([.1, .2], [.1, .2])
    if invalid == 'duplicate':
        sv.index = pd.PeriodIndex(['2024-01', '2024-01'], freq='M')
    elif invalid == 'missing_month':
        sv = sv.iloc[:1]
    elif invalid == 'extra_month':
        sv.loc[pd.Period('2024-03', freq='M')] = [.2, 0.]
    else:
        sv = sv.drop(columns='actual' if invalid == 'no_actual' else 'survey_median')
    with pytest.raises(ValueError):
        evaluate(p, sv)


@pytest.mark.parametrize('source', ['forecast', 'actual', 'survey_median'])
@pytest.mark.parametrize('value', [np.inf, -np.inf])
def test_infinite_values_are_rejected_instead_of_silently_dropped(source, value):
    p, sv = sample([.1, .2], [.1, .2])
    if source == 'forecast':
        p.iloc[0, 1] = value
    else:
        sv.loc[sv.index[0], source] = value
    with pytest.raises(ValueError, match='infini|finite'):
        evaluate(p, sv)


def test_missing_reference_duplicate_models_and_supplied_consensus_are_rejected():
    p, sv = sample([.1, .2], [.1, .2])
    for invalid in (p.drop(columns='R9_BASE'), p.assign(CONSENSUS=0.),
                    pd.concat([p, p[['CANDIDATE']]], axis=1)):
        with pytest.raises(ValueError):
            evaluate(invalid, sv)


def test_matching_survey_can_be_reordered_without_changing_scores():
    p, sv = sample([.1, .2, .3], [.1, .2, .3])
    result = evaluate(p, sv)
    reordered = evaluate(p, sv.iloc[::-1])
    pd.testing.assert_frame_equal(result['scores'], reordered['scores'])
