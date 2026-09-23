import numpy as np
import pandas as pd
import pytest


def test_incomplete_prospective_entry_cannot_use_legacy_units(monkeypatch):
    import cz_struct as s
    t=pd.Period('2027-01','M')
    monkeypatch.setattr(s,'_ANN',pd.DataFrame({'available_from':[pd.Timestamp('2026-11-30')],
        'provenance':['prospective'],'announced_regulated_mm_est_pct':[16.5],
        'elec_pct':[10.],'gas_pct':[np.nan],'heat_pct':[0.]},index=pd.PeriodIndex([t])))
    assert not s._gate_fires(t,pd.Timestamp('2026-12-31'),'documented')
    assert np.isnan(s._gate_value(t,pd.Timestamp('2026-12-31'),'documented',w_adm=.15))


def test_quarter_uses_known_and_forecast_months_and_omits_partial_end():
    from evaluation.path_calendar import complete_quarters
    past=pd.Series([1.,2.],index=pd.period_range('2026-07',periods=2,freq='M'))
    future=pd.Series([3.,4.,5.],index=pd.period_range('2026-09',periods=3,freq='M'))
    q=complete_quarters(past,future)
    assert list(q.index)==[pd.Period('2026Q3','Q')]
    assert q.iloc[0]==2.


def test_quarter_rejects_nonfinite_month():
    from evaluation.path_calendar import complete_quarters
    idx=pd.period_range('2026-07',periods=3,freq='M')
    q=complete_quarters(pd.Series(dtype=float,index=pd.PeriodIndex([],freq='M')),
                        pd.Series([1.,float('inf'),3.],index=idx))
    assert q.empty


def test_input_policies_exclude_forecast_expectations():
    from models.independent_nowcast import policy_frame
    f=pd.DataFrame({c:[1.] for c in ['exp12','exp36','exp12_x_state','household_exp','esi','core_l1']})
    assert list(policy_frame(f,'hard').columns)==['core_l1']
    assert list(policy_frame(f,'sentiment').columns)==['esi','core_l1']
    assert list(policy_frame(f,'legacy').columns)==list(f.columns)
    with pytest.raises(ValueError):policy_frame(f,'typo')


def test_independent_error_history_is_sequential_and_does_not_read_legacy_file(monkeypatch):
    import cz_struct as s
    from models.independent_nowcast import sequential_errors
    idx=pd.period_range('2010-01',periods=90,freq='M')
    x=pd.DataFrame({'core_l1':np.sin(np.arange(90)),'exp12':np.arange(90)*100.,'esi':np.arange(90)},index=idx)
    y=pd.Series(np.arange(90)/100,index=idx)
    monkeypatch.setattr(pd,'read_csv',lambda *a,**k:(_ for _ in ()).throw(AssertionError('no frozen legacy errors')))
    # Calendar lookup is independently covered by the release-calendar tests.
    monkeypatch.setattr(s,'_cpi_family_released_by',lambda u,clock:True)
    monkeypatch.setattr(s,'_first_release_dt',lambda u:(u+1).to_timestamp()+pd.Timedelta(days=10))
    a=sequential_errors(x,y,'hard',through=idx[75])
    yy=y.copy();yy.iloc[76:]=999.
    b=sequential_errors(x,yy,'hard',through=idx[75])
    pd.testing.assert_series_equal(a,b)
    u=a.index[-1]
    pred=s._ridge_predict(x[['core_l1']],y,u,as_of=(u+1).to_timestamp()+pd.Timedelta(days=9))[0]
    assert a.loc[u]==pytest.approx(y.loc[u]-pred)
    assert a.index.max()==idx[75]
