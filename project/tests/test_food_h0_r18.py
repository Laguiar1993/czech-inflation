import numpy as np
import pandas as pd
import pytest

from models.food_h0_r18 import (PROFILES, fit_profile, mature_origins,
    corrected_path, select_path, monthly_labels)


def fixture(n=16):
    dates=pd.period_range('2018-01',periods=n+15,freq='M')
    levels=pd.Series(np.arange(len(dates),dtype=float),index=dates)
    available=pd.Series([f'{m+1}-10T09:00:00+01:00' for m in dates],index=dates)
    saved={str(m):dict(origin=str(m),as_of=f'{m+1}-09T23:59:00+01:00',
                      signal=2.,baseline_log=np.zeros(13).tolist(),
                      baseline_mm=np.zeros(12).tolist()) for m in dates[:n]}
    return saved,levels,available


def test_maturity_requires_entire_future_path_and_both_known_endpoints():
    saved,levels,available=fixture()
    origins,audit=mature_origins(saved,levels,available,'2020-05','2020-06-09T23:59:00+02:00')
    assert origins[-1]=='2019-04'
    poisoned=available.copy();poisoned.loc[pd.Period('2019-07')]=None
    less,_=mature_origins(saved,levels,poisoned,'2020-05','2020-06-09T23:59:00+02:00')
    assert all(not (pd.Period(s)<=pd.Period('2019-07')<=pd.Period(s)+12) for s in less)
    assert all(pd.Period(r['target'])<pd.Period('2020-05') for r in audit)


def test_current_and_future_outcome_poisoning_cannot_change_fit():
    saved,levels,available=fixture(28)
    a=fit_profile(saved,levels,available,'2020-05','2020-06-09T23:59:00+02:00',.5)
    poisoned=levels.copy();poisoned.loc[poisoned.index>=pd.Period('2020-05')]=1e10
    b=fit_profile(saved,poisoned,available,'2020-05','2020-06-09T23:59:00+02:00',.5)
    assert a==b


def test_ridge_units_and_fixed_half_shrinkage():
    saved,levels,available=fixture()
    result=fit_profile(saved,levels,available,'2021-01','2021-02-09T23:59:00+01:00',.5)
    x=np.tile(2*.5**np.arange(1,13),16)
    expected=(x@np.ones(len(x)))/(x@x)*.5
    assert result['n_origins']==16
    assert result['beta_unbounded']==pytest.approx(expected)
    assert result['beta']==pytest.approx(min(1,expected))
    assert result['theta']/result['scale']==pytest.approx(result['beta_unbounded'])


def test_h1_is_one_decay_from_h0_and_zero_beta_is_exact_control():
    baseline=np.linspace(.12,.32,12)
    snap=dict(signal=2.,baseline_log=[-7.]+list(np.arange(12)*.01),baseline_mm=list(baseline))
    path=corrected_path(snap,.25,.5)
    assert path['log_rates'][0]==pytest.approx(.25)
    assert path['log_rates'][-1]==pytest.approx(.11+.5*.5**12)
    zero=corrected_path(snap,0.,.5)
    assert np.array_equal(zero['mm_rates'],baseline)
    assert PROFILES=={'FOOD_H0_FAST_R18':.5,'FOOD_H0_SLOW_R18':.9}


def test_insufficient_history_and_zero_signal_return_explicit_defaults():
    saved,levels,available=fixture(11)
    fit=fit_profile(saved,levels,available,'2021-01','2021-02-09T23:59:00+01:00',.9)
    assert fit['beta']==0 and fit['reason']=='fallback_insufficient_mature_origins'
    saved,levels,available=fixture()
    for s in saved.values():s['signal']=0.
    fit=fit_profile(saved,levels,available,'2021-01','2021-02-09T23:59:00+01:00',.9)
    assert fit['beta']==0 and fit['reason']=='fallback_zero_signal_variance'


