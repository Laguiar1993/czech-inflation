from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parents[2]
OUT=BASE/'output/review_r11/path'
OUT.mkdir(parents=True,exist_ok=True)
f=pd.read_csv(BASE/'output/independent_bridge_comparison_forecasts.csv')
f=f.loc[f.origin>='2019-02']
models=['INDEPENDENT_BRIDGE','TARGET_ML','TARGET_FX_ML','TARGET_U_FX_ML','BVAR_U_FX','RF_U_FX','NAIVE']
samples={'all':f,'recent_targets':f[f.target>='2024-01'],'recent_origins':f[f.origin>='2024-01'],'crisis_targets':f[(f.target>='2020-01')&(f.target<='2023-12')]}
scores=[]
for label,data in samples.items():
    for h,g in data[data.h>0].groupby('h'):
        w=g.pivot(index='origin',columns='model',values='yy_exante').reindex(columns=models)
        truth=g.drop_duplicates('origin').set_index('origin').yy_actual
        idx=w.index[np.isfinite(w).all(axis=1)&np.isfinite(truth.reindex(w.index))]
        for m in models:
            a=g[g.model==m].set_index('origin').loc[idx]
            e=a.yy_exante-a.yy_actual
            me=a.mm_forecast-a.mm_actual
            scores.append(dict(sample=label,h=h,model=m,n=len(idx),rmse=np.sqrt(np.mean(e**2)),mae=np.mean(abs(e)),bias=e.mean(),mm_rmse=np.sqrt(np.mean(me**2)),mm_bias=me.mean()))
s=pd.DataFrame(scores)
s.to_csv(OUT/'horizon_metrics.csv',index=False)
for label in samples:
    q=s[(s['sample']==label)&s.model.isin(['INDEPENDENT_BRIDGE','TARGET_ML','BVAR_U_FX','RF_U_FX','NAIVE'])]
    print(label+' RMSE')
    print(q.pivot(index='h',columns='model',values='rmse').round(4).to_string())
    print('BRIDGE COUNTS/BIASES '+q[q.model=='INDEPENDENT_BRIDGE'][['h','n','bias','mm_rmse','mm_bias']].round(4).to_json(orient='records'))

b=f[f.model=='INDEPENDENT_BRIDGE'].copy()
fixture=BASE/'tests/fixtures/cleanup'
def first(filename):
    return pd.read_csv(fixture/filename,index_col=0).iloc[:,0]
comp=pd.read_csv(fixture/'component_food_fuel_mm.csv',index_col=0)
actuals={'core':first('cnb_core_mm.csv'),'food':comp.food,'administered':first('cnb_regulated_mm.csv'),'alcohol_tobacco':first('alcohol_tobacco.csv'),'fuel':comp.fuel}
blocks=list(actuals)+['wedge']
for block,actual in actuals.items():
    wc='weight_'+('alc' if block=='alcohol_tobacco' else block)
    b['err_'+block]=b['contribution_'+block]-b[wc]*b.target.map(actual)
b['err_wedge']=(b.mm_forecast-b.mm_actual)-b[['err_'+z for z in actuals]].sum(axis=1,min_count=5)
attr=[]
for label,panel in [('all',b),('recent_targets',b[b.target>='2024-01']),('crisis_targets',b[(b.target>='2020-01')&(b.target<='2023-12')])]:
    for h,g in panel[panel.h>0].groupby('h'):
        g=g.dropna(subset=['err_'+z for z in blocks])
        e=g.mm_forecast-g.mm_actual
        for z in blocks:
            eb=g['err_'+z]
            attr.append(dict(sample=label,h=h,block=z,n=len(g),bias=eb.mean(),rmse=np.sqrt(np.mean(eb**2)),mse_allocation=np.mean(eb*e),total_mse=np.mean(e**2)))
a=pd.DataFrame(attr);a.to_csv(OUT/'bridge_block_errors.csv',index=False)
for label in ['all','recent_targets','crisis_targets']:
    print(label+' BLOCKS h1,3,6,12')
    print(a[(a['sample']==label)&a.h.isin([1,3,6,12])][['h','block','n','bias','rmse','mse_allocation']].round(5).to_string(index=False))
