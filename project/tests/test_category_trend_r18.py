import numpy as np
import pandas as pd
import pytest
from models.category_trend_r18 import fit_path, smooth_correction


def fixture():
    dates=pd.period_range('2015-02',periods=60,freq='M')
    rng=np.random.default_rng(42)
    return pd.DataFrame(rng.normal(0,.06,(60,8)),index=dates,columns=['core',*[f'cat{i}' for i in range(7)]])


def test_common_jump_changes_common_trend_more_than_isolated_jump():
    a=fixture();b=a.copy();a.iloc[-5:,:]+=.7;b.iloc[-5:,1]+=.7
    x=fit_path(a,'2020-02',.01);y=fit_path(b,'2020-02',.01)
    assert x['mean'][0]>y['mean'][0]+.2
    assert np.linalg.eigvalsh(x['covariance']).min()>-1e-10


def test_h1_is_two_transitions_and_no_future_observation_allowed():
    f=fixture();out=fit_path(f,'2020-02',.0025)
    mean=out['mean'];expected=out['seasonal'][3][0]+mean[0]+.3**2*mean[1]+.95**2*mean[2]
    assert out['path'][1]==pytest.approx(expected)
    f.loc[pd.Period('2020-02','M')]=100
    with pytest.raises(ValueError,match='future'):fit_path(f,'2020-02',.0025)


def test_missing_calendar_month_and_nonfinite_rejected():
    f=fixture()
    with pytest.raises(ValueError):fit_path(f.drop(f.index[-3]),'2020-02',.01)
    f.iloc[-1,2]=np.nan
    with pytest.raises(ValueError):fit_path(f,'2020-02',.01)


def test_smooth_ridge_does_not_borrow_future_targets():
    origins=pd.period_range('2015-01',periods=50,freq='M')
    features={str(o):[1.,-.5] for o in origins}
    rows=[]
    for o in origins:
        for h in range(1,13):rows.append(dict(origin=str(o),h=h,target=str(o+h),
            released=str((o+h+1).to_timestamp()+pd.Timedelta(days=10)),error=.2))
    rows=pd.DataFrame(rows);clock='2019-03-09';origin='2019-02'
    a=smooth_correction(features,rows,origin,clock,[1.,-.5])
    assert a['status']=='estimated'
    assert all(pd.Period(k,'M')<pd.Period(origin,'M') for k in a['training_targets'])
    rows.loc[(rows.target>=origin)|(pd.to_datetime(rows.released)>pd.Timestamp(clock)),'error']=100000
    b=smooth_correction(features,rows,origin,clock,[1.,-.5])
    np.testing.assert_array_equal(a['correction'],b['correction'])
    assert max(a['correction'])-min(a['correction'])<1e-9
