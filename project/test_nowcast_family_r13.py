"""R13 timing, historical forecast provenance and scoring contracts."""
import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest


def module():
    assert importlib.util.find_spec('models.nowcast_family_r13'), 'R13 model API is not implemented'
    return importlib.import_module('models.nowcast_family_r13')


def synthetic(n=110):
    from models.core_split import CATEGORIES
    idx = pd.period_range('2015-01', periods=n, freq='M')
    z = np.arange(n)
    core = pd.Series(.2 + .15*np.sin(z/5) + .01*np.cos(z), index=idx)
    categories = pd.DataFrame({c:.1+i*.04+.2*np.sin(z/(i+2)) for i,c in enumerate(CATEGORIES)},index=idx)
    dates = pd.Series((idx+1).to_timestamp()+pd.Timedelta(days=11,hours=9),index=idx)
    weights = pd.Series([.04,.09,.05,.008,.02],index=CATEGORIES)
    return core,categories,dates,weights


def test_category_only_exact_existing_equations():
    m=module()
    from models.core_remainder import forecast_origin
    from models.core_split import own_features
    c,k,d,w=synthetic()
    t=c.index[80]; clock=d.loc[t]-pd.Timedelta(days=1)
    got=m.category_raw(c,k,d,t,clock,w,core_weight=.55)
    old=forecast_origin(c,k,own_features(c),d,t,clock,w,core_weight=.55)
    assert got['prediction']==old['own_core']
    assert len(got['fits'])==6


def test_unreleased_core_categories_cannot_change_raw_forecast():
    m=module(); c,k,d,w=synthetic(); t=c.index[80]
    clock=d.loc[t]-pd.Timedelta(days=1)
    before=m.category_raw(c,k,d,t,clock,w,core_weight=.55)['prediction']
    c.loc[t:]=1e8; k.loc[t:]=1e8
    assert m.category_raw(c,k,d,t,clock,w,core_weight=.55)['prediction']==before


def test_48_label_warmup_and_missing_previous_label():
    m=module(); c,k,d,w=synthetic(); t=c.index[47]
    got=m.category_raw(c,k,d,t,d.loc[t]-pd.Timedelta(days=1),w,core_weight=.55)
    assert np.isnan(got['prediction'])
    assert all(f['fit_status']=='insufficient_history' for f in got['fits'])
    t=c.index[70]; d.loc[t-1]=d.loc[t]+pd.Timedelta(days=1)
    got=m.category_raw(c,k,d,t,d.loc[t]-pd.Timedelta(days=1),w,core_weight=.55)
    assert all(f['fit_status']=='previous_target_unavailable' for f in got['fits'])


def test_history_uses_each_historical_weight_and_own_raw_error():
    m=module(); c,k,d,w=synthetic(56)
    decisions=d-pd.Timedelta(days=1)
    calls=[]
    def provider(t,clock):
        calls.append((t,clock))
        return .5+(t.ordinal%3)*.01,w*(1+(t.ordinal%2)*.05)
    history,fits=m.category_history(c,k,d,decisions,provider)
    finite=history.raw_core.notna()
    assert history.loc[finite,'period'].iloc[0]=='2019-01'
    assert all(calls[i][0]<calls[i+1][0] for i in range(len(calls)-1))
    for row in history.loc[finite].itertuples():
        t=pd.Period(row.period,freq='M')
        assert row.error==pytest.approx(c.loc[t]-row.raw_core)
        assert row.core_weight==.5+(t.ordinal%3)*.01
    initial=history.loc[finite].iloc[0]
    def changed_future(t,clock):
        return ((.8,w*2) if t>pd.Period(initial.period) else provider(t,clock))
    later,_=m.category_history(c,k,d,decisions,changed_future)
    assert later.loc[later.period==initial.period,'raw_core'].iloc[0]==initial.raw_core
    assert (pd.to_datetime(fits.training_last_release.dropna())<pd.to_datetime(fits.as_of.dropna())).all()


