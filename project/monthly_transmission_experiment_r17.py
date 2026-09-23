"""Frozen R17 monthly category and generated-pressure experiment; offline only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.core_split import load_frozen
from models import monthly_transmission_r17 as engine
from models.path_inputs import compound_path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r17_monthly'
SPEC='docs/implementation/R17_MONTHLY_SPEC_2026-09-14.md'
FAST='STATE_FAST_R15'
PRIOR={'output/research_r13/core_path/native_forecasts.csv':'CORE_SPLIT_MONTHLY_R13',
       'output/research_r16/native_forecasts.csv':'TRANSMISSION_BOTH_R16'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [clean(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,np.integer):return int(value)
    return value


def dump(path,value):Path(path).write_text(json.dumps(clean(value),indent=2,allow_nan=False)+'\n',encoding='utf-8')


def read(name):return pd.read_csv(ROOT/name,float_precision='round_trip')


def verify_manifest(root,path):
    root=Path(root);path=Path(path);m=json.loads(path.read_text(encoding='utf-8'));result={path.relative_to(root).as_posix():sha(path)}
    for group in ('inputs','outputs'):
        base=root if group=='inputs' else path.parent
        for name,expected in m[group].items():
            actual=sha(base/name)
            if actual!=expected:raise ValueError(f'Preserved {group} hash mismatch: {name}')
            result[(base/name).relative_to(root).as_posix()]=actual
    return result


def dependencies():
    result={}
    for m in ('output/research_r15/manifest.json','output/research_r16/manifest.json'):
        result.update(verify_manifest(ROOT,ROOT/m))
    package=json.loads((ROOT/'data/core_split/manifest.json').read_text())
    for name,record in package['files'].items():
        path=ROOT/'data/core_split'/name
        if sha(path)!=record['sha256']:raise ValueError('Category package hash mismatch: '+name)
        result[path.relative_to(ROOT).as_posix()]=record['sha256']
    for source in PRIOR:
        m=Path(source).parent/'manifest.json';meta=json.loads((ROOT/m).read_text());expected=meta['outputs'][Path(source).name]
        if sha(ROOT/source)!=expected:raise ValueError('Prior forecast output hash mismatch: '+source)
        result[source]=expected;result[m.as_posix()]=sha(ROOT/m)
    names=['models/monthly_transmission_r17.py','monthly_transmission_experiment_r17.py',
           'tests/test_monthly_transmission_r17.py',SPEC,'data/core_split.py','data/core_split/manifest.json',
           'models/food_path_r14.py','models/path_inputs.py','data/vintages.py','models/trend_gap.py']
    result.update({name:sha(ROOT/name) for name in names})
    return dict(sorted(result.items()))


def publication(index):
    frame=read('data/release_calendar_cz_cpi.csv').set_index('target_month')
    frame.index=pd.PeriodIndex(frame.index,freq='M')
    if not frame.index.is_unique:raise ValueError('Duplicate detail release dates')
    dates=pd.to_datetime(frame.detail_release_dt).dt.normalize()+pd.Timedelta(hours=9)
    return dates.reindex(index)


def integrate_core(base,predictions,headline):
    outputs=[];contributions=['contribution_'+c for c in ('core','food','administered','alcohol_tobacco','fuel','wedge')]
    invariant=[c for c in base if c.startswith('weight_') or (c.startswith('value_') and c!='value_core') or (c.startswith('contribution_') and c!='contribution_core')]
    for (origin,name),group in predictions.groupby(['origin','model'],sort=False):
        source=base.loc[base.origin.eq(origin)].sort_values('h').copy()
        if source.empty:continue
        if list(source.h)!=list(range(13)) or sorted(group.h)!=list(range(1,13)):raise ValueError('Complete original/changed calendar required')
        changed=source.copy();changed['model']=name;g=group.set_index('h')
        changed['core_model_status']=changed.h.map(g.status).fillna('preserved_h0');changed['core_fallback_reason']=changed.h.map(g.reason).fillna('')
        changed['core_fallback_used']=changed.core_model_status.str.startswith('fallback')
        for h in range(1,13):
            mask=changed.h.eq(h);value=g.loc[h,'core_mm']
            changed.loc[mask,'value_core']=value;changed.loc[mask,'contribution_core']=changed.loc[mask,'weight_core']*value
            changed.loc[mask,'mm_forecast']=changed.loc[mask,contributions].sum(axis=1,min_count=6)
        changed.loc[changed.h.gt(0),'fallback_used']=changed.loc[changed.h.gt(0),'fallback_used'].astype(bool)|changed.loc[changed.h.gt(0),'core_fallback_used']
        changed.loc[changed.h.gt(0),'status']=np.where(np.isfinite(changed.loc[changed.h.gt(0),'mm_forecast']),'research_estimated','unavailable')
        changed.loc[changed.h.gt(0),'converged']=np.isfinite(changed.loc[changed.h.gt(0),'mm_forecast'])
        pd.testing.assert_frame_equal(source[invariant],changed[invariant],check_exact=True)
        assert source.mm_forecast.iloc[0]==changed.mm_forecast.iloc[0]
        path=changed.set_index('h').mm_forecast.to_dict();t=pd.Period(origin,'M')
        for index,row in changed.iterrows():
            h=int(row.h);changed.loc[index,'yy_exante']=compound_path(headline.loc[headline.index<t],path,t,h,path[0])
            changed.loc[index,'yy_conditional']=compound_path(headline.loc[headline.index<t],path,t,h,headline.get(t,np.nan))
            for suffix,values in [('forecast',[path[k] for k in range(1,h+1)]),('actual',headline.reindex(pd.period_range(t+1,t+h,freq='M')).to_numpy() if h else [])]:
                array=np.asarray(values,dtype=float)
                changed.loc[index,'cumulative_log_'+suffix]=float(100*np.log1p(array/100).sum()) if np.isfinite(array).all() and (array>-100).all() else np.nan
        outputs.append(changed)
    return pd.concat(outputs,ignore_index=True)


def add_cumulative(frame):
    rows=[]
    for _,group in frame.groupby(['origin','model','component'],sort=False):
        group=group.sort_values('h');forecasts=[];actuals=[];fallback=False
        for row in group.to_dict('records'):
            forecasts.append(row['log_forecast']);actuals.append(row['log_actual']);fallback|=row['status'].startswith('fallback')
            row['cumulative_fallback']=fallback
            for suffix,values in [('forecast',forecasts),('actual',actuals)]:
                total=float(sum(values)) if np.isfinite(values).all() else np.nan
                row['cumulative_log_'+suffix]=total;row['cumulative_pct_'+suffix]=float(100*np.expm1(total/100))
            rows.append(row)
    return pd.DataFrame(rows)


def scores(frame,control):
    rows=[]
    for component,data in frame.groupby('component',sort=False):
        names=sorted(data.model.unique())
        for sample in ('full','recent_origins','recent_targets'):
            selected=data if sample=='full' else data.loc[data.origin.ge('2024-01') if sample=='recent_origins' else data.target.ge('2024-01')]
            for h in range(13):
                subset=selected if h==0 else selected.loc[selected.h.eq(h)]
                if subset.empty:continue
                keys=['origin','h']
                for metric in ('mm','cumulative_log','cumulative_pct'):
                    f=metric+'_forecast';a=metric+'_actual';wide=subset.pivot(index=keys,columns='model',values=f).reindex(columns=names)
                    actual=subset.loc[subset.model.eq(control)].set_index(keys)[a].reindex(wide.index)
                    primary=np.isfinite(actual)&np.isfinite(wide[control]);common=primary&np.isfinite(wide).all(axis=1)
                    for scope,mask in [('primary_control_calendar',primary),('common',common)]:
                        calendar=wide.index[mask]
                        for name in names:
                            own=subset.loc[subset.model.eq(name)].set_index(keys);paired=own.reindex(calendar);error=paired[f]-paired[a];finite=np.isfinite(error);e=error.loc[finite]
                            fallback=paired.status.fillna('').str.startswith('fallback') if metric=='mm' else paired.cumulative_fallback.fillna(False)
                            rows.append(dict(component=component,scope=scope,sample=sample,h=h,horizon_label='pooled_h1_12' if h==0 else f'h{h}',metric=metric,model=name,
                                             n_rows_total=len(own),n_unavailable_targets=int((~np.isfinite(own[a])).sum()),n_intended=len(calendar),n_scored=int(finite.sum()),
                                             n_missing_forecasts=int((~np.isfinite(paired[f])).sum()),n_fallback=int(fallback.sum()),
                                             rmse=float(np.sqrt(np.mean(e*e))) if len(e) else np.nan,mae=float(e.abs().mean()) if len(e) else np.nan,bias=float(e.mean()) if len(e) else np.nan))
    return pd.DataFrame(rows)


def _record_fits(result,collector,calendars):
    for original in result:
        row=original.copy();training=row.pop('training');key=f"{row['origin']}|{row['h']}"
        if key in calendars and calendars[key]!=training:raise AssertionError('Shared family training calendars differ')
        calendars[key]=training;row['training_calendar_id']=key;collector.append(row)


def run(destination=OUT,end='2026-07'):
    destination=Path(destination)
    if destination.exists():raise FileExistsError('Refusing to overwrite '+str(destination))
    end=str(pd.Period(end,'M'))
    if not '2019-02'<=end<='2026-07':raise ValueError('End must be an original outer origin')
    hashes=dependencies();package=load_frozen();levels=package['levels'];weights=package['weights'];available=publication(levels.index)
    r15=json.loads((ROOT/'output/research_r15/states.json').read_text());macro=read('output/research_r15/features_by_origin.csv').set_index('origin')
    all_origins=list(map(str,pd.period_range('2016-02',end,freq='M')));outer=list(map(str,pd.period_range('2019-02',end,freq='M')))
    baseline=read('output/research_r15/native_forecasts.csv').query('model == @FAST');baseline=baseline.loc[baseline.origin.isin(outer)].copy()
    control=read('output/research_r16/forecasts.csv').query('model == @FAST');control=control.loc[control.origin.isin(outer)].copy()
    joined=baseline.merge(control,on=['origin','h'],suffixes=('_native','_saved'))
    if len(joined)!=13*len(outer) or not np.array_equal(joined.mm_forecast_native,joined.mm_forecast_saved,equal_nan=True):raise AssertionError('FAST control parity failed')
    for origin in outer:
        if engine._aware(r15[origin]['as_of'])!=engine._aware(baseline.loc[baseline.origin.eq(origin),'as_of_utc'].iloc[0]):raise AssertionError('Own-origin clock mismatch')
    destination.mkdir(parents=True)
    dump(destination/'declaration.json',dict(declared_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,specification=SPEC,
        models=engine.CORE_MODELS,stage1_families=engine.FAMILIES,domestic=engine.DOMESTIC,imported=engine.IMPORTED,
        category_penalties={'own':.1,'macro':1.},core_penalties={'own':1.,'generated':10.},min_train=24,window=96,
        source_definition=package['metadata'],outer_origins=outer,first_snapshot=all_origins[0],last_snapshot=end,parameter_selection='none_fixed'))
    print(f'Verified {len(hashes)} source/control hashes; pre-fit declaration saved.',flush=True)
    saved={s:engine.snapshot(levels,available,weights,macro.loc[s].to_dict(),s,r15[s]['as_of']) for s in all_origins}
    core_states={s:dict(as_of=engine._aware(r15[s]['as_of']).isoformat(),own=[r15[s]['x']['core3']-r15[s]['filter_states']['fast']['mu'],r15[s]['x']['core1']-r15[s]['x']['core3']],
                        fast_log=[r15[s]['forecasts_log']['fast'][str(h)] for h in range(1,13)]) for s in all_origins}
    dump(destination/'snapshots.json',saved);dump(destination/'core_states.json',core_states)
    generated={};generated_status={};first_rows=[];first_fits=[];first_calendars={}
    for i,s in enumerate(all_origins):
        result=engine.first_stage(saved,levels,available,s,r15[s]['as_of']);generated[s]=result['pressure_log'];generated_status[s]=result['status']
        _record_fits(result['fits'],first_fits,first_calendars)
        for family,path in result['category_log'].items():
            for h,log_values in enumerate(path,1):
                for j,category in enumerate(engine.CATEGORIES):
                    first_rows.append(dict(origin=s,as_of_utc=engine._aware(saved[s]['as_of']).tz_convert('UTC').isoformat(),target=str(pd.Period(s,'M')+h),h=h,
                        family=family,model=f'CATEGORY_{family.upper()}_R17',component=category,log_forecast=float(log_values[j]),mm_forecast=float(100*np.expm1(log_values[j]/100)),
                        status=result['status'][family][h-1],reason=result['reasons'][family][h-1],outer_origin=s in outer,weight_fraction=saved[s]['weights'][j]))
                signal=result['signals'][family][h-1]
                first_rows.append(dict(origin=s,as_of_utc=engine._aware(saved[s]['as_of']).tz_convert('UTC').isoformat(),target=str(pd.Period(s,'M')+h),h=h,
                    family=family,model=f'CATEGORY_{family.upper()}_R17',component='covered_pressure',log_forecast=signal['pressure_log'],mm_forecast=signal['pressure_mm'],
                    status=result['status'][family][h-1],reason=result['reasons'][family][h-1],outer_origin=s in outer,weight_fraction=signal['coverage_fraction'],
                    contribution_diagnostic=signal['contribution_diagnostic']))
        if i%12==0 or i==len(all_origins)-1:print(f'Pooled category stage {i+1}/{len(all_origins)}: {s}',flush=True)
    first=pd.DataFrame(first_rows);first.to_csv(destination/'firststage_predictions.csv',index=False)
    dump(destination/'generated_signals.json',generated);dump(destination/'generated_status.json',generated_status)
    dump(destination/'firststage_fits.json',first_fits);dump(destination/'firststage_training_calendars.json',first_calendars)
    lineage={n:sha(destination/n) for n in ('firststage_predictions.csv','generated_signals.json','generated_status.json','snapshots.json')}
    dump(destination/'stage2_declaration.json',dict(declared_at=datetime.now(timezone.utc).isoformat(),generated_inputs=lineage,
        input_semantics='Saved own-origin pressure LOG forecasts minus same-origin persistence LOG forecasts; no actual category regressor'))
    # Read the on-disk generated forecast artifact, making the second-stage lineage explicit.
    generated=json.loads((destination/'generated_signals.json').read_text());generated_status=json.loads((destination/'generated_status.json').read_text())
    core=read('tests/fixtures/cleanup/cnb_core_mm.csv').set_index('period').core;core.index=pd.PeriodIndex(core.index,freq='M');core_available=publication(core.index)
    core_rows=[];second_fits=[];second_calendars={};reconciliation=[]
    for i,s in enumerate(all_origins):
        result=engine.second_stage(core_states,generated,generated_status,core,core_available,s,r15[s]['as_of'])
        _record_fits(result['fits'],second_fits,second_calendars)
        for family,path in result['core_log'].items():
            pressure_family='persistence' if family=='own' else family
            for h,value in enumerate(path,1):
                mm=float(100*np.expm1(value/100));target=str(pd.Period(s,'M')+h);p=100*np.expm1(generated[s][pressure_family][h-1]/100)
                core_rows.append(dict(origin=s,as_of_utc=engine._aware(r15[s]['as_of']).tz_convert('UTC').isoformat(),target=target,h=h,family=family,model=engine.CORE_MODELS[family],
                                      core_log=value,core_mm=mm,status=result['status'][family][h-1],reason=result['reasons'][family][h-1],outer_origin=s in outer))
                reconciliation.append(dict(origin=s,target=target,h=h,model=engine.CORE_MODELS[family],pressure_family=pressure_family,core_mm_forecast=mm,pressure_mm_forecast=p,
                                           statistical_remainder_forecast=engine.remainder(mm,p),definition='Statistical difference; not an uncovered core component'))
        if i%24==0 or i==len(all_origins)-1:print(f'Generated core stage {i+1}/{len(all_origins)}: {s}',flush=True)
    predictions=pd.DataFrame(core_rows);predictions.to_csv(destination/'core_predictions.csv',index=False)
    dump(destination/'secondstage_fits.json',second_fits);dump(destination/'secondstage_training_calendars.json',second_calendars)
    headline=read('output/independent_path_frozen_inputs.csv').set_index('period').headline_mm;headline.index=pd.PeriodIndex(headline.index,freq='M')
    native=integrate_core(baseline,predictions.loc[predictions.outer_origin],headline);native.to_csv(destination/'native_forecasts.csv',index=False)
    fc=['origin','h','target','as_of_utc','model','mm_forecast','mm_actual','yy_actual','yy_exante','cumulative_log_forecast','cumulative_log_actual']
    pd.concat([native[fc],control[fc]],ignore_index=True).to_csv(destination/'forecasts.csv',index=False)
    # Outcome joining follows all saved forecasts and does not feed either model stage.
    actual_rates=100*np.log(levels/levels.shift());first_out=first.loc[first.outer_origin].copy();actuals=[]
    for row in first_out.itertuples():
        target=pd.Period(row.target,'M');values=actual_rates.reindex([target]).to_numpy()[0]
        actuals.append(engine.pressure(values,saved[row.origin]['weights'])['pressure_log'] if row.component=='covered_pressure' else values[engine.CATEGORIES.index(row.component)])
    first_out['log_actual']=actuals;first_out['mm_actual']=100*np.expm1(first_out.log_actual/100);first_out=add_cumulative(first_out)
    first_out.to_csv(destination/'firststage_outcomes.csv',index=False);first_scores=scores(first_out,'CATEGORY_PERSISTENCE_R17');first_scores.to_csv(destination/'firststage_summary.csv',index=False)
    core_out=predictions.loc[predictions.outer_origin].rename(columns={'core_log':'log_forecast','core_mm':'mm_forecast'}).copy();core_out['component']='core'
    references=[]
    for source,name in [('output/research_r15/native_forecasts.csv',FAST),*PRIOR.items()]:
        frame=read(source);g=frame.loc[frame.model.eq(name)&frame.origin.isin(outer)&frame.h.between(1,12),['origin','target','h','model','value_core']].rename(columns={'value_core':'mm_forecast'})
        g['log_forecast']=100*np.log1p(g.mm_forecast/100);g['component']='core';g['status']='preserved_control';g['reason']='';references.append(g)
    core_out=pd.concat([core_out,*references],ignore_index=True);core_out['mm_actual']=[core.get(pd.Period(t,'M'),np.nan) for t in core_out.target]
    core_out['log_actual']=100*np.log1p(core_out.mm_actual/100);core_out=add_cumulative(core_out);core_out.to_csv(destination/'core_outcomes.csv',index=False)
    main=core_out.loc[core_out.model.isin([FAST,*engine.CORE_MODELS.values()])];core_summary=scores(main,FAST);core_summary.to_csv(destination/'core_summary.csv',index=False)
    scores(core_out,FAST).to_csv(destination/'prior_core_comparison_scores.csv',index=False)
    rec=pd.DataFrame(reconciliation);rec=rec.loc[rec.origin.isin(outer)].copy();rec['core_mm_actual']=[core.get(pd.Period(t,'M'),np.nan) for t in rec.target]
    pressure_actual=first_out.loc[first_out.component.eq('covered_pressure')].drop_duplicates(['origin','h']).set_index(['origin','h']).mm_actual
    rec['pressure_mm_actual']=[pressure_actual.loc[(r.origin,r.h)] for r in rec.itertuples()]
    rec['statistical_remainder_actual']=rec.core_mm_actual-rec.pressure_mm_actual;rec.to_csv(destination/'statistical_reconciliation.csv',index=False)
    for name,digest in lineage.items():
        if sha(destination/name)!=digest:raise AssertionError('Generated stage-one artifact changed in stage two')
    if dependencies()!=hashes:raise AssertionError('Source/code changed during fit')
    validation=dict(status='passed',origin_count=len(outer),snapshot_count=len(saved),h0_noncore_values_weights_exact=True,fast_r15_r16_exact=True,
                    firststage_saved_before_secondstage=True,generated_lineage_hashes_verified=lineage,
                    firststage_rows=len(first),core_prediction_rows=len(predictions),native_rows=len(native),
                    firststage_outer_missing=int((~np.isfinite(first.loc[first.outer_origin,'mm_forecast'])).sum()),
                    core_outer_missing=int((~np.isfinite(predictions.loc[predictions.outer_origin,'core_mm'])).sum()),
                    full_run=end=='2026-07',not_a_core_partition=True)
    dump(destination/'validation.json',validation)
    dump(destination/'manifest.json',dict(completed_at=datetime.now(timezone.utc).isoformat(),inputs=hashes,outputs={p.name:sha(p) for p in sorted(destination.iterdir()) if p.is_file() and p.name!='manifest.json'},
        models=list(engine.CORE_MODELS.values()),origin_count=len(outer),snapshot_count=len(saved),parameters_selected='none_fixed',
        packages={p:importlib.metadata.version(p) for p in ('numpy','pandas')},definition='Tax-including service pressure proxy, current history with reconstructed availability; not an official core partition'))
    selected=first_scores.loc[first_scores.scope.eq('primary_control_calendar')&first_scores['sample'].eq('full')&first_scores.component.eq('covered_pressure')&first_scores.h.eq(0)&first_scores.metric.eq('mm')]
    print(selected[['model','n_intended','n_scored','n_fallback','rmse','bias']].to_string(index=False),flush=True)
    selected=core_summary.loc[core_summary.scope.eq('primary_control_calendar')&core_summary['sample'].eq('full')&core_summary.h.eq(0)&core_summary.metric.eq('mm')]
    print(selected[['model','n_intended','n_scored','n_fallback','rmse','bias']].to_string(index=False),flush=True)
    return validation


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUT);parser.add_argument('--end',default='2026-07')
    args=parser.parse_args();run(args.output,args.end)
