"""Read-only R17 evaluator; explicit rosters, fixed support, original CNB layout."""
import argparse
import colorsys
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from models.path_components_r17 import sustained
from tools.review import evaluate_r15 as prior, evaluate_r16 as r16

FAST=c.FAST
KEYS=['origin','h','model']


def attach_native_core(frame,native,actual):
    empty=native.iloc[:0][KEYS].assign(core_mm=pd.Series(dtype=float))
    return prior.attach_core(frame,native,empty,actual)


def component_outcomes(native,actual,blocks=('core','food','fuel','administered','alcohol_tobacco')):
    records=[]
    for (origin,model),g in native.groupby(['origin','model']):
        t=pd.Period(origin,'M');g=g.set_index('h').reindex(range(1,13))
        months=pd.period_range(t+1,t+12,freq='M')
        for block in blocks:
            pred=g['value_'+block].to_numpy(float);truth=actual[block].reindex(months).to_numpy(float)
            cp=100*np.cumsum(np.log1p(pred/100));ca=100*np.cumsum(np.log1p(truth/100))
            for i in range(12):records.append(dict(origin=origin,model=model,block=block,h=i+1,target=str(months[i]),
                mm_forecast=pred[i],mm_actual=truth[i],cumulative_log_forecast=cp[i],cumulative_log_actual=ca[i]))
    return pd.DataFrame(records)


def sustained_rows(bands):
    result=[]
    for (origin,model),g in bands.groupby(['origin','model']):
        g=g.set_index('band').reindex([1,2,3])
        pred=sustained(g.predicted_sa_annualized);actual=sustained(g.actual_sa_annualized)
        result.append(dict(origin=origin,target=str(pd.Period(origin,'M')+9),model=model,
            predicted=pred,actual=actual,eligible=bool(np.isfinite([pred,actual]).all()),
            predicted_change=g.predicted_sa_annualized.iloc[2]-g.predicted_sa_annualized.iloc[0],
            actual_change=g.actual_sa_annualized.iloc[2]-g.actual_sa_annualized.iloc[0]))
    return pd.DataFrame(result)


def sustained_summary(rows,roster):
    counts=rows[rows.eligible].groupby('origin').model.nunique();origins=counts[counts.eq(len(roster))].index
    rows=rows[rows.origin.isin(origins)];records=[]
    for sample,mask in prior.samples(rows).items():
        for model,g in rows[mask].groupby('model'):
            events=g.actual.ne(0);calls=g.predicted.ne(0);hits=events&calls&g.actual.eq(g.predicted)
            records.append(dict(sample=sample,model=model,n=len(g),actual_events=int(events.sum()),calls=int(calls.sum()),
                hits=int(hits.sum()),misses=int((events&~hits).sum()),false_calls=int((calls&~hits).sum()),
                recall=hits.sum()/events.sum() if events.any() else np.nan,precision=hits.sum()/calls.sum() if calls.any() else np.nan))
    return pd.DataFrame(records)


