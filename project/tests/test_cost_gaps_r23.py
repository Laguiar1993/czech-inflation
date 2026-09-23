import numpy as np
import pandas as pd
from models.cost_gaps_r23 import monthly_correction, fit, eligible, choose
from data.cost_gaps_r23 import features_at
from tools.research_r23.lead import lead_pairs, first_episodes


def test_monthly_interpolation_preserves_all_band_means():
    target=np.array([.1,-.2,.3,.15]);v=monthly_correction(target)
    assert len(v)==12
    np.testing.assert_allclose(v.reshape(4,3).mean(axis=1),target,atol=1e-14)
    np.testing.assert_allclose(monthly_correction(np.ones(4)),np.ones(12),atol=1e-14)


def test_positive_predictor_coefficients_do_not_silently_flip():
    x=pd.DataFrame({'gap':np.linspace(-2,2,40)});y=np.tile(-x.gap.to_numpy()[:,None],(1,4))
    constrained=fit(x,y,pd.Series({'gap':1.}),1.,'positive')
    free=fit(x,y,pd.Series({'gap':1.}),1.,'ridge')
    assert (np.array(constrained['coefficients'])[1:]>=-1e-12).all()
    assert (np.array(free['coefficients'])[1:]<0).all()


def label_fixture():
    ix=pd.period_range('2000Q1',periods=70,freq='Q').asfreq('M','end')
    x=pd.DataFrame({'gap':np.sin(np.arange(70)/5)},index=ix)
    y=pd.DataFrame(np.tile(x.gap.to_numpy()[:,None]/10,(1,4)),index=ix,columns=range(4))
    dates=pd.Series((ix+13).to_timestamp()+pd.Timedelta(days=12),index=ix)
    clocks=pd.Series((ix+1).to_timestamp()+pd.Timedelta(days=5),index=ix)
    return x,y,dates,clocks


def test_labels_and_inner_validation_are_fully_matured():
    x,y,a,clocks=label_fixture();t=pd.Period('2016-01','M');clock=pd.Timestamp('2016-02-01')
    keys=eligible(x,y,a,t,clock,24)
    assert ((keys+12)<t).all()
    assert (a.loc[keys]<=clock).all()
    result=choose(x,y,a,clocks,t,clock,['gap'],'ridge')
    for row in result['validation']:
        assert pd.Period(row['last_training_target'],'M')<pd.Period(row['validation_origin'],'M')
        assert pd.Timestamp(row['max_training_release'])<=pd.Timestamp(row['validation_clock'])
    poisoned=y.copy();poisoned.loc[a>clock]=1e8
    again=choose(x,poisoned,a,clocks,t,clock,['gap'],'ridge')
    assert result['alpha']==again['alpha']
    assert result['scores']==again['scores']


def input_fixture():
    from types import SimpleNamespace
    ix=pd.period_range('2000-01',periods=150,freq='M')
    core=pd.Series(.2,index=ix);pub=pd.Series((ix+1).to_timestamp()+pd.Timedelta(days=10),index=ix)
    q=pd.period_range('2000Q1',periods=50,freq='Q');qa=pd.Series(q.to_timestamp(how='end').normalize()+pd.Timedelta(days=75),index=q)
    raw={11:SimpleNamespace(values=pd.Series(5.,index=ix),available=pub.copy()),17:SimpleNamespace(values=pd.Series(100+np.arange(50),index=q),available=qa.copy()),
         26:SimpleNamespace(values=pd.Series(.2,index=ix),available=pub.copy()),47:SimpleNamespace(values=pd.Series(np.exp(np.arange(150)*.002)*100,index=ix),available=pub.copy())}
    fx=pd.Series(25.,index=ix)
    return core,pub,raw,fx


def test_feature_poison_and_quarterly_provenance():
    core,pub,raw,fx=input_fixture();t=pd.Period('2010-01','M');clock=pd.Timestamp('2010-02-05');season={i:0. for i in range(1,13)}
    a,audit=features_at(core,pub,raw,fx,t,clock,season)
    assert np.isfinite(a).all()
    ulc=next(r for r in audit if r['feature']=='ulc_gap')
    assert ulc['reference']=='2009Q3'
    for r in raw.values():r.values.loc[r.available.gt(clock)]=1e12
    core.loc[pub.gt(clock)]=1e12;fx.loc[fx.index>t]=1e12
    b,_=features_at(core,pub,raw,fx,t,clock,season)
    np.testing.assert_allclose(a,b,atol=0,rtol=0)


def test_missing_old_monthly_endpoint_fails_closed():
    core,pub,raw,fx=input_fixture();t=pd.Period('2010-01','M');clock=pd.Timestamp('2010-02-05')
    raw[26].available.loc['2008-03']=pd.NaT
    values,_=features_at(core,pub,raw,fx,t,clock,{i:0. for i in range(1,13)})
    assert np.isnan(values.import_gap)


def test_lead_uses_immediate_report_same_quarter_and_counts_losses():
    cnb=pd.DataFrame({'report_date':['2022-02-10','2022-05-12','2022-08-11'], 'quarter':['2023Q1']*3,'value':[2.,2.4,1.5],'is_forecast':[True]*3})
    pairs=pd.DataFrame({'report_date':['2022-02-10','2022-05-12'],'quarter':['2023Q1']*2,'clock':['report']*2,'model':['TEST']*2,
                        'forecast':[2.6,3.0],'cnb_forecast':[2.,2.4],'actual':[2.55,2.55]})
    result=lead_pairs(pairs,cnb,.3)
    assert result.iloc[0].revision_confirmed
    assert result.iloc[0].joint_success
    assert not result.iloc[1].revision_confirmed
    assert result.iloc[1].material_loss
    episodes=first_episodes(result,cnb)
    assert episodes.episode_start.tolist()==[True,False]
    cnb.loc[1,'quarter']='2023Q2'
    result=lead_pairs(pairs,cnb,.3)
    assert not result.iloc[0].revision_eligible


def test_small_cnb_revision_can_agree_in_direction_without_confirmation():
    cnb=pd.DataFrame({'report_date':['2022-02-10','2022-05-12'],'quarter':['2023Q1']*2,'value':[2.,2.05],'is_forecast':[True]*2})
    pairs=pd.DataFrame({'report_date':['2022-02-10'],'quarter':['2023Q1'],'clock':['report'],'model':['TEST'],'forecast':[2.6],'actual':[2.6]})
    r=lead_pairs(pairs,cnb,.3).iloc[0]
    assert r.revision_direction_agrees
    assert not r.revision_confirmed


def test_delayed_interior_release_returns_missing_feature_instead_of_aborting():
    core,pub,raw,fx=input_fixture();t=pd.Period('2010-01','M');clock=pd.Timestamp('2010-02-05')
    raw[26].available.loc['2008-03']=pd.Timestamp('2010-03-01')
    values,audit=features_at(core,pub,raw,fx,t,clock,{i:0. for i in range(1,13)})
    assert np.isnan(values.import_gap)
    row=next(r for r in audit if r['feature']=='import_gap')
    assert row['last_publication'] is None
    assert row['status']=='missing_required_history'


def test_irrelevant_pre_window_ppi_release_is_not_claimed_as_used():
    core,pub,raw,fx=input_fixture();t=pd.Period('2010-01','M');clock=pd.Timestamp('2010-02-05')
    season={i:0. for i in range(1,13)};before,_=features_at(core,pub,raw,fx,t,clock,season)
    raw[47].available.loc['2000-01']=pd.Timestamp('2010-03-01')
    after,audit=features_at(core,pub,raw,fx,t,clock,season)
    assert after.ppi_gap==before.ppi_gap
