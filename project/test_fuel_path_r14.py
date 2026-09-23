"""R14 fuel provenance, weekly dynamics and unchanged-bridge contracts."""
import importlib
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def model():
    assert importlib.util.find_spec('models.fuel_path_r14'), 'R14 fuel model not implemented'
    return importlib.import_module('models.fuel_path_r14')


def synthetic():
    days=pd.date_range('2010-01-01','2020-12-31')
    z=np.arange(len(days)); cost=40+5*np.sin(z/60)
    oil=pd.DataFrame({'brent_usd':cost},index=days)
    fx=pd.DataFrame({'usdczk':20+np.sin(z/100)},index=days)
    weeks=pd.date_range('2010-02-01','2020-12-28',freq='W-MON')
    pump=pd.DataFrame(index=weeks)
    for name,b in [('petrol95',1.1),('diesel',1.2)]:
        net=5+b*(oil.brent_usd*fx.usdczk/158.987294928).reindex(weeks).to_numpy()
        pump['net_'+name]=net
        pump['vat_'+name]=.21
        pump['excise_'+name]=12 if name=='petrol95' else 10
        pump['gross_'+name]=(net+pump['excise_'+name])*1.21
    return dict(pump=pump,oil=oil,fx=fx)


def test_conversion_eur_per_czk_and_tax_identity():
    assert importlib.util.find_spec('tools.r14_fuel.prepare'), 'R14 source preparation not implemented'
    prep=importlib.import_module('tools.r14_fuel.prepare')
    assert prep.local_price(1600,.04)==40
    assert prep.local_price(400,.04)==10
    with pytest.raises(ValueError): prep.local_price(1600,0)


def test_origin_gates_and_future_poisoning():
    m=model(); data=synthetic(); t=pd.Period('2019-01'); clock=pd.Timestamp('2019-02-10 23:59')
    first=m.forecast(data,t,clock,.67)
    poisoned={k:v.copy() for k,v in data.items()}
    poisoned['pump'].loc[poisoned['pump'].index+pd.Timedelta(days=7)>clock]=1e7
    poisoned['oil'].loc[poisoned['oil'].index+pd.Timedelta(days=14)>clock]=1e7
    poisoned['fx'].loc[poisoned['fx'].index+pd.Timedelta(hours=14,minutes=30)>clock]=1e7
    second=m.forecast(poisoned,t,clock,.67)
    for name in first['forecasts']:
        np.testing.assert_array_equal(first['forecasts'][name],second['forecasts'][name])
    assert pd.Timestamp(first['audit']['pump_available_end'])<=clock
    assert pd.Timestamp(first['audit']['oil_available_end'])<=clock
    assert pd.Timestamp(first['audit']['fx_available_end'])<=clock


def test_constant_pump_control_decays_to_zero_and_zero_control_is_literal():
    m=model(); data=synthetic()
    got=m.forecast(data,pd.Period('2019-01'),'2019-02-10 23:59',.67)
    assert len(got['forecasts']['FUEL_ZERO_R14'])==12
    np.testing.assert_array_equal(got['forecasts']['FUEL_ZERO_R14'],np.zeros(12))
    np.testing.assert_allclose(got['forecasts']['FUEL_CONSTANT_PUMP_R14'][2:],0,atol=1e-12)


def test_monthly_relative_blend_not_relative_of_blended_levels():
    m=model(); idx=pd.to_datetime(['2019-01-07','2019-02-04'])
    gross=pd.DataFrame({'petrol95':[10,11],'diesel':[100,100]},index=idx)
    assert m.monthly_rates(gross,pd.Period('2019-01'),.5,horizons=1)[0]==pytest.approx(5.)


def test_missing_target_weeks_do_not_become_observed_interpolations():
    m=model(); data=synthetic(); missing=data['pump'].index[-110]
    data['pump'].loc[missing,['net_petrol95','net_diesel','gross_petrol95','gross_diesel']]=np.nan
    got=m.forecast(data,pd.Period('2019-01'),'2019-02-10 23:59',.67)
    assert str(missing.date()) not in got['fit_rows'].week.tolist()
    assert not got['fit_rows'].isna().any().any()


def test_insufficient_fit_returns_named_constant_pump_fallback():
    m=model(); data=synthetic(); data['pump']=data['pump'].tail(70)
    got=m.forecast(data,pd.Period('2020-11'),'2020-12-10 23:59',.67)
    assert got['audit']['fallback_used']
    assert got['audit']['status']=='insufficient_history'
    np.testing.assert_array_equal(got['forecasts']['FUEL_ECM_R14'],got['forecasts']['FUEL_CONSTANT_PUMP_R14'])


