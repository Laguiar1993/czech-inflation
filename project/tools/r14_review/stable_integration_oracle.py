"""Independent R14B saved-result audit; no production model/scorer imports."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r14b/integration'
PRIMARY=['STABLE_PIPELINE_R14B','STABLE_LOCAL_CORE_R14B','STABLE_LONG_CORE_R14B','STABLE_LONG_GAP_R14B']
BASE='INDEPENDENT_BRIDGE'
COUNTS={};MAX={}

def table(path):return pd.read_csv(ROOT/path,float_precision='round_trip')
def same(a,b,label,tol=1e-10):
    aa=np.asarray(a,dtype=float);bb=np.asarray(b,dtype=float)
    if aa.shape!=bb.shape or not np.array_equal(np.isfinite(aa),np.isfinite(bb)):raise AssertionError((label,'shape/mask'))
    good=np.isfinite(aa);d=float(np.max(np.abs(aa[good]-bb[good]))) if good.any() else 0.
    if d>tol:raise AssertionError((label,d))
    COUNTS[label]=COUNTS.get(label,0)+aa.size;MAX[label]=max(MAX.get(label,0),d)
def pct(values):
    q=np.asarray(values,dtype=float)
    return 100*(math.prod(1+q/100)-1) if np.isfinite(q).all() and (q>-100).all() else np.nan
def logsum(values):
    q=np.asarray(values,dtype=float)
    return 100*math.fsum(math.log1p(v/100) for v in q) if np.isfinite(q).all() and (q>-100).all() else np.nan
def metrics(error):
    e=np.asarray(error,dtype=float);e=e[np.isfinite(e)]
    return (len(e),math.sqrt(float(np.mean(e*e))),float(np.mean(abs(e))),float(np.mean(e))) if len(e) else (0,np.nan,np.nan,np.nan)

def main():
    frozen=json.loads((OUT/'manifest.json').read_text())
    for prefix,hashes in [(ROOT,frozen['inputs']),(OUT,frozen['outputs'])]:
        for name,digest in hashes.items():
            if hashlib.sha256((prefix/name).read_bytes()).hexdigest()!=digest:raise AssertionError('Hash '+name)
    COUNTS['hashes']=len(frozen['inputs'])+len(frozen['outputs'])
    key=['origin','h'];base=table('output/independent_bridge_forecasts.csv').set_index(key).sort_index()
    food=table('output/research_r14b/food/native_forecasts.csv');food=food[food.model.eq('FOOD_STABLE_PIPELINE_R14B')].set_index(key).sort_index()
    fuel=table('output/research_r14/fuel/native_forecasts.csv');fuel=fuel[fuel.model.eq('FUEL_CONSTANT_PUMP_R14')].set_index(key).sort_index()
    old=table('output/research_r14/core/native_forecasts.csv');new=table('output/research_r14b/core/native_forecasts.csv')
    local=old[old.model.eq('CORE_LOCAL_R14')].set_index(key).sort_index()
    core=[None,local,new[new.model.eq('CORE_LEVEL_RIDGE_R14')].set_index(key).sort_index(),new[new.model.eq('CORE_GAP_RIDGE_R14')].set_index(key).sort_index()]
    same(local.mm_forecast,new[new.model.eq('CORE_LOCAL_R14')].set_index(key).sort_index().mm_forecast,'identical_local')
    native=table('output/research_r14b/integration/component_predictions.csv')
    for model,cp in zip(PRIMARY,core):
        got=native[native.model.eq(model)].set_index(key).sort_index();expected=base.copy()
        assert got.index.equals(base.index)
        assert got.target.equals(base.target) and got.as_of_utc.equals(base.as_of_utc)
        future=expected.index.get_level_values('h')>0
        for name,source in [('food',food),('fuel',fuel),('core',cp)]:
            if source is None:continue
            for col in ('value_'+name,'contribution_'+name):expected.loc[future,col]=source.loc[future,col]
        components=['contribution_'+b for b in ('core','food','administered','alcohol_tobacco','fuel','wedge')]
        for c in [c for c in base if c.startswith('weight_') or c.startswith('contribution_') or c.startswith('value_')]:
            same(got[c],expected[c],'exact_component_'+c,0.)
        manual=np.asarray([sum(v) if np.isfinite(v).all() else np.nan for v in expected.loc[future,components].to_numpy()])
        same(got.loc[future,'mm_forecast'],manual,'monthly_recombination',0.)
        same(got.loc[~future,'mm_forecast'],base.loc[~future,'mm_forecast'],'fixed_h0',0.)
        assert np.array_equal(got.converged.to_numpy(),np.isfinite(got.mm_forecast.to_numpy()))
    frame=table('output/research_r14b/integration/forecasts.csv')
    assert not frame.duplicated(['origin','model','h']).any()
    # Distinguish every extended algorithm's data policy and reproduce its rows.
    for name,g in new.groupby('model'):
        remapped=name.replace('_R14','_EXT_R14B')
        candidate=frame[frame.model.eq(remapped)].set_index(key).sort_index()
        same(candidate.mm_forecast,g.set_index(key).sort_index().mm_forecast,'extended_policy_'+name,0.)
    raw=table('output/independent_path_frozen_inputs.csv');raw.index=pd.PeriodIndex(raw.iloc[:,0],freq='M');headline=raw.headline_mm
    actual_yoy={m:pct(headline.reindex(pd.period_range(m-11,m,freq='M'))) for m in headline.index}
    for (origin,model),g in frame.groupby(['origin','model']):
        t=pd.Period(origin,'M');byh=g.set_index('h')
        for h,row in byh.iterrows():
            target=t+int(h);months=pd.period_range(target-11,target,freq='M')
            rates=[headline.get(m,np.nan) if m<t else byh.mm_forecast.get((m-t).n,np.nan) for m in months]
            same([row.yy_exante],[pct(rates)],'annual_products')
            same([row.yy_actual],[actual_yoy.get(target,np.nan)],'actual_annual_products')
            same([row.mm_actual],[headline.get(target,np.nan)],'actual_monthly')
            same([row.cumulative_log_forecast],[logsum(byh.mm_forecast.reindex(range(1,int(h)+1)))],'cumulative_forecast')
            same([row.cumulative_log_actual],[logsum(headline.reindex(pd.period_range(t+1,target,freq='M')) if h else [])],'cumulative_actual')
    summary=table('output/research_r14b/integration/summary.csv')
    model_names=[BASE]+sorted(set(frame.model)-{BASE})
    for row in summary.itertuples():
        names=[BASE,*PRIMARY] if row.scope=='combined_common' else ([row.model] if row.scope=='own_coverage' else [BASE,row.scope.removeprefix('paired_')])
        g=frame[frame.h.eq(row.h)&frame.model.isin(names)]
        if row.sample=='recent_origins':g=g[g.origin>='2024-01']
        if row.sample=='recent_targets':g=g[g.target>='2024-01']
        wide=g.pivot(index='origin',columns='model',values='yy_exante').reindex(columns=names)
        truth=g.drop_duplicates('origin').set_index('origin').yy_actual
        common=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.reindex(wide.index))]
        own=g[g.model.eq(row.model)].set_index('origin');selected=own.reindex(common)
        same([row.n_intended_origins,row.n_available_targets,row.n_own_forecasts,row.n_common],
             [len(own),np.isfinite(own.yy_actual).sum(),(np.isfinite(own.yy_actual)&np.isfinite(own.yy_exante)).sum(),len(common)],'panel_counts',0.)
        for tag,pred,actual in [('yy','yy_exante','yy_actual'),('mm','mm_forecast','mm_actual'),('cumulative_log','cumulative_log_forecast','cumulative_log_actual')]:
            same([getattr(row,tag+'_'+s) for s in ('n','rmse','mae','bias')],metrics(selected[pred]-selected[actual]),'score_'+tag)
    intervals=table('output/research_r14b/integration/paired_uncertainty.csv');rng=np.random.default_rng(1409);number=0
    for sample in ('full','recent_targets','recent_origins'):
        eligible=frame if sample=='full' else frame[frame['target' if sample=='recent_targets' else 'origin']>='2024-01']
        for h in range(1,13):
            g=eligible[eligible.h.eq(h)].copy();g['e']=g.yy_exante-g.yy_actual;wide=g.pivot(index='origin',columns='model',values='e')
            for model in model_names[1:]:
                pair=wide[[model,BASE]].dropna();n=len(pair)
                if not n:continue
                delta=(pair[model]**2-pair[BASE]**2).to_numpy();starts=rng.integers(0,n,(2000,int(np.ceil(n/12))))
                samples=np.concatenate([(starts[:,i,None]+np.arange(12))%n for i in range(starts.shape[1])],axis=1)[:,:n]
                lo,hi=np.quantile(delta[samples].mean(axis=1),[.025,.975])
                row=intervals[(intervals['sample']==sample)&intervals.h.eq(h)&intervals.model.eq(model)].iloc[0]
                same([row.n,row.mse_difference,row.lower,row.upper],[n,delta.mean(),lo,hi],'bootstrap');number+=1
    assert number==len(intervals)
    quarters=table('output/research_r14b/integration/cnb_quarters.csv');cnb=table('data/cnb_mpr_cpi_quarterly.csv')
    clocks=frame[['origin','as_of_utc']].drop_duplicates().copy();clocks['clock']=pd.to_datetime(clocks.as_of_utc,utc=True)
    lookup=frame.set_index(['origin','model','target']).yy_exante
    for row in quarters.itertuples():
        available=pd.Timestamp(row.report_date).tz_localize('Europe/Prague').tz_convert('UTC')
        prior=clocks[clocks.clock<available].sort_values('clock').iloc[-1]
        assert row.origin==prior.origin and row.as_of_utc==prior.as_of_utc
        t=pd.Period(row.origin,'M');q=pd.Period(row.quarter,'Q');months=pd.period_range(q.start_time,q.end_time,freq='M')
        actual=[actual_yoy.get(m,np.nan) for m in months]
        forecast=[actual_yoy.get(m,np.nan) if m<t else lookup.get((row.origin,row.model,str(m)),np.nan) for m in months]
        if row.model=='CNB':forecast=[row.cnb]*3
        value=np.mean(forecast) if np.isfinite(forecast).all() else np.nan
        same([row.forecast,row.realised],[value,np.mean(actual) if np.isfinite(actual).all() else np.nan],'quarter_products')
        same([row.known_months,row.forecast_months],[sum(m<t for m in months),sum(m>=t for m in months)],'quarter_month_counts',0.)
    qsummary=table('output/research_r14b/integration/cnb_summary.csv')
    for row in qsummary.itertuples():
        names=[BASE,*PRIMARY,'CNB'] if row.scope=='combined_common' else list(dict.fromkeys([BASE,row.scope.removeprefix('paired_'),'CNB']))
        g=quarters[quarters.model.isin(names)]
        if row.sample=='recent_reports':g=g[g.report_date>='2024-01-01']
        if str(row.quarters_ahead)!='all':g=g[g.quarters_ahead==int(row.quarters_ahead)]
        wide=g.pivot(index=['report_date','quarter'],columns='model',values='forecast').reindex(columns=names)
        truth=g.drop_duplicates(['report_date','quarter']).set_index(['report_date','quarter']).realised
        common=wide.index[np.isfinite(wide).all(axis=1)&np.isfinite(truth.reindex(wide.index))]
        n,rmse,mae,bias=metrics(wide.loc[common,row.model]-truth.reindex(common))
        same([row.n_report_quarter_pairs,row.n_unique_quarters,row.n_reports,row.rmse,row.mae,row.bias],
             [n,len(set(common.get_level_values('quarter'))),len(set(common.get_level_values('report_date'))),rmse,mae,bias],'quarter_scores')
    # Confirm the input/output snapshot did not move during independent review.
    for prefix,hashes in [(ROOT,frozen['inputs']),(OUT,frozen['outputs'])]:
        for name,digest in hashes.items():assert hashlib.sha256((prefix/name).read_bytes()).hexdigest()==digest
    report=dict(status='passed',counts=COUNTS,max_abs_differences=MAX,forecast_rows=len(frame),summary_rows=len(summary),
                interval_rows=len(intervals),quarter_rows=len(quarters),quarter_summary_rows=len(qsummary),
                review='Independent arithmetic only; no production model/scorer imports or model refits')
    (Path(__file__).parent/'stable_integration_receipt.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
