"""Behavioural R13 contracts, written before the estimator."""
import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest


def model():
    assert importlib.util.find_spec('models.core_path_r13') is not None, 'R13 estimator is not implemented'
    return importlib.import_module('models.core_path_r13')


def sample():
    idx = pd.period_range('2000-01', '2014-12', freq='M')
    z = np.arange(len(idx))
    core = pd.Series(.2 + .05*np.sin(z/4), index=idx)
    names = ('actual_rent', 'imputed_rent', 'catering', 'accommodation', 'package_holidays')
    cats = pd.DataFrame({n: .1+j*.02 + .08*np.sin(z/5+j) for j,n in enumerate(names)},index=idx)
    w = pd.Series([.02,.1,.06,.01,.015],index=names)
    dates = pd.Series([(p+1).to_timestamp()+pd.Timedelta(days=9) for p in idx],index=idx)
    clocks = pd.Series([(p+1).to_timestamp()+pd.Timedelta(days=8,hours=23) for p in idx],index=idx)
    ext = pd.DataFrame({'import_mm_l3':np.cos(z/7), 'eurczk_mm_l1':np.sin(z/7),
                        'unemployment_rate_l3':4+np.cos(z/30)},index=idx)
    return core,cats,w,dates,clocks,ext


def run_sample(origin='2012-01', **changes):
    m=model(); core,cats,w,dates,clocks,ext=sample(); t=pd.Period(origin,'M')
    args=dict(core=core,categories=cats,weights=w,core_weight=.55,available=dates,
              historical_clocks=clocks,external=ext,origin=t,as_of=clocks[t])
    args.update(changes)
    return m.forecast_origin(**args)


def test_cumulative_reconstruction_is_arithmetic_and_h1_exact():
    m=model(); cumulative={h:float(h*h)/100 for h in range(1,13)}
    path=m.reconstruct_cumulative(cumulative)
    assert path[1] == cumulative[1]
    assert sum(path.values()) == pytest.approx(cumulative[12],abs=1e-14)
    assert path[4] == pytest.approx(.07)


def test_cumulative_missing_horizon_is_not_skipped():
    m=model(); cumulative={h:float(h) for h in range(1,13)}; cumulative[5]=np.nan
    path=m.reconstruct_cumulative(cumulative)
    assert np.isnan(path[5]) and np.isnan(path[6])
    assert path[7] == 1


def test_origin_weights_reconstruct_entire_historical_remainder():
    m=model(); core,cats,w,dates,clocks,ext=sample(); t=pd.Period('2012-01','M')
    panel=m.target_panel(core,cats,w,.55,t,clocks[t],dates)
    reconstructed=panel[list(w.index)].mul(w).sum(axis=1,min_count=5)+panel[m.REMAINDER]
    np.testing.assert_allclose(reconstructed,.55*panel.core,equal_nan=True,atol=1e-15)
    changed=m.target_panel(core,cats,w*1.1,.6,t,clocks[t],dates)
    assert abs(changed.loc['2005-01',m.REMAINDER]-panel.loc['2005-01',m.REMAINDER])>1e-4


def test_future_outcome_poisoning_cannot_change_forecast():
    core,cats,w,dates,clocks,ext=sample(); t=pd.Period('2012-01','M')
    reference=run_sample()
    core.loc[core.index>=t]=1e8; cats.loc[cats.index>=t]=1e8
    changed=run_sample(core=core,categories=cats)
    assert reference['paths'] == changed['paths']


def test_future_external_rows_cannot_change_forecast():
    core,cats,w,dates,clocks,ext=sample(); reference=run_sample()
    ext.loc[ext.index>pd.Period('2012-01','M')]=1e12
    assert reference['paths'] == run_sample(external=ext)['paths']


def test_h1_monthly_and_cumulative_fits_match():
    result=run_sample()
    for prefix in ('CORE_AGG','CORE_SPLIT'):
        assert result['paths'][prefix+'_MONTHLY_R13'][1] == pytest.approx(
            result['paths'][prefix+'_CUMULATIVE_R13'][1],abs=1e-13)


def test_complete_future_window_and_delayed_labels_share_training_mask():
    core,cats,w,dates,clocks,ext=sample(); t=pd.Period('2012-01','M')
    dates.loc[t-4]=clocks[t]+pd.Timedelta(days=1)
    result=run_sample(available=dates)
    fits=pd.DataFrame(result['fits']); h12=fits[fits.h==12]
    assert h12.n_train.nunique()==1
    assert all(pd.Period(x,'M')<=t-2 for x in h12.last_training_target)
    assert h12.training_origins.nunique()==1
    assert str(t-12) not in h12.iloc[0].training_origins.split('|')


def test_insufficient_history_is_missing_without_bridge_fallback():
    result=run_sample(origin='2002-01')
    assert all(np.isnan(v) for path in result['paths'].values() for v in path.values())
    assert {f['fit_status'] for f in result['fits']} == {'insufficient_history'}


def test_missing_labour_only_removes_both_labour_diagnostics():
    core,cats,w,dates,clocks,ext=sample(); ext['unemployment_rate_l3']=np.nan
    result=run_sample(external=ext)
    assert np.isfinite(result['paths']['CORE_AGG_CUMULATIVE_R13'][12])
    assert np.isnan(result['paths']['CORE_AGG_CUMULATIVE_LABOUR_R13'][12])
    assert np.isnan(result['paths']['CORE_AGG_CUMULATIVE_LABOUR_CONTROL_R13'][12])


