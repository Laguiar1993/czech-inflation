"""Read-only independent reconstruction of the declared R18 food experiment."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r18_food'
read=lambda name:pd.read_csv(OUT/name,float_precision='round_trip')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((OUT/'manifest.json').read_text())
for name,digest in manifest['inputs'].items():assert sha(ROOT/name)==digest,name
for name,digest in manifest['outputs'].items():assert sha(OUT/name)==digest,name
saved=json.loads((OUT/'snapshots.json').read_text())
fits=json.loads((OUT/'fit_coefficients.json').read_text())
selections=json.loads((OUT/'selections.json').read_text())
training=read('training_rows.csv');predictions=read('food_predictions.csv')
levels=pd.read_csv(ROOT/'data/research_r14/food/pipeline_log_levels.csv',index_col=0,float_precision='round_trip').food
available=pd.read_csv(ROOT/'data/research_r14/food/pipeline_available_from.csv',index_col=0).food
actual=levels.diff();original=pd.read_csv(ROOT/'output/research_r15/native_forecasts.csv',float_precision='round_trip').query("model=='STATE_FAST_R15'")
native=read('native_forecasts.csv');coefficient_error=path_error=0.
for fit in fits:
    t=fit['origin'];clock=pd.Timestamp(fit['as_of'])
    eligible=[]
    for key in saved:
        s=pd.Period(key,'M')
        if s+12>=pd.Period(t,'M'):continue
        endpoints=list(map(str,pd.period_range(s,s+12,freq='M')))
        if all(k in levels.index and np.isfinite(levels[k]) and pd.notna(available[k])
               and pd.Timestamp(available[k])<=clock for k in endpoints):eligible.append(key)
    eligible=eligible[-60:]
    assert eligible==fit['training_origins']
    rows=training.loc[training.fit_origin.eq(t)&training.model.eq(fit['model'])]
    assert len(rows)==12*len(eligible)
    x=[];error=[]
    for key in eligible:
        s=pd.Period(key,'M')
        for h in range(1,13):
            x.append(saved[key]['signal']*fit['rho']**h)
            error.append(actual[str(s+h)]-saved[key]['baseline_log'][h])
    x=np.asarray(x);error=np.asarray(error)
    beta=0.
    if len(eligible)>=12 and np.mean(x*x)>1e-24:
        beta=float(np.clip((x@error)/(2*(x@x)),0,1))
    coefficient_error=max(coefficient_error,abs(beta-fit['beta']))
    assert coefficient_error<1e-12
    state=saved[t]
    expected=np.asarray(state['baseline_log'][1:])+beta*state['signal']*fit['rho']**np.arange(1,13)
    issued=predictions.loc[predictions.origin.eq(t)&predictions.model.eq(fit['model'])].sort_values('h')
    path_error=max(path_error,float(np.max(np.abs(expected-issued.log_rate_forecast))))
    assert path_error<1e-12
    if len(rows):
        assert rows.target.max()<t
        assert all(pd.Timestamp(v)<=clock for v in rows.current_release)
        assert all(pd.Timestamp(v)<=clock for v in rows.previous_release)
        np.testing.assert_allclose(rows.x,x,atol=1e-12,rtol=0)
        np.testing.assert_allclose(rows.error,error,atol=1e-12,rtol=0)
for selection in selections:
    t=selection['origin'];clock=pd.Timestamp(selection['as_of'])
    eligible=[]
    for key in saved:
        s=pd.Period(key,'M')
        if s+12>=pd.Period(t,'M'):continue
        ends=list(map(str,pd.period_range(s,s+12,freq='M')))
        if all(k in levels.index and np.isfinite(levels[k]) and pd.notna(available[k])
               and pd.Timestamp(available[k])<=clock for k in ends):eligible.append(key)
    eligible=eligible[-36:];assert eligible==selection['training_origins']
    choices=['STATE_FAST_R15','FOOD_H0_FAST_R18','FOOD_H0_SLOW_R18'];winner=choices[0]
    if len(eligible)>=12:
        losses={}
        for name in choices:
            errors=[]
            for key in eligible:
                p=saved[key]['baseline_log'][1:] if name==choices[0] else predictions.loc[
                    predictions.origin.eq(key)&predictions.model.eq(name)].sort_values('h').log_rate_forecast.to_numpy()
                y=actual.reindex(list(map(str,pd.period_range(pd.Period(key,'M')+1,pd.Period(key,'M')+12,freq='M')))).to_numpy()
                errors.append(np.mean((np.asarray(p)-y)**2))
            losses[name]=float(np.mean(errors))
            assert abs(losses[name]-selection['losses'][name])<1e-12
        for name in choices[1:]:
            if losses[name]<losses[winner]-1e-12:winner=name
    assert selection['selected']==winner
    expected=saved[t]['baseline_log'][1:] if winner==choices[0] else predictions.loc[
        predictions.origin.eq(t)&predictions.model.eq(winner)].sort_values('h').log_rate_forecast.to_numpy()
    issued=predictions.loc[predictions.origin.eq(t)&predictions.model.eq('FOOD_H0_SELECT_R18')].sort_values('h')
    np.testing.assert_array_equal(expected,issued.log_rate_forecast)
for name,changed in native.groupby('model'):
    joined=changed.merge(original,on=['origin','h'],suffixes=('_new','_old'),validate='one_to_one')
    protected=[c for c in original if c.startswith('weight_') or c.startswith('value_') and c!='value_food'
               or c.startswith('contribution_') and c!='contribution_food']
    for c in protected:np.testing.assert_array_equal(joined[c+'_new'],joined[c+'_old'])
    np.testing.assert_array_equal(joined.loc[joined.h.eq(0),'mm_forecast_new'],joined.loc[joined.h.eq(0),'mm_forecast_old'])
    q=changed.loc[changed.h.gt(0)].sort_values(['origin','h'])
    p=predictions.loc[predictions.model.eq(name)].sort_values(['origin','h'])
    np.testing.assert_array_equal(q.value_food,p.mm_forecast)
    np.testing.assert_array_equal(q.contribution_food,q.weight_food*q.value_food)
    # Different summation order is independent and allowed only machine precision.
    sums=q[[c for c in changed if c.startswith('contribution_')]].sum(axis=1,min_count=6)
    np.testing.assert_allclose(q.mm_forecast,sums,atol=1e-14,rtol=0)
support=read('primary_support.csv');assert len(support)==969 and not support.duplicated().any()
assert len(native)==3510 and len(predictions)==3240 and native.origin.nunique()==90
assert native.groupby(['model','origin']).size().eq(13).all()
assert not native.duplicated(['model','origin','h']).any()
receipt=dict(status='passed',verified_inputs=len(manifest['inputs']),verified_outputs=len(manifest['outputs']),
    reconstructed_coefficients=len(fits),reconstructed_selections=len(selections),training_rows=len(training),
    coefficient_max_abs=coefficient_error,log_path_max_abs=path_error,h0_nonfood_exact=True,
    all_training_maturity_and_endpoints_valid=True,primary_keys=969,models=3,origins=90,
    source_first_release_clock='90 matching; detail release clock used for labels independently')
(Path(__file__).parent/'verification_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
