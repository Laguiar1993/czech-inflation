"""R12 clock, target, arithmetic and unchanged-leg acceptance tests."""
import importlib

import numpy as np
import pandas as pd
import pytest


def food_api():
    return importlib.import_module('models.food_path_r12')


def path_api():
    return importlib.import_module('models.cumulative_path_r12')


def sample():
    idx = pd.period_range('2000-01', '2014-12', freq='M')
    q = .15 + .22*np.sin(2*np.pi*(idx.month-1)/12) + .05*np.sin(np.arange(len(idx))/8)
    return pd.Series(100*np.expm1(q/100), index=idx)


def costs():
    idx = pd.period_range('1999-01', '2015-12', freq='M')
    return pd.DataFrame({'agri': np.sin(np.arange(len(idx))/8),
        'ppi': np.cos(np.arange(len(idx))/9),
        'agri_available_at': [(p+1).to_timestamp().tz_localize('UTC')+pd.Timedelta(days=25) for p in idx],
        'ppi_available_at': [(p+1).to_timestamp().tz_localize('UTC')+pd.Timedelta(days=15) for p in idx]}, index=idx)


def clocks():
    return {p: (p+1).to_timestamp().tz_localize('UTC')+pd.Timedelta(days=9)
            for p in sample().index}


def test_food_state_centred_and_future_poison_invariant():
    y = sample(); t = pd.Period('2012-01','M')
    a = food_api().trend_state(y,t)
    y.loc[t:] = 9000.
    b = food_api().trend_state(y,t)
    assert sum(a['seasonal'].values()) == pytest.approx(0.,abs=1e-13)
    assert a['trend'] == b['trend']
    assert a['seasonal'] == b['seasonal']
    assert a['history_end'] == '2011-12'


@pytest.mark.parametrize('n',[60,137])
def test_constant_predictor_has_unit_scale_and_no_spurious_signal(n):
    idx=pd.period_range('2000-01',periods=n,freq='M')
    x=pd.DataFrame({'constant':.3},index=idx)
    correction,diag=food_api().ridge_zero_prior(x,pd.Series(1.,index=idx),pd.Series({'constant':.3}),24)
    assert diag['training_scale']['constant'] == 1.
    assert correction == pytest.approx(0.,abs=1e-14)


def test_causal_trend_handles_pure_seasonal_zero_mean():
    idx=pd.period_range('2000-01','2014-12',freq='M')
    q=.3+.4*np.sin(2*np.pi*(idx.month-1)/12)
    got=food_api().trend_state(pd.Series(100*np.expm1(q/100),index=idx),'2015-01')
    assert got['trend'] == pytest.approx(.3,abs=1e-10)
    assert got['seasonal'][1] == pytest.approx(0.,abs=1e-12)
    assert got['seasonal'][4] == pytest.approx(.4,abs=1e-12)


def test_cost_features_source_alignment_and_both_clocks_fail_closed():
    c=costs(); t=pd.Period('2012-01','M'); clock=clocks()[t]
    got=food_api().cost_features(c,t,clock,clock)
    source=pd.period_range(t-4,t-2,freq='M')
    assert got['agri'] == pytest.approx(c.loc[source,'agri'].mean())
    assert got['ppi'] == pytest.approx(c.loc[source,'ppi'].mean())
    c.loc[t-2,'ppi_available_at']=clock+pd.Timedelta(days=1)
    assert np.isnan(food_api().cost_features(c,t,clock,clock)['ppi'])
    assert np.isnan(food_api().cost_features(c,t,clock+pd.Timedelta(days=2),clock)['ppi'])
    c.loc[t-2,'ppi_available_at']=pd.NaT
    assert np.isnan(food_api().cost_features(c,t,clock,clock)['ppi'])


def test_reconstructed_publication_dates_remain_local_midnight_across_dst():
    runner=importlib.import_module('path_improvements_experiment_r12')
    features=runner.read(runner.ROOT/'tests/fixtures/cleanup/food_block_features.csv')
    records,_=runner.verify_cost_mapping(features)
    for source,expected in [('2015-09','2015-10-26T00:00:00+01:00'),
                            ('2018-02','2018-03-26T00:00:00+02:00')]:
        stamp=records.loc[pd.Period(source,'M'),'agri_available_at']
        assert stamp == pd.Timestamp(expected)
        assert stamp.tz_convert('Europe/Prague').hour == 0
        t=pd.Period(source,'M')+2
        assert np.isnan(food_api().cost_features(records,t,stamp-pd.Timedelta(seconds=1),stamp)['agri'])
        assert np.isfinite(food_api().cost_features(records,t,stamp,stamp)['agri'])


def test_food_cost_future_label_and_source_poison_invariant():
    y=sample(); c=costs(); t=pd.Period('2012-01','M'); clock=clocks()[t]
    a=food_api().forecast_food(y,t,c,clocks(),clock)
    y.loc[t:]=1000.; c.loc[c.index>t-2,['agri','ppi']]=1000000.
    b=food_api().forecast_food(y,t,c,clocks(),clock)
    for key in ('FOOD_TREND_R12','FOOD_COST_R12'):
        assert a['paths'][key] == b['paths'][key]
    assert pd.Period(a['diagnostics']['FOOD_COST_R12']['last_training_target'],'M') <= t-1


