import numpy as np
import pandas as pd
import pytest


def test_signal_inputs_use_annual_log_changes_and_gate_unpublished_prices():
    from data.core_slope_transmission_r16 import signal_features_at
    months=pd.period_range('2003-01','2008-12',freq='M');t=pd.Period('2008-01','M')
    panel=pd.DataFrame({f'a6_{i:02}':100.+np.arange(len(months)) for i in range(1,73)},index=months)
    broad=pd.DataFrame({'services':np.arange(len(months))/10,'goods':np.arange(len(months))/20},index=months)
    fx=pd.Series(.1,index=months);available=pd.Series([(m+1).to_timestamp() for m in months],index=months)
    rows=signal_features_at(panel,broad,fx,available,t,pd.Timestamp('2008-02-09'))
    z=100*np.log1p(broad.services/100)
    assert rows['services']['level']==pytest.approx(z[t-1])
    assert rows['services']['change12']==pytest.approx(z[t-1]-z[t-13])
    assert rows['services']['change3']==pytest.approx(z[t-1]-z[t-4])
    broad.loc[broad.index>=t]=1e9;panel.loc[panel.index>=t]=1e9;fx.loc[fx.index>=t]=1e9
    poisoned=signal_features_at(panel,broad,fx,available,t,pd.Timestamp('2008-02-09'))
    for group in rows:pd.testing.assert_series_equal(rows[group],poisoned[group])
    available[t-1]=pd.Timestamp('2008-03-01')
    hidden=signal_features_at(panel,broad,fx,available,t,pd.Timestamp('2008-02-09'))
    assert np.isnan(hidden['services']['level'])


def test_stage2_never_imputes_a_missing_generated_forecast():
    from data.core_slope_transmission_r16 import stage2_design
    months=pd.period_range('2010-01','2010-03',freq='M')
    projections=pd.DataFrame([{'origin':str(t),'band':0,'signal':s,'predicted_change':v}
        for t,v in zip(months,[1.,np.nan,3.]) for s in ('services','goods')])
    acceleration=pd.Series([.1,.2,.3],index=months)
    design=stage2_design(projections,acceleration,0,'both')
    assert list(design.index)==[months[0],months[2]]
    assert design.loc[months[0],'services_projection']==pytest.approx(1/12)
    assert len(stage2_design(projections,acceleration,0,'own'))==3
    with pytest.raises(ValueError,match='Duplicate'):
        stage2_design(pd.concat([projections,projections.iloc[:1]]),acceleration,0,'both')