def test_train_only_scaling_handles_decimal_constant():
    m=model(); idx=pd.period_range('2000-01',periods=60,freq='M')
    x=pd.DataFrame({'x':np.arange(60.),'constant':.1},index=idx); y=pd.Series(np.arange(60.)/100,index=idx)
    p,diag=m.fit_ridge(x,y,pd.Series({'x':100000.,'constant':.1}))
    assert np.isfinite(p)
    assert diag['training_center']['x']==29.5
    assert diag['training_scale']['constant']==1.
    assert diag['training_scale']['x']==pytest.approx(np.arange(60.).std())


def test_destination_calendar_is_target_month_not_origin():
    m=model(); core,cats,w,dates,clocks,ext=sample()
    design=m.feature_design(core,ext,12)
    assert design.loc['2003-02','destination_mon_2']==1.
    design=m.feature_design(core,ext,1)
    assert design.loc['2003-01','destination_mon_2']==1.
    assert design.loc['2003-02','destination_mon_2']==0.


def test_unknown_external_feature_rejected():
    m=model(); core,cats,w,dates,clocks,ext=sample(); ext['exp12']=2.
    with pytest.raises(ValueError,match='Unsupported'):
        m.feature_design(core,ext,1)


def test_external_lags_releases_and_future_vintage_poisoning():
    m=model(); idx=pd.period_range('2019-01','2021-01',freq='M'); t=pd.Period('2020-06','M')
    features=pd.DataFrame({'eurczk_mm':np.arange(len(idx)), 'import_l2':100+np.arange(len(idx))},index=idx)
    old=dict(reference_period='2020-03',available_from='2020-05-01T00:00:00Z',value=3.,adjustment='sa',vintage_kind='historical_release')
    late={**old,'available_from':'2021-01-01T00:00:00Z','value':9999.}
    stamp=pd.Timestamp('2020-07-09T23:00:00Z')
    values,audit=m.external_at(features,pd.DataFrame([old,late]),t,stamp,stamp)
    assert values['unemployment_rate_l3']==3.
    assert values['eurczk_mm_l1']==features.loc[t-1,'eurczk_mm']
    assert values['import_mm_l3']==features.loc[t-1,'import_l2']
    assert audit['unemployment_reference']=='2020-03'
    assert audit['unemployment_adjustment']=='sa'


def test_exact_noncore_h0_and_failed_baseline_preservation():
    m=model(); base=pd.DataFrame({'h':range(13),'mm_forecast':[.3]*13,'value_core':[.2]*13,
        'weight_core':[.55]*13,'contribution_core':[.11]*13,
        'contribution_food':[.10]*13,'contribution_fuel':[.02]*13,
        'contribution_administered':[.03]*13,'contribution_alcohol_tobacco':[.01]*13,
        'contribution_wedge':[.03]*13})
    base.loc[2,'mm_forecast']=np.nan; base.loc[2,'contribution_food']=np.nan
    new=m.replace_core(base,{h:.4 for h in range(1,13)})
    pd.testing.assert_series_equal(new.loc[0],base.loc[0])
    cols=[c for c in base if c.startswith('contribution_') and c!='contribution_core']+['weight_core']
    pd.testing.assert_frame_equal(new[cols],base[cols])
    assert np.isnan(new.loc[2,'mm_forecast'])
    assert new.loc[1,'mm_forecast']==pytest.approx(.41)


def test_labour_missing_forecasts_do_not_shrink_main_panel():
    assert importlib.util.find_spec('core_path_experiment_r13') is not None, 'R13 runner is not implemented'
    runner=importlib.import_module('core_path_experiment_r13')
    records=[]
    for name in (*runner.PRIMARY,*runner.LABOUR,*runner.REFERENCE):
        for origin in ('2023-01','2024-01'):
            missing=name in runner.LABOUR and origin=='2023-01'
            records.append(dict(origin=origin,target='2024-01',h=1,model=name,
                yy_exante=np.nan if missing else 1., yy_actual=1.1, mm_forecast=.2,mm_actual=.3,
                cumulative_log_forecast=.2,cumulative_log_actual=.3))
    scores=runner.all_scores(pd.DataFrame(records))
    main=scores[(scores.scope=='primary_common')&(scores['sample']=='full')]
    labour=scores[(scores.scope=='labour_common')&(scores['sample']=='full')]
    assert main.n_common.eq(2).all()
    assert labour.n_common.eq(1).all()


def test_saved_h0_roundtrip_ulp_does_not_change_original_bridge():
    runner=importlib.import_module('core_path_experiment_r13')
    assert hasattr(runner,'verify_h0'), 'Explicit saved h0 numerical comparison not implemented'
    base=pd.DataFrame({'h':[0], 'mm_forecast':[.3177548805881821]})
    runner.verify_h0(base.copy(),base,.31775488058818213)
    changed=base.copy(); changed.loc[0,'mm_forecast']+=1e-8
    with pytest.raises(AssertionError):
        runner.verify_h0(changed,base,.31775488058818213)


def test_duplicate_target_categories_fail_explicitly():
    m=model(); core,cats,w,dates,clocks,ext=sample(); t=pd.Period('2012-01','M')
    duplicate=pd.concat([cats,cats[['actual_rent']]],axis=1)
    with pytest.raises(ValueError,match='unique'):
        m.target_panel(core,duplicate,w,.55,t,clocks[t],dates)


def test_labour_naive_publication_is_rejected():
    m=model(); t=pd.Period('2020-06','M'); idx=pd.period_range(t-1,t,freq='M')
    features=pd.DataFrame({'eurczk_mm':[1.,2.], 'import_l2':[3.,4.]},index=idx)
    labour=pd.DataFrame([dict(reference_period='2020-03',available_from='2020-05-01',value=3.,
                             adjustment='sa',vintage_kind='historical_release')])
    with pytest.raises(ValueError,match='timezone-aware'):
        m.external_at(features,labour,t,pd.Timestamp('2020-07-01T00:00:00Z'),pd.Timestamp('2020-07-01T00:00:00Z'))
