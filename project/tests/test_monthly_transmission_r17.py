"""Declared category-pressure and generated-forecast information contracts."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PATH = Path(__file__).resolve().parents[1] / 'models/monthly_transmission_r17.py'
CATEGORIES = ['actual_rent','imputed_rent','catering','accommodation','package_holidays']


def engine():
    assert PATH.exists(), 'Monthly transmission implementation is absent'
    from models import monthly_transmission_r17
    return monthly_transmission_r17


def fixture():
    dates = pd.period_range('2015-01','2024-12',freq='M'); k = np.arange(len(dates))
    rates = np.array([.2+j*.02+(j+1)*.12*np.sin(k*2*np.pi/12)+.03*np.cos(k) for j in range(5)]).T
    levels = pd.DataFrame(100*np.exp(rates.cumsum(axis=0)/100),index=dates,columns=CATEGORIES)
    available = pd.Series([(m+1).start_time+pd.Timedelta(days=9,hours=9) for m in dates],index=dates)
    weights = pd.DataFrame([dict(effective_year=year,series_name=c,weight_permille=10+j*10+(year-2014),availability_assumption_date=f'{year}-02-10') for year in (2014,2016,2018,2020,2022,2024) for j,c in enumerate(CATEGORIES)])
    macro = dict(unemployment_change3=.1,ip_growth3=2.,ulc_growth12=4.,fx3=-1.,cost_26_mean3=.01,cost_45_mean3=.02)
    return levels,available,weights,macro


def snapshots(end='2021-01'):
    model=engine();levels,available,weights,macro=fixture();saved={}
    for t in pd.period_range('2016-02',end,freq='M'):
        clock=(t+1).start_time+pd.Timedelta(days=8,hours=23)
        saved[str(t)]=model.snapshot(levels,available,weights,macro,t,clock)
    return levels,available,weights,saved


def test_level_changes_need_both_released_endpoints():
    model=engine();levels,available,_,_=fixture();available.loc['2018-11']=pd.Timestamp('2030-01-01')
    rates=model.released_rates(levels,available,'2019-01','2019-02-09 23:00')
    assert rates.loc[['2018-11','2018-12']].isna().all().all()
    assert rates.index.max()==pd.Period('2018-12') and rates.iloc[0].isna().all()


def test_snapshot_seasonality_scale_and_features_ignore_future_values():
    model=engine();levels,available,weights,macro=fixture()
    a=model.snapshot(levels,available,weights,macro,'2019-01','2019-02-09 23:00')
    poison=levels.copy();poison.loc[poison.index>=pd.Period('2019-01')]=1e12
    b=model.snapshot(poison,available,weights,macro,'2019-01','2019-02-09 23:00')
    assert a==b
    raw=100*np.log(levels.loc[:'2018-12']/levels.loc[:'2018-12'].shift())
    means=raw.groupby(raw.index.month).mean().reindex(range(1,13))
    np.testing.assert_allclose(a['seasonal'],means.to_numpy())
    adjusted=raw.to_numpy()-means.to_numpy()[raw.index.month-1]
    np.testing.assert_allclose(a['scales'],np.maximum(.05,np.nanstd(adjusted,axis=0)))


def test_weight_regime_requires_publication_and_origin_effective_year():
    model=engine();levels,available,weights,macro=fixture()
    a=model.snapshot(levels,available,weights,macro,'2020-01','2020-02-09 23:59')
    b=model.snapshot(levels,available,weights,macro,'2020-01','2020-02-10 00:00')
    assert a['weight_metadata']['effective_year']==2018
    assert b['weight_metadata']['effective_year']==2020
    assert a['weights']!=b['weights']


def test_pressure_uses_exact_relative_arithmetic_and_requires_all_categories():
    model=engine();rates=np.array([10.,-5.,2.,3.,4.]);weights=np.array([.05,.1,.03,.02,.01])
    mm=100*np.expm1(rates/100);result=model.pressure(rates,weights)
    assert result['pressure_mm']==pytest.approx(weights@mm/weights.sum())
    assert result['contribution_diagnostic']==pytest.approx(weights@mm)
    assert result['pressure_log']==pytest.approx(100*np.log1p(result['pressure_mm']/100))
    assert model.remainder(.7,result['pressure_mm'])+result['pressure_mm']==pytest.approx(.7)
    rates[3]=np.nan
    assert np.isnan(model.pressure(rates,weights)['pressure_mm'])


def test_calendar_gap_is_not_collapsed_into_a_lag():
    model=engine();levels,available,weights,macro=fixture()
    with pytest.raises(ValueError,match='Contiguous'):
        model.snapshot(levels.drop(pd.Period('2018-10')),available,weights,macro,'2019-01','2019-02-09 23:00')


def test_pooled_training_uses_saved_scale_and_means_and_shared_origin_support():
    model=engine();levels,available,_,saved=snapshots()
    saved['2017-04']['macro']['fx3']=np.nan
    results=[model.stage1_training(saved,levels,available,'2021-01','2021-02-09 23:00',12,f) for f in model.FAMILIES]
    for result in results[1:]:
        assert result[2]==results[0][2]
    x,y,audit=results[0]
    assert '2017-04' not in [r['origin'] for r in audit]
    assert len(y)==5*len(audit)
    source=saved[audit[0]['origin']];target=pd.Period(audit[0]['target']);j=0
    rate=100*np.log(levels.iloc[:,j].loc[target]/levels.iloc[:,j].loc[target-1])
    assert y[0]==pytest.approx((rate-source['seasonal'][target.month-1][j])/source['scales'][j])
    np.testing.assert_allclose(x[0,:2],source['own'][j])
    assert all(pd.Period(r['target'])<pd.Period('2021-01') for r in audit)


def test_train_only_pooled_rms_and_declared_penalties():
    model=engine();x=np.array([[1.,3.],[2.,4.],[3.,5.]]);y=np.array([.2,.4,.1]);penalties=np.array([.1,1.])
    fit=model.ridge(x,y,penalties);scale=np.sqrt((x*x).mean(axis=0));z=x/scale
    np.testing.assert_allclose(fit['scale'],scale)
    np.testing.assert_allclose(fit['beta'],np.linalg.solve(z.T@z/3+np.diag(penalties),z.T@y/3))


def test_early_category_forecasts_are_explicit_persistence_fallbacks():
    model=engine();levels,available,_,saved=snapshots('2016-02')
    result=model.first_stage(saved,levels,available,'2016-02','2016-03-09 23:00')
    for family in model.FAMILIES:
        np.testing.assert_array_equal(result['category_log'][family],result['category_log']['persistence'])
        assert result['status'][family]==['fallback_persistence']*12
    assert all(r['n_train_origins']==0 for r in result['fits'])


def test_stage2_uses_saved_generated_forecasts_and_mature_core_labels_only():
    model=engine();levels,available,_,saved=snapshots('2021-01');generated={};core_states={}
    core=pd.Series(.3,index=levels.index)
    for s in saved:
        generated[s]={f:np.full(12,.05 if f=='persistence' else .15).tolist() for f in ('persistence',*model.FAMILIES)}
        core_states[s]={'own':[.1,-.1],'fast_log':[.2]*12,'as_of':saved[s]['as_of']}
    x,y,audit=model.stage2_training(core_states,generated,core,available,'2021-01','2021-02-09 23:00',12,'both')
    assert np.allclose(x[:,2],.1)
    assert np.allclose(y,100*np.log1p(.3/100)-.2)
    assert all(pd.Period(r['target'])<pd.Period('2021-01') for r in audit)
    poison=core.copy();poison.loc[poison.index>=pd.Period('2021-01')]=1000
    b=model.stage2_training(core_states,generated,poison,available,'2021-01','2021-02-09 23:00',12,'both')
    np.testing.assert_array_equal(x,b[0]);np.testing.assert_array_equal(y,b[1])
    generated[audit[0]['origin']]['both'][11]=.75
    c=model.stage2_training(core_states,generated,core,available,'2021-01','2021-02-09 23:00',12,'both')
    assert c[0][0,2]==pytest.approx(.7)


def test_stage2_unreleased_target_is_excluded_not_imputed():
    model=engine();levels,available,_,saved=snapshots('2021-01');generated={};states={}
    core=pd.Series(.2,index=levels.index)
    for s in saved:
        generated[s]={f:[0.]*12 for f in ('persistence',*model.FAMILIES)}
        states[s]={'own':[.1,.2],'fast_log':[.2]*12,'as_of':saved[s]['as_of']}
    available.loc['2020-12']=pd.NaT
    _,_,audit=model.stage2_training(states,generated,core,available,'2021-01','2021-02-09 23:00',1,'own')
    assert '2020-12' not in [r['target'] for r in audit]


def runner():
    path=PATH.parents[1]/'monthly_transmission_experiment_r17.py'
    assert path.exists(), 'Monthly transmission runner is absent'
    import monthly_transmission_experiment_r17
    return monthly_transmission_experiment_r17


def test_native_replacement_recomputes_all_derived_fields_and_preserves_h0():
    module=runner();base=pd.DataFrame(dict(origin=['2020-01']*13,h=range(13),mm_forecast=[.2]*13,
        model=['STATE_FAST_R15']*13,value_core=[.1]*13,weight_core=[.5]*13,contribution_core=[.05]*13,
        yy_exante=[999.]*13,yy_conditional=[999.]*13,cumulative_log_forecast=[999.]*13,
        cumulative_log_actual=[999.]*13, fallback_used=[False]*13))
    for c in ('food','administered','alcohol_tobacco','fuel','wedge'):base['contribution_'+c]=.03
    predictions=pd.DataFrame(dict(origin=['2020-01']*12,model=['MONTHLY_BOTH_CORE_R17']*12,h=range(1,13),core_mm=[.4]*12,status=['estimated']*12,reason=['']*12))
    actual=pd.Series(.1,index=pd.period_range('2018-01','2021-12',freq='M'))
    result=module.integrate_core(base,predictions,actual)
    assert result.mm_forecast.iloc[0]==.2 and np.allclose(result.mm_forecast.iloc[1:],.35)
    assert result.cumulative_log_forecast.iloc[-1]==pytest.approx(1200*np.log1p(.35/100))
    assert result.yy_exante.iloc[-1]==pytest.approx(100*((1+.35/100)**12-1))
    assert result.yy_conditional.iloc[1]!=result.yy_exante.iloc[1]
    pd.testing.assert_series_equal(result.weight_core,base.weight_core)
    pd.testing.assert_series_equal(result.contribution_food,base.contribution_food)


def test_runner_refuses_overwrite_and_verifies_source_manifest(tmp_path):
    module=runner()
    with pytest.raises(FileExistsError):module.run(tmp_path)
    m=tmp_path/'manifest.json';m.write_text('{"inputs":{"a.csv":"bad"},"outputs":{}}');(tmp_path/'a.csv').write_text('a')
    with pytest.raises(ValueError,match='hash'):module.verify_manifest(tmp_path,m)


def test_current_macro_gap_causes_common_firststage_fallback():
    model=engine();levels,available,_,saved=snapshots('2021-01');saved['2021-01']['macro']['fx3']=np.nan
    result=model.first_stage(saved,levels,available,'2021-01','2021-02-09 23:00')
    for family in model.FAMILIES:
        assert result['status'][family]==['fallback_persistence']*12
        assert result['reasons'][family]==['missing_current_common_feature']*12
    assert result['status']['persistence']==['control']*12


def test_stage_two_zero_increment_equals_own_control_with_identical_calendar():
    model=engine();levels,available,_,saved=snapshots('2021-01');generated={};states={};status={}
    core=pd.Series(.3,index=levels.index)
    for s in saved:
        generated[s]={f:[.1]*12 for f in ('persistence',*model.FAMILIES)}
        states[s]={'own':[.1,.2],'fast_log':[.2]*12,'as_of':saved[s]['as_of']}
        status[s]={f:['fallback_persistence']*12 for f in model.FAMILIES}
    result=model.second_stage(states,generated,status,core,available,'2021-01','2021-02-09 23:00')
    for family in model.FAMILIES:
        np.testing.assert_allclose(result['core_log'][family],result['core_log']['own'])
    assert all(f['n_generated_estimated']==0 for f in result['fits'])


def test_missing_generated_json_value_remains_unavailable_without_imputation():
    model=engine();levels,available,_,saved=snapshots('2021-01');generated={};states={};status={}
    core=pd.Series(.3,index=levels.index)
    for s in saved:
        generated[s]={f:[.1]*12 for f in ('persistence',*model.FAMILIES)}
        states[s]={'own':[.1,.2],'fast_log':[.2]*12,'as_of':saved[s]['as_of']}
        status[s]={f:['estimated']*12 for f in model.FAMILIES}
    generated['2017-01']['domestic'][0]=None
    _,_,audit=model.stage2_training(states,generated,core,available,'2021-01','2021-02-09 23:00',1,'both')
    assert '2017-01' not in [r['origin'] for r in audit]
    generated['2021-01']['domestic'][0]=None
    result=model.second_stage(states,generated,status,core,available,'2021-01','2021-02-09 23:00')
    for f in model.CORE_FAMILIES:
        assert result['core_log'][f][0]==.2
        assert result['status'][f][0]=='fallback_fast'