@pytest.mark.parametrize('mode',['monthly','cumulative'])
def test_direct_targets_calendar_and_delayed_eligibility(mode):
    y=sample(); t=pd.Period('2012-01','M'); h=12
    data=path_api().training_data(y,t,h,mode)
    assert data['x'].index.max()+h == t-1
    r=data['x'].index[-1]
    q=100*np.log1p(y/100)
    state=food_api().trend_state(y,r)
    prior=lambda k: state['trend']+state['seasonal'][(r+k).month]
    expect=q.loc[r+h]-prior(h) if mode=='monthly' else np.mean([q.loc[r+k]-prior(k) for k in range(1,h+1)])
    assert data['target'].iloc[-1] == pytest.approx(expect)
    assert data['last_training_target'] == str(t-1)


def test_cumulative_reconstruction_exact_products_and_h0_separation():
    cumulative={h:.15*h+.03*h*h for h in range(1,13)}
    got=path_api().reconstruct_cumulative(cumulative,h0=.7)
    assert got[0] == .7
    for h in range(1,13):
        assert 100*np.log(np.prod([1+got[k]/100 for k in range(1,h+1)])) == pytest.approx(cumulative[h],abs=2e-12)
    from models.path_inputs import compound_path
    yy=compound_path(sample().loc[:'2011-12'],got,'2012-01',12,.7)
    assert yy == pytest.approx(100*np.expm1(cumulative[12]/100))


def test_matched_h1_and_future_poisoned_direct_paths():
    y=sample(); t=pd.Period('2012-01','M')
    a=path_api().forecast_targets(y,t,.42)
    y.loc[t:]=1000.
    b=path_api().forecast_targets(y,t,.42)
    assert a['paths'] == b['paths']
    assert a['paths']['DIRECT_MONTHLY_R12'][1] == pytest.approx(a['paths']['DIRECT_CUMULATIVE_R12'][1])
    assert all(p[0] == .42 for p in a['paths'].values())
    assert all(pd.Period(d['last_training_target'],'M') <= t-1
               for model in a['diagnostics'].values() for d in model.values())


def test_interior_missing_history_rejected():
    y=sample().drop(pd.Period('2005-06','M'))
    with pytest.raises(ValueError,match='contiguous'):
        food_api().trend_state(y,'2012-01')
    with pytest.raises(ValueError,match='contiguous'):
        path_api().forecast_targets(y,'2012-01',.2)


def test_cpi_label_calendar_must_pass_before_model_receives_history():
    runner=importlib.import_module('path_improvements_experiment_r12')
    # January 2026 CPI was not public on 12 February; t-1 alone is insufficient.
    y=pd.Series(.2,index=pd.period_range('2025-01','2026-03',freq='M'))
    with pytest.raises(AssertionError,match='Unreleased prior CPI'):
        runner.released_at_origin(y,pd.Period('2026-02','M'),pd.Timestamp('2026-02-12T23:59:00'))


def test_replace_food_preserves_short_and_nonfood_legs():
    runner=importlib.import_module('path_improvements_experiment_r12')
    frame=pd.DataFrame({'h':range(13),'mm_forecast':np.arange(13)*.1,
        'value_food':np.arange(13)*.2,'weight_food':.2,
        'contribution_food':np.arange(13)*.04,'contribution_core':.03})
    changed=runner.replace_food(frame,{h:.5 for h in range(4,13)})
    pd.testing.assert_frame_equal(changed.loc[:3],frame.loc[:3])
    assert np.array_equal(changed.contribution_core,frame.contribution_core)
    assert np.allclose(changed.loc[4:,'mm_forecast'],frame.loc[4:,'mm_forecast']+.2*(.5-frame.loc[4:,'value_food']))


def test_scoring_common_panel_keeps_hard_year_and_distinguishes_samples():
    runner=importlib.import_module('path_improvements_experiment_r12')
    rows=[]
    for origin,target,actual in [('2021-01','2022-01',20.),('2023-01','2024-01',2.),('2024-01','2025-01',2.)]:
        for model in ['A','B']:
            rows.append(dict(origin=origin,target=target,h=12,model=model,
                yy_exante=1.,yy_actual=actual,mm_forecast=.1,mm_actual=.2,cumulative_log_forecast=1.,cumulative_log_actual=2.))
    score=runner.score_panel(pd.DataFrame(rows),['A','B'])
    assert set(score.loc[score['sample']=='full','n_common']) == {3}
    assert set(score.loc[score['sample']=='recent_targets','n_common']) == {2}
    assert set(score.loc[score['sample']=='recent_origins','n_common']) == {1}
    assert score.loc[(score['sample']=='full')&(score.model=='A'),'yy_rmse'].iloc[0] > 10
