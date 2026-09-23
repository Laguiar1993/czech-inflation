"""Ex-post accounting diagnostics, never an available forecast candidate."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c


def main():
    root=ROOT/'output/research_r22/full';out=ROOT/'output/research_r22/diagnostics'
    actual=c.monthly('output/research_r14b/attribution/actual_component_targets.csv','core')
    base=c.read('output/research_r22/full/native_forecasts.csv').query("model=='STATE_FAST_R15'")
    paths=[]
    for origin,g in base.groupby('origin'):
        t=pd.Period(origin,'M')
        rates={h:actual.get(t+h,np.nan) for h in range(1,13)}
        z=c.replace_block(g,'core',rates);z['model']='EX_POST_CORE_TRUTH_ACCOUNTING_ONLY';paths.append(z)
    oracle=c.compound(pd.concat(paths)).rename(columns={'yy_exante':'ex_post_core_truth_yy'})
    p=pd.read_csv(root/'evaluation/primary_rows.csv')
    p=p.merge(oracle[['origin','h','ex_post_core_truth_yy']],on=['origin','h'],validate='many_to_one')
    p=p.dropna(subset=['ex_post_core_truth_yy','yy_actual','yy_exante'])
    p['other_error']=p.ex_post_core_truth_yy-p.yy_actual
    p['core_difference']=p.yy_exante-p.ex_post_core_truth_yy
    p['headline_error']=p.yy_exante-p.yy_actual
    np.testing.assert_allclose(p.headline_error,p.other_error+p.core_difference,atol=1e-12)
    summaries=[]
    for (model,h),g in p.groupby(['model','h']):
        for sample,z in [('full',g),('origins_2024plus',g[g.origin.ge('2024-01')])]:
            other=(z.other_error**2).mean();core=(z.core_difference**2).mean()
            cross=2*(z.other_error*z.core_difference).mean();mse=(z.headline_error**2).mean()
            np.testing.assert_allclose(mse,other+core+cross,atol=1e-10)
            summaries.append(dict(model=model,h=h,sample=sample,n=len(z),headline_mse=mse,
                                  other_mse=other,core_difference_mse=core,cross_term=cross))
    p.to_csv(out/'ex_post_error_accounting_pairs.csv',index=False)
    pd.DataFrame(summaries).to_csv(out/'ex_post_error_accounting_summary.csv',index=False)
    d=pd.read_csv(root/'driver_forecasts.csv');checks=[]
    prices=['fx','brent','metals','ppi','imports']
    for (model,variable,h),g in d[d.variable.isin(prices)].groupby(['model','variable','h']):
        for sample,z in [('full',g),('origins_2024plus',g[g.origin.ge('2024-01')])]:
            z=z.dropna(subset=['actual','forecast'])
            checks.append(dict(model=model,variable=variable,h=h,sample=sample,n=len(z),
                rmse=np.sqrt(((z.forecast-z.actual)**2).mean()),zero_change_rmse=np.sqrt((z.actual**2).mean())))
    pd.DataFrame(checks).to_csv(out/'driver_zero_change_benchmark.csv',index=False)
    c.dump(out/'accounting_method.json',dict(status='post-score explanation, not a feasible forecast or trading strategy',
        identity='headline error = other_error + core_difference; MSE = other MSE + core difference MSE + 2 mean(other_error*core_difference)',
        other_error='Headline error after replacing h1..h12 core by realised core while preserving fixed h0, noncore blocks and basket approximation.',
        caveat='Core difference is its exact compounded annual effect relative to that oracle, not an official additive CNB contribution. All models have identical oracle.',
        drivers='Zero change is a fixed level benchmark for FX, Brent, metals, PPI and imports, not a persistent monthly growth forecast.'))
    print(pd.DataFrame(summaries).query("h==12 and sample=='full'").round(4).to_string(index=False))


if __name__=='__main__':main()
