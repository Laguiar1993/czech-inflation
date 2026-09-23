"""Independent offline recomputation of September 14 nowcast review claims.

Run using Python with numpy/pandas/statsmodels. Reads source data; writes only here.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p / 'cz_struct.py').exists())
REL = REPO / 'output/independent_nowcast_releases.csv'
d = pd.read_csv(REL)
assert not d.duplicated(['model','period']).any()
assert d[['actual','consensus','forecast']].notna().all().all()
assert (d.groupby('period').actual.nunique() == 1).all()
assert (d.groupby('period').consensus.nunique() == 1).all()
d['error'] = d.forecast-d.actual
d['surprise'] = d.actual-d.consensus
d['deviation'] = d.forecast-d.consensus
d['gain'] = d.surprise.abs()-d.error.abs()
d['big'] = d.surprise.abs() >= .4-1e-9
d['alert'] = d.deviation.abs() >= .2-1e-9
rmse = lambda x: float(np.sqrt(np.mean(np.square(x))))

rows=[]
for model,g in d.groupby('model'):
    masks={'all':g.period.notna(),'2019-21':g.period<'2022-01',
           '2022-23':(g.period>='2022-01')&(g.period<'2024-01'),
           '2024+':g.period>='2024-01','flash2025+':g.period>='2025-01',
           'big':g.big,'big2024+':g.big&(g.period>='2024-01'),
           'big2025+':g.big&(g.period>='2025-01'),
           'ex_jan':~g.period.str.endswith('-01'),
           'big_ex_jan':g.big&~g.period.str.endswith('-01'),'alerts':g.alert}
    for frame,mask in masks.items():
        z=g[mask]
        rows.append(dict(model=model,frame=frame,n=len(z),rmse=rmse(z.error),
            mae=z.error.abs().mean(),bias=z.error.mean(),consensus_rmse=rmse(z.surprise),
            consensus_mae=z.surprise.abs().mean(),mean_gain=z.gain.mean(),total_gain=z.gain.sum(),
            closer=int((z.gain>1e-9).sum()),material_win=int((z.gain>=.15-1e-9).sum()),
            material_loss=int((z.gain<=-.15+1e-9).sum()),
            direction=int((z.deviation*z.surprise>0).sum()),
            alerts=int(z.alert.sum()),alerted_big=int((z.alert&z.big).sum()),
            false_alarm=int((z.alert&~z.big).sum()),missed_big=int((~z.alert&z.big).sum()),
            big_precision=(z.alert&z.big).sum()/z.alert.sum() if z.alert.sum() else np.nan,
            big_recall=(z.alert&z.big).sum()/z.big.sum() if z.big.sum() else np.nan))
board=pd.DataFrame(rows)
board.to_csv(OUT/'recomputed_scores.csv',index=False)
old=pd.read_csv(REPO/'output/independent_nowcast_scores.csv').set_index(['model','frame'])
new=board.set_index(['model','frame']).reindex(old.index)[old.columns]
assert np.allclose(new,old,equal_nan=True,atol=1e-12)

regressions=[]
shrinks=[]
shrink_scores=[]
loss_tests=[]
loo=[]
for model in ['HARD_BASE','HARD_HALF','HARD_FULL','LEGACY_BASE']:
    g=d[d.model==model].sort_values('period').reset_index(drop=True)
    for frame,z in [('all',g),('2024+',g[g.period>='2024-01']),('2025+',g[g.period>='2025-01'])]:
        ols=sm.OLS(z.surprise,sm.add_constant(z.deviation)).fit()
        for covariance in ['ordinary','HC3','HAC3','HAC6']:
            reg=ols if covariance=='ordinary' else ols.get_robustcov_results(
                cov_type='HC3' if covariance=='HC3' else 'HAC',
                **({} if covariance=='HC3' else {'maxlags':int(covariance[-1]),'use_correction':True}))
            regressions.append(dict(model=model,frame=frame,covariance=covariance,n=len(z),
                intercept=float(reg.params[0]),slope=float(reg.params[1]),t=float(reg.tvalues[1]),
                p=float(reg.pvalues[1]),lower=float(reg.conf_int()[1,0]) if not isinstance(reg.conf_int(),pd.DataFrame) else float(reg.conf_int().iloc[1,0]),
                upper=float(reg.conf_int()[1,1]) if not isinstance(reg.conf_int(),pd.DataFrame) else float(reg.conf_int().iloc[1,1]),r2=float(reg.rsquared)))
        diff=(z.error**2-z.surprise**2).to_numpy()
        ld=sm.OLS(diff,np.ones((len(z),1))).fit()
        for lag in [0,3,6]:
            test=ld if lag==0 else ld.get_robustcov_results(cov_type='HAC',maxlags=lag,use_correction=True)
            loss_tests.append(dict(model=model,frame=frame,n=len(z),lag=lag,mean_loss_difference=diff.mean(),t=float(test.tvalues[0]),p=float(test.pvalues[0])))
        for i in z.index:
            v=z.drop(index=i)
            loo.append(dict(model=model,frame=frame,removed=g.loc[i,'period'],rmse_model=rmse(v.error),rmse_consensus=rmse(v.surprise),
                            model_minus_consensus=rmse(v.error)-rmse(v.surprise)))
    for i in range(len(g)):
        if g.loc[i,'period']<'2021-02':continue
        past=g.iloc[:i]
        x=past.deviation.to_numpy();y=past.surprise.to_numpy()
        b=float(x@y/(x@x)) if len(past)>=12 and x@x>0 else 0.
        r=g.loc[i]
        shrinks.append(dict(model=model,period=r.period,n_training=len(past),last_training=past.period.max(),b=b,
            actual=r.actual,consensus=r.consensus,forecast=r.forecast,
            shrink=r.consensus+b*r.deviation))
o=pd.DataFrame(shrinks)
for model,g in o.groupby('model'):
    for frame,z in [('all',g),('2024+',g[g.period>='2024-01']),('2025+',g[g.period>='2025-01']),
                     ('big_correct',g[(g.actual-g.consensus).abs()>=.4-1e-9]),
                     ('big_script',g[(g.actual-g.consensus).abs()>=.4])]:
        shrink_scores.append(dict(model=model,frame=frame,n=len(z),consensus_rmse=rmse(z.consensus-z.actual),
            shrink_rmse=rmse(z.shrink-z.actual),model_rmse=rmse(z.forecast-z.actual),
            consensus_mae=(z.consensus-z.actual).abs().mean(),shrink_mae=(z.shrink-z.actual).abs().mean(),
            model_mae=(z.forecast-z.actual).abs().mean()))
pd.DataFrame(regressions).to_csv(OUT/'surprise_regressions.csv',index=False)
pd.DataFrame(loss_tests).to_csv(OUT/'paired_loss_tests.csv',index=False)
o.to_csv(OUT/'shrink_predictions.csv',index=False)
pd.DataFrame(shrink_scores).to_csv(OUT/'shrink_scores.csv',index=False)
pd.DataFrame(loo).to_csv(OUT/'leave_one_out.csv',index=False)

selected=d[d.model.isin(['HARD_BASE','HARD_HALF','HARD_FULL','LEGACY_BASE'])].copy()
selected[(selected.gain.abs()>=.15-1e-9)|selected.big|selected.alert].to_csv(OUT/'material_and_alert_events.csv',index=False)
summary={'source_sha256':hashlib.sha256(REL.read_bytes()).hexdigest(),
         'source_rows':len(d),'source_models':d.model.unique().tolist(),
         'scoreboard_all_cells_match':True,
         'sample':[d.period.min(),d.period.max()],
         'source_scoreboard_sha256':hashlib.sha256((REPO/'output/independent_nowcast_scores.csv').read_bytes()).hexdigest()}
g=d[d.model=='HARD_BASE'].copy();g['sq_error']=g.error**2
top=g.nlargest(3,'sq_error')
summary['top3_error_months']=top[['period','error','sq_error']].to_dict('records')
summary['top3_share_all_sse']=top.sq_error.sum()/g.sq_error.sum()
shock=g[g.period.isin(['2022-01','2022-10','2023-01'])]
summary['energy_shocks']=shock[['period','error','sq_error']].to_dict('records')
summary['energy_shocks_share_all_sse']=shock.sq_error.sum()/g.sq_error.sum()
summary['energy_shocks_share_2022_23_sse']=shock.sq_error.sum()/g.loc[(g.period>='2022-01')&(g.period<'2024-01'),'sq_error'].sum()
summary['strict_threshold_excluded']=g[(g.surprise.abs()>=.4-1e-9)&(g.surprise.abs()<.4)][['period','actual','consensus','surprise']].to_dict('records')
summary['recent_false_alerts']=selected[(selected.period>='2024-01')&selected.alert&~selected.big][['model','period','actual','consensus','forecast','surprise','deviation','gain']].to_dict('records')
summary['recent_big']=selected[(selected.period>='2024-01')&selected.big][['model','period','actual','consensus','forecast','surprise','deviation','gain','alert']].to_dict('records')
(OUT/'audit_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
print(board[board.model.isin(['HARD_BASE','HARD_HALF','HARD_FULL','LEGACY_BASE','CONSENSUS'])&board.frame.isin(['all','2024+','flash2025+','big','big2024+'])].to_string(index=False))
print(pd.DataFrame(shrink_scores).to_string(index=False))
