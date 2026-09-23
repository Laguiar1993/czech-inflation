import importlib
import numpy as np
import pandas as pd
import pytest


def engine():return importlib.import_module('models.core_adaptation_r17')


def test_fixed_filter_matches_r16_and_future_history_is_rejected():
    from models.core_slope_transmission_r16 import slope_state
    dates=pd.period_range('2010-01',periods=70,freq='M');t=dates[-1]+1
    values=pd.Series(.2+.15*np.sin(np.arange(70)/4),index=dates);seasonal={m:0. for m in range(1,13)}
    expected=slope_state(values,t,seasonal)['forecasts_log']['p95_q001']
    got=engine().filter_state(values,t,seasonal,'fixed')
    assert got['path']==pytest.approx(expected)
    contaminated=pd.concat([values,pd.Series([999.],index=[t])])
    with pytest.raises(ValueError):engine().filter_state(contaminated,t,seasonal,'news')


def test_repeated_news_and_isolated_observation_have_different_treatment():
    e=engine()
    assert e.update_settings('news',[.7,.8],.9)==(.20,.01,1.,True)
    q,qs,r,p=e.update_settings('news',[.1,-.1],8.)
    assert (q,qs,p)==(.05,.001,False) and r>1
    assert e.update_settings('robust',[1.,1.],8.)[2]>1
    assert e.innovation_scale([1.,1.,1.],np.zeros(12))==.05


def test_covariance_is_psd_and_zero_signal_does_not_move_any_horizon():
    e=engine();dates=pd.period_range('2010-01',periods=90,freq='M');t=dates[-1]+1
    x=pd.Series(np.sin(np.arange(90))*.2,index=dates);x.iloc[60:63]=[4.,5.,6.]
    state=e.filter_state(x,t,{m:.01*m for m in range(1,13)},'news')
    assert np.linalg.eigvalsh(state['covariance']).min()>-1e-12
    np.testing.assert_allclose(list(e.condition_h0(state,0.).values()),list(state['path'].values()),atol=1e-12)


def test_h0_coefficient_uses_only_released_prior_errors_and_defaults():
    e=engine();dates=pd.period_range('2017-01',periods=18,freq='M')
    rows=pd.DataFrame(dict(origin=dates.astype(str),signal=np.ones(18),error=np.ones(18)*2,
                           available_from=[str((m+1).to_timestamp()+pd.Timedelta(days=15)) for m in dates]))
    beta,meta=e.h0_coefficient(rows,pd.Period('2018-03'),pd.Timestamp('2018-03-10'))
    assert meta['n_train']==13 and beta==pytest.approx(2*13/(13+24))
    altered=rows.copy();altered.loc[altered.origin.ge('2018-02'),'error']=1e6
    assert e.h0_coefficient(altered,pd.Period('2018-03'),pd.Timestamp('2018-03-10'))[0]==beta
    assert e.h0_coefficient(rows,pd.Period('2017-06'),pd.Timestamp('2017-07-10'))[0]==0