def replay_data(frame,cnb,actual,pairs,clocks,roster):
    labels={FAST:'FAST · reference','STABLE_LOCAL_CORE_R14B':'Current core','STABLE_PIPELINE_R14B':'Stable pipeline',
        'INDEPENDENT_BRIDGE':'Independent bridge','DAMPED_P95_Q001_R16':'Gentle slope · R16',
        'CORE_NEWS_H0_R17':'Core · repeated news + h0','CORE_ROBUST_R17':'Core · robust',
        'PATH_POOL_R17':'Constrained path pool','PATH_COMPONENT_SELECT_R17':'Component correction · selected',
        'COMBO_ALL_R17':'Combined components','PATH_FAST_CURRENT_HALF_R17':'Half FAST + current core'}
    defaults={FAST,'STABLE_LOCAL_CORE_R14B','PATH_POOL_R17'}
    series=[dict(id='realised',label='Realised · current vintage',kind='realised',color='--realised',width=2.4,default=True),
            dict(id='cnb',label='CNB published forecast',kind='cnb',color='--cnb',width=2.,default=True)]
    for i,model in enumerate(roster):
        rgb=colorsys.hsv_to_rgb((i*.618034)%1,.64,.68);color='#'+''.join(f'{round(x*255):02x}' for x in rgb)
        label=labels.get(model,model.removesuffix('_R17').replace('_',' ').title())
        series.append(dict(id=model,label=label,short=label,kind='model',color=f'--r17-{i}',hex=color,width=2.,default=model in defaults))
    reports={'report':[],'cutoff':[]}
    selected=cnb[cnb.is_forecast.astype(str).str.lower().eq('true')&cnb.report_date.ge('2022-01-01')]
    for clock in clocks.to_dict('records'):
        if clock['origin'] is None:continue
        mode,date,origin=clock['clock'],clock['report_date'],clock['origin']
        g=selected[selected.report_date.eq(date)].sort_values('quarter')
        if g.empty:continue
        o,q=pd.Period(origin,'M'),pd.Period(date,'Q');paths={};points={}
        for model in roster:
            mg=frame[frame.origin.eq(origin)&frame.model.eq(model)].sort_values('h')
            path=dict(zip(mg.target,mg.yy_exante));anchor=actual.get(o-1,np.nan)
            pathpoints=[[str(o-1),float(anchor)]] if np.isfinite(anchor) else []
            for h in range(13):
                value=path.get(str(o+h),np.nan)
                if not np.isfinite(value):break
                pathpoints.append([str(o+h),float(value)])
            paths[model]=pathpoints
            points[model]=[[k,v] for k in g.quarter if np.isfinite(v:=prior.quarter_value(k,o,path,actual))]
        scores=pairs[pairs.clock.eq(mode)&pairs.report_date.eq(date)]
        season=str(g.season.iloc[0]).capitalize()
        reports[mode].append(dict(id=date+'-'+mode,report_date=date,cutoff_date=clock['cutoff_date'],origin=origin,
            origin_clock=pd.Timestamp(clock['as_of_utc']).tz_convert('Europe/Prague').strftime('%Y-%m-%d %H:%M'),
            season=season,season_cs={'Winter':'Zima','Spring':'Jaro','Summer':'Léto','Autumn':'Podzim'}.get(season,''),year=int(date[:4]),
            window=dict(start=str((q-2).asfreq('M','start')),end=str(pd.Period(g.quarter.iloc[-1],'Q').asfreq('M','end'))),
            cnb=[dict(quarter=r.quarter,value=float(r.value)) for r in g.itertuples()],
            realised_quarters=[dict(quarter=k,value=v) for k in g.quarter if np.isfinite(v:=prior.quarter_actual(k,actual))],
            paths=paths,quarter_points=points,score=dict(n=scores.quarter.nunique(),quarters=sorted(scores.quarter.unique()),
                mae={m:float(abs(z.error).mean()) for m,z in scores.groupby('model')})))
    method=[
        'Historical research replay, last frozen origin July2026. Current-vintage inputs and reconstructed availability; no untouched holdout or live forecast.',
        'Report clock uses the last existing snapshot strictly before report-day midnight Prague; cutoff clock includes the full CNB cutoff day. Neither clock is chosen by accuracy.',
        'Each monthly path retains independent HARD_BASE h0. Annual CPI compounds same-origin monthly rates. A model quarter averages three annual rates, with known history before its origin. No later forecast is borrowed.',
        f'Every per-round score uses identical complete support for all {len(roster)} models and CNB, regardless of visible checkboxes. Repeated quarters across reports are dependent.',
        'A material gain means model absolute error is at least0.15pp below CNB; material loss is the reverse. Correct direction alone does not imply a useful forecast.',
        'Single-block core, food, monthly service-proxy and annual-index fuel tests remain visible. Low/high commodity assumptions are separate sensitivities, not calibrated probability bands. No national bill point forecast is claimed without exposure and baseline data.',
        'Path selectors use only earlier fully matured12month headline forecasts, one weight vector for all horizons, with FAST at least half in the constrained pool. Early insufficient history defaults to FAST. Equal half FAST/current-core is unrelated to nowcast HALF.',
        'The original strict core peak/trough score remains; sustained acceleration/deceleration is an additional diagnostic. Base-effect headline direction, component accuracy and core turning skill are separate.',
        'Defaults show FAST, current core and the constrained pool for readability, not promotion. All models are available. No survey, expectations or CNB forecast enters the new independent models.'
    ]
    return dict(series=series,reportsByClock=reports,realised={str(k):float(v) for k,v in actual.dropna().items()},method=method,
        title='CNB Rounds Replayed · R17 · historical',vintage='current-vintage simulated historical')


def write_replay(artifact,payload):
    n=sum(s['kind']=='model' for s in payload['series'])
    prior.write_replay(artifact,payload,ROOT/'tools/cnb_rounds/cnb_rounds_template.html')
    text=artifact.read_text(encoding='utf-8').replace('cnb-rounds-r15-visible-v1','cnb-rounds-r17-visible-v1').replace('complete 14-model roster',f'complete {n}-model roster').replace('Czech CPI · R15 ·','Czech CPI · R17 ·').replace('<title>CNB Rounds Replayed</title>','<title>CNB Rounds Replayed · R17 · historical</title>')
    artifact.write_text(text,encoding='utf-8')


