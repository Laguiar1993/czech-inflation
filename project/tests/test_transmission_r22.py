import numpy as np
import pandas as pd
from data.research_transmission_r22 import quarterly_pressure, log_change
from models.transmission_r22 import mask_panel, companion, stabilize, run_origin


def test_quarterly_proxy_carries_source_release_not_future_quarter():
    ix=pd.period_range('2018Q1',periods=8,freq='Q')
    values=pd.Series(np.arange(8)+100.,index=ix)
    dates=pd.Series(ix.to_timestamp(how='end').normalize()+pd.Timedelta(days=75),index=ix)
    v,a,q=quarterly_pressure(values,dates)
    assert v.loc['2019-03']==v.loc['2019-04']==v.loc['2019-05']
    assert a.loc['2019-04']==dates.loc['2019Q1']
    assert q.loc['2019-05']=='2019Q1'
    assert a.loc['2019-06']>a.loc['2019-05']


def test_log_change_requires_both_endpoint_releases():
    ix=pd.period_range('2020-01',periods=4,freq='M')
    levels=pd.Series([100,101,102,103],index=ix)
    dates=pd.Series(pd.to_datetime(['2020-05-01','2020-03-01','2020-04-01',None]),index=ix)
    v,a=log_change(levels,dates)
    assert a.iloc[1]==pd.Timestamp('2020-05-01')
    assert pd.isna(a.iloc[3])


def fixture():
    ix=pd.period_range('2007-01',periods=150,freq='M');rng=np.random.default_rng(2209)
    x=pd.DataFrame({'core':.2+rng.normal(0,.07,150),'unemployment':5+rng.normal(0,.2,150)},index=ix)
    a=pd.DataFrame({c:(ix+1).to_timestamp()+pd.Timedelta(days=10) for c in x},index=ix)
    return x,a


def test_forecast_is_invariant_to_future_or_unreleased_observations():
    x,a=fixture();t=x.index[130];clock=(t+1).to_timestamp()+pd.Timedelta(days=5)
    p=run_origin(x,a,t,clock,{'OWN':['core'],'JOINT':['core','unemployment']})
    x.loc[x.index>=t]=1e7
    b=run_origin(x,a,t,clock,{'OWN':['core'],'JOINT':['core','unemployment']})
    for k in p['paths']:np.testing.assert_allclose(p['paths'][k],b['paths'][k])


def test_stability_contraction_scales_companion_roots():
    beta=np.zeros((13,2));beta[1,0]=1.4;beta[2,1]=1.2
    new,info=stabilize(beta)
    assert info['raw_radius']>1
    assert max(abs(np.linalg.eigvals(companion(new))))<=.98+1e-10


def test_families_share_training_dates_and_missing_current_core_is_not_h0_truth():
    x,a=fixture();t=x.index[130];clock=(t+1).to_timestamp()+pd.Timedelta(days=5)
    result=run_origin(x,a,t,clock,{'OWN':['core'],'JOINT':['core','unemployment']})
    assert result['fits']['OWN']['train_dates']==result['fits']['JOINT']['train_dates']
    assert result['fits']['OWN']['known_h0']==[]
    assert len(result['paths']['OWN'])==12


def test_known_h0_macro_conditions_state_and_h1_advances_one_month():
    x,a=fixture();t=x.index[130];clock=(t+1).to_timestamp()+pd.Timedelta(days=5)
    a.loc[t,'unemployment']=clock-pd.Timedelta(days=1)
    result=run_origin(x,a,t,clock,{'JOINT':['core','unemployment']})
    d=result['fits']['JOINT'];pre=result['preprocessing'];state=np.array(d['state_at_internal_h0'])
    assert d['known_h0']==['unemployment']
    expected=(x.loc[t,'unemployment']-pre['center']['unemployment'])/pre['sigma']['unemployment']
    np.testing.assert_allclose(state[1],expected,atol=1e-12)
    beta=np.array(d['coefficients']);manual=[]
    for h in range(1,13):
        first=beta[0]+state@beta[1:]
        state=np.r_[first,state[:-2]]
        lograte=first[0]*pre['sigma']['core']+pre['center']['core']+pre['seasonal']['core'][(t+h).month]
        manual.append(100*np.expm1(lograte/100))
    np.testing.assert_allclose(result['paths']['JOINT'],manual,rtol=1e-12,atol=1e-12)


def test_delayed_old_quarter_endpoint_delays_entire_proxy():
    ix=pd.period_range('2018Q1',periods=8,freq='Q')
    values=pd.Series(np.arange(8)+100.,index=ix)
    dates=pd.Series(ix.to_timestamp(how='end').normalize()+pd.Timedelta(days=75),index=ix)
    dates.iloc[0]=pd.Timestamp('2025-01-01')
    v,a,q=quarterly_pressure(values,dates)
    assert (a.loc['2019-03':'2019-05']==pd.Timestamp('2025-01-01')).all()
    values.iloc[4]=np.nan
    v,a,q=quarterly_pressure(values,dates)
    assert v.loc['2019-03':'2019-05'].isna().all()
    assert a.loc['2019-03':'2019-05'].isna().all()
