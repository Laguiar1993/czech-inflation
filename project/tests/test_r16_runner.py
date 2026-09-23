import numpy as np
import pandas as pd
import pytest


def test_cached_outcomes_are_gated_again_at_each_earlier_origin():
    from path_slope_transmission_r16 import eligible_targets
    cached=pd.DataFrame([dict(origin='2018-01',last_target='2018-04',available_from='2018-05-10',actual=1.),
                         dict(origin='2018-02',last_target='2018-05',available_from='2018-08-10',actual=999.)])
    y,rows=eligible_targets(cached,pd.Period('2018-06','M'),pd.Timestamp('2018-07-10'))
    assert list(y.index)==[pd.Period('2018-01','M')]
    assert list(rows.actual)==[1.]


def test_target_centering_uses_saved_own_origin_value():
    from path_slope_transmission_r16 import center_targets
    cache=pd.DataFrame([dict(origin='2018-01',last_target='2018-04',available_from='2018-05-10',actual=5.)])
    baseline=pd.Series([3.],index=pd.PeriodIndex(['2018-01'],freq='M'))
    result=center_targets(cache,baseline)
    assert result.actual.iloc[0]==2.
    assert cache.actual.iloc[0]==5.


def test_new_paths_preserve_fixed_noncore_and_propagate_missing_core():
    from path_slope_transmission_r16 import attach_components,MODELS,BASE
    t=pd.Period('2019-02','M')
    base=pd.DataFrame(dict(origin=str(t),h=range(13),model=BASE,mm_forecast=.25,
                           weight_core=.5,value_core=.3,contribution_core=.15))
    for name in ('food','administered','alcohol_tobacco','fuel','wedge'):base['contribution_'+name]=.02
    pred=pd.DataFrame([dict(origin=str(t),h=h,model=m,core_mm=.8) for m in MODELS for h in range(1,7)])
    out=attach_components(pred,base,[t])
    assert out[out.h.eq(0)].mm_forecast.eq(.25).all()
    assert np.allclose(out[out.h.between(1,6)].mm_forecast,.5)
    assert out[out.h.gt(6)].mm_forecast.isna().all()
    assert out.contribution_food.eq(.02).all()


def test_saved_projection_rows_do_not_get_reestimated_in_second_stage(monkeypatch):
    from path_slope_transmission_r16 import sequential_ridge
    import path_slope_transmission_r16 as r
    months=pd.period_range('2010-01','2010-04',freq='M')
    design=pd.DataFrame({'projection':[.1,.2,999.,999.]},index=months)
    cache=pd.DataFrame([dict(origin='2010-01',last_target='2010-02',available_from='2010-03-10',actual=.3)])
    seen=[]
    def fit(x,y,now,lam):
        seen.append((list(y.index),list(x.loc[y.index].projection)))
        return .4,dict(status='estimated',n_train=len(y),converged=True)
    monkeypatch.setattr(r.engine,'ridge_fit',fit)
    selected,*_=sequential_ridge(design,cache,{m:pd.Timestamp('2010-05-10') for m in months},months,'core','both',0)
    assert selected.predicted_change.eq(.4).all()
    assert all(v==[.1] for k,v in seen if k)


def test_missing_current_signal_level_is_not_imputed_into_a_projection(monkeypatch):
    import path_slope_transmission_r16 as r
    t=pd.Period('2010-01','M');design=pd.DataFrame({'level':[np.nan]},index=[t])
    cache=pd.DataFrame(columns=['origin','last_target','available_from','actual'])
    monkeypatch.setattr(r.engine,'ridge_fit',lambda *a:(_ for _ in ()).throw(AssertionError('must not fit')))
    selected,*_=r.sequential_ridge(design,cache,{t:pd.Timestamp('2010-02-10')},[t],'signal','services',0)
    assert selected.predicted_change.isna().all()
