"""Independent final evaluator audit using source and reviewer reference tables."""
from pathlib import Path
import hashlib
import argparse
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'output/research_r16';EV=EXP/'evaluation';OUT=Path(__file__).resolve().parent/'evaluation'
read=lambda name,base=EV:pd.read_csv(base/name,float_precision='round_trip')
parser=argparse.ArgumentParser();parser.add_argument('--skip-integrity',action='store_true');args=parser.parse_args()
receipt=json.loads((EV/'input_manifest.json').read_text(encoding='utf-8'));checked=0
if not args.skip_integrity:
    for name,digest in receipt['inputs'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name;checked+=1
    for name,digest in receipt['outputs'].items():assert hashlib.sha256((EV/name).read_bytes()).hexdigest()==digest,name;checked+=1
manifest=json.loads((EXP/'manifest.json').read_text(encoding='utf-8'));roster=manifest['controls']+manifest['models'];controls=manifest['controls']
frame=read('forecast_core_outcomes.csv');scores=read('scoreboard.csv');metrics={
    'headline_yy':('yy_exante','yy_actual'),'headline_mm':('mm_forecast','mm_actual'),
    'headline_cumulative_log':('cumulative_log_forecast','cumulative_log_actual'),
    'core_mm':('core_mm_forecast','core_mm_actual'),'core_cumulative_log':('core_cumulative_log_forecast','core_cumulative_log_actual')}
assert set(frame.model)==set(roster) and len(frame)==90*13*15
assert not frame.duplicated(['origin','h','model']).any()
def close(a,b):
    aa=np.asarray(a,dtype=float);bb=np.asarray(b,dtype=float)
    assert aa.shape==bb.shape and np.array_equal(np.isnan(aa),np.isnan(bb)),(aa.shape,bb.shape)
    assert np.allclose(aa,bb,rtol=1e-10,atol=1e-10,equal_nan=True)
    return float(np.nanmax(np.abs(aa-bb))) if np.isfinite(aa).any() else 0.
def compare_csv(actual,reference,keys,columns=None):
    a=actual.set_index(keys).sort_index();b=reference.set_index(keys).sort_index();assert a.index.equals(b.index)
    maximum=0.
    for col in columns or b.columns:
        if pd.api.types.is_numeric_dtype(b[col]):maximum=max(maximum,close(a[col],b[col]))
        else:assert list(a[col].fillna('<missing>'))==list(b[col].fillna('<missing>')),col
    return maximum
def mask(index,target,sample):
    if sample=='full':return np.ones(len(index),bool)
    if sample=='origins_2019_2021':return (index>='2019-01')&(index<='2021-12')
    if sample=='origins_2022_2023':return (index>='2022-01')&(index<='2023-12')
    if sample=='origins_2024plus':return index>='2024-01'
    if sample=='recent_targets':return np.asarray(target)>='2024-01'
    raise AssertionError(sample)

maximum_score_error=0.;score_rows=0
for (scope,metric),table in scores.groupby(['scope','metric']):
    if scope=='all_models_common':models=roster
    elif scope.startswith('paired_pipeline_'):models=['STABLE_PIPELINE_R14B',scope[len('paired_pipeline_'):]]
    elif scope.startswith('paired_fast_'):models=['STATE_FAST_R15',scope[len('paired_fast_'):]]
    else:raise AssertionError(scope)
    assert set(table.model)==set(models)
    pred,truth=metrics[metric];source=frame[frame.h.gt(0)&frame.model.isin(models)]
    wide=source.pivot(index=['origin','h','target'],columns='model',values=pred).reindex(columns=models)
    yy=source.drop_duplicates(['origin','h','target']).set_index(['origin','h','target'])[truth]
    valid=wide.notna().all(axis=1)&yy.notna();err=wide.loc[valid].sub(yy[valid],axis=0)
    for (h,sample),rows in table.groupby(['h','sample']):
        own=err[err.index.get_level_values('h')==h]
        own=own[mask(own.index.get_level_values('origin'),own.index.get_level_values('target'),sample)]
        stats={'n':pd.Series(len(own),index=models),'mae':own.abs().mean(),'rmse':(own.pow(2).mean())**.5,'bias':own.mean()}
        actual=rows.set_index('model')
        for col,values in stats.items():maximum_score_error=max(maximum_score_error,close(actual.loc[models,col],values.loc[models]))
        score_rows+=len(rows)
old=read('output/research_r15/evaluation/scoreboard.csv',ROOT)
new=scores[scores.scope.eq('all_models_common')&scores.model.isin(controls)]
old=old[old.scope.eq('all_models_common')&old.model.isin(controls)]
control_score_error=compare_csv(new,old,['scope','sample','metric','h','model'],['n','mae','rmse','bias'])
support=read('r15_support_comparison.csv');assert support.r16_only_n.eq(0).all() and support.r15_only_n.eq(0).all()

band_error=compare_csv(read('underlying_core_bands.csv'),read('reference_core_bands.csv',OUT),['origin','model','band'])
turn_error=compare_csv(read('underlying_core_turns.csv'),read('reference_core_turns.csv',OUT),['origin','model','band'])
ts=read('underlying_core_turn_summary.csv');ref=read('reference_turn_summary.csv',OUT)
actual=ts[ts.scope.eq('all_models_common')&ts['sample'].isin(ref['sample'].unique())]
compare_csv(actual,ref,['sample','model'])
pair_error=compare_csv(read('cnb_pairs.csv'),read('reference_cnb_pairs.csv',OUT),['clock','report_date','quarter','model'])
compare_csv(read('cnb_clocks.csv'),read('reference_cnb_clocks.csv',OUT),['clock','report_date'])
compare_csv(read('cnb_coverage.csv'),read('reference_cnb_coverage.csv',OUT),['clock','report_date','quarter'])
cs=read('cnb_summary.csv');cs=cs[cs.scope.eq('within_clock_common')&cs.quarters_ahead.eq('all')]
compare_csv(cs,read('reference_cnb_summary.csv',OUT),['sample','clock','model'])
lo=read('cnb_leave_one_report_out.csv');ref=read('reference_cnb_leave_one_report_out.csv',OUT)
omission_error=compare_csv(lo[lo.scope.eq('within_clock_common')],ref,['sample','clock','model','omitted_report'])
oldpairs=read('output/research_r15/evaluation/cnb_pairs.csv',ROOT)
oldpairs=oldpairs[oldpairs.model.isin(controls+['cnb'])]
compare_csv(read('cnb_pairs.csv').query('model in @controls or model == "cnb"'),oldpairs,['clock','report_date','quarter','model'])

projections=read('signal_projections.csv',EXP);signals=read('signal_coverage.csv');sb=read('signal_scoreboard.csv')
raw=read('data/core_split/broad_yoy.csv',ROOT).set_index('target_month');raw.index=pd.PeriodIndex(raw.index,freq='M')
z=100*np.log1p(raw/100);signal_error=0.
for row in signals.itertuples():
    t=pd.Period(row.origin,'M');vals=z[row.signal].reindex(pd.period_range(t+3*row.band+1,t+3*row.band+3,freq='M'))
    actual=float(vals.mean()) if np.isfinite(vals).all() else np.nan
    signal_error=max(signal_error,close([row.actual_z],[actual]),close([row.current_z],[z.loc[t-1,row.signal]]))
    assert row.unit=='annual_log_pp'
    assert row.included==bool(np.isfinite([row.current_z,row.projected_z,actual]).all())
assert len(signals)==90*2*4 and signals.origin.min()=='2019-02'
for row in sb.itertuples():
    group=signals[signals.signal.eq(row.signal)&signals.band.eq(row.band)]
    selected=mask(group.origin.to_numpy(),group.target.to_numpy(),row.sample);assert row.n_intended==int(selected.sum())
    group=group[selected&group.included]
    err=group.projection_error if row.model=='selected_projection' else group.persistence_error
    stats=[len(err),err.abs().mean(),np.sqrt((err**2).mean()),err.mean()]
    signal_error=max(signal_error,close([row.n,row.mae,row.rmse,row.bias],stats))

rev=read('revision_pairs.csv');own=frame.sort_values(['model','target','origin']).copy()
gg=own.groupby(['model','target']);own['previous_origin']=gg.origin.shift();own['previous_h']=gg.h.shift();own['previous_forecast']=gg.yy_exante.shift()
own['revision']=own.yy_exante-own.previous_forecast
gap=pd.PeriodIndex(own.origin,freq='M').asi8-pd.PeriodIndex(own.previous_origin,freq='M').asi8
own=own[(gap==1)&own.previous_h.eq(own.h+1)&np.isfinite(own.revision)]
compare_csv(rev,own,['origin','target','model'],['previous_origin','previous_h','previous_forecast','revision'])
assert rev.yy_actual.isna().any()

data=json.loads((EV/'replay_data.json').read_text(encoding='utf-8'));html=(EV/'cnb_rounds_replayed_r16.html').read_text(encoding='utf-8')
payload=html.split('const DATA = ',1)[1];embedded,_=json.JSONDecoder().raw_decode(payload)
assert {k:v for k,v in embedded.items() if k!='reports'}==data
assert embedded['reports']==data['reportsByClock']['report']
series=data['series'];assert [s['id'] for s in series if s['kind']=='model']==roster
assert len({s['label'] for s in series})==17
assert 'complete 15-model roster' in html and 'complete 14-model roster' not in html and '/*__DATA__*/null' not in html
assert 'R16' in data['title']
pairs=read('cnb_pairs.csv');source=read('forecasts.csv',EXP);actualseries=pd.Series(data['realised']);actualseries.index=pd.PeriodIndex(actualseries.index,freq='M')
artifact_paths=0;artifact_score_error=0.
for mode,reports in data['reportsByClock'].items():
    assert len(reports)==19
    for report in reports:
        group=pairs[pairs.clock.eq(mode)&pairs.report_date.eq(report['report_date'])]
        assert report['score']['n']==group.quarter.nunique()
        assert report['score']['quarters']==sorted(group.quarter.unique())
        for model,g in group.groupby('model'):artifact_score_error=max(artifact_score_error,close([report['score']['mae'][model]],[abs(g.error).mean()]))
        for model,points in report['paths'].items():
            values=source[source.origin.eq(report['origin'])&source.model.eq(model)].set_index('target').yy_exante
            for target,value in points:
                expected=actualseries.get(pd.Period(target,'M'),np.nan) if target<report['origin'] else values[target]
                artifact_score_error=max(artifact_score_error,close([value],[expected]));artifact_paths+=1
        for model,points in report['quarter_points'].items():
            path=source[source.origin.eq(report['origin'])&source.model.eq(model)].set_index('target').yy_exante
            for quarter,value in points:
                q=pd.Period(quarter,'Q');months=pd.period_range(q.asfreq('M','start'),q.asfreq('M','end'),freq='M')
                vals=[actualseries.get(t,np.nan) if str(t)<report['origin'] else path.get(str(t),np.nan) for t in months]
                artifact_score_error=max(artifact_score_error,close([value],[np.mean(vals)]))

result=dict(verified_hashes=checked,integrity_skipped=args.skip_integrity,score_rows_recomputed=score_rows,score_max_error=maximum_score_error,
    control_score_max_difference=control_score_error,r15_support_unchanged=True,core_band_max_error=band_error,
    core_turn_max_error=turn_error,cnb_pair_max_error=pair_error,cnb_omission_max_error=omission_error,
    signal_max_error=signal_error,revision_pairs_verified=len(rev),future_revisions_included=int(rev.yy_actual.isna().sum()),
    embedded_replay_equals_json=True,artifact_monthly_points=artifact_paths,artifact_score_max_error=artifact_score_error)
(OUT/'audit_summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
