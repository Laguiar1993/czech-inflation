"""Reweight saved outer quantiles only from predictions available at their origins."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'cz_struct.py').exists())
sys.path.insert(0,str(ROOT))
from models import paper_tvwqrf as en
out=[]
pred=[]
for run_name in ['paper_full_exact','paper_full_luci','realtime_full_luci','realtime_full_luci_month']:
    run=ROOT/'output/paper_tvwqrf_20260912'/run_name
    f=pd.read_csv(run/'forecasts.csv')
    f['edge']=pd.PeriodIndex(f.edge,freq='M')
    q=pd.read_csv(run/'quantiles.csv')
    q['edge']=pd.PeriodIndex(q.edge,freq='M')
    for h,g in q.groupby('horizon'):
        wide=g.pivot(index='edge',columns='quantile',values='value').sort_index()
        # CSV parsing changes 2/3 insignificant decimal, but TVW3 quantiles exact.
        quants,lo,hi=en.SCHEMES['TVW3']
        wide=wide[list(quants)]
        ft=f[(f.horizon==h)&(f.model=='TVW3')].set_index('edge')
        median=f[(f.horizon==h)&(f.model=='QRF_MEDIAN')].set_index('edge').forecast
        rows=[]
        for e in wide.index:
            vals=pd.period_range(e-h-11,e-h,freq='M')
            if not vals.isin(wide.index).all():
                continue
            yy=ft.reindex(vals).actual.to_numpy(float)
            if not np.isfinite(yy).all():
                continue
            w=en.solve_weights(wide.loc[vals].to_numpy(float),yy,lo,hi,en.kernel_weights(12))
            forecast=float(wide.loc[e].to_numpy(float)@w)
            rows.append({'run':run_name,'horizon':h,'edge':str(e),'original':float(ft.loc[e,'forecast']),
                         'causal':forecast,'actual':float(ft.loc[e,'actual']),'median':float(median.loc[e])})
        a=pd.DataFrame(rows)
        if len(a):
            result={'run':run_name,'horizon':int(h),'n':len(a),'first_edge':a.edge.min(),'last_edge':a.edge.max()}
            for model in ['original','causal','median']:
                result[model+'_rmse']=float(np.sqrt(np.mean((a[model]-a.actual)**2)))
            result['max_forecast_change']=float((a.causal-a.original).abs().max())
            out.append(result)
            pred.append(a)
pd.DataFrame(out).to_csv(HERE/'causal_reweight_scores.csv',index=False)
pd.concat(pred,ignore_index=True).to_csv(HERE/'causal_reweight_forecasts.csv',index=False)
print(pd.DataFrame(out).query('horizon in [3,6,9,12]').to_string(index=False))

import paper_tvwqrf_path as paths
from models.path_inputs import compound_path
predictions=pd.concat(pred,ignore_index=True)
headline=paths.headline_series()
hard=pd.read_csv(paths.NOWCAST).set_index('period').HARD_BASE
bridge=pd.read_csv(paths.BOARD_A)
bridge=bridge[bridge.model==paths.BASE][['origin','h','yy_exante']].rename(columns={'yy_exante':'bridge'})
path_out=[]
for run_name,score_dir in [('realtime_full_luci','path_scores_luci'),('realtime_full_luci_month','path_scores_luci_month')]:
    old=pd.read_csv(ROOT/'output/paper_tvwqrf_20260912'/score_dir/'board_a_forecasts.csv')
    model_name='TVWQRF_TVW3_FULLM' if 'month' in run_name else 'TVWQRF_TVW3_FULL'
    old=old[old.model==model_name].merge(bridge,on=['origin','h'],how='left')
    all_g=predictions[predictions.run==run_name].copy()
    all_g['origin']=(pd.PeriodIndex(all_g.edge,freq='M')+1).astype(str)
    all_g['path_h']=all_g.horizon-1
    new=[]
    for origin_text,g in old.groupby('origin'):
        origin=pd.Period(origin_text,freq='M')
        gg=all_g[all_g.origin==origin_text].set_index('path_h').causal
        path={k:gg.get(k,np.nan) for k in range(13)}
        for r in g.itertuples():
            if r.h in (1,3,6,9,12):
                causal_yy=compound_path(headline[headline.index<origin],path,origin,int(r.h),hard.get(origin_text,np.nan))
                new.append({'origin':origin_text,'h':r.h,'target':r.target,'actual':r.yy_actual,
                            'original':r.yy_exante,'causal':causal_yy,'bridge':r.bridge})
    pp=pd.DataFrame(new)
    for sample,mask in [('full',pd.Series(True,index=pp.index)),('recent_origins',pp.origin>='2024-01'),('recent_targets',pp.target>='2024-01')]:
        for h,g in pp[mask].groupby('h'):
            g=g.dropna(subset=['actual','original','causal','bridge'])
            r={'run':run_name,'sample':sample,'h':h,'n':len(g)}
            for model in ['original','causal','bridge']:
                r[model+'_rmse']=float(np.sqrt(np.mean((g[model]-g.actual)**2)))
            path_out.append(r)
pd.DataFrame(path_out).to_csv(HERE/'causal_reweight_path_scores.csv',index=False)
print(pd.DataFrame(path_out).query("sample=='full'").to_string(index=False))
