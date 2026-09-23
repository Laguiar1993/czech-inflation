"""Frozen R21 next-release point experiment. No consensus enters estimation."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from quantile_forest import RandomForestQuantileRegressor
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from models.independent_nowcast import policy_frame
from models.released_error_research_r21 import offset_prediction


def main():
    import cz_struct as s
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    files=['output/independent_nowcast_forecasts.csv','output/independent_nowcast_hard_errors.csv',
           'tests/fixtures/cleanup/core_features.csv','work/model_briefing_20260914/nowcast_release_evidence.csv',
           'data/release_calendar_cz_cpi.csv','models/released_error_research_r21.py','models/independent_nowcast.py',
           'cz_struct.py','config.py','docs/implementation/R21_RESEARCH_SPEC_2026-09-15.md',Path(__file__).relative_to(ROOT).as_posix()]
    hashes={p:c.sha(ROOT/p) for p in files}
    base=c.monthly(files[0]);errors=c.monthly(files[1]).iloc[:,0]
    x=policy_frame(c.monthly(files[2]),'hard')
    evidence=c.read(files[3]);ev=evidence[evidence.model.eq('HARD_BASE')].set_index('period')
    ev.index=pd.PeriodIndex(ev.index,freq='M');ev=ev.reindex(base.index)
    if len(ev)!=90 or ev.actual.isna().any() or not ev.index.is_unique:raise ValueError('Invalid first-release support')
    cal=c.monthly(files[4]);first=pd.to_datetime(cal.first_release_dt);detail=pd.to_datetime(cal.detail_release_dt)
    # Freeze each feature row at that row's own original decision, including pre-2019 core errors.
    decisions={}
    for m in sorted(set(errors.index)|set(base.index)):
        if m in base.index:clock=pd.Timestamp(base.loc[m,'as_of_eve'])
        else:
            released=s._first_release_dt(m)
            if pd.isna(released):released=(m+1).to_timestamp()+pd.Timedelta(days=19,hours=9)
            clock=released-pd.Timedelta(days=1)
        decisions[m]=clock
        x=s._mask_row_by_availability(x,m,clock)
    # Label creation sees actuals; consuming functions gate each label by its publication.
    labels=ev.actual-base.HARD_BASE
    hx=x.reindex(base.index).copy();hx['base_forecast']=base.HARD_BASE
    for m in base.index:
        past=labels[(labels.index<m)&first.reindex(labels.index).le(decisions[m]).to_numpy()].dropna()
        hx.loc[m,'released_headline_error_last']=past.iloc[-1] if len(past) else np.nan
        hx.loc[m,'released_headline_error_last3']=past.tail(3).mean()
    rows=[];diagnostics=[]
    for i,m in enumerate(base.index):
        clock=decisions[m];values={name:float(base.loc[m,name]) for name in ['HARD_BASE','HARD_HALF','HARD_FULL']}
        for kind in ['mean','enet']:
            info=offset_prediction(hx,labels,first,m,clock,kind)
            name='HEADLINE_'+kind.upper()+'_R21';values[name]=values['HARD_BASE']+info['correction']
            diagnostics.append(dict(origin=str(m),model=name,as_of=clock.isoformat(),**info))
        eligible=errors[(errors.index<m)&detail.reindex(errors.index).le(clock).to_numpy()].dropna()
        for kind in ['mean','median']:
            correction=0.
            if len(eligible)>=40:
                xp=x.loc[eligible.index].astype(float);mu=xp.mean().fillna(0.);xp=xp.fillna(mu)
                now=x.loc[[m]].fillna(mu)
                options=dict(n_estimators=200,min_samples_leaf=8,max_features=1.,random_state=42,n_jobs=2)
                forest=(RandomForestRegressor if kind=='mean' else RandomForestQuantileRegressor)(**options)
                forest.fit(xp,eligible.to_numpy(float))
                correction=float(forest.predict(now,**({'quantiles':.5} if kind=='median' else {}))[0])
            name='CORE_RF_'+kind.upper()+'_R21';values[name]=values['HARD_BASE']+base.loc[m,'coreweight']*correction
            diagnostics.append(dict(origin=str(m),model=name,as_of=clock.isoformat(),correction=correction,n=len(eligible),
                last_release=detail.reindex(eligible.index).max().isoformat() if len(eligible) else None,
                train_origins='|'.join(map(str,eligible.index)),status='estimated' if len(eligible)>=40 else 'warmup'))
        # Benchmark fields are attached AFTER every model prediction has been computed.
        for model,point in values.items():rows.append(dict(origin=str(m),as_of=clock.isoformat(),model=model,forecast=point,
            actual=ev.loc[m,'actual'],consensus=ev.loc[m,'consensus'],release_kind=ev.loc[m,'release_kind']))
        if i%15==0:print(f'Nowcast {i+1}/90',flush=True)
    pd.DataFrame(rows).to_csv(out/'predictions.csv',index=False)
    pd.DataFrame(diagnostics).to_csv(out/'training.csv',index=False)
    hx.to_csv(out/'headline_features.csv');x.to_csv(out/'core_features_at_decision.csv')
    c.finish(out,hashes,models=sorted(set(r['model'] for r in rows)),notes='Four fixed research candidates; benchmark attached after prediction.')
    print('Finished',out,flush=True)


if __name__=='__main__':main()
