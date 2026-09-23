"""Independent synthetic oracles for R14 survey clocks and target arithmetic."""
import copy,json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from survey_benchmark_r14 import core_custom,rebuild,score,PRIMARY
from path_integration_r14 import survey_h12,combine_components
from independent_bridge_experiment import match_cnb_quarters
from models.core_learning_r14 import origin_state
from test_core_learning_r14 import inputs
from test_path_integration_r14 import fixture

def historical_fixture():
    core,f,dates=inputs();t=pd.Period('2015-06','M');history={}
    for r in pd.period_range('2008-01',t,freq='M'):
        state=origin_state(core,f,dates,r,(r+1).to_timestamp()+pd.Timedelta(days=20))
        if state is not None:history[r]=state
    return core,f,dates,t,history

def test_json_roundtrip_seasonal_states_remain_usable():
    core,f,dates,t,history=historical_fixture();clock=pd.Timestamp('2015-06-25',tz='Europe/Prague')
    expected,_=core_custom(core,f,dates,history,t,clock)
    saved=json.loads(json.dumps({str(k):v for k,v in history.items()}))
    historical={pd.Period(k,'M'):v for k,v in saved.items()}
    actual,_=core_custom(core,f,dates,historical,t,clock)
    assert actual==expected

def test_historical_state_after_clock_cannot_enter_training():
    core,f,dates,t,history=historical_fixture();clock=pd.Timestamp('2015-06-25',tz='Europe/Prague')
    blocked=pd.Period('2013-01','M');history[blocked]['as_of']='2015-07-01 00:00:00'
    expected,_=core_custom(core,f,dates,history,t,clock)
    history[blocked]['x']={k:1e12 for k in history[blocked]['x']};history[blocked]['trend']=1e12
    actual,_=core_custom(core,f,dates,history,t,clock)
    assert actual==expected

def test_published_target_at_or_after_origin_still_excluded():
    core,f,dates,t,history=historical_fixture();clock=pd.Timestamp('2015-07-25',tz='Europe/Prague')
    expected,_=core_custom(core,f,dates,history,t,clock)
    core.loc[t:]=1e8;f.loc[t:]=1e8
    actual,audit=core_custom(core,f,dates,history,t,clock)
    assert actual==expected
    for row in audit:assert pd.Timestamp(row['training_last_release'])<=clock.tz_localize(None)

def test_rebuild_uses_exact_fixed_contributions_and_rejects_missing():
    blocks=dict(core=.1,food=.04,fuel=.02,administered=.02,alcohol_tobacco=.01,wedge=.01)
    weights=dict(core=.6,food=.2,fuel=.04,administered=.1,alc=.06)
    base=dict(contributions={h:blocks.copy() for h in range(1,13)},weights={h:weights.copy() for h in range(1,13)})
    path,terms=rebuild(base,food={h:.5 for h in range(1,13)},core={h:.3 for h in range(1,13)})
    assert path[0]==0 and path[1]==pytest.approx(.18+.1+.02+.02+.01+.01)
    assert terms[1]['fuel']==blocks['fuel'] and terms[1]['wedge']==blocks['wedge']
    expected=100*((1+path[1]/100)**12-1)
    assert survey_h12(path)==pytest.approx(expected)
    missing={h:.5 for h in range(1,13)};missing[3]=np.nan
    assert np.isnan(survey_h12(rebuild(base,food=missing)[0]))

def test_common_panel_and_survey_precision_are_exact():
    rows=[]
    for i,t in enumerate(pd.period_range('2023-08',periods=24,freq='M')):
        for j,m in enumerate(PRIMARY):
            rows.append(dict(survey_month=str(t),model=m,forecast=float(i+j)/10,actual=float(i)/10,
                             survey_mean_yoy_pct=float(i)/10+.2))
    frame=pd.DataFrame(rows);frame.loc[(frame.model==PRIMARY[-1])&frame.survey_month.eq('2023-08'),'forecast']=np.nan
    got=score(frame);common=got[got.scope.eq('primary_common')]
    assert (common.n==23).all()
    for j,m in enumerate(PRIMARY):
        assert common[common.model.eq(m)].rmse.iloc[0]==pytest.approx(j/10)
    assert common[common.model.eq('FMIE')].rmse.iloc[0]==pytest.approx(.2)
    paired=got[got.scope.eq('paired_'+PRIMARY[0])]
    assert (paired.n==24).all()

def test_cnb_uses_pre_report_clock_and_complete_three_month_yoy_mean():
    headline=pd.Series(.2,index=pd.period_range('2018-01','2021-12',freq='M'))
    rows=[]
    # At 2020-03-15 the 2020-02 path exists; 2020-03 is later and cannot enter.
    for origin,clock in [('2020-02','2020-03-10T08:00:00Z'),('2020-03','2020-04-09T08:00:00Z')]:
        t=pd.Period(origin,'M')
        for h in range(13):
            rows.append(dict(origin=origin,as_of_utc=clock,target=str(t+h),h=h,model='M',yy_exante=2.+h if origin=='2020-02' else 999.))
    paths=pd.DataFrame(rows);cnb=pd.DataFrame([dict(report_date='2020-03-15',quarter='2020Q1',is_forecast=True,value=2.5),
        dict(report_date='2020-03-15',quarter='2021Q2',is_forecast=True,value=2.6)])
    result=match_cnb_quarters(paths,cnb,headline,['M'])
    selected=result[result.model.eq('M')].set_index('quarter')
    actual_jan=100*((1.002)**12-1)
    assert selected.loc['2020Q1','origin']=='2020-02'
    assert selected.loc['2020Q1','forecast']==pytest.approx((actual_jan+2.+3.)/3)
    assert selected.loc['2020Q1','known_months']==1
    assert np.isnan(selected.loc['2021Q2','forecast'])

def test_integrated_target_h12_equals_independent_monthly_product():
    base=fixture();food=base.copy();fuel=base.copy()
    food.loc[food.h.gt(0),'contribution_food']=np.linspace(.02,.2,12)
    fuel.loc[fuel.h.gt(0),'contribution_fuel']=np.linspace(-.04,.05,12)
    result=combine_components(base,food,fuel,None,'M')
    path=result.set_index('h').mm_forecast.to_dict()
    oracle=100*(np.prod(1+result.loc[result.h.gt(0),'mm_forecast'].to_numpy()/100)-1)
    assert survey_h12(path)==pytest.approx(oracle,abs=1e-12)

def test_integrated_status_does_not_inherit_replaced_food_failure():
    base=fixture();food=base.copy();fuel=base.copy()
    base['origin_status']='legacy_failed';base['converged']=True
    base.loc[1,['value_food','contribution_food','mm_forecast']]=np.nan
    base.loc[1,'converged']=False;base.loc[1,'fallback_used']=True
    result=combine_components(base,food,fuel,None,'M')
    assert np.isfinite(result.mm_forecast).all()
    assert result.converged.all()
    assert result.origin_status.ne('legacy_failed').all()
    assert not result.fallback_used.any()
    assert result.legacy_source_fallback_used.iloc[1]
