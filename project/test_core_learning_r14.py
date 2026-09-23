import numpy as np
import pandas as pd
import pytest

from models.core_learning_r14 import (BANDS, CONFIGS, DEFAULT, origin_state,
    band_design, labels_at, ridge, select_config, monthly_path)


def inputs():
    idx=pd.period_range('2000-01','2020-12',freq='M')
    q=.18+.09*np.sin(np.arange(len(idx))*2*np.pi/12)+.02*np.cos(np.arange(len(idx))/7)
    core=pd.Series(100*np.expm1(q/100),index=idx)
    f=pd.DataFrame({'eurczk_mm':np.sin(np.arange(len(idx)))*.4,
                    'import_l2':np.cos(np.arange(len(idx)))*.5},index=idx)
    dates=pd.Series([(p+1).to_timestamp()+pd.Timedelta(days=19,hours=9) for p in idx],index=idx)
    return core,f,dates


def test_future_values_cannot_change_origin_state():
    core,f,dates=inputs();t=pd.Period('2015-06','M');clock=pd.Timestamp('2015-07-09 23:59')
    a=origin_state(core,f,dates,t,clock)
    core.loc[t:]=99;f.loc[t:]=999
    b=origin_state(core,f,dates,t,clock)
    assert a==b
    assert a['history_end']=='2015-05'
    assert abs(sum(a['seasonal'].values()))<1e-12


def test_unpublished_last_core_month_is_unavailable():
    core,f,dates=inputs();t=pd.Period('2015-06','M')
    dates.loc[t-1]=pd.Timestamp('2015-07-12')
    assert origin_state(core,f,dates,t,pd.Timestamp('2015-07-09')) is None


def test_source_lags_and_release_clock():
    core,f,dates=inputs();t=pd.Period('2015-06','M');clock=pd.Timestamp('2015-07-09')
    a=origin_state(core,f,dates,t,clock)
    # import at r-3 is recovered from fixture row r-1, not r.
    f.loc[t,'import_l2']=777;f.loc[t,'eurczk_mm']=777
    assert origin_state(core,f,dates,t,clock)==a
    vals=100*np.log1p(f.loc[t-3:t-1,'import_l2']/100)
    assert a['x']['import3']==pytest.approx(vals.mean())


def test_delayed_band_label_cannot_enter_training():
    core,f,dates=inputs(); r=pd.Period('2014-01','M'); t=pd.Period('2015-06','M')
    state=origin_state(core,f,dates,r,pd.Timestamp('2014-02-09'))
    states={r:state}
    y,meta=labels_at(core,dates,states,t,pd.Timestamp('2015-07-09'),(10,12))
    assert r in y.index
    dates.loc[r+11]=pd.Timestamp('2015-07-10')
    y,meta=labels_at(core,dates,states,t,pd.Timestamp('2015-07-09'),(10,12))
    assert y.empty


def test_band_target_uses_own_origin_seasonality():
    core,f,dates=inputs();r=pd.Period('2014-01','M'); t=pd.Period('2015-06','M')
    s=origin_state(core,f,dates,r,pd.Timestamp('2014-02-09'))
    y,meta=labels_at(core,dates,{r:s},t,pd.Timestamp('2015-07-09'),(1,3))
    expected=np.mean([100*np.log1p(core[r+h]/100)-s['seasonal'][(r+h).month] for h in range(1,4)])
    assert y[r]==pytest.approx(expected)
    core.loc[t:]=99
    assert labels_at(core,dates,{r:s},t,pd.Timestamp('2015-07-09'),(1,3))[0][r]==y[r]


def test_ridge_is_sum_loss_with_training_only_scaling():
    ix=pd.period_range('2000-01',periods=60,freq='M')
    x=pd.DataFrame({'x':np.linspace(-1,1,60),'constant':.3},index=ix)
    y=pd.Series(2*x.x+3,index=ix);now=pd.Series({'x':2.,'constant':.3})
    result,info=ridge(x,y,now,30.)
    z=(x.x-x.x.mean())/x.x.std(ddof=0)
    beta=np.dot(z,y-y.mean())/(np.dot(z,z)+30)
    expected=y.mean()+(2-x.x.mean())/x.x.std(ddof=0)*beta
    assert result==pytest.approx(expected)
    assert info['scale']['constant']==1.


def test_insufficient_rows_do_not_silently_fallback():
    x=pd.DataFrame({'x':np.arange(47.)})
    pred,info=ridge(x,pd.Series(np.arange(47.)),pd.Series({'x':50.}),30.)
    assert np.isnan(pred)
    assert info['status']=='insufficient_history'


def test_exact_log_monthly_reconstruction():
    t=pd.Period('2020-01','M');seas={m:(m-6.5)*.03 for m in range(1,13)}
    means={b:.2+b*.01 for b in range(4)}
    path=monthly_path(t,seas,means)
    for b,(lo,hi) in enumerate(BANDS):
        got=np.mean([100*np.log1p(path[h]/100)-seas[(t+h).month] for h in range(lo,hi+1)])
        assert got==pytest.approx(means[b])


def test_selector_requires_matured_errors_and_uses_default_tie():
    dates=pd.period_range('2010-01',periods=40,freq='M')
    pred=pd.DataFrame([dict(origin=str(r),band=0,config=c,prediction=float(j==0))
                       for j,c in enumerate(CONFIGS) for r in dates])
    truth=pd.DataFrame({'origin':dates.astype(str),'actual':0.,
                        'last_target':(dates+3).astype(str),
                        'available_from':[(r+4).to_timestamp()+pd.Timedelta(days=19) for r in dates]})
    chosen=select_config(pred,truth,pd.Period('2014-01','M'),pd.Timestamp('2014-02-09'),0)
    assert chosen['config']==DEFAULT
    assert chosen['n_validation']==36
    # A future outcome must never affect selected configuration or reported MSE.
    extra=truth.iloc[[-1]].copy();extra['origin']='2013-12';extra['last_target']='2014-03'
    extra['available_from']=pd.Timestamp('2014-04-20');extra['actual']=1e30
    ep=pd.DataFrame([dict(origin='2013-12',band=0,config=c,prediction=0.) for c in CONFIGS])
    assert select_config(pd.concat([pred,ep]),pd.concat([truth,extra]),pd.Period('2014-01','M'),pd.Timestamp('2014-02-09'),0)==chosen


def test_band_calendar_and_feature_roster():
    core,f,dates=inputs();r=pd.Period('2015-06','M')
    s=origin_state(core,f,dates,r,pd.Timestamp('2015-07-09'))
    x=band_design({r:s},(4,6))
    assert x.shape==(1,10)
    assert not any('exp' in c or 'survey' in c for c in x.columns)
    assert x.loc[r,'calendar_sin']==pytest.approx(np.mean([np.sin(2*np.pi*(r+h).month/12) for h in range(4,7)]))


def test_reference_rows_respect_declared_outer_calendar():
    from core_learning_experiment_r14 import reference_rows
    data=pd.DataFrame({'origin':['2008-01','2019-02','2019-02'],
                       'model':['NAIVE','NAIVE','TARGET_ML'],'h':[0,0,0]})
    got=reference_rows(data,['2019-02'],list(data.columns))
    assert len(got)==1
    assert got.iloc[0].origin=='2019-02'
    assert got.iloc[0].model=='NAIVE'
