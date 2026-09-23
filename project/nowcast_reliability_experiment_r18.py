"""Freeze independent points and test sequential error laws and all-alert outcomes."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import r17_common as c
from models import nowcast_reliability_r18 as e

MODELS=['HARD_BASE','HARD_HALF','HARD_FULL','CATEGORY_RAW']
FAMILIES=['POOLED','SCALE','STATE']


def summarize(rows):
    records=[]
    for (model,family),z in rows.groupby(['model','family']):
        masks={'all':np.ones(len(z),bool),'2024+':z.origin.ge('2024-01'),
               'flash':z.release_kind.eq('flash'),'january':z.origin.str.endswith('-01'),
               'ex_january':~z.origin.str.endswith('-01'),'big':z.big}
        for frame,mask in masks.items():
            a=z.loc[mask];n=len(a)
            records.append(dict(model=model,family=family,frame=frame,n=n,rmse=np.sqrt(np.mean(a.error**2)),
                mae=a.error.abs().mean(),survey_mae=a.surprise.abs().mean(),crps=a.crps.mean(),
                coverage80=a.cover80.mean(),coverage90=a.cover90.mean(),width80=(a.hi80-a.lo80).mean(),
                width90=(a.hi90-a.lo90).mean(),brier_material=((a.p_material_gain-a.material_win)**2).mean(),
                brier_big=((a.p_big-a.big)**2).mean()))
    return pd.DataFrame(records)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=c.ROOT/'output/research_r18_nowcast');args=p.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    names=['work/model_briefing_20260914/nowcast_release_evidence.csv','output/research_r15/states.json',
           'data/release_calendar_cz_cpi.csv','docs/implementation/R18_NOWCAST_SPEC_2026-09-15.md',
           'models/nowcast_reliability_r18.py','nowcast_reliability_experiment_r18.py']
    hashes={name:c.sha(c.ROOT/name) for name in names};hashes.update(c.preserved_hashes())
    c.dump(out/'declaration.json',dict(inputs=hashes,models=MODELS,families=FAMILIES,probability_gate=.65))
    source=c.read(names[0]);source=source[source.model.isin(MODELS)].copy()
    states=json.loads((c.ROOT/names[1]).read_text());cal=c.read(names[2]).set_index('target_month')
    points=source.pivot(index='period',columns='model',values='forecast').sort_index()
    features=pd.DataFrame({'full_gap':abs(points.HARD_FULL-points.HARD_BASE),
                           'category_gap':abs(points.CATEGORY_RAW-points.HARD_BASE)})
    records=[];histories=[];laws=[];coverage=[]
    for model in MODELS:
        z=source[source.model.eq(model)].sort_values('period').set_index('period')
        assert len(z)==90 and z.index.equals(points.index)
        history=pd.DataFrame({'origin':z.index,'error':(z.actual-z.forecast).to_numpy(),
            'released':pd.to_datetime(cal.loc[z.index,'first_release_dt']).to_numpy()+pd.Timedelta(hours=9),
            'full_gap':features.full_gap.to_numpy(),'category_gap':features.category_gap.to_numpy()})
        own=[]
        for origin in history.origin:
            clock=pd.Timestamp(states[origin]['as_of'])
            release=pd.Timestamp(cal.loc[origin,'first_release_dt'])
            assert clock.normalize()==release.normalize()-pd.Timedelta(days=1),(origin,clock,release)
            before=history[(history.origin<origin)&history.released.le(clock)]
            own.append(e.past_scale(before.error.to_numpy()))
        history['own_scale']=own;histories.append(history.assign(model=model))
        for origin,row in z.iterrows():
            clock=states[origin]['as_of'];f=features.loc[origin].to_numpy()
            for family in FAMILIES:
                law=e.error_law(history,origin,clock,row.forecast,f,family)
                laws.append(dict(origin=origin,model=model,family=family,as_of=clock,**law))
                coverage.append(dict(origin=origin,model=model,family=family,status=law['status'],n=law['n']))
                if law['status']!='estimated':continue
                x,w=law['support'],law['weights'];q=lambda p:e.weighted_quantile(x,w,p)
                surprise=row.actual-row.consensus;error=row.forecast-row.actual;gain=abs(surprise)-abs(error)
                probs=e.event_probabilities(x,w,row.forecast,row.consensus)
                records.append(dict(origin=origin,as_of=clock,model=model,family=family,point=row.forecast,
                    actual=row.actual,consensus=row.consensus,error=error,surprise=surprise,deviation=row.forecast-row.consensus,
                    gain=gain,big=abs(surprise)>=.4-1e-9,material_win=gain>=.15-1e-9,material_loss=gain<=-.15+1e-9,
                    alert=abs(row.forecast-row.consensus)>=.2-1e-9,release_kind=cal.loc[origin,'first_release_kind'],
                    median=q(.5),lo80=q(.1),hi80=q(.9),lo90=q(.05),hi90=q(.95),
                    cover80=q(.1)<=row.actual<=q(.9),cover90=q(.05)<=row.actual<=q(.95),
                    crps=e.crps(x,w,row.actual),ess=law['ess'],current_scale=law['current_scale'],**probs))
    result=pd.DataFrame(records);alerts=[]
    for (model,family),z in result.groupby(['model','family']):
        for threshold in [0.,.55,.65,.75]:
            for frame,subset in [('all',z),('2024+',z[z.origin.ge('2024-01')]),('flash',z[z.release_kind.eq('flash')])]:
                a=subset[subset.alert&subset.p_material_gain.ge(threshold)]
                alerts.append(dict(model=model,family=family,threshold=threshold,frame=frame,n_eligible=len(subset),
                    n_alert=len(a),n_big=int(a.big.sum()),n_false=int((~a.big).sum()),
                    material_wins=int(a.material_win.sum()),material_losses=int(a.material_loss.sum()),
                    mae=a.error.abs().mean(),survey_mae=a.surprise.abs().mean(),total_gain=a.gain.sum(),
                    missed_big=int(subset.big.sum()-a.big.sum())))
    for filename,frame in [('predictions',result),('scores',summarize(result)),('alerts',pd.DataFrame(alerts)),
                          ('coverage',pd.DataFrame(coverage)),('error_history',pd.concat(histories,ignore_index=True))]:
        frame.to_csv(out/(filename+'.csv'),index=False)
    c.dump(out/'laws.json',laws)
    c.finish(out,hashes,n_origins=90,n_eligible=int(result.groupby(['model','family']).size().min()),
             point_forecasts_unchanged=True,probability_status='experimental_uncalibrated')
    print('Completed',out,'eligible',result.groupby(['model','family']).size().unique().tolist(),flush=True)


if __name__=='__main__':main()
