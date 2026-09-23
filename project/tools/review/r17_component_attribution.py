"""Frozen FAST component and joint replacement accounting, never a forecast."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import path_attribution_r14 as prior


def common_support(raw,roster):
    if raw.duplicated(['origin','h','model']).any():raise ValueError('Duplicate forecast keys')
    selected=raw[raw.model.isin(roster)&raw.h.gt(0)].copy()
    selected['finite']=np.isfinite(selected.yy_exante)&np.isfinite(selected.yy_actual)
    counts=selected.groupby(['origin','h']).agg(n=('model','nunique'),finite=('finite','sum'))
    return counts[counts.n.eq(len(roster))&counts.finite.eq(len(roster))].reset_index()[['origin','h']]


def joint_oracles(native,actual):
    rows=[]
    for (model,origin),group in native.groupby(['model','origin']):
        t=pd.Period(origin,'M');g=group.set_index('h').sort_index()
        if g.index.tolist()!=list(range(13)):raise ValueError('Complete native horizon calendar required')
        if g.target.tolist()!=pd.period_range(t,t+12,freq='M').astype(str).tolist():raise ValueError('Target/horizon mismatch')
        path=g.mm_forecast.to_dict();history=actual.headline.loc[actual.index<t]
        for name,blocks in [('noncore',prior.BLOCKS[1:]),('all_components',prior.BLOCKS)]:
            oracle=path.copy()
            for h in range(1,13):
                effects=[]
                for block in blocks:
                    w=g.at[h,'weight_'+('alc' if block=='alcohol_tobacco' else block)]
                    effects.append(w*(actual[block].get(t+h,np.nan)-g.at[h,'value_'+block]))
                oracle[h]=path[h]+prior.strict_sum(effects)
            for h in range(1,13):
                prediction=prior.annual_path(history,path,t,h)
                truth=prior.annual_value(actual.headline.reindex(pd.period_range(t+h-11,t+h,freq='M')))
                counter=prior.annual_path(history,oracle,t,h)
                e,b,r=prediction-truth,prediction-counter,counter-truth
                rows.append(dict(model=model,origin=origin,target=str(t+h),h=h,block=name,
                    annual_forecast=prediction,annual_actual=truth,annual_oracle=counter,
                    annual_error=e,annual_block_error=b,annual_other_error=r,block_squared_error=b*b,
                    other_squared_error=r*r,cross_term=2*b*r,headline_squared_error=e*e,oracle_mse_gain=e*e-r*r))
    return pd.DataFrame(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'output/research_r17/attribution')
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    files=['output/research_r15/native_forecasts.csv','output/research_r14b/integration/native_forecasts.csv',
        'output/research_r16/forecasts.csv','output/research_r16/manifest.json','output/research_r14b/attribution/actual_component_targets.csv',
        'output/independent_path_frozen_inputs.csv','path_attribution_r14.py','tools/review/r17_component_attribution.py']
    hashes={f:prior.sha(ROOT/f) for f in files}
    read=lambda f:pd.read_csv(ROOT/f,float_precision='round_trip')
    native=pd.concat([read(files[0]).query("model == 'STATE_FAST_R15'"),read(files[1]).query("model == 'STABLE_LOCAL_CORE_R14B'")],ignore_index=True)
    raw=read(files[2]);roster=json.loads((ROOT/files[3]).read_text(encoding='utf-8'))
    support=common_support(raw,roster['models']+roster['controls'])
    actual=read(files[4]).set_index('period');actual.index=pd.PeriodIndex(actual.index,freq='M')
    headline=read(files[5]).set_index('period').headline_mm;headline.index=pd.PeriodIndex(headline.index,freq='M')
    actual=actual.reindex(actual.index.union(headline.index));actual['headline']=headline
    singles=prior.calculate(native,actual);joint=joint_oracles(native,actual)
    all_rows=pd.concat([singles,joint],ignore_index=True)
    chosen=all_rows.merge(support,on=['origin','h'],validate='many_to_one')
    summary=prior.summarize_oracles(chosen)
    for name,frame in [('component_errors.csv',singles),('joint_oracles.csv',joint),('primary_rows.csv',chosen),
                       ('primary_oracle_summary.csv',summary),('primary_support.csv',support)]:frame.to_csv(out/name,index=False)
    meta=dict(purpose='Hindsight arithmetic only; no model fit, no future input made available to a forecast.',
        support='Original R16 all15 annual-headline support. Missing component outcomes remain visible and have fewer oracle-valid rows.',
        weights='Frozen origin projection weights, not exact chain-linked official contributions.',
        wedge='Held fixed. No realised wedge manufactured; all-components oracle still includes reconciliation and h0 where in window.',
        units='Ordinary annual-CPI percentage points, matching original R14 oracle definitions; not R16 annual-log attribution units.',
        nonadditivity='Single-block oracle gains are conditional and nonadditive; joint noncore/all-components replacements are computed separately.',
        inputs=hashes,outputs={p.name:prior.sha(p) for p in out.glob('*.csv')})
    for f,d in hashes.items():
        if prior.sha(ROOT/f)!=d:raise ValueError('Source changed: '+f)
    (out/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(summary.query("sample == 'recent_origins' and scope == 'model_all_blocks_common' and h == 12")
          [['model','block','n','headline_rmse','oracle_rmse']].to_string(index=False))


if __name__=='__main__':main()