def test_detail_release_and_missing_dates_filter_error_targets():
    m=module(); idx=pd.period_range('2020-01',periods=43,freq='M')
    errors=pd.Series(np.arange(43,dtype=float),index=idx)
    dates=pd.Series(pd.Timestamp('2025-02-01 09:00'),index=idx)
    dates.iloc[-3]=pd.Timestamp('2025-02-13 09:00')
    dates.iloc[-2]=pd.NaT
    origin=idx[-1]
    got=m.eligible_errors(errors,idx,origin,'2025-02-07 09:00',dates)
    assert len(got)==40
    assert idx[-3] not in got.index and idx[-2] not in got.index and origin not in got.index
    assert len(m.eligible_errors(errors,idx,origin,'2025-02-13 09:00',dates))==41


def test_matched_error_histories_keep_own_values_and_same_dates():
    m=module(); idx=pd.period_range('2015-01',periods=55,freq='M')
    base=pd.Series(np.arange(55,dtype=float),index=idx)
    category=pd.Series(-np.arange(45,dtype=float),index=idx[-45:]); category.iloc[1]=np.nan
    b,c=m.matched_histories(base,category)
    assert b.index.equals(c.index)
    assert len(b)==44
    assert (b==base.reindex(b.index)).all() and (c==category.reindex(c.index)).all()


def test_zero_correction_before_40_published_errors():
    m=module(); c,k,d,w=synthetic(55); t=c.index[45]
    from models.core_split import own_features
    value,info=m.correct(own_features(c),c.iloc[:39],t,d.loc[t]-pd.Timedelta(days=1),d)
    assert value==0 and info['status']=='insufficient_errors' and info['n_errors']==39


def test_forest_receives_only_this_family_released_errors_and_hard_features(monkeypatch):
    m=module(); c,k,d,w=synthetic(55); t=c.index[45]
    from models.core_split import own_features
    x=own_features(c).assign(exp12=1e9,esi=1e9,survey_median=1e9)
    errors=c.copy(); errors.iloc[40:]=1e8
    d.iloc[40:]=d.loc[t]+pd.Timedelta(days=1)
    captured={}
    class Forest:
        def __init__(self,**kwargs): captured['options']=kwargs
        def fit_predict(self,x,y,now):
            captured.update(x=x,y=y,now=now)
            return {'point':float(y.mean()),'weights':[.1,.2,.4,.2,.1]}
    monkeypatch.setattr('models.horizon_models.TVWQRF',Forest)
    correction,info=m.correct(x,errors,t,d.iloc[39]+pd.Timedelta(days=1),d)
    assert info['n_errors']==40 and info['status']=='ok'
    assert info['validation_rows']==8
    np.testing.assert_array_equal(captured['y'],c.iloc[:40].to_numpy())
    assert captured['options']=={'n_estimators':200}
    assert captured['x'].shape==(40,14)
    assert correction==pytest.approx(c.iloc[:40].mean())


def test_half_full_sign_weight_and_headline_shape():
    m=module()
    raw,half,full=m.family_forecasts(.3,-.4,.55)
    assert raw==.3 and half==pytest.approx(.19) and full==pytest.approx(.08)
    assert half==pytest.approx((raw+full)/2)
    with pytest.raises(ValueError): m.family_forecasts(.3,.2,0)


def test_scoring_material_direction_alert_and_bootstrap_blocks():
    assert importlib.util.find_spec('nowcast_family_experiment_r13'), 'R13 runner API is not implemented'
    runner=importlib.import_module('nowcast_family_experiment_r13')
    idx=pd.period_range('2024-01',periods=24,freq='M')
    survey=pd.DataFrame({'actual':[.4,-.4,.1,0]*6,'survey_median':0.},index=idx)
    pred=pd.DataFrame({'R9_BASE':0.,'CATEGORY_RAW':[.2,-.2,.3,0]*6},index=idx)
    result=runner.score(pred,survey,pd.Series(True,index=idx))
    events=result['release_rows'].query("model=='CATEGORY_RAW'")
    assert events.material_win.sum()==12 and events.direction.sum()==18
    assert events.false_alarm.sum()==6
    assert set(result['bootstrap'].block)=={6,12,18}
    assert set(result['bootstrap'].metric)=={'rmse','mae'}
    assert 'post_warmup' in set(result['scores'].frame)


