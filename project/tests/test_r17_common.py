import importlib
import numpy as np
import pandas as pd
import pytest


def test_transform_and_month_calendar_are_explicit():
    m=importlib.import_module('r17_common')
    raw=pd.Series([20.,2.],index=pd.period_range('2020-01',periods=2,freq='M'))
    s={k:k*.1 for k in range(1,13)}
    np.testing.assert_allclose(m.adjusted_core(raw,s),100*np.log1p(raw/100)-[.1,.2])
    calendar=pd.DataFrame({'target_month':['2020-01'],'detail_release_dt':['2020-02-10']})
    dates=m.publication_dates(pd.period_range('2019-12',periods=3,freq='M'),calendar)
    assert dates.iloc[0]==pd.Timestamp('2020-01-20 09:00')
    assert dates.iloc[1]==pd.Timestamp('2020-02-10 09:00')
    assert pd.isna(dates.iloc[2])


def test_single_block_replacement_preserves_h0_and_other_contributions():
    m=importlib.import_module('r17_common')
    frame=pd.DataFrame({'h':range(13),'mm_forecast':[.2]*13,'value_core':[.1]*13,
        'weight_core':[.5]*13,'contribution_core':[.05]*13,'value_food':[.3]*13})
    got=m.replace_block(frame,'core',{h:.4 for h in range(1,13)})
    pd.testing.assert_series_equal(got.iloc[0],frame.iloc[0])
    np.testing.assert_allclose(got.loc[got.h.gt(0),'mm_forecast'],.35)
    assert got.value_food.equals(frame.value_food)
    with pytest.raises(ValueError):m.replace_block(frame,'core',{0:1.})


def test_changed_block_does_not_advertise_old_annual_or_cumulative_forecast():
    m=importlib.import_module('r17_common')
    f=pd.DataFrame(dict(h=range(13),mm_forecast=.2,value_core=.1,weight_core=.5,
        contribution_core=.05,yy_exante=2.,yy_conditional=2.,cumulative_log_forecast=1.))
    out=m.replace_block(f,'core',{h:.4 for h in range(1,13)})
    assert out.loc[out.h.gt(0),['yy_exante','yy_conditional','cumulative_log_forecast']].isna().all().all()
    pd.testing.assert_series_equal(out.iloc[0],f.iloc[0])
