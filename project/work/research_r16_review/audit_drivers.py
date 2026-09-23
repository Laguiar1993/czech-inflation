"""Rebuild every exported two-stage contribution without driver helper imports."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'output/research_r16';OUT=Path(__file__).resolve().parent/'evaluation'
receipt=json.loads((EXP/'interpretation/manifest.json').read_text(encoding='utf-8'))
for name,digest in receipt['inputs'].items():assert hashlib.sha256((EXP/name).read_bytes()).hexdigest()==digest
for name,digest in receipt['outputs'].items():assert hashlib.sha256((EXP/'interpretation'/name).read_bytes()).hexdigest()==digest
assert hashlib.sha256((ROOT/'tools/review/r16_drivers.py').read_bytes()).hexdigest()==receipt['source_sha256']
assert hashlib.sha256((ROOT/'tools/review/r15_drivers.py').read_bytes()).hexdigest()==receipt['helper_sha256']
read=lambda name:pd.read_csv(EXP/name,float_precision='round_trip')
fits=json.loads((EXP/'fits.json').read_text(encoding='utf-8'));states=json.loads((EXP/'states.json').read_text(encoding='utf-8'))
signals={(f['origin'],f['family'],f['band']):f for f in fits if f['stage']=='signal'}
raw={s:read('signal_features_'+s+'.csv').set_index('origin') for s in ['services','goods']}
stage2=read('stage2_features.csv').set_index(['origin','family','band'])
pred=read('core_predictions.csv').set_index(['origin','model','h']).core_log
outer=set(pred.index.get_level_values('origin'));rows=[];max_sum=0.;count=0
for f in fits:
    t=f['origin'];family=f['family'];band=f['band']
    if f['stage']!='core' or t not in outer or f['status']!='estimated':continue
    count+=1;parts={'core_intercept':f['intercept']}
    for col in f['columns']:
        beta=f['coefficients'][col];mu=f['means'][col];scale=f['scales'][col]
        if not col.endswith('_projection'):
            value=stage2.loc[(t,family,band),col]
            parts[col]=beta*(value-mu)/scale if np.isfinite(value) else 0.
            continue
        s=col[:-len('_projection')];one=signals[(t,s,band)];multiple=beta/(12*scale)
        parts[s+'_centering']=-beta*mu/scale
        parts[s+'.intercept']=multiple*one['intercept']
        for c in one['columns']:
            value=raw[s].loc[t,c]
            z=(value-one['means'][c])/one['scales'][c] if np.isfinite(value) else 0.
            parts[s+'.'+c]=multiple*one['coefficients'][c]*z
    for h in range(3*band+1,3*band+4):
        residual=pred[(t,'TRANSMISSION_'+family.upper()+'_R16',h)]-states[t]['forecasts_log']['fast'][str(h)]
        max_sum=max(max_sum,abs(sum(parts.values())-residual))
    rows.extend(dict(origin=t,family=family,band=band,source=c,log_core_pp=v) for c,v in parts.items())
reference=pd.DataFrame(rows).set_index(['origin','family','band','source']).sort_index()
saved=read('interpretation/source_contributions.csv').set_index(reference.index.names).sort_index()
assert reference.index.equals(saved.index)
max_part=float(abs(reference.log_core_pp-saved.log_core_pp).max())
assert max_part<1e-12 and max_sum<1e-12
result=dict(explained_fits=count,contributions=len(reference),maximum_component_difference=max_part,maximum_total_difference=max_sum)
(OUT/'driver_audit_summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
