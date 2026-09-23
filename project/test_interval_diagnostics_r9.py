import numpy as np
import pandas as pd


def test_interval_only_uses_errors_published_before_current_decision():
    from evaluation.independent_intervals import interval_radius
    errors=pd.Series([.1,.2,100.],index=pd.period_range('2026-01',periods=3,freq='M'))
    releases=pd.Series(pd.to_datetime(['2026-02-10','2026-03-10','2026-04-10']),index=errors.index)
    radius,n=interval_radius(errors,releases,pd.Timestamp('2026-04-01'),minimum=2,coverage=.5)
    assert n==2 and radius==.2


def test_insufficient_pool_is_not_a_zero_width_interval():
    from evaluation.independent_intervals import interval_radius
    idx=pd.period_range('2026-01',periods=2,freq='M')
    radius,n=interval_radius(pd.Series([.1,.2],index=idx),pd.Series(pd.to_datetime(['2026-02-10','2026-03-10']),index=idx),pd.Timestamp('2026-04-01'))
    assert np.isnan(radius) and n==2