b['yy_error']=b.yy_exante-b.yy_actual
worst=b[(b.h==12)&b.yy_error.notna()].copy();worst['squared_error']=worst.yy_error**2
worst.sort_values('squared_error',ascending=False).to_csv(OUT/'h12_errors.csv',index=False)
print('WORST BRIDGE h12')
print(worst.sort_values('squared_error',ascending=False)[['origin','target','yy_exante','yy_actual','yy_error']].head(16).round(4).to_string(index=False))
print('RECENT TARGET BRIDGE h12')
print(worst[worst.target>='2024-01'][['origin','target','yy_exante','yy_actual','yy_error']].round(4).to_string(index=False))

p=pd.read_csv(BASE/'output/independent_path_parameters.csv');p=p[(p.origin>='2019-02')&(p.model=='TARGET_ML')]
print('TARGET_ML parameter quantiles');print(p[['level','gap','phi','rho','sd_eta','sd_eps','sd_e']].quantile([0,.25,.5,.75,1]).round(5).to_string())
print('TARGET_ML recent h12 starts');print(p[(p.origin>='2023-01')&(p.origin<='2024-07')][['origin','level','gap','phi','rho']].round(5).to_string(index=False))

# Exact additive error accounting in log space, allocated proportionally among
# component errors within each month. This diagnoses errors; it is not an ex-ante
# experiment, and does not attribute causal effects.
alloc=[]
for origin,g in b.groupby('origin'):
    g=g.set_index('h').reindex(range(1,13))
    if not np.isfinite(g[['mm_forecast','mm_actual','yy_exante','yy_actual']]).all().all():continue
    predicted=g.mm_forecast.to_numpy(); realised=g.mm_actual.to_numpy()
    delta=predicted-realised
    ld=np.log1p(predicted/100)-np.log1p(realised/100)
    monthly_factor=np.divide(ld,delta,out=1/(100+realised),where=np.abs(delta)>1e-12)
    yy_error=float(g.loc[12,'yy_exante']-g.loc[12,'yy_actual'])
    annual_factor=yy_error/ld.sum() if abs(ld.sum())>1e-12 else 100*np.exp(np.log1p(realised/100).sum())
    pieces={z:float((g['err_'+z].to_numpy()*monthly_factor).sum()*annual_factor) for z in blocks}
    assert abs(sum(pieces.values())-yy_error)<1e-10,(origin,pieces,yy_error)
    alloc.append(dict(origin=origin,target=g.loc[12,'target'],yy_error=yy_error,**pieces))
aa=pd.DataFrame(alloc);aa.to_csv(OUT/'h12_log_error_allocation.csv',index=False)
for label,sub in [('all',aa),('recent_targets',aa[aa.target>='2024-01']),('recent_origins',aa[aa.origin>='2024-01']),('crisis_targets',aa[(aa.target>='2020-01')&(aa.target<='2023-12')])]:
    print(label+' H12 EXACT LOG-SPACE ERROR ALLOCATION N='+str(len(sub)))
    print(pd.DataFrame({'bias':sub[blocks].mean(),'rmse':np.sqrt((sub[blocks]**2).mean()),'mse_allocation':sub[blocks].mul(sub.yy_error,axis=0).mean()}).round(5).to_string())

for label,panel in [('all',b),('recent_targets',b[b.target>='2024-01'])]:
    for h in [1,3,6,12]:
        g=panel[(panel.h==h)&panel.mm_forecast.notna()&panel.mm_actual.notna()].copy()
        g['se']=(g.mm_forecast-g.mm_actual)**2;g['month']=g.target.str[-2:]
        print(label+' h'+str(h)+' monthly MSE shares '+(g.groupby('month').se.sum()/g.se.sum()).round(4).to_json())

worst=worst.sort_values('squared_error',ascending=False)
print('h12 top4/top12 MSE shares',float(worst.squared_error.head(4).sum()/worst.squared_error.sum()),float(worst.squared_error.head(12).sum()/worst.squared_error.sum()))
qs=pd.read_csv(BASE/'output/independent_bridge_cnb_summary.csv')
print('CNB quarter ahead comparison')
print(qs[(qs.scope=='including_references')&qs.model.isin(['INDEPENDENT_BRIDGE','CNB','SURVEY_TREND_STORED_REF'])][['sample','quarters_ahead','model','n_report_quarter_pairs','rmse','mae','bias']].round(5).to_string(index=False))

