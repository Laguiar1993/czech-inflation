"""Independent core-turn, CNB and first-stage outcome calculations."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'evaluation';OUT.mkdir(exist_ok=True)
EXP=ROOT/'output/research_r16';EV=EXP/'evaluation'
read=lambda name,base=ROOT:pd.read_csv(base/name,float_precision='round_trip')
manifest=json.loads((EXP/'manifest.json').read_text());roster=manifest['controls']+manifest['models']
frame=read('forecasts.csv',EXP);states=json.loads((EXP/'states.json').read_text())
core=read('tests/fixtures/cleanup/cnb_core_mm.csv').set_index('period').core
core.index=pd.PeriodIndex(core.index,freq='M');corelog=100*np.log1p(core/100)
source=read('output/independent_path_frozen_inputs.csv');headline=source.set_index(source.columns[0]).headline_mm
headline.index=pd.PeriodIndex(headline.index,freq='M')
actualyy=100*np.expm1(np.log1p(headline/100).rolling(12).sum())
newcore=read('core_predictions.csv',EXP)[['origin','h','model','core_log']]
oldcore=read('output/research_r15/evaluation/forecast_core_outcomes.csv')
oldcore=oldcore[oldcore.model.isin(manifest['controls'])&oldcore.h.gt(0)]
oldcore=oldcore.assign(core_log=100*np.log1p(oldcore.core_mm_forecast/100))[newcore.columns]
combined=pd.concat([newcore,oldcore],ignore_index=True)
bands=[];turns=[]
def classify(a,b,c):
    if not np.isfinite([a,b,c]).all():return None
    d1,d2=b-a,c-b
    if d1>=.5-1e-12 and d2<=-.5+1e-12:return 'peak'
    if d1<=-.5+1e-12 and d2>=.5-1e-12:return 'trough'
    return 'none'
for (origin,model),rows in combined.groupby(['origin','model']):
    op=pd.Period(origin,'M');ref=states[origin]['seasonal'];path=rows.set_index('h').core_log
    values=[]
    for b in range(1,5):
        hs=list(range(3*b-2,3*b+1));months=[op+h for h in hs]
        season=np.array([ref[str(t.month)] for t in months])
        predictions=path.reindex(hs).to_numpy()-season;truth=corelog.reindex(months).to_numpy()-season
        pred=float(12*predictions.mean()) if np.isfinite(predictions).all() else np.nan
        actual=float(12*truth.mean()) if np.isfinite(truth).all() else np.nan
        values.append((pred,actual));bands.append(dict(origin=origin,model=model,band=b,target=str(op+3*b),predicted_sa_annualized=pred,actual_sa_annualized=actual))
    for b in [2,3]:
        pp=classify(*[values[i][0] for i in [b-2,b-1,b]])
        aa=classify(*[values[i][1] for i in [b-2,b-1,b]])
        eligible=pp is not None and aa is not None;hit=eligible and aa!='none' and pp==aa
        turns.append(dict(origin=origin,model=model,band=b,target=str(op+3*b),predicted_turn=pp,actual_turn=aa,eligible=eligible,
            exact_hit=hit,missed_turn=eligible and aa!='none' and not hit,false_turn=eligible and pp!='none' and not hit))
bands=pd.DataFrame(bands);turns=pd.DataFrame(turns)
bands.to_csv(OUT/'reference_core_bands.csv',index=False);turns.to_csv(OUT/'reference_core_turns.csv',index=False)
common=turns[turns.eligible].groupby(['origin','band']).model.nunique();keys=common[common.eq(len(roster))].index
scored=turns.set_index(['origin','band']).loc[lambda z:z.index.isin(keys)].reset_index()
summary=[]
for sample,cut in [('full',scored),('origins_2024plus',scored[scored.origin.ge('2024-01')])]:
    for model,g in cut.groupby('model'):
        summary.append(dict(sample=sample,model=model,n=len(g),actual_turns=int(g.actual_turn.ne('none').sum()),
            predicted_turns=int(g.predicted_turn.ne('none').sum()),exact_band_hits=int(g.exact_hit.sum()),
            false_turns=int(g.false_turn.sum()),missed_turns=int(g.missed_turn.sum())))
pd.DataFrame(summary).to_csv(OUT/'reference_turn_summary.csv',index=False)

clocksource=pd.to_datetime(frame.drop_duplicates('origin').set_index('origin').as_of_utc,utc=True)
cnb=read('data/cnb_mpr_cpi_quarterly.csv');cnb=cnb[cnb.is_forecast.astype(str).str.lower().eq('true')&cnb.report_date.ge('2022-01-01')]
paths={(o,m):dict(zip(g.target,g.yy_exante)) for (o,m),g in frame.groupby(['origin','model'])}
clocks=[];pairs=[];coverage=[]
for (report,cutoff),g in cnb.groupby(['report_date','cutoff_date']):
    for mode,day in [('report',report),('cutoff',cutoff)]:
        boundary=(pd.Timestamp(day)+pd.Timedelta(days=int(mode=='cutoff'))).tz_localize('Europe/Prague').tz_convert('UTC')
        visible=clocksource[clocksource<boundary].sort_values();origin=visible.index[-1] if len(visible) else None
        clocks.append(dict(clock=mode,report_date=report,cutoff_date=cutoff,origin=origin,as_of_utc=str(visible.iloc[-1]) if len(visible) else None))
        op=pd.Period(origin,'M') if origin else None
        for row in g.itertuples():
            q=pd.Period(row.quarter,'Q');months=pd.period_range(q.asfreq('M','start'),q.asfreq('M','end'),freq='M')
            vv=actualyy.reindex(months).to_numpy();actual=float(vv.mean()) if np.isfinite(vv).all() else np.nan
            predicted={}
            for model in roster:
                path=paths.get((origin,model),{})
                monthly=np.array([actualyy.get(t,np.nan) if op and t<op else path.get(str(t),np.nan) for t in months])
                predicted[model]=float(monthly.mean()) if np.isfinite(monthly).all() else np.nan
            included=np.isfinite([actual,row.value,*predicted.values()]).all()
            coverage.append(dict(clock=mode,report_date=report,quarter=row.quarter,included=included))
            if not included:continue
            for model,pred in {**predicted,'cnb':row.value}.items():
                gain=abs(row.value-actual)-abs(pred-actual)
                pairs.append(dict(clock=mode,report_date=report,quarter=row.quarter,origin=origin,model=model,
                    forecast=pred,realised=actual,error=pred-actual,realised_cnb_error=actual-row.value,
                    abs_error_gain_vs_cnb=gain,squared_error_gain_vs_cnb=(actual-row.value)**2-(pred-actual)**2,
                    material_gain=gain>=.15-1e-12,material_loss=gain<=-.15+1e-12))
pairs=pd.DataFrame(pairs);pairs.to_csv(OUT/'reference_cnb_pairs.csv',index=False)
pd.DataFrame(clocks).to_csv(OUT/'reference_cnb_clocks.csv',index=False);pd.DataFrame(coverage).to_csv(OUT/'reference_cnb_coverage.csv',index=False)
stats=[];omissions=[]
for sample,d in [('full',pairs),('reports_2024plus',pairs[pairs.report_date.ge('2024-01-01')])]:
    for (clock,model),g in d.groupby(['clock','model']):
        stats.append(dict(sample=sample,clock=clock,model=model,n=len(g),mae=float(abs(g.error).mean()),rmse=float(np.sqrt((g.error**2).mean())),
            material_gains=int(g.material_gain.sum()),material_losses=int(g.material_loss.sum()),report_count=g.report_date.nunique()))
        for date in sorted(g.report_date.unique()):
            cut=g[g.report_date.ne(date)]
            omissions.append(dict(sample=sample,clock=clock,model=model,omitted_report=date,n=len(cut),
                mae=float(abs(cut.error).mean()),rmse=float(np.sqrt((cut.error**2).mean())),cnb_mae=float(abs(cut.realised_cnb_error).mean()),
                cnb_rmse=float(np.sqrt((cut.realised_cnb_error**2).mean()))))
pd.DataFrame(stats).to_csv(OUT/'reference_cnb_summary.csv',index=False);pd.DataFrame(omissions).to_csv(OUT/'reference_cnb_leave_one_report_out.csv',index=False)
focus=['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16','DAMPED_P95_Q010_R16','DAMPED_ADAPT_R16','TRANSMISSION_BOTH_R16','cnb']
print('Underlying core turns:')
print(pd.DataFrame(summary).query('sample == "full" and model in @focus').to_string(index=False))
print('CNB comparisons:')
print(pd.DataFrame(stats).query('clock == "report" and model in @focus').to_string(index=False))
