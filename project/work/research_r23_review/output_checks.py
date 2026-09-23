"""Independent accounting and timing verification of an R23 output directory."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from models.cost_gaps_r23 import monthly_correction
from data.cost_gaps_r23 import local

path=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'output/research_r23/verified')
native=pd.read_csv(path/'native_forecasts.csv',float_precision='round_trip')
fits=[json.loads(line) for line in (path/'fits.jsonl').read_text().splitlines()]
features=pd.read_csv(path/'features.csv',index_col=0,float_precision='round_trip')
features.index=pd.PeriodIndex(features.index,freq='M')
available=pd.read_csv(path/'target_available.csv',index_col=0).iloc[:,0]
available.index=pd.PeriodIndex(available.index,freq='M')
models=sorted(native.model.unique())
assert native.origin.nunique()==90 and len(models)==11
assert not native.duplicated(['origin','h','model']).any()
assert native.groupby('model').size().eq(1170).all()
base=native[native.model.eq('STATE_FAST_R15')].set_index(['origin','h']).sort_index()
fixed=[c for c in native if c.startswith('weight_') or
       ((c.startswith('value_') or c.startswith('contribution_')) and not c.endswith('_core'))]
for model in [m for m in models if m.endswith('_R23')]:
    current=native[native.model.eq(model)].set_index(['origin','h']).sort_index()
    np.testing.assert_allclose(current[fixed],base[fixed],rtol=0,atol=0)
    np.testing.assert_allclose(current.xs(0,level='h')[['mm_forecast','value_core','contribution_core']],
                               base.xs(0,level='h')[['mm_forecast','value_core','contribution_core']],rtol=0,atol=0)
for result in fits:
    origin=result['origin'];t=pd.Period(origin,'M');keys=pd.PeriodIndex(result['train_dates'],freq='M')
    assert all(keys.month%3==0) and all(keys+12<t) and 24<=len(keys)<=40
    assert all(pd.to_datetime(available.loc[keys])<=local(result['as_of']))
    for model,fit in result['fits'].items():
        coefficient=np.asarray(fit['coefficients'])
        if fit['kind']=='positive':assert np.all(coefficient[1:]>=-1e-12)
        np.testing.assert_allclose(np.asarray(fit['contributions']).sum(axis=0),fit['prediction'],atol=1e-14)
        test=np.array([1.,*[(features.loc[t,c]-fit['mean'][c])/fit['scale'][c] for c in fit['columns']]])
        np.testing.assert_allclose(test@coefficient,fit['prediction'],atol=1e-14)
        correction=monthly_correction(fit['prediction'])
        np.testing.assert_allclose(correction,result['paths'][model],atol=1e-14)
        selection=result['selection'][model]
        if selection['scores']:
            expected=min(selection['scores'],key=lambda a:(selection['scores'][a],-float(a)))
            assert selection['alpha']==float(expected)
        for fold in selection['validation']:
            assert pd.Period(fold['last_training_target'],'M')<pd.Period(fold['validation_origin'],'M')
            assert pd.Timestamp(fold['max_training_release'])<=pd.Timestamp(fold['validation_clock'])
            assert pd.Period(fold['validation_target'],'M')<t
            assert pd.Timestamp(fold['validation_available'])<=local(result['as_of'])
    np.testing.assert_allclose(result['paths']['GAP_HALF_R23'],.5*np.asarray(result['paths']['GAP_JOINT_R23']),atol=1e-14)
    for model,correction in result['paths'].items():
        f=native[native.origin.eq(origin)&native.model.eq(model)&native.h.gt(0)].sort_values('h')
        b=base.loc[origin].loc[range(1,13)]
        computed=100*np.log1p(f.value_core.to_numpy()/100)-100*np.log1p(b.value_core.to_numpy()/100)
        np.testing.assert_allclose(computed,correction,rtol=0,atol=1e-12)
print(json.dumps({'path':str(path),'origins':90,'models':11,'native_rows':len(native),'fits':len(fits),
  'checks':['fixed h0 and noncore','quarterly outer labels','all twelve target publications','own-clock inner maturity',
            'selected minimum cumulative loss','positive coefficients','coefficient reconstruction',
            'monthly log corrections','half correction'],'status':'pass'},indent=2))
