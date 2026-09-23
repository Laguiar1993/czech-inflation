"""Frozen R23 quarterly cost equations, seven full monthly path candidates."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from data.cost_gaps_r23 import load_inputs,features_at,local,COLUMNS
from models.cost_gaps_r23 import run_origin,FAMILIES

CONTROLS=['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16','CORE_FEEDBACK_R21']
MODELS=[*FAMILIES,'GAP_HALF_R23']


def targets(core,dates,states):
    rows={};releases={};audit=[]
    for origin,state in states.items():
        t=pd.Period(origin,'M');months=pd.period_range(t+1,t+12,freq='M');truth=core.reindex(months);a=dates.reindex(months)
        complete=truth.notna().all() and a.notna().all() and truth.gt(-100).all()
        base=np.array([state['forecasts_log']['fast'][str(h)] for h in range(1,13)])
        rows[t]=(100*np.log1p(truth.to_numpy()/100)-base).reshape(4,3).mean(axis=1) if complete else np.full(4,np.nan)
        releases[t]=a.max() if complete else pd.NaT
        audit.append(dict(origin=origin,last_target=str(t+12),available_from=str(releases[t]),complete=bool(complete)))
    return pd.DataFrame.from_dict(rows,orient='index'),pd.Series(releases),pd.DataFrame(audit)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--limit',type=int);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    core,dates,raw,fx,hashes=load_inputs();hashes.update(c.preserved_hashes())
    for path in ['models/cost_gaps_r23.py','tools/research_r23/run.py','docs/implementation/R23_COST_GAPS_SPEC_2026-09-16.md',
                 'output/research_r21/path_anchor/native_forecasts.csv']:
        hashes[path]=c.sha(ROOT/path)
    states=json.loads((ROOT/'output/research_r15/states.json').read_text())
    native=c.read('output/research_r21/path_anchor/native_forecasts.csv');native=native[native.model.isin(CONTROLS)].copy()
    outer=native[native.model.eq('STATE_FAST_R15')&native.h.eq(0)].set_index('origin').as_of_utc.to_dict()
    features={};provenance=[];clocks={}
    for origin,state in states.items():
        t=pd.Period(origin,'M');clock=outer.get(origin,state['as_of'])
        if local(state['as_of'])>local(clock) or local(state['last_release'])>local(clock):raise ValueError('Saved core state postdates decision')
        row,info=features_at(core,dates,raw,fx,t,clock,state['seasonal']);features[t]=row;clocks[t]=local(clock)
        provenance.extend(dict(origin=origin,as_of=str(local(clock)),**r) for r in info)
    x=pd.DataFrame.from_dict(features,orient='index')[COLUMNS];clock_series=pd.Series(clocks)
    y,a,target_audit=targets(core,dates,states)
    x.to_csv(out/'features.csv',index_label='origin');y.to_csv(out/'band_targets.csv',index_label='origin')
    a.to_csv(out/'target_available.csv',index_label='origin');clock_series.to_csv(out/'feature_clocks.csv',index_label='origin')
    pd.DataFrame(provenance).to_csv(out/'feature_provenance.csv',index=False);target_audit.to_csv(out/'target_audit.csv',index=False)
    meta=[dict(variable=name,a6_number=n,source=raw[n].source,kind=raw[n].kind,frequency=raw[n].values.index.freqstr,
               first=str(raw[n].values.index.min()),last=str(raw[n].values.index.max())) for name,n in [('unemployment',11),('ulc',17),('imports',26),('ppi',47)]]
    c.dump(out/'sources.json',meta)
    origins=sorted(outer);origins=origins[:args.limit] if args.limit else origins;native=native[native.origin.isin(origins)]
    results=[native];statuses=[];validation=[];contributions=[];training=[]
    print(f'R23 inputs frozen: {len(x)} snapshots, {int(x.notna().all(axis=1).sum())} complete; fitting {len(origins)} origins.',flush=True)
    with (out/'fits.jsonl').open('w',encoding='utf-8') as log:
        for i,origin in enumerate(origins):
            t=pd.Period(origin,'M');base=native[native.model.eq('STATE_FAST_R15')&native.origin.eq(origin)].sort_values('h')
            if len(base)!=13 or base.h.duplicated().any():raise ValueError('Invalid baseline support')
            baseline=np.array([states[origin]['forecasts_log']['fast'][str(h)] for h in range(1,13)])
            np.testing.assert_allclose(100*np.log1p(base[base.h.gt(0)].value_core.to_numpy()/100),baseline,atol=1e-10,rtol=0)
            result=run_origin(x,y,a,clock_series,t,outer[origin]);estimated=result['status']=='estimated'
            log.write(json.dumps(dict(origin=origin,as_of=outer[origin],**result),allow_nan=False)+'\n')
            for model in MODELS:
                if estimated:
                    rates=100*np.expm1((baseline+np.array(result['paths'][model]))/100)
                    if not np.isfinite(rates).all():raise ArithmeticError('Nonfinite monthly core forecast')
                    frame=c.replace_block(base,'core',dict(zip(range(1,13),rates)))
                else:frame=base.copy()
                frame['model']=model;frame['core_model_status']=result['status'];frame['core_fallback_used']=not estimated
                results.append(frame);statuses.append(dict(origin=origin,model=model,status=result['status'],n_train=result['n_train']))
            if estimated:
                for key in result['train_dates']:
                    training.append(dict(origin=origin,training_origin=key,last_target=str(pd.Period(key,'M')+12),
                                         target_available=str(a.loc[pd.Period(key,'M')]),as_of=str(local(outer[origin]))))
                for model,fit in result['fits'].items():
                    for j,column in enumerate(['intercept',*fit['columns']]):
                        for band in range(4):contributions.append(dict(origin=origin,model=model,feature=column,band=band+1,
                            monthly_log_core_correction=fit['contributions'][j][band],coefficient=fit['coefficients'][j][band]))
                    setting=result['selection'][model]
                    validation.extend(dict(origin=origin,model=model,chosen_alpha=setting['alpha'],**r) for r in setting['validation'])
            if i%5==0 or i==len(origins)-1:print(f'R23 {i+1}/{len(origins)} {origin}: {result["status"]} n={result["n_train"]}, {time.perf_counter()-start:.1f}s',flush=True)
    combined=pd.concat(results,ignore_index=True);combined.to_csv(out/'native_forecasts.csv',index=False);c.compound(combined).to_csv(out/'forecasts.csv',index=False)
    for name,rows in [('status',statuses),('inner_validation',validation),('coefficient_contributions',contributions),('training',training)]:pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    c.finish(out,hashes,controls=CONTROLS,models=MODELS,origin_count=len(origins),notes='Seven frozen quarterly cost-gap corrections; shared FAST seasonality, independent h0 and noncore unchanged.')
    m=json.loads((out/'manifest.json').read_text());m['outputs']['fits.jsonl']=c.sha(out/'fits.jsonl');c.dump(out/'manifest.json',m)
    print('Completed R23',out,flush=True)


if __name__=='__main__':main()
