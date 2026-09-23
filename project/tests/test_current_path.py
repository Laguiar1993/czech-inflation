import numpy as np
import pandas as pd
import pytest


def test_constant_pump_uses_weighted_relative_changes():
    from models.current_path import constant_pump_path
    idx=pd.to_datetime(['2026-01-05','2026-01-12','2026-01-19','2026-01-26'])
    pump=pd.DataFrame({'gross_petrol95':[20.,20.,40.,40.],'gross_diesel':[10.,10.,10.,10.]},index=idx)
    path,diag=constant_pump_path(pump,'2026-01','2026-02-04T12:00:00Z',.5)
    assert path[1]==pytest.approx(.5*(40/30-1)*100)
    assert path[1]!=pytest.approx((25/20-1)*100)
    assert np.allclose([path[h] for h in range(2,13)],0)
    assert diag['available_from'].startswith('2026-02-02')


def test_pump_future_poison_cannot_change_path():
    from models.current_path import constant_pump_path
    idx=pd.date_range('2026-01-05',periods=10,freq='W-MON')
    pump=pd.DataFrame({'gross_petrol95':np.arange(10)+30.,'gross_diesel':np.arange(10)+31.},index=idx)
    a,_=constant_pump_path(pump,'2026-01','2026-02-04T12:00:00Z',.6)
    pump.loc[pump.index>='2026-02-01',:]=9000
    b,_=constant_pump_path(pump,'2026-01','2026-02-04T12:00:00Z',.6)
    assert a==b


def test_pump_rejects_duplicate_dates():
    from models.current_path import constant_pump_path
    pump=pd.DataFrame({'gross_petrol95':[30.,31.],'gross_diesel':[32.,33.]},index=pd.to_datetime(['2026-01-05']*2))
    with pytest.raises(ValueError,match='unique'):constant_pump_path(pump,'2026-01','2026-02-04T12:00:00Z',.6)


def test_core_h1_is_two_transitions_after_last_observation():
    from models.current_path import core_paths
    from models.core_trend_residual_r15 import state_at
    idx=pd.period_range('2010-01','2026-01',freq='M')
    core=pd.Series(.2+.1*np.sin(np.arange(len(idx))),index=idx)
    available=pd.Series([(m+1).to_timestamp()+pd.Timedelta(days=10) for m in idx],index=idx)
    features=pd.DataFrame({'import_l2':0.,'eurczk_mm':0.},index=idx)
    paths,diag=core_paths(core,features,available,'2026-01','2026-02-04T12:00:00Z')
    state=state_at(core,available,'2026-01','2026-02-04T12:00:00Z')
    f=state['filter_states']['fast']
    expected=100*np.expm1((f['mu']+.8**2*f['cycle']+state['seasonal'][2])/100)
    assert paths['STATE_FAST_R15'][1]==pytest.approx(expected)
    core.loc['2026-01']=800.
    again,_=core_paths(core,features,available,'2026-01','2026-02-04T12:00:00Z')
    assert paths==again


def test_unreleased_last_core_fails_closed():
    from models.current_path import core_paths
    idx=pd.period_range('2010-01','2026-01',freq='M')
    core=pd.Series(.2,index=idx);features=pd.DataFrame({'import_l2':0.,'eurczk_mm':0.},index=idx)
    available=pd.Series([(m+1).to_timestamp()+pd.Timedelta(days=10) for m in idx],index=idx)
    available.loc['2025-12']=pd.Timestamp('2026-02-10')
    with pytest.raises(ValueError,match='core'):core_paths(core,features,available,'2026-01','2026-02-04T12:00:00Z')


def test_timezone_required():
    from models.current_path import aware_clock
    with pytest.raises(ValueError,match='timezone'):aware_clock('2026-01-01')
