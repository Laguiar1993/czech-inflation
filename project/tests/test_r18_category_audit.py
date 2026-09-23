"""Independent source-clock and smooth-regression adversarial checks for R18."""
import numpy as np
import pandas as pd
import pytest
from models.category_trend_r18 import fit_path,smooth_correction
from tools.research_r18.category_inputs import levels_asof


def signal_fixture():
    dates=pd.period_range('2015-01',periods=72,freq='M');rng=np.random.default_rng(1809)
    features={str(m):rng.normal(size=3).tolist() for m in dates}
    rows=[]
    for s in dates:
        for h in range(1,13):
            rows.append(dict(origin=str(s),h=h,target=str(s+h),released=f'{s+h+1}-10 09:00:00',
                error=.2*np.array(features[str(s)]).sum()+.002*h))
    return features,pd.DataFrame(rows)


def test_smooth_fit_ignores_late_and_unknown_publications_with_own_horizon_counts():
    features,labels=signal_fixture();t='2020-07';clock='2020-08-09 23:59:00';current=[.3,-.2,.1]
    labels.loc[(labels.origin=='2018-03')&(labels.h==3),'released']=None
    labels.loc[(labels.origin=='2018-04')&(labels.h==4),'released']='2021-01-01 09:00:00'
    first=smooth_correction(features,labels,t,clock,current)
    poisoned=labels.copy();mask=(poisoned.target>=t)|pd.to_datetime(poisoned.released).gt(pd.Timestamp(clock))|poisoned.released.isna()
    poisoned.loc[mask,'error']=1e12
    second=smooth_correction(features,poisoned,t,clock,current)
    np.testing.assert_array_equal(first['correction'],second['correction'])
    assert first['n_by_h'][0]>first['n_by_h'][-1]
    used=set(zip(first['training_origins'],first['training_h']))
    assert ('2018-03',3) not in used and ('2018-04',4) not in used


def test_future_feature_rows_do_not_enter_horizon_fit_and_missing_current_zeroes_all():
    features,labels=signal_fixture();t='2020-07';clock='2020-08-09 23:59:00';current=[.3,-.2,.1]
    first=smooth_correction(features,labels,t,clock,current)
    features={s:([1e15]*3 if s>=t else v) for s,v in features.items()}
    second=smooth_correction(features,labels,t,clock,current)
    np.testing.assert_array_equal(first['coefficients'],second['coefficients'])
    missing=smooth_correction(features,labels,t,clock,[.3,np.nan,.1])
    assert missing['status']=='fallback_missing_features' and missing['correction']==[0.]*12


def test_category_clock_is_local_detail_midnight_and_utc_equivalent():
    levels=pd.DataFrame({'category':[100.,101.]},index=['2026-05','2026-06'])
    availability=pd.DataFrame(dict(target_month=levels.index,available_from=['2026-06-16','2026-07-16']))
    before=levels_asof(levels,availability,'2026-07-15T21:59:59+00:00')
    exact=levels_asof(levels,availability,'2026-07-15T22:00:00+00:00')
    assert before.index.tolist()==['2026-05'] and exact.index.tolist()==levels.index.tolist()
    pd.testing.assert_frame_equal(exact,levels_asof(levels,availability,'2026-07-16T00:00:00+02:00'))
    availability.loc[1,'available_from']=None
    with pytest.raises(ValueError,match='availability'):levels_asof(levels,availability,'2026-07-20')


def test_unavailable_endpoint_gap_cannot_be_silently_bridged_into_fit():
    dates=pd.period_range('2015-01','2020-01',freq='M');columns=['core','category']
    levels=pd.DataFrame(np.arange(len(dates))[:,None]+np.array([[100.,150.]]),index=dates.astype(str),columns=columns)
    availability=pd.DataFrame(dict(target_month=levels.index,available_from=[f'{m+1}-10' for m in dates]))
    availability.loc[availability.target_month.eq('2019-07'),'available_from']='2021-01-01'
    known=levels_asof(levels,availability,'2020-02-09');known.index=pd.PeriodIndex(known.index,freq='M')
    rates=100*np.log(known/known.shift(1));rates=rates.iloc[1:]
    with pytest.raises(ValueError,match='contiguous'):fit_path(rates,'2020-02',.01)


