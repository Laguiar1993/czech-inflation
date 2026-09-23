"""Same-target CNB next-report revisions and predeclared ex-ante call episodes."""
import numpy as np
import pandas as pd


def lead_pairs(pairs,cnb,threshold=.3):
    dates=sorted(cnb.report_date.unique());nexts=dict(zip(dates,dates[1:]));rows=[]
    predictions=cnb[cnb.is_forecast.astype(str).str.lower().eq('true')].set_index(['report_date','quarter']).value
    if predictions.index.duplicated().any():raise ValueError('Duplicate CNB report/quarter forecast')
    for r in pairs.to_dict('records'):
        report=r['report_date'];q=r['quarter'];next_report=nexts.get(report)
        old=float(predictions.get((report,q),np.nan));new=float(predictions.get((next_report,q),np.nan))
        forecast=r['forecast'];actual=r.get('realised',r.get('actual',np.nan));deviation=forecast-old
        future=bool(next_report is not None and pd.Period(q,'Q')>pd.Period(next_report,'Q'))
        eligible=bool(future and np.isfinite([old,new,forecast]).all())
        call=bool(np.isfinite(deviation) and abs(deviation)>=threshold-1e-12)
        revision=new-old if eligible else np.nan
        same=bool(eligible and revision!=0 and np.sign(revision)==np.sign(deviation))
        gain=abs(old-forecast)-abs(new-forecast) if eligible else np.nan
        confirmed=bool(call and same and gain>=.15-1e-12)
        abs_gain=abs(old-actual)-abs(forecast-actual) if np.isfinite(actual) else np.nan
        rows.append(dict(**{k:r[k] for k in ['model','clock','report_date','quarter']},next_report=next_report,
            forecast=forecast,cnb_current=old,cnb_next=new,realised=actual,threshold=threshold,deviation=deviation,call=call,
            forecast_available=bool(np.isfinite(forecast)),next_report_available=next_report is not None,
            next_forecast_available=bool(np.isfinite(new)),target_still_future=future,
            revision_eligible=eligible,revision=revision,revision_direction_agrees=same,revision_distance_gain=gain,
            revision_confirmed=confirmed,abs_error_gain=abs_gain,material_gain=bool(abs_gain>=.15-1e-12),
            material_loss=bool(abs_gain<=-.15+1e-12),joint_success=bool(confirmed and abs_gain>=.15-1e-12)))
    return pd.DataFrame(rows)


def first_episodes(pairs,cnb):
    out=pairs.sort_values(['model','clock','threshold','quarter','report_date']).copy();out['episode_start']=False
    order={d:i for i,d in enumerate(sorted(cnb.report_date.unique()))}
    for _,g in out.groupby(['model','clock','threshold','quarter']):
        previous=None;direction=None
        for i,r in g.iterrows():
            d=np.sign(r.deviation);position=order[r.report_date]
            if r.call:
                out.loc[i,'episode_start']=previous is None or position!=previous+1 or d!=direction
                previous=position;direction=d
            else:previous=None;direction=None
    return out


def summaries(rows):
    output=[]
    for (model,clock,threshold),g in rows.groupby(['model','clock','threshold']):
        for sample,s in [('full',g),('reports_2024plus',g[g.report_date.ge('2024-01-01')])]:
            for scope,z in [('all_pairs',s),('first_call_episodes',s[s.episode_start])]:
                e=z[z.revision_eligible];calls=e[e.call];mature=calls[calls.realised.notna()]
                output.append(dict(model=model,clock=clock,threshold=threshold,sample=sample,scope=scope,
                    considered_pairs=len(z),all_calls=int(z.call.sum()),calls_without_eligible_revision=int((z.call&~z.revision_eligible).sum()),
                    n_pairs=len(e),n_reports=e.report_date.nunique(),n_target_quarters=e.quarter.nunique(),calls=len(calls),
                    revision_direction_matches=int(calls.revision_direction_agrees.sum()),
                    revision_confirmations=int(calls.revision_confirmed.sum()),mature_calls=len(mature),
                    material_gains=int(mature.material_gain.sum()),material_losses=int(mature.material_loss.sum()),
                    joint_successes=int(mature.joint_success.sum()),unconfirmed_calls=int((~calls.revision_confirmed).sum()),
                    mean_abs_error_gain=mature.abs_error_gain.mean()))
    return pd.DataFrame(output)