def test_frozen90_raw_parity_midpoints_and_matched_clock_audit():
    from core_split_experiment import ROOT,read_frame
    folder=ROOT/'output/research_r13/nowcast'
    assert (folder/'forecasts.csv').exists(), 'R13 empirical output has not been produced'
    got=read_frame(folder/'forecasts.csv')
    old=read_frame(ROOT/'output/core_split_forecasts.csv')
    assert got.index.equals(pd.period_range('2019-02','2026-07',freq='M'))
    assert got.shape==(90,8) and np.isfinite(got.to_numpy()).all()
    for col in ('R9_BASE','R9_HALF','R9_FULL'):
        np.testing.assert_array_equal(got[col],old[col])
    np.testing.assert_allclose(got.CATEGORY_RAW,old.TARGET_OWN,atol=1e-12,rtol=0)
    np.testing.assert_allclose(got.CATEGORY_HALF_CORRECTION,(got.CATEGORY_RAW+got.CATEGORY_FULL_CORRECTION)/2,atol=1e-14,rtol=0)
    np.testing.assert_allclose(got.BASE_MATCHED_HALF,(got.R9_BASE+got.BASE_MATCHED_FULL)/2,atol=1e-14,rtol=0)
    audit=pd.read_csv(folder/'correction_audit.csv')
    base=audit[audit.family=='BASE_MATCHED'].reset_index(drop=True)
    cat=audit[audit.family=='CATEGORY'].reset_index(drop=True)
    assert base.eligible_error_months.fillna('').equals(cat.eligible_error_months.fillna(''))
    assert (cat.status=='insufficient_errors').sum()==40
    assert (cat.status=='ok').sum()==50
    assert (base.status=='insufficient_errors').sum()==40
    assert (base.status=='ok').sum()==50
    used=audit[audit.n_errors>0]
    assert (pd.to_datetime(used.training_last_release)<=pd.to_datetime(used.as_of)).all()
    for row in used.itertuples():
        assert all(pd.Period(t)<pd.Period(row.period) for t in row.eligible_error_months.split('|'))
    cal=pd.read_csv(folder/'scoring_calendar.csv')
    assert cal.post_warmup.sum()==50
    assert cal.loc[cal.post_warmup,'period'].iloc[0]=='2022-06'
    history=pd.read_csv(folder/'category_history.csv')
    assert history.loc[history.raw_core.notna(),'period'].iloc[0]=='2019-02'
    checks=pd.read_csv(folder/'origin_checks.csv')
    assert checks.filter(like='_difference').abs().max().max()<1e-12


def test_category_decisions_match_all90_saved_release_eve_clocks():
    import nowcast_family_experiment_r13 as runner
    from core_split_experiment import ROOT,read_frame
    reference=read_frame(ROOT/'output/independent_nowcast_forecasts.csv')
    assert hasattr(runner,'category_decisions'), 'explicit category release-eve clock helper missing'
    got=runner.category_decisions(reference.index)
    np.testing.assert_array_equal(got.to_numpy(),pd.to_datetime(reference.as_of_eve).to_numpy())


def test_matched_base_uses_evening_clock_for_intraday_predictor(monkeypatch):
    m=module(); c,k,d,w=synthetic(80)
    from models.core_split import own_features
    import cz_struct as s
    t=c.index[-1]; evening=d.loc[t].normalize()-pd.Timedelta(minutes=1)
    morning=evening.normalize()+pd.Timedelta(hours=9)
    published=evening.normalize()+pd.Timedelta(hours=12)
    x=own_features(c); x['noon_source']=c*.8
    x.loc[t,'noon_source']=30.
    def mask(frame,origin,clock):
        out=frame.copy()
        if pd.Timestamp(clock)<published: out.loc[origin,'noon_source']=np.nan
        return out
    monkeypatch.setattr(s,'_mask_row_by_availability',mask)
    assert hasattr(m,'base_history'), 'matched BASE own forecast history missing'
    early,_=m.base_history(x,c,pd.Series({t:morning}))
    late,audit=m.base_history(x,c,pd.Series({t:evening}))
    assert abs(early.loc[t]-late.loc[t])>.01
    assert audit.as_of.iloc[0]==evening
    assert late.loc[t]==pytest.approx(c.loc[t]-audit.raw_core.iloc[0])
