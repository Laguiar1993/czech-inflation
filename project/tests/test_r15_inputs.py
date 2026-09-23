import numpy as np
import pandas as pd


def test_feature_origin_excludes_later_panel_and_detail():
    from data.core_trend_residual_r15 import features_at, feature_groups
    idx=pd.period_range('2005-01','2011-12',freq='M');t=pd.Period('2010-06','M')
    panel=pd.DataFrame({f'a6_{i:02}':np.arange(len(idx),dtype=float)+100 for i in range(1,73)},index=idx)
    broad=pd.DataFrame({'goods':1.,'services':2.},index=idx)
    fx=pd.Series(.2,index=idx)
    available=pd.Series([(m+1).to_timestamp()+pd.Timedelta(days=19) for m in idx],index=idx)
    clock=pd.Timestamp('2010-07-08');state={'x':{'midtrend':.2}}
    a=features_at(state,panel,broad,fx,available,t,clock)
    panel.loc[t:]=999; broad.loc[t:]=888;fx.loc[t:]=99
    b=features_at(state,panel,broad,fx,available,t,clock)
    pd.testing.assert_series_equal(a,b)
    assert a['services_yoy']==2.
    available.loc[t-1]=clock+pd.Timedelta(days=1)
    c=features_at(state,panel,broad,fx,available,t,clock)
    assert np.isnan(c['services_yoy'])
    groups=feature_groups(a.index)
    assert 'services_yoy' in groups['domestic']
    assert 'goods_yoy' not in groups['domestic']
    assert 'goods_yoy' in groups['imported']
    assert not any(f'a6_{i:02}' in groups['wide'] for i in [1,14,15,16,27,28,69,70,71,72])
    assert 'a6_11' in groups['wide'] and 'unemployment' not in groups['wide']
    assert 'a6_26' in groups['wide'] and 'cost_26_now' not in groups['wide']
