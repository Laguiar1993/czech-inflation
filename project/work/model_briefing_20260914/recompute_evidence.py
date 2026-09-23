"""Descriptive workplace briefing evidence; no forecasting or parameter fitting."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EPS = 1e-9
SOURCES = [
    'output/audit_fixes_20260914/nowcast/independent_nowcast_releases.csv',
    'output/research_r13/nowcast/release_rows.csv',
    'output/research_r17/path/evaluation/cnb_quarter_projections.csv',
    'output/research_r17/path/evaluation/cnb_clocks.csv',
    'data/cnb_mpr_cpi_quarterly.csv',
    'data/czcpmom_survey_history_extended.csv',
    'data/release_calendar_cz_cpi.csv',
    'work/model_briefing_20260914/ANALYSIS_SCOPE.md',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def turn(a, b, c, delta):
    if not np.isfinite([a, b, c]).all():
        return None
    if b-a >= delta-EPS and b-c >= delta-EPS:
        return 1
    if a-b >= delta-EPS and c-b >= delta-EPS:
        return -1
    return 0


def nowcast():
    d = pd.read_csv(ROOT / SOURCES[0])
    cats = pd.read_csv(ROOT / SOURCES[1])
    # Every retained raw/half/full forecast is the same saved R9 prediction.
    for old, new in [('R9_BASE','HARD_BASE'),('R9_HALF','HARD_HALF'),('R9_FULL','HARD_FULL')]:
        a = d[d.model.eq(new)].set_index('period')
        b = cats[cats.model.eq(old)].set_index('period')
        np.testing.assert_allclose(a[['forecast','actual','consensus']], b.loc[a.index,['forecast','actual','consensus']], rtol=0, atol=1e-12)
    wanted = ['CATEGORY_RAW','CATEGORY_HALF_CORRECTION','CATEGORY_FULL_CORRECTION']
    cats = cats[cats.model.isin(wanted)]
    d = pd.concat([d[d.model.isin(['HARD_BASE','HARD_HALF','HARD_FULL','CONSENSUS'])],cats],ignore_index=True)
    assert not d.duplicated(['model','period']).any()
    d['surprise'] = d.actual-d.consensus
    d['deviation'] = d.forecast-d.consensus
    d['error'] = d.forecast-d.actual
    d['gain'] = d.surprise.abs()-d.error.abs()
    d['big'] = d.surprise.abs().ge(.4-EPS)
    d['alert'] = d.deviation.abs().ge(.2-EPS)
    d['direction'] = (d.deviation*d.surprise).gt(0)
    d['material_win'] = d.gain.ge(.15-EPS)
    d['material_loss'] = d.gain.le(-.15+EPS)
    d['capture'] = (d.deviation/d.surprise).where(d.big)
    d['directional_big_hit'] = d.big & d.alert & d.direction
    d['material_big_hit'] = d.big & d.alert & d.material_win
    d['false_alarm'] = d.alert & ~d.big
    sv = pd.read_csv(ROOT / SOURCES[5])
    sv = sv[sv.era.ne('flash_survey_suspect')].set_index('target_month')
    calendar = pd.read_csv(ROOT / SOURCES[6]).set_index('target_month')
    d['release_kind'] = d.period.map(calendar.first_release_kind)
    d['release_date'] = d.period.map(calendar.first_release_dt)
    for model, z in d.groupby('model'):
        assert len(z)==90 and z.period.min()=='2019-02' and z.period.max()=='2026-07'
        np.testing.assert_allclose(z.actual,sv.loc[z.period,'actual'],rtol=0,atol=1e-12)
        np.testing.assert_allclose(z.consensus,sv.loc[z.period,'survey_median'],rtol=0,atol=1e-12)
    rows=[]
    for model,z in d.groupby('model'):
        masks={'all':np.ones(len(z),bool),'2024+':z.period.ge('2024-01'),
               'flash2025+':z.period.ge('2025-01'),'big':z.big,
               'big_ex_jan':z.big & ~z.period.str.endswith('-01'),
               'alerts':z.alert,'big_2024+':z.big & z.period.ge('2024-01')}
        for frame,mask in masks.items():
            a=z.loc[mask];n=len(a)
            rows.append(dict(model=model,frame=frame,n=n,
                rmse=float(np.sqrt(np.mean(a.error**2))) if n else np.nan,
                mae=a.error.abs().mean(),consensus_mae=a.surprise.abs().mean(),
                consensus_rmse=float(np.sqrt(np.mean(a.surprise**2))) if n else np.nan,
                closer=int(a.gain.gt(EPS).sum()),direction=int(a.direction.sum()),
                material_win=int(a.material_win.sum()),material_loss=int(a.material_loss.sum()),
                alerts=int(a.alert.sum()),big=int(a.big.sum()),alerted_big=int((a.big&a.alert).sum()),
                false_alarm=int(a.false_alarm.sum()),directional_big_hit=int(a.directional_big_hit.sum()),
                material_big_hit=int(a.material_big_hit.sum()),median_capture=a.capture.median(),
                overshoot_over_2=int(a.capture.gt(2+EPS).sum()),total_gain=a.gain.sum()))
    board=pd.DataFrame(rows);board.to_csv(OUT/'nowcast_summary.csv',index=False)
    d.to_csv(OUT/'nowcast_release_evidence.csv',index=False)
    d[d.big].to_csv(OUT/'nowcast_large_events.csv',index=False)
    print('NOWCAST\n'+board[board.frame.isin(['all','big','alerts'])].to_string(index=False))


def turns():
    p=pd.read_csv(ROOT/SOURCES[2]);c=pd.read_csv(ROOT/SOURCES[4])
    p['q']=pd.PeriodIndex(p.quarter,freq='Q');c['q']=pd.PeriodIndex(c.quarter,freq='Q')
    assert not p.duplicated(['clock','report_date','model','q']).any()
    actual={}
    for q,z in p[np.isfinite(p.realised)].groupby('q'):
        assert np.ptp(z.realised.to_numpy())<1e-9
        actual[q]=float(z.realised.iloc[0])
    cnb={str(date):z.set_index('q') for date,z in c.groupby('report_date')}
    first_report=min(cnb)
    opportunities=[];cnbevidence=[]
    for delta in [.25,.10,.50]:
        # All CNB vintages and its full available horizon, not just our horizon.
        for report,z in cnb.items():
            for clock in ['report','cutoff']:
                decision=pd.Timestamp(report if clock=='report' else z.cutoff_date.iloc[0])
                for q in z.index:
                    if q.end_time<decision or q-1 not in z.index or q+1 not in z.index:
                        continue
                    if not bool(z.loc[q,'is_forecast']):
                        continue
                    if any(x not in actual for x in [q-1,q,q+1]):
                        continue
                    trip=z.loc[[q-1,q,q+1],'value'].to_numpy(float)
                    pred=turn(*trip,delta);real=turn(*(actual[x] for x in [q-1,q,q+1]),delta)
                    cnbevidence.append(dict(threshold=delta,clock=clock,report_date=report,quarter=str(q),
                        predicted=pred,actual=real,hit=pred!=0 and pred==real,
                        fully_future=q.start_time>decision))
        for (clock,report,model),z in p.groupby(['clock','report_date','model']):
            if model=='cnb':continue
            z=z.set_index('q');decision=pd.Timestamp(report if clock=='report' else z.cutoff_date.iloc[0])
            raw=cnb[report]
            for q in z.index:
                if q.end_time<decision or any(x not in z.index or x not in raw.index or x not in actual for x in [q-1,q,q+1]):
                    continue
                vals=z.loc[[q-1,q,q+1],'forecast'].to_numpy(float)
                cmp=raw.loc[[q-1,q,q+1],'value'].to_numpy(float)
                if not np.isfinite(vals).all() or not np.isfinite(cmp).all():continue
                pred=turn(*vals,delta);real=turn(*(actual[x] for x in [q-1,q,q+1]),delta)
                cturn=turn(*cmp,delta)
                opportunities.append(dict(threshold=delta,clock=clock,report_date=report,
                    origin=z.origin.iloc[0],as_of_utc=z.as_of_utc.iloc[0],model=model,quarter=str(q),
                    actual_turn=real,model_turn=pred,cnb_turn=cturn,
                    model_hit=pred!=0 and pred==real,cnb_hit=cturn!=0 and cturn==real,
                    model_false_call=pred!=0 and pred!=real,fully_future=q.start_time>decision,
                    actual_before=actual[q-1],actual_centre=actual[q],actual_after=actual[q+1],
                    model_before=vals[0],model_centre=vals[1],model_after=vals[2],
                    cnb_before=cmp[0],cnb_centre=cmp[1],cnb_after=cmp[2]))
    o=pd.DataFrame(opportunities);ce=pd.DataFrame(cnbevidence)
    summaries=[];events=[]
    for (delta,clock,model),z in o.groupby(['threshold','clock','model']):
        for q,a in z[z.actual_turn.ne(0)].groupby('quarter'):
            m=a[a.model_hit];bc=ce[ce.threshold.eq(delta)&ce.clock.eq(clock)&ce.quarter.eq(q)&ce.hit]
            fm=m.report_date.min() if len(m) else None
            fc=bc.report_date.min() if len(bc) else None
            if fm is None:status='model_missed'
            elif fc is None:status='model_only_no_cnb_call'
            elif fm==fc:status='same_round'
            elif fm<fc:status='earlier_round'
            else:status='later_round'
            censored=fm==first_report
            events.append(dict(threshold=delta,clock=clock,model=model,quarter=q,
                actual_turn=int(a.actual_turn.iloc[0]),first_model_round=fm,first_cnb_round=fc,
                status=status,left_censored=censored,
                supported_earlier_round=status=='earlier_round' and not censored,
                lead_days_between_reports=(pd.Timestamp(fc)-pd.Timestamp(fm)).days if fm and fc else np.nan,
                n_opportunities=len(a)))
        for frame,a in [('unfinished_or_future_quarter',z),('fully_future_centre',z[z.fully_future])]:
            summaries.append(dict(threshold=delta,clock=clock,model=model,frame=frame,n=len(a),
                actual_turns=int(a.actual_turn.ne(0).sum()),calls=int(a.model_turn.ne(0).sum()),
                hits=int(a.model_hit.sum()),false_calls=int(a.model_false_call.sum()),
                cnb_calls=int(a.cnb_turn.ne(0).sum()),cnb_hits=int(a.cnb_hit.sum()),
                correct_model_cnb_not=int((a.model_hit&~a.cnb_hit).sum()),
                distinct_actual_turns=a[a.actual_turn.ne(0)].quarter.nunique(),
                distinct_model_hits=a[a.model_hit].quarter.nunique()))
    events=pd.DataFrame(events);scores=pd.DataFrame(summaries)
    o.to_csv(OUT/'headline_turn_opportunities.csv',index=False)
    ce.to_csv(OUT/'cnb_all_vintage_turn_calls.csv',index=False)
    events.to_csv(OUT/'headline_turn_event_priority.csv',index=False)
    scores.to_csv(OUT/'headline_turn_summary.csv',index=False)
    keep=['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16','RF_RESIDUAL_R15','CORE_NEWS_R17','PATH_POOL_R17','INDEPENDENT_BRIDGE']
    print('\nPRIMARY HEADLINE TURNS\n'+scores[scores.threshold.eq(.25)&scores.model.isin(keep)].to_string(index=False))
    print('\nPRIMARY EVENT PRIORITY\n'+events[events.threshold.eq(.25)&events.clock.eq('report')&events.model.isin(keep)].to_string(index=False))


if __name__=='__main__':
    assert turn(1,2,1,.25)==1 and turn(2,1,2,.25)==-1
    assert turn(1,1.1,1,.25)==0 and turn(1,1.25,1,.25)==1
    assert turn(1,np.nan,1,.25) is None and turn(1,2,3,.25)==0
    before={n:sha(ROOT/n) for n in SOURCES}
    nowcast();turns()
    assert before=={n:sha(ROOT/n) for n in SOURCES}
    outputs={p.name:sha(p) for p in OUT.glob('*.csv')}
    (OUT/'manifest.json').write_text(json.dumps(dict(inputs=before,outputs=outputs,
        script_sha256=sha(Path(__file__)),interpretation='Descriptive frozen-forecast analysis; no fitting or model selection'),indent=2)+'\n',encoding='utf-8')