def test_nonpositive_projection_fails_closed_to_control(monkeypatch):
    m=model(); data=synthetic()
    def bad(*args,**kwargs): return np.full(len(args[0]),-1.)
    monkeypatch.setattr(m,'project_net',bad)
    got=m.forecast(data,pd.Period('2019-01'),'2019-02-10 23:59',.67)
    assert got['audit']['status']=='nonpositive_projection'
    np.testing.assert_array_equal(got['forecasts']['FUEL_ECM_R14'],got['forecasts']['FUEL_CONSTANT_PUMP_R14'])


def test_stable_constant_cost_at_long_run_equilibrium():
    m=model(); idx=pd.date_range('2019-01-07',periods=60,freq='W-MON')
    result=m.project_net(idx,pd.Series(10.,index=idx),10.,0.,10.,0.,
                         dict(a=5.,b=.5,lam=.25,beta0=.3,beta1=.2,phi=.5))
    np.testing.assert_allclose(result,10.)


def test_effective_wedge_closes_observed_price_despite_schedule_conflict():
    m=model()
    assert hasattr(m,'effective_wedge'), 'observed tax/reconciliation wedge missing'
    gross,net,vat=41.297,24.17974344,.21
    wedge=m.effective_wedge(gross,net,vat)
    assert abs(wedge-8.011)>1.9
    assert (net+wedge)*(1+vat)==pytest.approx(gross,abs=1e-13)


def test_training_uses_own_clock_source_bounds():
    m=model(); got=m.forecast(synthetic(),pd.Period('2019-01'),'2019-02-10 23:59',.67)
    for row in got['parameters']:
        assert row['n_longrun']<=260 and row['n_dynamic']>=104
        assert pd.Timestamp(row['last_training_available'])<=pd.Timestamp('2019-02-10 23:59')
        assert 0<=row['lam']<=1 and 0<=row['phi']<=.8


def test_native_output_preserves_h0_nonfuel_and_weights():
    root=Path(__file__).parent
    file=root/'output/research_r14/fuel/native_forecasts.csv'
    assert file.exists(), 'R14 fuel empirical output not produced'
    got=pd.read_csv(file,float_precision='round_trip')
    base=pd.read_csv(root/'output/independent_bridge_forecasts.csv',float_precision='round_trip')
    base=base[base.model=='INDEPENDENT_BRIDGE'].set_index(['origin','h'])
    for name,group in got.groupby('model'):
        group=group.set_index(['origin','h']).reindex(base.index)
        cols=[c for c in base if (c.startswith('value_') or c.startswith('contribution_') or c.startswith('weight_')) and c not in ('value_fuel','contribution_fuel')]
        for c in cols: np.testing.assert_array_equal(group[c],base[c])
        h0=base.index.get_level_values('h')==0
        np.testing.assert_array_equal(group.loc[h0,'mm_forecast'],base.loc[h0,'mm_forecast'])
        changed=group.mm_forecast-base.mm_forecast
        np.testing.assert_array_equal(np.isfinite(group.mm_forecast),np.isfinite(base.mm_forecast))
        valid=(~h0)&np.isfinite(base.mm_forecast)
        np.testing.assert_allclose(changed.loc[valid],(group.contribution_fuel-base.contribution_fuel).loc[valid],atol=1e-12)


def test_custom_clock_calls_are_immutable_and_order_independent():
    m=model(); data=synthetic(); saved={k:v.copy(deep=True) for k,v in data.items()}
    origin=pd.Period('2019-01'); clock='2019-01-24 00:00'
    first=m.forecast(data,origin,clock,.67)
    m.forecast(data,origin,'2019-02-10 23:59',.67)
    again=m.forecast(data,origin,clock,.67)
    for name in first['forecasts']:
        np.testing.assert_array_equal(first['forecasts'][name],again['forecasts'][name])
    for key in data: pd.testing.assert_frame_equal(data[key],saved[key])
    assert first['audit']==again['audit']


def test_native_annual_forecasts_compound_changed_monthly_path():
    from models.path_inputs import compound_path
    from path_improvements_experiment_r12 import read
    root=Path(__file__).parent
    head=read(root/'tests/fixtures/cleanup/target_headline_cpi_mm.csv').iloc[:,0]
    native=pd.read_csv(root/'output/research_r14/fuel/native_forecasts.csv',float_precision='round_trip')
    for (origin,name),group in native.groupby(['origin','model']):
        t=pd.Period(origin,'M'); group=group.set_index('h'); path=group.mm_forecast.to_dict()
        for h in range(1,13):
            expected=compound_path(head.loc[head.index<t],path,t,h,path[0])
            np.testing.assert_allclose(group.loc[h,'yy_exante'],expected,atol=1e-12,equal_nan=True)
