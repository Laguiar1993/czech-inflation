"""Publication clocks, units and shrinkage for R12 category pooling."""
import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest

from test_core_split_models_r10 import synthetic
from models.core_split import CATEGORIES, REMAINDER, own_features, visible_history
from models.core_tuning import ridge_prediction


def module():
    assert importlib.util.find_spec('models.core_pooling_r12') is not None, 'R12 estimator missing'
    return importlib.import_module('models.core_pooling_r12')


def args():
    core, cats, _, _, _, dates, t, clock, weights = synthetic()
    return [core, cats, dates, t, clock, weights]


def test_separate_control_matches_existing_ridge_and_contribution_units():
    core, cats, dates, t, clock, weights = args()
    result = module().forecast_origin(*args(), core_weight=.55)
    c = visible_history(core, t, clock, dates)
    cat = visible_history(cats, t, clock, dates)
    remaining_weight = .55 - weights.sum()
    common = c.notna() & cat.notna().all(axis=1)
    targets = {name: cat[name].where(common) for name in CATEGORIES}
    targets[REMAINDER] = ((.55*c-cat.mul(weights).sum(axis=1,min_count=5))/remaining_weight).where(common)
    contributions = [r for r in result['contributions'] if r['model']=='POOL_SEPARATE']
    for r in contributions:
        target = targets[r['block']]
        frame = own_features(target)
        frame.insert(3,'common_core_l1',c.shift(1))
        expected = ridge_prediction(frame,target,t,clock,dates)['prediction']
        assert r['prediction']==pytest.approx(expected,abs=2e-12)
    for model in module().VARIANTS:
        total = sum(r['contribution'] for r in result['contributions'] if r['model']==model)
        assert total==pytest.approx(.55*result['predictions'][model],abs=1e-12)
    assert result['max_reconciliation_error']<1e-12


def test_future_outcomes_and_unpublished_history_cannot_change_forecasts():
    a = args()
    # A missing older release must not contribute either a label or a lag.
    a[2] = a[2].copy()
    late = a[3]-18
    a[2].loc[late] = a[4]+pd.Timedelta(days=100)
    first = module().forecast_origin(*a,core_weight=.55)
    for i in (0,1):
        a[i] = a[i].copy()
        a[i].loc[a[3]:] = 1e9
        a[i].loc[late] = -1e9
    second = module().forecast_origin(*a,core_weight=.55)
    assert first['predictions']==second['predictions']


def test_unpublished_previous_month_fails_closed():
    a = args()
    a[2] = a[2].copy()
    a[2].loc[a[3]-1] = pd.NaT
    result = module().forecast_origin(*a,core_weight=.55)
    assert all(np.isnan(p) for p in result['predictions'].values())
    assert result['fits'][0]['fit_status']=='previous_target_unavailable'


def test_all_equations_share_one_published_training_calendar():
    a = args()
    result = module().forecast_origin(*a,core_weight=.55)
    assert len({(r['n_train'],r['train_start'],r['train_end']) for r in result['fits']})==1
    for row in result['fits']:
        assert row['train_end']<a[3]
        assert row['training_last_release']<=a[4]


def test_reordering_categories_does_not_change_predictions():
    a = args()
    expected = module().forecast_origin(*a,core_weight=.55)
    a[1] = a[1][list(reversed(a[1].columns))]
    a[5] = a[5].iloc[::-1]
    actual = module().forecast_origin(*a,core_weight=.55)
    assert actual['predictions']==expected['predictions']


def test_shorter_category_history_matches_explicit_missing_padding():
    a = args()
    a[1] = a[1].copy()
    a[1].iloc[:30] = np.nan
    padded = module().forecast_origin(*a,core_weight=.55)
    a[1] = a[1].iloc[30:]
    shortened = module().forecast_origin(*a,core_weight=.55)
    assert padded['predictions']==shortened['predictions']


@pytest.mark.parametrize('core_weight',[0.,float('nan'),.1,1.1])
def test_invalid_residual_or_core_weight_rejected(core_weight):
    with pytest.raises(ValueError,match='weight'):
        module().forecast_origin(*args(),core_weight=core_weight)


def test_strong_pooling_converges_towards_shared_dynamic_coefficients():
    rng = np.random.default_rng(173)
    xx = [rng.normal(size=(100,15)) for _ in range(6)]
    yy = [x[:,0]*(j+1)+rng.normal(size=100)*.1 for j,x in enumerate(xx)]
    _, coef = module().solve_pooled(xx,yy,[x[-1] for x in xx],deviation_penalty=1e10)
    assert np.max(np.ptp(coef,axis=0))<1e-6


def test_constant_prices_remain_constant_under_pooling():
    a = args()
    a[0] = a[0]*0+.3
    a[1] = a[1]*0+.3
    result = module().forecast_origin(*a,core_weight=.55)
    for p in result['predictions'].values():
        assert p==pytest.approx(.3,abs=1e-12)
