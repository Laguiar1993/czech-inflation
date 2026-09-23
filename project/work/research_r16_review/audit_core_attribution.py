"""Independent weighted-core oracle check; imports no estimator/evaluator code."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'output/research_r16';ATTR=EXP/'attribution'
OUT=Path(__file__).resolve().parent/'attribution';OUT.mkdir(exist_ok=True)
read=lambda name,base=ROOT:pd.read_csv(base/name,float_precision='round_trip')
manifest=json.loads((ATTR/'manifest.json').read_text(encoding='utf-8'));verified=0
for name,digest in manifest['inputs'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest;verified+=1
for name,digest in manifest['outputs'].items():assert hashlib.sha256((ATTR/name).read_bytes()).hexdigest()==digest;verified+=1
run=json.loads((EXP/'manifest.json').read_text(encoding='utf-8'));roster=run['controls']+run['models']
models=['STATE_FAST_R15','DAMPED_P95_Q001_R16','DAMPED_P95_Q010_R16']
raw=read('forecasts.csv',EXP)
wide=raw[raw.h.gt(0)].pivot(index=['origin','h'],columns='model',values='yy_exante').reindex(columns=roster)
truth=raw.drop_duplicates(['origin','h']).set_index(['origin','h']).yy_actual
support=wide.notna().all(axis=1)&truth.reindex(wide.index).notna()
keys=wide.index[support]
assert sum(h==12 for _,h in keys)==75
head=read('output/independent_path_frozen_inputs.csv');head=head.set_index(head.columns[0]).headline_mm
head.index=pd.PeriodIndex(head.index,freq='M')
core=read('tests/fixtures/cleanup/cnb_core_mm.csv').set_index('period').core;core.index=pd.PeriodIndex(core.index,freq='M')
new=read('native_forecasts.csv',EXP);old=read('output/research_r15/native_forecasts.csv')
native=pd.concat([new[new.model.isin(models)],old[old.model.eq(models[0])]],ignore_index=True)
pred={(o,m):g.set_index('h') for (o,m),g in raw[raw.model.isin(models)].groupby(['origin','model'])}
paths={(o,m):g.set_index('h') for (o,m),g in native.groupby(['origin','model'])}
noncore=[c for c in native.columns if c.startswith('contribution_') and c!='contribution_core']
rows=[];monthly_error=0.
for origin,h in keys:
    op=pd.Period(origin,'M');window=pd.period_range(op+h-11,op+h,freq='M')
    for model in models:
        path=paths[(origin,model)];rp=pred[(origin,model)]
        oracle=[];forecast=[]
        for t in window:
            k=t.ordinal-op.ordinal
            if k<0:
                forecast.append(head[t]);oracle.append(head[t])
            elif k==0:
                forecast.append(rp.loc[0,'mm_forecast']);oracle.append(rp.loc[0,'mm_forecast'])
            else:
                row=path.loc[k]
                kept=float(row[noncore].sum(min_count=len(noncore)))
                assert np.isclose(kept,row.mm_forecast-row.contribution_core,atol=1e-14,rtol=0)
                assert np.isclose(row.contribution_core,row.weight_core*row.value_core,atol=1e-14,rtol=0)
                assert rp.loc[k,'mm_forecast']==row.mm_forecast
                forecast.append(rp.loc[k,'mm_forecast'])
                oracle.append(kept+row.weight_core*core[t])
        actual=head.reindex(window).to_numpy()
        assert np.isfinite([*forecast,*oracle,*actual]).all()
        # Products of gross factors provide an independent arithmetic route
        # from the production sum-of-log implementation.
        fg=np.prod(1+np.array(forecast)/100);og=np.prod(1+np.array(oracle)/100);ag=np.prod(1+actual/100)
        f,o,a=100*np.log(fg),100*np.log(og),100*np.log(ag)
        total=100*np.log(fg/ag);effect=100*np.log(fg/og);retained=100*np.log(og/ag)
        future=path.reindex(range(1,h+1));target=pd.period_range(op+1,op+h,freq='M')
        cg=np.prod(1+future.value_core.to_numpy()/100)/np.prod(1+core.reindex(target).to_numpy()/100)
        unweighted=100*np.log(cg)
        rows.append(dict(origin=origin,h=h,model=model,actual_annual_log=a,forecast_annual_log=f,oracle_annual_log=o,
            oracle_headline_yy=100*(og-1),total_error_log=total,core_effect_log=effect,retained_error_log=retained,
            core_cumulative_error_log=unweighted,h0_in_annual_window=op in window))
reference=pd.DataFrame(rows)
export=read('attribution.csv',ATTR);export=export[export.model.isin(models)]
key=['origin','h','model'];a=reference.set_index(key).sort_index();b=export.set_index(key).sort_index()
assert a.index.equals(b.index)
errors={}
for c in a:
    if c=='h0_in_annual_window':assert list(a[c])==list(b[c]);continue
    errors[c]=float(abs(a[c]-b[c]).max());assert errors[c]<3e-12,(c,errors[c])
assert reference[reference.h.eq(12)].h0_in_annual_window.eq(False).all()
assert reference[reference.h.lt(12)].h0_in_annual_window.eq(True).all()
spread=reference.groupby(['origin','h']).retained_error_log.agg(lambda x:x.max()-x.min()).max()
assert spread<3e-12
stats=[]
for model,g in reference[reference.h.eq(12)].groupby('model'):
    total=float(np.mean(g.total_error_log**2));ce=float(np.mean(g.core_effect_log**2));ret=float(np.mean(g.retained_error_log**2))
    cross=float(2*np.mean(g.core_effect_log*g.retained_error_log))
    twice_cov=float(2*np.mean((g.core_effect_log-g.core_effect_log.mean())*(g.retained_error_log-g.retained_error_log.mean())))
    stats.append(dict(model=model,n=len(g),total_rmse_annual_log_pp=np.sqrt(total),core_effect_mse_annual_log_pp_squared=ce,
        retained_mse_annual_log_pp_squared=ret,twice_uncentered_cross_moment=cross,total_mse_annual_log_pp_squared=total,
        identity_error=total-ce-ret-cross,unweighted_cumulative_core_rmse_log_pp=float(np.sqrt(np.mean(g.core_cumulative_error_log**2))),
        twice_centered_covariance=twice_cov,twice_product_of_biases=float(2*g.core_effect_log.mean()*g.retained_error_log.mean())))
stats=pd.DataFrame(stats)
assert stats.identity_error.abs().max()<3e-12
saved=read('scoreboard.csv',ATTR).query('sample == "full" and h == 12 and model in @models').set_index('model')
for r in stats.itertuples():
    expected=saved.loc[r.model]
    assert expected.n==r.n==75
    for x,y in [(r.total_rmse_annual_log_pp,expected.total_rmse_log),(r.core_effect_mse_annual_log_pp_squared,expected.core_effect_mse_log),
                (r.retained_mse_annual_log_pp_squared,expected.retained_mse_log),(r.twice_uncentered_cross_moment,expected.twice_core_retained_cross_moment),
                (r.unweighted_cumulative_core_rmse_log_pp,expected.core_cumulative_rmse_log)]:assert abs(x-y)<3e-12
reference[reference.h.eq(12)].to_csv(OUT/'h12_independent_rows.csv',index=False);stats.to_csv(OUT/'h12_independent_scoreboard.csv',index=False)
receipt=dict(verified_hashes=verified,models=models,original_all15_support_h12_n=75,rows_verified_all_horizons=len(reference),
    maximum_export_difference=max(errors.values()),maximum_retained_spread=float(spread),h0_window_flags_correct=True,
    maximum_h12_mean_square_identity_error=float(stats.identity_error.abs().max()),
    units='Annual-log headline percentage points; cross moment uncentered; weighted oracle effect distinct from unweighted core error.',
    status='passed')
(OUT/'audit_summary.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2));print(stats.to_string(index=False))
