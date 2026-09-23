"""Recompute saved joint empirical uncertainty outputs without model helpers."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
def read(path):return pd.read_csv(path,float_precision='round_trip',low_memory=False)
def equal(a,b,label):
    assert np.allclose(a,b,rtol=0,atol=3e-11,equal_nan=True),label


def run(experiment,uncertainty):
    native=read(ROOT/experiment/'native_forecasts.csv')
    data=read(ROOT/'output/independent_path_frozen_inputs.csv')
    history=pd.Series(data.headline_mm.to_numpy(),index=pd.PeriodIndex(data.period,freq='M'))
    cal=read(ROOT/'data/release_calendar_cz_cpi.csv')
    cal.index=pd.PeriodIndex(cal.target_month,freq='M')
    releases=pd.to_datetime(cal.detail_release_dt).dt.normalize()+pd.Timedelta(hours=9)
    # All pool targets start in2019 and are covered by the explicit calendar;
    # this audit does not reuse the implementation's older-date fallback.
    output=ROOT/uncertainty
    pools=json.loads((output/'pools.json').read_text())
    intervals=read(output/'intervals.csv')
    coverage=read(output/'coverage.csv').set_index(['origin','model'])
    groups={(o,m):g.sort_values('h') for (o,m),g in native.groupby(['origin','model'])}
    model_paths={m:[] for m in native.model.unique()}
    for (o,m),g in groups.items():
        target=pd.PeriodIndex(g.target,freq='M')
        f=g.mm_forecast.to_numpy(float);a=history.reindex(target).to_numpy(float)
        if not np.isfinite([f,a]).all() or (f<=-100).any() or (a<=-100).any():continue
        dates=releases.reindex(target)
        if dates.isna().any():continue
        model_paths[m].append((o,100*np.log((1+a/100)/(1+f/100)),dates.max()))
    for m in model_paths:model_paths[m].sort(key=lambda x:x[0])
    sample_lookup={};max_error=0.;pool_coordinates=0;statuses={}
    for saved in pools:
        origin,model=saved['origin'],saved['model'];o=pd.Period(origin,'M')
        current=groups[(origin,model)]
        clock=pd.Timestamp(current.as_of_utc.iloc[0]).tz_convert('Europe/Prague').tz_localize(None)
        assert pd.Timestamp(saved['as_of'])==clock
        eligible=[x for x in model_paths[model] if pd.Period(x[0],'M')+12<o and x[2]<=clock][-60:]
        assert [x[0] for x in eligible]==saved['pool_origins']
        assert [str(x[2]) for x in eligible]==saved['pool_final_releases']
        expected=np.array([x[1] for x in eligible]).reshape(-1,13)
        got=np.array(saved['errors']).reshape(-1,13);equal(got,expected,'pool errors')
        pool_coordinates+=expected.size
        if expected.size:max_error=max(max_error,float(abs(got-expected).max()))
        n=len(eligible)
        status='estimated' if n>=24 and np.isfinite(current.mm_forecast).all() else 'insufficient_pool' if n<24 else 'missing_point_path'
        assert saved['status']==status
        assert coverage.loc[(origin,model),'status']==status
        assert coverage.loc[(origin,model),'n_pool']==n
        statuses[status]=statuses.get(status,0)+1
        if status!='estimated':continue
        # Direct products of twelve monthly relatives, retaining row identity.
        known=history.reindex(pd.period_range(o-11,o-1,freq='M')).to_numpy(float)
        assert np.isfinite(known).all()
        projected=(1+current.mm_forecast.to_numpy(float)[None,:]/100)*np.exp(expected/100)
        joined=np.concatenate([np.tile(1+known/100,(n,1)),projected],axis=1)
        scenarios=np.stack([100*(np.prod(joined[:,h:h+12],axis=1)-1) for h in range(13)],axis=1)
        for h in range(1,13):sample_lookup[(origin,model,h)]=scenarios[:,h]
    assert len(pools)==native[['origin','model']].drop_duplicates().shape[0]
    assert set(intervals[['origin','model','h']].itertuples(index=False,name=None))==set(sample_lookup)
    for r in intervals.itertuples():
        x=sample_lookup[(r.origin,r.model,r.h)];ordered=np.sort(x);n=len(x)
        quant=lambda p:ordered[max(0,int(np.ceil(n*p))-1)]
        equal([r.median,r.lo80,r.hi80,r.lo90,r.hi90],
              [quant(.5),quant(.1),quant(.9),quant(.05),quant(.95)],'inverse CDF')
        target=pd.Period(r.target,'M')
        a=history.reindex(pd.period_range(target-11,target,freq='M')).to_numpy(float)
        truth=100*(np.prod(1+a/100)-1) if np.isfinite(a).all() else np.nan
        equal(r.actual,truth,'actual annual')
        equal(r.point,groups[(r.origin,r.model)].iloc[r.h].yy_exante,'unchanged point')
        if np.isfinite(truth):
            score=np.mean(np.abs(x-truth))-.5*np.mean(np.abs(x[:,None]-x[None,:]))
            equal(r.crps,score,'CRPS')
            assert r.coverage80==float(quant(.1)<=truth<=quant(.9))
            assert r.coverage90==float(quant(.05)<=truth<=quant(.95))
        else:assert not np.isfinite([r.crps,r.coverage80,r.coverage90]).any()
    scores=read(output/'scores.csv');n_models=native.model.nunique()
    ledger=read(output/'scored_calendar.csv')
    assert not ledger.duplicated(['origin','h','model']).any()
    intended_source=read(ROOT/experiment/'evaluation/primary_rows.csv') if output.name=='uncertainty_final' else native[native.h.gt(0)]
    assert set(ledger[['origin','h','model']].itertuples(index=False,name=None))==set(intended_source[['origin','h','model']].itertuples(index=False,name=None))
    if output.name=='uncertainty_final':assert len(ledger)==969*n_models
    assert len(scores)==2*n_models*12
    for r in scores.itertuples():
        own=intervals[intervals.h.eq(r.h)&np.isfinite(intervals.actual)]
        if r.sample=='origins_2024plus':own=own[own.origin.ge('2024-01')]
        common=set(own.groupby('origin').model.nunique().loc[lambda x:x.eq(n_models)].index)
        own=own[own.origin.isin(common)&own.model.eq(r.model)]
        assert r.n==len(own)
        l=ledger[ledger.model.eq(r.model)&ledger.h.eq(r.h)]
        if r.sample=='origins_2024plus':l=l[l.origin.ge('2024-01')]
        assert r.n_common==len(own)==int(l.common_scored.sum())
        assert r.n_intended==int(np.isfinite(l.actual).sum())
        assert r.n_estimated==int(l.distribution_available.sum())
        assert r.n_missing_distributions==r.n_intended-r.n_estimated
        assert r.n_noncommon_distributions==r.n_estimated-len(own)
        equal([r.crps,r.coverage80,r.coverage90,r.width80,r.width90,r.point_mae,r.median_mae],
              [own.crps.mean(),own.coverage80.mean(),own.coverage90.mean(),(own.hi80-own.lo80).mean(),
               (own.hi90-own.lo90).mean(),abs(own.point-own.actual).mean(),abs(own['median']-own.actual).mean()],
              'common interval scores')
    result=dict(pool_groups=len(pools),pool_error_coordinates=pool_coordinates,error_coordinate_max=max_error,
                interval_rows=len(intervals),score_rows=len(scores),statuses=statuses,
                first_estimated_origin=intervals.origin.min(),last_estimated_origin=intervals.origin.max(),
                scored_calendar_rows=len(ledger),scores_have_n_intended='n_intended' in scores,
                no_national_energy_probability_claim=True,
                limitations=['Current-vintage labels, not first-release CPI.',
                  'Overlapping source paths are dependent and crisis errors recur across many vectors.',
                  'Empirical equally weighted tails with24to60 whole vectors are coarse and uncalibrated.',
                  'These historical errors do not assign probabilities to new geopolitical shocks.'])
    result['hashes']={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in
        [Path(__file__),output/'manifest.json',ROOT/'models/path_uncertainty_r18.py',
         ROOT/('models/nowcast_reliability_r18_final.py' if output.name=='uncertainty_final' else 'models/nowcast_reliability_r18_verified.py'),
         ROOT/('tools/research_r18/path_uncertainty_final.py' if output.name=='uncertainty_final' else 'tools/research_r18/path_uncertainty_verified.py')]}
    resultname='uncertainty_final_verification.json' if output.name=='uncertainty_final' else 'uncertainty_verification.json'
    (OUT/resultname).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,default=Path('output/research_r18/path_v2'))
    p.add_argument('--uncertainty',type=Path,default=Path('output/research_r18/uncertainty_final'));a=p.parse_args()
    run(a.experiment,a.uncertainty)
