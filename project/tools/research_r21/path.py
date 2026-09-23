"""R21 exact-path pooling and component error feedback, fixed archived origins."""
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from models.path_components_r17 import blend_native
from models.released_error_research_r21 import PRIOR,eligible_rows,bias_offset,pool_weights

EXPERTS=['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16']


def prepare_training(native,actual,available,origin,asof,complete=False):
    """The full mask is constructed before actuals are accessed or compounded."""
    p=[];truth=[];masks=[];ages=[];ledger=[]
    for old,g in native.groupby('origin'):
        s=pd.Period(old,'M')
        if s>=origin:continue
        target=pd.period_range(s+1,s+12,freq='M');dates=available.reindex(target)
        prefix=np.logical_and.accumulate(dates.notna().to_numpy()&dates.le(asof).to_numpy()&(target<origin))
        use=prefix&(target>=origin-36)
        if complete and not prefix.all():continue
        if not use.any():continue
        forecasts=g[g.h.gt(0)].pivot(index='model',columns='h',values='mm_forecast').reindex(index=EXPERTS,columns=range(1,13)).to_numpy(float)
        values=np.full(12,np.nan);values[prefix]=actual.reindex(target[prefix]).to_numpy(float)
        cumulative=100*np.cumsum(np.log1p(values/100))
        if not np.isfinite(cumulative[use]).all():raise ValueError('Missing published actual')
        p.append(forecasts);truth.append(cumulative);masks.append(use);ages.append(origin.ordinal-target.asi8)
        for h in np.flatnonzero(use):ledger.append(dict(train_origin=old,h=h+1,target=str(target[h]),available_from=dates.iloc[h].isoformat()))
    return (np.asarray(p).reshape(-1,3,12),np.asarray(truth).reshape(-1,12),np.asarray(masks,bool).reshape(-1,12),np.asarray(ages).reshape(-1,12)),ledger


def feedback(frame,errors,origin,asof,blocks):
    out=frame.copy();diagnostics=[]
    for block in blocks:
        used=eligible_rows(errors[errors.block.eq(block)],origin,asof).sort_values('target').tail(24)
        delta=bias_offset(used)
        old=out[out.h.gt(0)].set_index('h')['value_'+block]
        new=100*np.expm1(np.log1p(old/100)+delta*.9**(old.index.to_numpy()-1)/100)
        out=c.replace_block(out,block,new.to_dict())
        diagnostics.append(dict(block=block,offset_log=delta,n=len(used),last_release=used.available_from.max() if len(used) else None,
                                targets='|'.join(used.target)))
    return out,diagnostics


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    hashes=c.preserved_hashes()
    files=['output/research_r17/path/native_forecasts.csv','output/independent_path_frozen_inputs.csv',
           'output/research_r14b/attribution/actual_component_targets.csv','data/release_calendar_cz_cpi.csv',
           'models/released_error_research_r21.py','models/path_components_r17.py','r17_common.py',
           'docs/implementation/R21_RESEARCH_SPEC_2026-09-15.md',Path(__file__).relative_to(ROOT).as_posix()]
    hashes.update({p:c.sha(ROOT/p) for p in files})
    native=c.read(files[0]);native=native[native.model.isin(EXPERTS)].copy()
    if native.groupby('model').size().ne(1170).any() or native.duplicated(['origin','h','model']).any():raise ValueError('Bad frozen calendar')
    headline=c.monthly(files[1],'headline_mm');components=c.monthly(files[2]);available=c.publication_dates(headline.index)
    error_rows=[]
    for row in native[native.model.eq(EXPERTS[0])&native.h.eq(1)].itertuples():
        target=pd.Period(row.target,'M')
        for block in ['core','food']:
            truth=components.loc[target,block] if target in components.index else np.nan
            error_rows.append(dict(block=block,target=str(target),available_from=available.get(target,pd.NaT),
                error=100*(np.log1p(truth/100)-np.log1p(getattr(row,'value_'+block)/100))))
    errors=pd.DataFrame(error_rows)
    results=[native];training=[];weights=[];biases=[]
    for i,(origin,g) in enumerate(native.groupby('origin')):
        t=pd.Period(origin,'M');asof=pd.Timestamp(g.as_of_utc.iloc[0]).tz_convert('Europe/Prague').tz_localize(None)
        frames=[g[g.model.eq(m)].copy() for m in EXPERTS]
        for name,complete in [('POOL_PRIOR_R21',None),('POOL_COMPLETE_R21',True),('POOL_PARTIAL_R21',False)]:
            if complete is None:w=PRIOR.copy();ledger=[]
            else:
                arrays,ledger=prepare_training(native,headline,available,t,asof,complete)
                w=pool_weights(*arrays)
            results.append(blend_native(frames,w,name))
            weights.append(dict(origin=origin,model=name,as_of=asof.isoformat(),fast=w[0],current=w[1],gentle=w[2],
                n_labels=len(ledger),n_origins=len(set(r['train_origin'] for r in ledger))))
            training.extend(dict(origin=origin,model=name,as_of=asof.isoformat(),**r) for r in ledger)
        for name,blocks in [('CORE_FEEDBACK_R21',['core']),('FOOD_FEEDBACK_R21',['food']),('DUAL_FEEDBACK_R21',['core','food'])]:
            adjusted,diag=feedback(frames[0],errors,t,asof,blocks);adjusted['model']=name;results.append(adjusted)
            biases.extend(dict(origin=origin,model=name,as_of=asof.isoformat(),**r) for r in diag)
        if i%15==0:print(f'Path {i+1}/90',flush=True)
    result=pd.concat(results,ignore_index=True);forecasts=c.compound(result)
    result.to_csv(out/'native_forecasts.csv',index=False);forecasts.to_csv(out/'forecasts.csv',index=False)
    pd.DataFrame(training).to_csv(out/'training.csv',index=False);pd.DataFrame(weights).to_csv(out/'weights.csv',index=False)
    pd.DataFrame(biases).to_csv(out/'biases.csv',index=False);errors.to_csv(out/'feedback_error_history.csv',index=False)
    c.finish(out,hashes,controls=EXPERTS,models=sorted(set(result.model)-set(EXPERTS)),
             notes='R21 six fixed path candidates. Equal h0. Partial pool uses exact cumulative log loss on released prefixes.')
    print('Finished',out,flush=True)


if __name__=='__main__':main()
