import numpy as np
import pandas as pd
import path_trend_residual_r15 as runner


def test_integrated_band_accepts_model_diagnostics_and_emits_all_models(monkeypatch):
    t=pd.Period('2019-02','M')
    state={'seasonal':dict.fromkeys(range(1,13),0.),
           'forecasts_log':{k:dict.fromkeys(range(1,13),.2) for k in runner.engine.FILTERS}}
    monkeypatch.setattr(runner,'feature_groups',lambda columns:dict.fromkeys(['domestic','imported','both','wide'],['x']))
    monkeypatch.setattr(runner.engine,'residual_labels',lambda *args:(pd.Series(dtype=float),pd.DataFrame(columns=['origin','last_target','available_from','actual'])))
    monkeypatch.setattr(runner.engine,'fit_residual',lambda x,y,now,kind,config:(.1,dict(config=config,status='estimated',n_train=48)))
    result=runner.fit_band(0,{t:state},pd.DataFrame({'x':[1.]},index=[t]),None,None,{t:pd.Timestamp('2019-03-08')},{t})
    assert set(result[0].model)==set(runner.MODELS)
    assert len(result[0])==33 and len(result[2])==5
    mixed=result[0].query("model=='BLEND_LINEAR_RF_R15'")
    assert np.allclose(mixed.core_log,.3)


def test_component_replacement_keeps_h0_and_missing_bands_missing():
    t=pd.Period('2019-02','M')
    base=pd.DataFrame(dict(origin=str(t),h=range(13),model=runner.BASE,mm_forecast=.25,
                           weight_core=.5,value_core=.3,contribution_core=.15))
    for name in ('food','administered','alcohol_tobacco','fuel','wedge'):
        base['contribution_'+name]=.02
    pred=pd.DataFrame([dict(origin=str(t),h=h,model=m,core_mm=.8)
                       for m in runner.MODELS for h in range(1,7)])
    out=runner.attach_components(pred,base,[t])
    assert out.loc[out.h.eq(0),'mm_forecast'].eq(.25).all()
    assert np.allclose(out.loc[out.h.between(1,6),'mm_forecast'],.5)
    assert out.loc[out.h.gt(6),'mm_forecast'].isna().all()
    assert out.contribution_food.eq(.02).all()