def test_zero_measurement_noise_uses_floor_and_stays_psd():
    dates=pd.period_range('2015-02',periods=60,freq='M')
    rates=pd.DataFrame(np.zeros((60,3)),index=dates,columns=['core','goods','services'])
    result=fit_path(rates,'2020-02',.01)
    np.testing.assert_allclose(result['observation_variance'],.05**2,atol=0,rtol=0)
    np.testing.assert_array_equal(list(result['path'].values()),np.zeros(12))
    assert np.linalg.eigvalsh(result['covariance']).min()>0


def verified_runner():
    from pathlib import Path
    assert (Path(__file__).resolve().parents[1]/'category_trend_experiment_r18_verified.py').exists(), 'Verified runner missing'
    import category_trend_experiment_r18_verified
    return category_trend_experiment_r18_verified


def runner_fixture():
    dates=pd.period_range('2015-01','2025-01',freq='M');rng=np.random.default_rng(18)
    levels=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.002,.003,(len(dates),3)),axis=0)),
                        index=dates.astype(str),columns=['goods','services','housing'])
    availability=pd.DataFrame(dict(target_month=levels.index,available_from=[f'{m+1}-10' for m in dates]))
    core=pd.Series(rng.normal(.2,.08,len(dates)),index=dates)
    releases=pd.Series([pd.Timestamp(f'{m+1}-10 09:00:00') for m in dates],index=dates)
    control=np.array([.29658023473168465,.39480349843260493,.449894282347563,.928374653763841,
                      .3243983743673472,.32847927393428376,.2873482736482346,.2319373489834,
                      .8734893748338723,.9248972374347,.9384792373473472,.0983423948732493])
    base=pd.DataFrame(dict(h=np.arange(13),value_core=[np.nan,*control])).set_index('h')
    return levels,availability,core,releases,base


def test_verified_runner_missing_availability_returns_complete_exact_fast_fallback():
    module=verified_runner();levels,available,core,releases,base=runner_fixture()
    available.loc[20,'available_from']=None
    states,predictions,status=module.fit_origin(levels,available,core,releases,'2025-02',pd.Timestamp('2025-03-09 23:59:00'),base)
    for name in module.MODELS:
        rows=pd.DataFrame(predictions).query('model==@name').sort_values('h')
        assert rows.h.tolist()==list(range(1,13)) and rows.status.eq('fallback_FAST').all()
        np.testing.assert_array_equal(rows.core_mm,base.loc[range(1,13),'value_core'])
        assert states[name]['status']=='fallback_FAST' and 'availability' in states[name]['reason'].lower()
    assert all(row['n_history']==0 for row in status)


def test_verified_runner_fit_failure_copies_monthly_control_and_reports_actual_sample():
    module=verified_runner();levels,available,core,releases,base=runner_fixture()
    levels.iloc[-1,0]=np.nan
    _,predictions,status=module.fit_origin(levels,available,core,releases,'2025-02',pd.Timestamp('2025-03-09 23:59:00'),base)
    for name in module.MODELS:
        rows=pd.DataFrame(predictions).query('model==@name').sort_values('h')
        np.testing.assert_array_equal(rows.core_mm,base.loc[range(1,13),'value_core'])
    assert all(row['n_history']==0 and row['n_available_history']==120 for row in status)
    levels,available,core,releases,base=runner_fixture()
    states,_,status=module.fit_origin(levels,available,core,releases,'2025-02',pd.Timestamp('2025-03-09 23:59:00'),base)
    assert all(row['n_history']==96 and row['n_available_history']==120 for row in status)
    assert all(states[name]['n_history']==96 for name in module.MODELS)
