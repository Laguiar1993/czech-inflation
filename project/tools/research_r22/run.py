"""Run all seven declared joint-transmission candidates on the frozen90 origins."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from data.research_transmission_r22 import load_inputs
from models.transmission_r22 import run_origin,FAMILIES,mask_panel

CONTROLS=['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16','CORE_FEEDBACK_R21']
MODELS=[*FAMILIES,'JOINT_HALF_R22']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--limit',type=int)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False);started=time.perf_counter()
    panel,available,quarters,metadata,hashes=load_inputs();hashes.update(c.preserved_hashes())
    extra=['models/transmission_r22.py','models/food_path_r14.py','docs/implementation/R22_TRANSMISSION_SPEC_2026-09-15.md',
           'output/research_r21/path_anchor/native_forecasts.csv','r17_common.py',Path(__file__).relative_to(ROOT).as_posix()]
    hashes.update({p:c.sha(ROOT/p) for p in extra})
    native=c.read(extra[3]);native=native[native.model.isin(CONTROLS)].copy()
    origins=sorted(native.origin.unique());origins=origins[:args.limit] if args.limit else origins
    native=native[native.origin.isin(origins)]
    if native.duplicated(['origin','h','model']).any() or native.groupby('model').size().ne(len(origins)*13).any():raise ValueError('Invalid reference support')
    panel.to_csv(out/'measurements.csv',index_label='period');available.to_csv(out/'available_from.csv',index_label='period')
    quarters.to_csv(out/'ulc_source_quarter.csv',index_label='period',header=['source_quarter']);c.dump(out/'measurement_metadata.json',metadata)
    results=[native];drivers=[];responses=[];training=[];status=[]
    with (out/'fits.jsonl').open('w',encoding='utf-8') as log:
        for i,origin in enumerate(origins):
            t=pd.Period(origin,'M');base=native[native.origin.eq(origin)&native.model.eq('STATE_FAST_R15')].copy()
            clock=base.as_of_utc.iloc[0];result=run_origin(panel,available,t,clock)
            log.write(json.dumps(dict(origin=origin,as_of=clock,**result),default=str,allow_nan=False)+'\n');log.flush()
            learned=result['status']=='estimated'
            for model in MODELS:
                if not learned:frame=base.copy()
                else:
                    if model=='JOINT_HALF_R22':
                        rates=.5*np.array(result['paths']['JOINT_LINEAR_R22'])+.5*base[base.h.gt(0)].sort_values('h').value_core.to_numpy()
                    else:rates=result['paths'][model]
                    frame=c.replace_block(base,'core',dict(zip(range(1,13),rates)))
                frame['model']=model;frame['core_model_status']=result['status'];frame['core_fallback_used']=not learned
                frame['core_fallback_reason']='insufficient_common_history' if not learned else ''
                results.append(frame)
                status.append(dict(origin=origin,as_of=clock,model=model,status=result['status'],n_train=result['n_train']))
            if learned:
                observed_panel=mask_panel(panel,available,t,clock)
                for model,fit in result['fits'].items():
                    keys=pd.PeriodIndex(fit['train_dates'],freq='M');all_used=keys
                    for lag in range(1,7):all_used=all_used.union(keys-lag)
                    # Every common training response/lag cell must have a released source.
                    releases=available.loc[all_used];latest=releases.max().max()
                    cutoff=pd.Timestamp(clock).tz_convert('Europe/Prague').tz_localize(None)
                    if releases.isna().any().any() or latest>cutoff:raise ValueError('Unpublished common training input')
                    for key in keys:training.append(dict(origin=origin,model=model,target=str(key),
                        last_input_release=available.loc[pd.period_range(key-6,key,freq='M')].max().max().isoformat()))
                    for variable,path in result['drivers'][model].items():
                        last=observed_panel[variable].dropna().iloc[-1]
                        last_month=observed_panel[variable].last_valid_index()
                        seasonal=result['preprocessing']['seasonal'][variable]
                        for h,value in path.items():drivers.append(dict(origin=origin,as_of=clock,model=model,variable=variable,h=int(h),
                            target=str(t+int(h)),forecast=value,actual=panel[variable].get(t+int(h),np.nan),
                            persistence=last-seasonal[last_month.month]+seasonal[(t+int(h)).month],
                            n_distinct_ulc_quarters=int(quarters.loc[keys].nunique())))
                responses.extend(dict(origin=origin,**r) for r in result['responses'])
            if i%5==0 or i==len(origins)-1:print(f'R22 {i+1}/{len(origins)} {origin}: {result["status"]}, n={result["n_train"]}, elapsed={time.perf_counter()-started:.1f}s',flush=True)
    result=pd.concat(results,ignore_index=True);result.to_csv(out/'native_forecasts.csv',index=False)
    c.compound(result).to_csv(out/'forecasts.csv',index=False)
    for name,rows in [('driver_forecasts',drivers),('response_diagnostics',responses),('training',training),('status',status)]:pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    c.finish(out,hashes,controls=CONTROLS,models=MODELS,origin_count=len(origins),
             notes='Seven fixed joint economic systems; all new core paths share dates. Proxy category and quarterly ULC limitations explicit; h0 and noncore preserved.')
    # r17 finish hashes CSV/JSON; add diagnostic JSONL explicitly.
    m=json.loads((out/'manifest.json').read_text());m['outputs']['fits.jsonl']=c.sha(out/'fits.jsonl');c.dump(out/'manifest.json',m)
    print('Completed',out,flush=True)


if __name__=='__main__':main()
