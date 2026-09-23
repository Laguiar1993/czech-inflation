"""Evaluate marginal annual-CPI intervals from coherent joint error paths."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from models.path_uncertainty_r18 import joint_pool,annual_scenarios
from models.nowcast_reliability_r18_verified import weighted_quantile,crps


def score_intervals(intended, intervals):
    """Keep the full intended calendar visible, including unavailable laws."""
    keys=['origin','h','model']
    metrics=['point','median','lo80','hi80','lo90','hi90','crps','coverage80','coverage90']
    if intended.duplicated(keys).any() or (len(intervals) and intervals.duplicated(keys).any()):
        raise ValueError('Duplicate interval calendar keys')
    values=intervals.reindex(columns=keys+metrics)
    ledger=intended[keys+['actual']].merge(values,on=keys,how='left',validate='one_to_one')
    ledger['realised']=np.isfinite(ledger.actual)
    finite=np.isfinite(ledger[metrics]).all(axis=1)
    ledger['distribution_available']=finite & ledger.realised
    ledger['distribution_status']=np.where(~ledger.realised,'unrealised_target',
        np.where(ledger.distribution_available,'estimated','missing_distribution'))
    models=sorted(intended.model.unique());horizons=sorted(intended.h.unique())
    count=ledger[ledger.distribution_available].groupby(['origin','h']).model.nunique()
    common_keys=count[count.eq(len(models))].index
    ledger['common_scored']=ledger.distribution_available & ledger.set_index(['origin','h']).index.isin(common_keys)
    scores=[]
    for sample,sub in [('full',ledger),('origins_2024plus',ledger[ledger.origin.ge('2024-01')])]:
        for model in models:
            for h in horizons:
                all_rows=sub[sub.model.eq(model)&sub.h.eq(h)]
                z=all_rows[all_rows.common_scored]
                n_intended=int(all_rows.realised.sum());n_estimated=int(all_rows.distribution_available.sum())
                scores.append(dict(sample=sample,model=model,h=h,n=len(z),n_common=len(z),
                    n_intended=n_intended,n_estimated=n_estimated,n_missing_distributions=n_intended-n_estimated,
                    n_noncommon_distributions=n_estimated-len(z),crps=z.crps.mean(),coverage80=z.coverage80.mean(),
                    coverage90=z.coverage90.mean(),width80=(z.hi80-z.lo80).mean(),width90=(z.hi90-z.lo90).mean(),
                    point_mae=(z.point-z.actual).abs().mean(),median_mae=(z['median']-z.actual).abs().mean()))
    return pd.DataFrame(scores),ledger


def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,default=ROOT/'output/research_r18/path_v2')
    p.add_argument('--output',type=Path,default=ROOT/'output/research_r18/uncertainty_verified');args=p.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False);source=args.experiment/'native_forecasts.csv'
    hashes=c.preserved_hashes();names=[source,ROOT/'models/path_uncertainty_r18.py',ROOT/'models/nowcast_reliability_r18.py',ROOT/'models/nowcast_reliability_r18_verified.py',
        Path(__file__),ROOT/'docs/implementation/R18_UNCERTAINTY_SPEC_2026-09-15.md',ROOT/'data/release_calendar_cz_cpi.csv',
        ROOT/'output/independent_path_frozen_inputs.csv']
    hashes.update({x.resolve().relative_to(ROOT).as_posix():c.sha(x) for x in names})
    c.dump(out/'declaration.json',dict(inputs=hashes,min_pool=24,max_pool=60,weighting='equal_joint_h0_h12_errors'))
    native=pd.read_csv(source,float_precision='round_trip',low_memory=False)
    headline=c.monthly('output/independent_path_frozen_inputs.csv','headline_mm')
    yy=100*np.expm1(np.log1p(headline/100).rolling(12).sum());release=c.publication_dates(headline.index)
    rows=[];pools=[];availability=[]
    for model,g in native.groupby('model'):
        history=g[['origin','h','target','mm_forecast']].rename(columns={'mm_forecast':'forecast'}).copy()
        history['actual']=[headline.get(pd.Period(x,'M'),np.nan) for x in history.target]
        history['released']=[release.get(pd.Period(x,'M'),pd.NaT) for x in history.target]
        for origin,current in g.groupby('origin',sort=True):
            current=current.sort_values('h');t=pd.Period(origin,'M')
            clock=pd.Timestamp(current.as_of_utc.iloc[0]).tz_convert('Europe/Prague').tz_localize(None)
            pool=joint_pool(history,origin,clock)
            valid=np.isfinite(current.mm_forecast).all()
            status='estimated' if pool['n_pool']>=24 and valid else 'insufficient_pool' if pool['n_pool']<24 else 'missing_point_path'
            availability.append(dict(origin=origin,model=model,status=status,n_pool=pool['n_pool']))
            pools.append(dict(origin=origin,model=model,as_of=str(clock),status=status,
                         pool_origins=pool['origins'],pool_final_releases=pool['final_releases'],errors=pool['errors'].tolist()))
            if status!='estimated':continue
            samples=annual_scenarios(current.mm_forecast.to_numpy(),pool['errors'],headline[headline.index<t],t)
            weights=np.ones(pool['n_pool'])/pool['n_pool']
            for h in range(1,13):
                x=samples[:,h];actual=yy.get(t+h,np.nan);q=lambda p:weighted_quantile(x,weights,p)
                rows.append(dict(origin=origin,h=h,target=str(t+h),model=model,n_pool=pool['n_pool'],actual=actual,
                    point=current.iloc[h].yy_exante,median=q(.5),lo80=q(.1),hi80=q(.9),lo90=q(.05),hi90=q(.95),
                    crps=crps(x,weights,actual) if np.isfinite(actual) else np.nan,
                    coverage80=float(q(.1)<=actual<=q(.9)) if np.isfinite(actual) else np.nan,
                    coverage90=float(q(.05)<=actual<=q(.95)) if np.isfinite(actual) else np.nan))
    result=pd.DataFrame(rows);models=sorted(native.model.unique())
    intended=native.loc[native.h.between(1,12),['origin','h','model','target']].copy()
    intended['actual']=[yy.get(pd.Period(x,'M'),np.nan) for x in intended.target]
    scores,ledger=score_intervals(intended,result)
    result.to_csv(out/'intervals.csv',index=False);scores.to_csv(out/'scores.csv',index=False)
    ledger.to_csv(out/'scored_calendar.csv',index=False)
    pd.DataFrame(availability).to_csv(out/'coverage.csv',index=False);c.dump(out/'pools.json',pools)
    c.finish(out,hashes,models=models,probability_status='experimental_uncalibrated',h0_errors_included=True)
    print('Completed joint path-error experiment',out,flush=True)


if __name__=='__main__':main()