stored=pd.read_csv(BASE/'output/independent_bridge_summary.csv')
mapping={'all':'2019_plus','recent_targets':'2024_plus_targets','crisis_targets':'crisis_2020_2023_targets'}
max_score_diff=0.
for row in s[s['sample'].isin(mapping)&s.h.isin([1,3,6,12])].itertuples():
    saved=stored[(stored.scope=='independent_plus_bridge')&(stored['sample']==mapping[row.sample])&(stored['case']=='exante')&(stored.h==row.h)&(stored.model==row.model)].iloc[0]
    assert row.n==saved.n_common
    max_score_diff=max(max_score_diff,abs(row.rmse-saved.yy_rmse),abs(row.bias-saved.yy_bias),abs(row.mae-saved.yy_mae))
assert max_score_diff<1e-12
assert not f.duplicated(['origin','model','h']).any()
assert (f.groupby(['origin','model']).h.nunique()==13).all()
assert np.allclose(f[f.h==0].mm_forecast,f[f.h==0].h0_exante)
assert np.allclose(f[f.h==12].yy_exante,f[f.h==12].yy_conditional,equal_nan=True)
cnbq=pd.read_csv(BASE/'output/independent_bridge_cnb_quarters.csv')
assert (pd.to_datetime(cnbq.as_of_utc,utc=True)<pd.to_datetime(cnbq.report_clock_utc,utc=True)).all()
receipt={'status':'passed','matched_saved_summary_max_abs_difference':max_score_diff,'summary_rows_verified':len(s[s['sample'].isin(mapping)&s.h.isin([1,3,6,12])]),'h0_equality':True,'h12_conditional_equality':True,'unique_keys':True,'thirteen_points_per_path':True,'cnb_strict_prepublication_clocks':True,'annual_error_allocation_identity_tolerance':1e-10,'model_fits_run':0,'forecasting_model_changes':0,'runtime':{'pandas':pd.__version__,'numpy':np.__version__}}
(OUT/'validation.json').write_text(json.dumps(receipt,indent=2))
print('VALIDATION',receipt)

# Cheap omitted-benchmark diagnostic: last RELEASED YoY, held flat. It has no
# common independent h0 replacement, so stays outside the official roster.
y=pd.read_csv(BASE/'output/independent_path_frozen_inputs.csv',index_col=0).headline_mm
y.index=pd.PeriodIndex(y.index,freq='M')
released_yy=100*((1+y/100).rolling(12).apply(np.prod,raw=True)-1)
rw=[]
for label,data in samples.items():
    for h,g in data[data.h>0].groupby('h'):
        w=g.pivot(index='origin',columns='model',values='yy_exante').reindex(columns=models)
        truth=g.drop_duplicates('origin').set_index('origin').yy_actual
        idx=w.index[np.isfinite(w).all(axis=1)&np.isfinite(truth.reindex(w.index))]
        pred=released_yy.reindex(pd.PeriodIndex(idx,freq='M')-1).to_numpy()
        error=pred-truth.reindex(idx).to_numpy()
        rw.append(dict(sample=label,h=h,n=len(idx),model='LAST_RELEASED_YY_RW',rmse=np.sqrt(np.mean(error**2)),mae=np.mean(abs(error)),bias=np.mean(error)))
rr=pd.DataFrame(rw);rr.to_csv(OUT/'omitted_rw_benchmark.csv',index=False)
print('OMITTED LAST RELEASED YY RW benchmark')
print(rr[rr.h.isin([1,3,6,12])].round(5).to_string(index=False))
input_names = [
    'output/independent_bridge_comparison_forecasts.csv',
    'output/independent_path_parameters.csv', 'output/independent_path_frozen_inputs.csv',
    'output/independent_bridge_summary.csv', 'output/independent_bridge_cnb_summary.csv',
    'output/independent_bridge_cnb_quarters.csv', 'output/independent_bridge_forecasts.csv',
    'output/independent_path_forecasts.csv', 'tools/r11_review/path_review.py',
    *['tests/fixtures/cleanup/'+name for name in ('cnb_core_mm.csv',
       'component_food_fuel_mm.csv','cnb_regulated_mm.csv','alcohol_tobacco.csv')],
]
hashes={name:hashlib.sha256((BASE/name).read_bytes()).hexdigest() for name in input_names}
(OUT/'manifest.json').write_text(json.dumps({'inputs':hashes,'outputs':{
    p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob('*.csv'))}},indent=2))