def test_selection_uses_saved_whole_paths_only_after_maturity():
    saved,levels,available=fixture()
    history={s:{'STATE_FAST_R15':[0.]*12,'FOOD_H0_FAST_R18':[1.]*12,
                'FOOD_H0_SLOW_R18':[2.]*12} for s in saved}
    selection=select_path(history,saved,levels,available,'2021-01','2021-02-09T23:59:00+01:00')
    assert selection['selected']=='FOOD_H0_FAST_R18' and selection['n_origins']==16
    history['2021-01']={'STATE_FAST_R15':[1e10]*12,'FOOD_H0_FAST_R18':[1e10]*12,'FOOD_H0_SLOW_R18':[1.]*12}
    assert select_path(history,saved,levels,available,'2021-01','2021-02-09T23:59:00+01:00')==selection
    for choices in history.values():
        for name in choices:choices[name]=[1.]*12
    assert select_path(history,saved,levels,available,'2021-01','2021-02-09T23:59:00+01:00')['selected']=='STATE_FAST_R15'


def test_monthly_endpoint_release_boundary_and_calendar_gap():
    _,levels,available=fixture()
    target=pd.Period('2018-03')
    assert monthly_labels(levels,available,[target],'2018-04-10T08:59:59+01:00') is None
    assert monthly_labels(levels,available,[target],'2018-04-10T09:00:00+01:00')[0]==[1.]
    assert monthly_labels(levels.drop(target-1),available,[target],'2021-01-01') is None


def runner():
    from pathlib import Path
    assert (Path(__file__).resolve().parents[1]/'food_h0_experiment_r18.py').exists(), 'R18 runner not implemented'
    import food_h0_experiment_r18
    return food_h0_experiment_r18


def test_source_archive_has_exact_pipeline_and_first_release_clocks():
    module=runner();sources=module.load_sources()
    saved,audit=module.validate_sources(*sources)
    assert len(saved)==len(audit)==90
    assert audit.first_release_eve_match.all()
    assert audit.detail_release_eve_match.sum()==71
    assert audit.pipeline_fast_max_abs.max()==0
    damaged=list(sources);damaged[0]=damaged[0].copy()
    damaged[0].loc['2019-02','as_of_eve']='2019-03-11T23:59:00'
    with pytest.raises(ValueError,match='clock'):
        module.validate_sources(*damaged)


def test_source_horizon_poisoning_is_rejected():
    import copy
    module=runner();sources=list(module.load_sources())
    sources[1]=copy.deepcopy(sources[1]);sources[1][0]['forecast_food_rates']['FOOD_STABLE_PIPELINE_R14B'][1]+=1
    with pytest.raises(ValueError,match='pipeline'):
        module.validate_sources(*sources)


def test_native_h0_nonfood_and_annual_accounting():
    module=runner();sources=module.load_sources();base=sources[3].query("origin=='2019-02'").copy()
    paths=pd.DataFrame([dict(origin='2019-02',model='TEST',h=h,mm_forecast=1.,
                           status='estimated',reason='') for h in range(1,13)])
    headline=module.common.monthly('output/independent_path_frozen_inputs.csv','headline_mm')
    changed=module.integrate_food(base,paths,headline)
    assert changed.loc[changed.h.eq(0),'mm_forecast'].iloc[0]==base.mm_forecast.iloc[0]
    invariants=[c for c in base if c.startswith('weight_') or c.startswith('value_') and c!='value_food'
                or c.startswith('contribution_') and c!='contribution_food']
    pd.testing.assert_frame_equal(changed[invariants].reset_index(drop=True),base[invariants].reset_index(drop=True),check_exact=True)
    columns=[c for c in base if c.startswith('contribution_')]
    np.testing.assert_allclose(changed.query('h>0').mm_forecast,changed.query('h>0')[columns].sum(axis=1,min_count=6),rtol=0,atol=1e-15)
    assert changed.loc[changed.h.eq(12),'yy_exante'].iloc[0]==pytest.approx(100*(np.prod(1+changed.query('h>0').mm_forecast/100)-1))


def test_runner_refuses_to_overwrite_original_or_new_destination():
    module=runner()
    with pytest.raises(FileExistsError):module.run(module.ROOT)
