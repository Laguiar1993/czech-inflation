from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'work/research_r17_review'
from models.core_adaptation_r17 import fast_state
def read(p):return pd.read_csv(ROOT/p,float_precision='round_trip')
def annual(values):
    v=np.asarray(values,dtype=float)
    return float(100*(np.prod(1+v/100)-1)) if len(v)==12 and np.isfinite(v).all() and (v>-100).all() else np.nan
def maxdiff(a,b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    assert np.array_equal(np.isfinite(a),np.isfinite(b))
    return float(np.max(abs(a[np.isfinite(a)]-b[np.isfinite(b)]))) if np.isfinite(a).any() else None
manifest=json.loads((ROOT/'output/research_r17/attribution/manifest.json').read_text())
hashes={}
for name,digest in manifest['inputs'].items():
    hashes[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
for name,digest in manifest['outputs'].items():
    hashes['output/research_r17/attribution/'+name]=hashlib.sha256((ROOT/'output/research_r17/attribution'/name).read_bytes()).hexdigest()==digest
assert all(hashes.values())
r16=read('output/research_r16/forecasts.csv'); info=json.loads((ROOT/'output/research_r16/manifest.json').read_text())
roster=info['models']+info['controls']; assert len(roster)==len(set(roster))
selected=r16[r16.model.isin(roster)&r16.h.gt(0)].copy()
keys=['origin','h']; counts=selected.groupby(keys).agg(n=('model','nunique'),valid_y=('yy_exante',lambda x:np.isfinite(x).sum()),valid_a=('yy_actual',lambda x:np.isfinite(x).sum()),actual_range=('yy_actual',lambda x: x.max()-x.min()),target_n=('target','nunique'))
expected_support=counts.query('n==@len(roster)') if False else counts.loc[counts.n.eq(len(roster))&counts.valid_y.eq(len(roster))&counts.valid_a.eq(len(roster))]
support=read('output/research_r17/attribution/primary_support.csv').set_index(keys).sort_index()
assert expected_support.sort_index().index.equals(support.index)
assert expected_support.actual_range.max()<1e-10 and expected_support.target_n.max()==1
native=pd.concat([read('output/research_r15/native_forecasts.csv').query("model=='STATE_FAST_R15'"),read('output/research_r14b/integration/native_forecasts.csv').query("model=='STABLE_LOCAL_CORE_R14B'")])
actual=read('output/research_r14b/attribution/actual_component_targets.csv').set_index('period'); actual.index=pd.PeriodIndex(actual.index,freq='M')
head=read('output/independent_path_frozen_inputs.csv').set_index('period').headline_mm;head.index=pd.PeriodIndex(head.index,freq='M')
blocks=['core','food','fuel','administered','alcohol_tobacco']
independent=[]
for (model,origin),g0 in native.groupby(['model','origin']):
    t=pd.Period(origin,'M');g=g0.set_index('h').sort_index()
    for name,used in [('noncore',blocks[1:]),('all_components',blocks)]:
        forecasts={int(h):float(row.mm_forecast) for h,row in g.iterrows()}
        replacement=forecasts.copy()
        for h in range(1,13):
            a=np.asarray([actual.loc[t+h,b] if t+h in actual.index else np.nan for b in used],float)
            f=np.asarray([g.at[h,'value_'+b] for b in used],float)
            w=np.asarray([g.at[h,'weight_'+('alc' if b=='alcohol_tobacco' else b)] for b in used],float)
            replacement[h]=forecasts[h]+np.sum(w*(a-f)) if np.isfinite([a,f,w]).all() else np.nan
        for h in range(1,13):
            months=pd.period_range(t+h-11,t+h,freq='M')
            pred=annual([head.get(m,np.nan) if m<t else forecasts[m.ordinal-t.ordinal] for m in months])
            oracle=annual([head.get(m,np.nan) if m<t else replacement[m.ordinal-t.ordinal] for m in months])
            truth=annual([head.get(m,np.nan) for m in months])
            independent.append(dict(model=model,origin=origin,h=h,block=name,annual_forecast=pred,annual_oracle=oracle,annual_actual=truth))
independent=pd.DataFrame(independent)
joint=read('output/research_r17/attribution/joint_oracles.csv')
comp=joint.merge(independent,on=['model','origin','h','block'],suffixes=('','_check'),validate='one_to_one')
errors={c:maxdiff(comp[c],comp[c+'_check']) for c in ['annual_forecast','annual_oracle','annual_actual']}
assert all(v<1e-9 for v in errors.values())
identity=maxdiff(joint.headline_squared_error,joint.block_squared_error+joint.other_squared_error+joint.cross_term)
assert identity<1e-8
chosen=read('output/research_r17/attribution/primary_rows.csv')
expected_keys=set(map(tuple,support.reset_index().values))
assert set(map(tuple,chosen[keys].drop_duplicates().values))==expected_keys
assert chosen.groupby(keys).model.nunique().eq(2).all()
assert chosen.groupby(['model',*keys]).block.nunique().eq(7).all()
states=json.loads((ROOT/'output/research_r15/states.json').read_text())
fast=[]
for origin,saved in states.items():
    adapted=fast_state(saved,origin)
    for h in range(1,13):fast.append(adapted['path'][h]-saved['forecasts_log']['fast'][str(h)])
fast_error=float(max(abs(np.asarray(fast))))
assert fast_error<1e-12
result=dict(source_and_output_hashes=hashes,original_roster_count=len(roster),primary_support_rows=len(support),support_exact=True,all_two_models_seven_oracles_present=True,joint_independent_product_max_error=errors,joint_squared_identity_max_error=identity,fast_saved_state_origins=len(states),fast_saved_path_max_error=fast_error,limitations=['Joint oracle is conditional algebra with frozen weights and retained wedge/h0, not exact official chain-linked attribution.','Missing component outcomes reduce oracle-valid support; compare same scope.'])
(OUT/'attribution_fast_review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='source_and_output_hashes'},indent=2))

