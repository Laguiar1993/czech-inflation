"""Frozen R17 core and independent-h0 experiment; no network or old-file writes."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import r17_common as common
from models import core_adaptation_r17 as engine

MODELS=('CORE_ROBUST_R17','CORE_NEWS_R17','CORE_FAST_H0_R17','CORE_NEWS_H0_R17')
ROOT=common.ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/research_r17_core')
    parser.add_argument('--limit-origins',type=int)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    hashes=common.preserved_hashes()
    files=['r17_common.py','models/core_adaptation_r17.py','core_adaptation_experiment_r17.py',
        'docs/implementation/R17_CORE_SPEC_2026-09-14.md','tests/fixtures/cleanup/cnb_core_mm.csv',
        'data/release_calendar_cz_cpi.csv','output/independent_nowcast_diagnostics.json',
        'output/research_r13/nowcast/core_predictions.csv']
    hashes.update({f:common.sha(ROOT/f) for f in files})
    common.dump(out/'declaration.json',dict(inputs=hashes,models=MODELS))
    saved=json.loads((ROOT/'output/research_r15/states.json').read_text())
    core=common.monthly(files[4],'core');available=common.publication_dates(core.index)
    h0=pd.DataFrame(json.loads((ROOT/files[6]).read_text())).query("policy == 'hard'").set_index('period').core_forecast
    check=common.read(files[7]).query("model == 'R9_BASE'").set_index('period').core_forecast
    if h0.index.duplicated().any() or check.index.duplicated().any():raise ValueError('Duplicate h0')
    if set(h0.index)!=set(check.index) or not np.allclose(h0,check.reindex(h0.index),atol=1e-12,rtol=0):raise ValueError('Archived h0 mismatch')
    origins=sorted(h0.index)
    if args.limit_origins:origins=origins[:args.limit_origins]
    saved={k:v for k,v in saved.items() if k<=origins[-1]}
    filters={};p0=[];traces=[];parity=0.;fast_parity=0.
    reference=json.loads((ROOT/'output/research_r16/slope_states.json').read_text())
    for key,state in saved.items():
        t=pd.Period(key,'M');clock=pd.Timestamp(state['as_of']);known=core.loc[:t-1]
        releases=available.reindex(known.index)
        if releases.isna().any() or releases.gt(clock).any():raise ValueError('Unreleased core used')
        factors={int(k):v for k,v in state['seasonal'].items()};adjusted=common.adjusted_core(known,factors)
        parents={mode:engine.filter_state(adjusted,t,factors,mode) for mode in ('fixed','robust','news')}
        parents['fast']=engine.fast_state(state,t)
        expected=reference[key]['forecasts_log']['p95_q001']
        parity=max(parity,max(abs(parents['fixed']['path'][h]-expected[str(h)]) for h in range(1,13)))
        fast_parity=max(fast_parity,max(abs(parents['fast']['path'][h]-state['forecasts_log']['fast'][str(h)]) for h in range(1,13)))
        for mode,parent in parents.items():
            traces.extend(dict(origin=key,mode=mode,**r) for r in parent.pop('trace',[]))
            if key in h0.index and mode in ('fast','news'):
                h0_log=float(100*np.log1p(h0[key]/100));actual=core.get(t,np.nan)
                p0.append(dict(origin=key,parent=mode,baseline_log=parent['h0_log'],h0_log=h0_log,
                    signal=h0_log-parent['h0_log'],error=float(100*np.log1p(actual/100)-parent['h0_log']),
                    available_from=str(available.get(t,pd.NaT))))
        filters[key]=parents
    if parity>1e-11 or fast_parity>1e-11:raise ValueError('Fixed state replay drift')
    history=pd.DataFrame(p0);predictions=[];updates=[]
    for key in origins:
        t=pd.Period(key,'M');parents=filters[key]
        paths={'CORE_ROBUST_R17':parents['robust']['path'],'CORE_NEWS_R17':parents['news']['path']}
        for mode in ('fast','news'):
            beta,metadata=engine.h0_coefficient(history[history.parent.eq(mode)],t,saved[key]['as_of'])
            signal=float(history.loc[history.origin.eq(key)&history.parent.eq(mode),'signal'].iloc[0])
            paths['CORE_'+mode.upper()+'_H0_R17']=engine.condition_h0(parents[mode],beta*signal)
            updates.append(dict(origin=key,parent=mode,beta=beta,signal=signal,delta=beta*signal,
                as_of=saved[key]['as_of'],**metadata))
        for model,path in paths.items():
            predictions.extend(dict(origin=key,h=h,model=model,core_log=v,core_mm=float(100*np.expm1(v/100))) for h,v in path.items())
    predictions=pd.DataFrame(predictions);native=[]
    baseline=common.read('output/research_r15/native_forecasts.csv').query('model == @common.FAST')
    for (key,model),group in predictions.groupby(['origin','model']):
        base=baseline[baseline.origin.eq(key)]
        changed=common.replace_block(base,'core',group.set_index('h').core_mm.to_dict())
        changed['model']=model;native.append(changed)
    native=pd.concat(native,ignore_index=True);forecasts=common.compound(native)
    keys=['origin','h','model'];derived=['yy_exante','cumulative_log_forecast','cumulative_log_actual']
    native=native.drop(columns=derived).merge(forecasts[keys+derived],on=keys,validate='one_to_one')
    for name,frame in [('core_predictions',predictions),('h0_history',history),('innovation_trace',pd.DataFrame(traces)),('native_forecasts',native),('forecasts',forecasts)]:frame.to_csv(out/(name+'.csv'),index=False)
    common.dump(out/'states.json',filters);common.dump(out/'updates.json',updates)
    common.finish(out,hashes,models=MODELS,origin_count=len(origins),state_count=len(filters),
        fixed_r16_max_error=parity,fast_r15_max_error=fast_parity,
        covariance_note='h0 updates modify conditional means only; state covariance is not posterior uncertainty')
    print('Completed',out,'fixed parity',parity,'fast parity',fast_parity,flush=True)


if __name__=='__main__':main()
