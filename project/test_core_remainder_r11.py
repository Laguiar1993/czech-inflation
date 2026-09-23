"""R11 changes only the remainder information set, with R10 timing preserved."""
import importlib

import numpy as np
import pandas as pd
import pytest

from models.core_split import forecast_origin as old_forecast, REMAINDER, CATEGORIES
from test_core_split_models_r10 import synthetic


def new_module():
    return importlib.import_module('models.core_remainder')


def new_args():
    core, categories, _, x, _, dates, origin, clock, weights = synthetic()
    return [core, categories, x, dates, origin, clock, weights]


def test_five_category_equations_and_own_replay_are_unchanged():
    old = old_forecast(*synthetic(), core_weight=.55)
    new = new_module().forecast_origin(*new_args(), core_weight=.55)
    assert new['own_core'] == pytest.approx(old['predictions']['TARGET_OWN'], abs=1e-12)
    expected = {r['block']: r['prediction'] for r in old['contributions'] if r['model']=='TARGET_OWN'}
    for model in ('TARGET_BASE_REMAINDER', 'TARGET_MACRO_REMAINDER'):
        rows = [r for r in new['contributions'] if r['model']==model]
        assert len(rows)==6
        for r in rows:
            if r['block'] in CATEGORIES:
                assert r['prediction']==expected[r['block']]
        assert sum(r['contribution'] for r in rows)==pytest.approx(.55*new['predictions'][model], abs=1e-12)


def test_macro_remainder_is_exactly_existing_channel_remainder():
    old = old_forecast(*synthetic(), core_weight=.55)
    expected = next(r['prediction'] for r in old['contributions'] if r['model']=='TARGET_CHANNEL' and r['block']==REMAINDER)
    new = new_module().forecast_origin(*new_args(), core_weight=.55)
    actual = next(r['prediction'] for r in new['contributions'] if r['model']=='TARGET_MACRO_REMAINDER' and r['block']==REMAINDER)
    assert actual==expected


def test_feature_sets_distinguish_aggregate_from_remainder_dynamics():
    m = new_module()
    core, _, x, *_ = new_args()
    frames = m.remainder_frames(core, x)
    primary = frames['TARGET_BASE_REMAINDER']
    macro = frames['TARGET_MACRO_REMAINDER']
    assert 'core_l1' in primary and 'own_l1' not in primary
    assert 'own_l1' in macro and 'core_l1' not in macro
    for f in frames.values():
        assert {'eurczk_mm', 'import_l2', 'state'}.issubset(f.columns)
        assert not {'exp12','exp36','household_exp','exp12_x_state','esi','services_l1'}.intersection(f.columns)


def test_future_labels_and_excluded_inputs_cannot_change_prediction():
    args = new_args()
    expected = new_module().forecast_origin(*args, core_weight=.55)
    for i in (0,1):
        args[i] = args[i].copy()
        args[i].loc[args[4]:] = 99999.
    args[2] = args[2].copy()
    args[2].loc[args[2].index>args[4]] = -777777.
    for column in ('exp12','exp36','household_exp','exp12_x_state','esi','services_l1'):
        args[2][column] = 1e12
    actual = new_module().forecast_origin(*args, core_weight=.55)
    assert actual['predictions']==expected['predictions']
    assert actual['own_core']==expected['own_core']


def test_macro_news_changes_remainder_but_not_category_predictions():
    args = new_args()
    expected = new_module().forecast_origin(*args, core_weight=.55)
    args[2] = args[2].copy()
    args[2].loc[args[4], 'eurczk_mm'] += 100.
    actual = new_module().forecast_origin(*args, core_weight=.55)
    assert expected['own_core']==actual['own_core']
    for before, after in zip(expected['contributions'], actual['contributions']):
        if before['block'] in CATEGORIES:
            assert before['prediction']==after['prediction']
        else:
            assert abs(before['prediction']-after['prediction'])>1e-5


def test_unpublished_previous_target_fails_closed():
    args = new_args()
    args[3] = args[3].copy()
    args[3].loc[args[4]-1] = args[5]+pd.Timedelta(days=10)
    result = new_module().forecast_origin(*args, core_weight=.55)
    assert all(np.isnan(x) for x in result['predictions'].values())
    assert np.isnan(result['own_core'])


def test_every_remainder_fit_uses_same_available_label_calendar():
    result = new_module().forecast_origin(*new_args(), core_weight=.55)
    fits = result['fits']
    assert len(fits)==8
    assert len({(r['n_train'],r['train_start'],r['train_end']) for r in fits})==1
    for r in fits:
        assert pd.Period(r['train_end'],freq='M')<new_args()[4]
        assert pd.Timestamp(r['training_last_release'])<=new_args()[5]


@pytest.mark.parametrize('coreweight', [0., -1., float('nan'), 1.1])
def test_invalid_core_weight_rejected(coreweight):
    with pytest.raises(ValueError, match='core weight'):
        new_module().forecast_origin(*new_args(), core_weight=coreweight)
