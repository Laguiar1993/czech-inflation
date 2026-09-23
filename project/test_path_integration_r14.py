import numpy as np
import pandas as pd
import pytest

from path_integration_r14 import combine_components, survey_h12


def fixture():
    rows=[]
    for h in range(13):
        row=dict(origin='2020-01',target=str(pd.Period('2020-01','M')+h),h=h,
                 model='INDEPENDENT_BRIDGE',as_of_utc='2020-02-09T22:59:00Z',mm_forecast=.2,
                 yy_exante=99.,yy_conditional=99.,fallback_used=False)
        for b,w in [('core',.6),('food',.2),('fuel',.04),('administered',.1),('alcohol_tobacco',.06)]:
            row['value_'+b]=.2;row['contribution_'+b]=w*.2;row['weight_'+('alc' if b=='alcohol_tobacco' else b)]=w
        row['contribution_wedge']=0.;rows.append(row)
    return pd.DataFrame(rows)


def test_replaces_only_declared_contributions_and_preserves_h0():
    base=fixture();food=base.copy();fuel=base.copy();core=base.copy()
    for frame,block,value in [(food,'food',1.),(fuel,'fuel',2.),(core,'core',.3)]:
        frame.loc[frame.h>0,'value_'+block]=value
        frame.loc[frame.h>0,'contribution_'+block]=frame['weight_'+block]*value
    got=combine_components(base,food,fuel,core,'TEST')
    assert got.loc[0,'mm_forecast']==base.loc[0,'mm_forecast']
    assert got.loc[1,'mm_forecast']==pytest.approx(.6*.3+.2*1+.04*2+.1*.2+.06*.2)
    for c in ['contribution_administered','contribution_alcohol_tobacco','contribution_wedge','weight_core']:
        pd.testing.assert_series_equal(got[c],base[c])
    assert got.yy_exante.isna().all()


def test_missing_component_is_not_silently_zero():
    base=fixture();food=base.copy();food.loc[1,'contribution_food']=np.nan;food.loc[1,'value_food']=np.nan
    got=combine_components(base,food,base,None,'TEST')
    assert np.isnan(got.loc[1,'mm_forecast'])


def test_rejects_conflicting_clock_weight_or_key():
    base=fixture();food=base.copy();food.loc[1,'as_of_utc']='2020-02-10T00:00:00Z'
    with pytest.raises(ValueError,match='clock'):combine_components(base,food,base,None,'TEST')
    food=base.copy();food.loc[1,'weight_food']=.21
    with pytest.raises(ValueError,match='weight'):combine_components(base,food,base,None,'TEST')
    with pytest.raises(ValueError,match='keys'):combine_components(base,base.iloc[:-1],base,None,'TEST')


def test_exact_survey_h12_does_not_use_h0():
    path={h:.1+.01*h for h in range(13)}
    expected=100*(np.prod([1+path[h]/100 for h in range(1,13)])-1)
    a=survey_h12(path);path[0]=99999.
    assert survey_h12(path)==a
    assert a==pytest.approx(expected)
    path[6]=np.nan
    assert np.isnan(survey_h12(path))


def test_custom_survey_clock_rebuilds_current_state_and_ignores_future():
    from survey_benchmark_r14 import core_custom
    from models.core_learning_r14 import origin_state
    from test_core_learning_r14 import inputs
    core,features,dates=inputs();t=pd.Period('2015-06','M');clock=pd.Timestamp('2015-06-25',tz='Europe/Prague')
    history={}
    for r in pd.period_range('2008-01',t,freq='M'):
        s=origin_state(core,features,dates,r,(r+1).to_timestamp()+pd.Timedelta(days=8))
        if s is not None:history[r]=s
    first,_=core_custom(core,features,dates,history,t,clock)
    # A saved release-eve current state is later than the survey clock and must be rebuilt.
    history[t]['trend']=1e8
    core.loc[t:]=999.;features.loc[t:]=999.
    second,audit=core_custom(core,features,dates,history,t,clock)
    assert first==second
    assert all(pd.Timestamp(r['training_last_release'])<=clock.tz_localize(None) for r in audit)
    assert all(r['current_state']['as_of']=='2015-06-25 00:00:00' for r in audit)
