import importlib
import numpy as np
import pandas as pd


def e():return importlib.import_module('models.path_components_r17')


def test_whole_path_selection_waits_for_all_released_labels_and_defaults():
    origins=pd.period_range('2017-01',periods=20,freq='M')
    rows=[]
    for t in origins:
        for model,value in [('zero',1.),('half',0.)]:
            for h in range(1,13):rows.append(dict(origin=str(t),h=h,model=model,yy_exante=value,yy_actual=0.))
    frame=pd.DataFrame(rows);months=pd.period_range('2017-01','2021-01',freq='M')
    dates=pd.Series([(m+1).to_timestamp()+pd.Timedelta(days=15) for m in months],index=months)
    configs={'zero':[1.,0.],'half':[.5,.5]}
    name,meta=e().choose_path(frame,dates,'2019-03','2019-03-10',configs,'zero')
    assert name=='half' and meta['n_validation']==13
    altered=frame.copy();altered.loc[altered.origin.ge('2018-02'),'yy_actual']=1000
    assert e().choose_path(altered,dates,'2019-03','2019-03-10',configs,'zero')==(name,meta)
    assert e().choose_path(frame,dates,'2018-01','2018-02-10',configs,'zero')[0]=='zero'


def test_sustained_movement_is_distinct_from_exact_interior_turn():
    assert e().sustained([2.,2.2,2.5])==1
    assert e().sustained([2.,2.4,1.5])==-1
    assert e().sustained([2.,1.5,2.6])==0
    assert np.isnan(e().sustained([2.,np.nan,3.]))


def test_pool_is_nonnegative_normalized_and_keeps_fast_at_least_half():
    grid=e().pool_grid()
    assert len(grid)==7
    for weights in grid.values():
        assert sum(weights)==1 and weights[0]>=.5 and max(weights[1:])<=.25 and min(weights)>=0


def test_monthly_blend_preserves_h0_and_uses_monthly_component_values():
    f=pd.DataFrame(dict(origin='2020-01',h=range(13),target=pd.period_range('2020-01',periods=13,freq='M').astype(str),
        as_of_utc='2020-02-01T00:00Z',model='a',mm_forecast=.2,value_core=.1,contribution_core=.05,weight_core=.5))
    b=f.copy();b.loc[b.h.gt(0),['mm_forecast','value_core','contribution_core']]=[.4,.5,.25]
    out=e().blend_native([f,b],[.75,.25],'mix')
    assert out.mm_forecast.iloc[0]==.2
    np.testing.assert_allclose(out.mm_forecast.iloc[1:],.25)
    np.testing.assert_allclose(out.value_core.iloc[1:],.2)