def evaluate(experiment):
    experiment=Path(experiment);out=experiment/'evaluation';out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((experiment/'manifest.json').read_text());hashes={}
    for category,parent in [('inputs',ROOT),('outputs',experiment)]:
        for name,digest in manifest[category].items():
            path=parent/name
            if c.sha(path)!=digest:raise ValueError('Frozen experiment drift '+str(path))
            hashes[str(path.resolve())]=digest
    for path in [Path(__file__),Path(prior.__file__),Path(r16.__file__),ROOT/'tools/cnb_rounds/cnb_rounds_template.html',
                 ROOT/'data/cnb_mpr_cpi_quarterly.csv',ROOT/'tests/fixtures/cleanup/cnb_core_mm.csv']:
        hashes[str(path.resolve())]=c.sha(path)
    read=lambda name:pd.read_csv(experiment/name,float_precision='round_trip',low_memory=False)
    frame=read('forecasts.csv');native=read('native_forecasts.csv');roster=[*manifest['controls'],*manifest['models']]
    for f in (frame,native):prior.unique(f)
    if set(frame.model)!=set(roster):raise ValueError('Roster mismatch')
    if frame.groupby('model').size().ne(90*13).any():raise ValueError('Original90origin calendar required')
    headline=c.monthly('output/independent_path_frozen_inputs.csv','headline_mm')
    actual=100*np.expm1(np.log1p(headline/100).rolling(12).sum());core=c.monthly('tests/fixtures/cleanup/cnb_core_mm.csv','core')
    checks=prior.verify_arithmetic(frame,headline,actual)
    frame=attach_native_core(frame,native,core)
    states=json.loads((ROOT/'output/research_r15/states.json').read_text())
    support=c.read('output/research_r17/attribution/primary_support.csv')
    hashes[str((ROOT/'output/research_r17/attribution/primary_support.csv').resolve())]=c.sha(ROOT/'output/research_r17/attribution/primary_support.csv')
    primary=frame.merge(support,on=['origin','h'],validate='many_to_one')
    def csv(name,data):data.to_csv(out/(name+'.csv'),index=False)
    def dump(name,data):(out/(name+'.json')).write_text(json.dumps(prior.json_safe(data),indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    csv('forecast_core_outcomes',frame);csv('primary_rows',primary)
    ledger=frame.copy();summary=[]
    for metric,(prediction,truth) in prior.METRICS.items():
        ledger[metric+'_forecast_finite']=np.isfinite(ledger[prediction]);ledger[metric+'_actual_finite']=np.isfinite(ledger[truth])
        for (model,h),g in primary.groupby(['model','h']):
            for sample,mask in prior.samples(g).items():
                own=g[mask];summary.append(dict(scope='original_R16_calendar',model=model,h=h,metric=metric,sample=sample,
                    n_intended=len(own),n_missing_forecasts=int((~np.isfinite(own[prediction])).sum()),**prior.error_stats(own[prediction]-own[truth])))
    csv('coverage_ledger',ledger);csv('primary_scoreboard',pd.DataFrame(summary))
    scores,differences=r16.score_tables(frame,models=roster)
    csv('scoreboard',scores);csv('paired_loss_differences',differences)
    component_source=ROOT/'output/research_r14b/attribution/actual_component_targets.csv'
    hashes[str(component_source.resolve())]=c.sha(component_source)
    components=component_outcomes(native,c.monthly(component_source))
    csv('component_outcomes',components)
    component_scores=[];component_differences=[]
    cm={'monthly':('mm_forecast','mm_actual'),'cumulative_log':('cumulative_log_forecast','cumulative_log_actual')}
    for block,g in components.groupby('block'):
        sc,di=r16.score_tables(g,models=roster,metrics=cm)
        component_scores.append(sc.assign(block=block));component_differences.append(di.assign(block=block))
    csv('component_scoreboard',pd.concat(component_scores));csv('component_paired_loss_differences',pd.concat(component_differences))
    boot=[]
    for (scope,benchmark,model,metric,h),g in differences[differences.metric.eq('headline_yy')&differences.scope.str.startswith('paired_fast')].groupby(['scope','benchmark','model','metric','h']):
        for sample,mask in prior.samples(g).items():boot.append(dict(scope=scope,benchmark=benchmark,model=model,metric=metric,h=h,sample=sample,**prior.block_bootstrap(g[mask])))
    csv('headline_paired_block_bootstrap',pd.DataFrame(boot))
    bands,changes,turns=prior.core_turn_diagnostics(frame,states)
    csv('underlying_core_bands',bands);csv('underlying_core_changes',changes);csv('underlying_core_turns',turns)
    csv('underlying_core_turn_summary',prior.turn_summaries(turns,models=roster))
    sr=sustained_rows(bands);csv('sustained_movement_pairs',sr);csv('sustained_movement_summary',sustained_summary(sr,roster))
    direction,dp=prior.direction_tables(frame,actual,models=roster);csv('headline_direction_summary',direction);csv('headline_direction_pairs',dp)
    rev=prior.revision_pairs(frame);csv('revision_pairs',rev);csv('revision_summary',prior.revision_summaries(rev,models=roster))
    cnb=c.read('data/cnb_mpr_cpi_quarterly.csv');pairs,coverage,clocks,projections=prior.cnb_comparison(frame,cnb,actual,roster)
    for name,data in [('cnb_pairs',pairs),('cnb_coverage',coverage),('cnb_clocks',clocks),('cnb_quarter_projections',projections)]:csv(name,data)
    both=pairs.groupby(['report_date','quarter']).clock.nunique();both=both[both.eq(2)].index
    cross=pairs.set_index(['report_date','quarter']).loc[lambda x:x.index.isin(both)].reset_index()
    csv('cnb_cross_clock_matched_pairs',cross)
    csv('cnb_summary',pd.concat([prior.cnb_summaries(pairs),prior.cnb_summaries(cross,'cross_clock_common')]))
    departure_rows=[];departure_scores=[]
    for threshold in (.5,1.):
        large=pairs[pairs.model.ne('cnb')&pairs.realised_cnb_error.abs().ge(threshold)].copy()
        large['threshold']=threshold
        large['capture_ratio']=large.model_cnb_deviation/large.realised_cnb_error
        large['relative_absolute_error_gain']=large.abs_error_gain_vs_cnb/large.realised_cnb_error.abs()
        departure_rows.append(large)
        for (clock,model),g in large.groupby(['clock','model']):
            for sample,own in [('full',g),('reports_2024plus',g[g.report_date.ge('2024-01-01')])]:
                departure_scores.append(dict(threshold=threshold,clock=clock,model=model,sample=sample,n=len(own),
                    reports=own.report_date.nunique(),actual_direction_hits=int(own.deviation_direction_correct.sum()),
                    material_gains=int(own.material_gain.sum()),material_losses=int(own.material_loss.sum()),
                    mean_abs_gain=own.abs_error_gain_vs_cnb.mean(),median_capture=own.capture_ratio.median(),
                    median_relative_abs_gain=own.relative_absolute_error_gain.median(),
                    overshoot_beyond_twice=int(own.capture_ratio.gt(2).sum())))
    csv('cnb_large_departure_pairs',pd.concat(departure_rows));csv('cnb_large_departure_summary',pd.DataFrame(departure_scores))
    csv('cnb_leave_one_report_out',pd.concat([r16.cnb_leave_one_report_out(pairs).assign(scope='within_clock_common'),r16.cnb_leave_one_report_out(cross).assign(scope='cross_clock_common')]))
    payload=replay_data(frame,cnb,actual,pairs,clocks,roster);dump('replay_data',payload)
    artifact=out/'cnb_rounds_replayed_r17.html';write_replay(artifact,payload)
    dump('definitions',dict(roster=roster,primary_calendar='Original R16 annual-headline969row support, not filtered by a new model.',
        errors='Forecast minus actual in percentage points. Show failures separately; matched comparisons require identical finite support.',
        core='Monthly core and cumulative log core h1..h, original frozen target. Underlying bands subtract own-origin saved R15 seasonality.',
        bootstrap='12 consecutive calendar-origin blocks;2000draws seed1509; suppress when complete calendar blocks cannot cover all support.',
        sustained='Bands1to3 change>=.5pp annualized, without opposite adjacent>=.5pp. Additional to strict exact-turn test.',
        cnb='Both clocks; same-origin quarter means;0.15pp absolute-error materiality; repeated quarters dependent; every-report omission.',
        limitations=payload['method']))
    for path,digest in hashes.items():
        if c.sha(path)!=digest:raise ValueError('Evaluator changed input '+path)
    checks.update(origin_count=90,model_count=len(roster),primary_origin_h_rows=len(support),all_inputs_unchanged=True)
    dump('checks',checks)
    dump('input_manifest',dict(inputs=hashes,outputs={p.name:c.sha(p) for p in out.iterdir() if p.is_file() and p.name!='input_manifest.json'}))
    print('R17 evaluation completed',out,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,default=ROOT/'output/research_r17/path');evaluate(p.parse_args().experiment)
