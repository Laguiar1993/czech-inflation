"""Re-estimate the accepted R27 path from explicitly refreshed, verified inputs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd
from tools.live_bundle_r32 import adapter
from tools.live_bundle_r32.runner import calendar_scope
from tools.forecast_updates_r33 import workflow
from tools.current_path.run import clean_json
from models.path_inputs import compound_path

ROOT=Path(__file__).resolve().parents[2]
BLOCKS=('core','food','administered','alcohol_tobacco','fuel','wedge')
MODEL_IDS={'STATE_FAST_R15':'ROSTER_R27','STABLE_LOCAL_CORE_R14B':'LOCAL_CORE_R27_SENSITIVITY','DAMPED_P95_Q001_R16':'GENTLE_CORE_R27_SENSITIVITY'}
PRIMARY='ROSTER_R27'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def utcnow():return datetime.now(timezone.utc)
def dump(path,value):Path(path).write_text(json.dumps(clean_json(value),ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')

def known_history(series,origin):
    t=pd.Period(origin,'M')
    if not isinstance(series.index,pd.PeriodIndex) or not series.index.is_unique or not series.index.is_monotonic_increasing:
        raise ValueError('Ordered unique monthly history required')
    known=series.loc[series.index<t].copy()
    needed=pd.period_range(t-12,t-1,freq='M')
    recent=known.reindex(needed)
    if len(known)<12 or not np.isfinite(recent).all() or (recent<=-100).any():
        raise ValueError('Complete positive-gross-rate twelve-month history required')
    return known

def validate_table(table,h0):
    if table.empty or table.duplicated(['model','h']).any():raise ValueError('Empty or duplicate forecast horizon')
    for _,g in table.groupby('model',sort=False):
        g=g.sort_values('h')
        if list(g.h)!=list(range(13)) or g.origin.nunique()!=1:raise ValueError('Complete h0-h12 horizon required')
        origin=pd.Period(g.origin.iloc[0],'M')
        if list(g.target)!=[str(origin+h) for h in range(13)]:raise ValueError('Forecast target labels do not match origin/horizon')
        if float(g.iloc[0].mm_forecast)!=float(h0):raise ValueError('Recorded h0 nowcast was changed')
        cols=['contribution_'+b for b in BLOCKS]
        if not np.isfinite(g[cols+['mm_forecast','yy_exante']].to_numpy()).all():raise ValueError('Nonfinite forecast or contribution')
        if not np.allclose(g[cols].sum(axis=1),g.mm_forecast,atol=1e-10,rtol=0):raise ValueError('Component contributions do not reconcile')
        if (g.mm_forecast<=-100).any() or (g.yy_exante<=-100).any():raise ValueError('Nonpositive price-level gross rate')
    return True

def apply_food(base,food_path,history):
    if set(food_path)!=set(range(1,13)) or not np.isfinite(list(food_path.values())).all():raise ValueError('Twelve finite future food rates required')
    rows=[]
    for model,g in base.groupby('model',sort=False):
        g=g.sort_values('h').copy().reset_index(drop=True)
        if list(g.h)!=list(range(13)):raise ValueError('Complete horizon required')
        t=pd.Period(g.origin.iloc[0],'M');known=known_history(history,t)
        for h in range(1,13):
            value=float(food_path[h]);g.loc[h,'value_food']=value
            g.loc[h,'contribution_food']=g.loc[h,'weight_food']*value
            g.loc[h,'mm_forecast']=sum(float(g.loc[h,'contribution_'+b]) for b in BLOCKS)
        forecasts=dict(zip(g.h,g.mm_forecast));h0=float(forecasts[0])
        g['yy_exante']=[compound_path(known,forecasts,t,h,h0) for h in range(13)]
        g['model']=MODEL_IDS.get(model,model)
        rows.append(g)
    result=pd.concat(rows,ignore_index=True)
    validate_table(result,float(base[base.h.eq(0)].mm_forecast.iloc[0]))
    return result

def compute(frames,levels,available,pump,history,origin,as_of,h0,components,calendar):
    import cz_struct
    from models.current_path import forecast_current_path
    from models.food_drift_r24 import LONG_HISTORY,long_food_rates,candidates_at as drift_at
    from models.food_ecm_r27 import candidates_at as ecm_at
    t=pd.Period(origin,'M');known=known_history(history,t)
    frames={k:v.copy(deep=True) for k,v in frames.items()}
    frames['path_headline']=known.rename('headline_mm').to_frame()
    with calendar_scope(cz_struct,calendar):
        base=forecast_current_path(frames,levels,available,pump,t,as_of,h0,components)
        rates,published=long_food_rates(levels,available,ROOT/LONG_HISTORY)
        drift=drift_at(levels,available,rates,published,t,as_of)
        if drift['status']!='estimated':raise ValueError('R24 food drift unavailable: '+drift['status'])
        ecm=ecm_at(levels,available,t,as_of,np.asarray(drift['log_rates']['FOOD_NORM_SHIFT_R24']),fixed_alphas=())
        if ecm['status']!='estimated' or 'FOOD_ECM_R27' not in ecm['paths']:raise ValueError('R27 food correction unavailable')
    # The primary model must be complete. Alternative core recipes remain sensitivities.
    base_table=base['monthly'];available_models=[];unavailable_models=[]
    for model,g in base_table.groupby('model',sort=False):
        if np.isfinite(g[['mm_forecast','yy_exante']].to_numpy()).all():available_models.append(model)
        else:unavailable_models.append(model)
    if 'STATE_FAST_R15' not in available_models:raise ValueError('Primary FAST path is unavailable')
    valid=base_table[base_table.model.isin(available_models)].copy()
    table=apply_food(valid,ecm['paths']['FOOD_ECM_R27'],known)
    diagnostics=dict(base=base['diagnostics'],food_drift=drift,food_ecm=ecm,
                     unavailable_sensitivities=unavailable_models,primary_model=PRIMARY,
                     sensitivity_note='Alternative core recipes with the same food path; not promoted models or a probability interval.')
    return table,base_table,diagnostics

def load_inputs(directory,origin,as_of):
    as_of=as_of.isoformat() if isinstance(as_of,(datetime,pd.Timestamp)) else as_of
    directory=Path(directory).resolve();raw=(directory/'MANIFEST.json').read_bytes()
    manifest=json.loads(raw);files=adapter.checked_files(directory,manifest['files'])
    monthly=lambda name:adapter.csv_frame(adapter.required(files,name),name)
    levels=monthly('food_levels.csv').reindex(columns=['agri4','food_ppi','food'])
    available=pd.read_csv(io.BytesIO(adapter.required(files,'food_available.csv')),index_col=0)
    available.index=pd.PeriodIndex(available.index,freq='M');available=available.reindex(columns=levels.columns)
    if not levels.index.equals(available.index) or available.index.has_duplicates:raise ValueError('Food level/availability alignment required')
    pump=adapter.csv_frame(adapter.required(files,'pump_weekly.csv'),'pump',monthly=False)
    history=known_history(monthly('headline_history.csv').headline_mm,origin)
    prov=json.loads(adapter.required(files,'provenance.json'))
    # Preparation/capture timestamps are a conservative availability bound for this snapshot.
    for key in ('as_of','prepared_at','available_from','completed_at'):
        if prov.get(key) and workflow.clock(prov[key])>workflow.clock(as_of):raise ValueError('Path inputs prepared or captured after decision clock')
    t=pd.Period(origin,'M')
    if not levels.index.equals(pd.period_range(levels.index.min(),t-1,freq='M')):raise ValueError('Food calendar must end at origin-1')
    for col in levels:
        dates=pd.to_datetime(available[col],utc=True,errors='coerce')
        if (levels[col].notna() & dates.isna()).any():raise ValueError('Every observed food level requires availability')
        used=levels[col].where(dates.le(pd.Timestamp(as_of)))
        if col=='food' and (pd.isna(used.loc[t-1]) or pd.isna(used.loc[t-2])):raise ValueError('Consumer food history is not current')
    return levels,available,pump,history,prov,files,raw

def freshness_gate(levels,available,origin,as_of,calendar):
    import cz_struct
    from tools.current_path.run import input_freshness
    with calendar_scope(cz_struct,calendar):
        audit=input_freshness(levels,available,origin,as_of)
    if not audit['ready']:raise ValueError('Stale path upstream inputs: '+str(audit['series']))
    return audit

def record_sources():
    from tools.current_path.run import source_hashes
    from models.food_drift_r24 import LONG_HISTORY
    hashes=source_hashes()
    hashes[LONG_HISTORY]=sha(ROOT/LONG_HISTORY)
    for p in Path(__file__).parent.glob('*'):
        if p.is_file():hashes[p.relative_to(ROOT).as_posix()]=sha(p)
    return hashes

def record(bundle,path_inputs,nowcast_run,output,*,rehearsal=False,as_of=None):
    started=utcnow();stamp=workflow.clock(as_of) if as_of else started
    if stamp>started or (not rehearsal and as_of is not None):raise ValueError('Prospective path uses the actual recording clock')
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():raise ValueError('Choose a new output directory within the repository')
    nowcast_run=Path(nowcast_run).resolve();bundle=Path(bundle).resolve();path_inputs=Path(path_inputs).resolve()
    if not all(p.is_relative_to(ROOT) for p in (nowcast_run,bundle,path_inputs)):raise ValueError('Inputs must be within the repository')
    h0_record=workflow.load_run(nowcast_run);origin=h0_record['target']
    if h0_record['mode']!='prospective' or workflow.clock(h0_record['as_of'])>stamp:raise ValueError('A previously recorded prospective h0 is required')
    if stamp>=workflow.clock(h0_record['forecast']['first_release']):raise ValueError('Target first release already reached')
    h0_inputs=json.loads((nowcast_run/'inputs.json').read_bytes())
    _,_,bundle_prov=workflow.bundle_evidence(bundle,h0_inputs['bundle_manifest_sha256'])
    workflow.check_bundle_availability(dict(mode='prospective',as_of=stamp.isoformat()),bundle_prov)
    loaded=adapter.load_bundle(bundle,ROOT)
    from .inputs import load_prepared
    load_prepared(path_inputs,as_of=stamp.isoformat())
    levels,available,pump,history,provenance,input_bytes,path_manifest=load_inputs(path_inputs,origin,stamp)
    local=adapter.decision_clock(stamp)
    calendar,calendar_info=adapter.load_calendar(ROOT/'data/release_calendar_cz_cpi.csv',nowcast_run/'live_calendar.csv',local)
    freshness=freshness_gate(levels,available,origin,stamp.isoformat(),calendar)
    frames,fx=adapter.prepare_frames(loaded,pd.Period(origin,'M'),local,calendar)
    ready=adapter.readiness(frames,pd.Period(origin,'M'),local,calendar,fx)
    if not ready['data_ready']:raise ValueError('Nowcast bundle is not ready for the path: '+str(ready['reasons']))
    # Pin code/statics and all source bytes before computation.
    code=record_sources()
    sources={}
    for folder in (bundle,path_inputs,nowcast_run):
        for p in folder.rglob('*'):
            if p.is_file():sources[p.relative_to(ROOT).as_posix()]=sha(p)
    point=float(h0_record['forecast']['point']);components=h0_record['forecast']['components']
    table,base,diagnostics=compute(frames,levels,available,pump,history,origin,stamp.isoformat(),point,components,calendar)
    diagnostics['input_freshness']=freshness
    if diagnostics['base']['fuel']['stale']:raise ValueError('Path pump inputs are stale')
    completed=utcnow()
    if completed>=workflow.clock(h0_record['forecast']['first_release']):raise ValueError('Path completed after first release')
    for name,digest in {**sources,**code}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Input or implementation changed while calculating: '+name)
    output.mkdir(parents=True)
    (output/'.gitattributes').write_text('* -text\n',encoding='utf-8')
    table.to_csv(output/'path.csv',index=False)
    base.to_csv(output/'base_paths.csv',index=False)
    history.rename('headline_mm').to_csv(output/'headline_history.csv',index_label='period')
    dump(output/'diagnostics.json',diagnostics)
    snapshot=dict(schema='current-path-r34/v1',mode='rehearsal' if rehearsal else 'prospective',origin=origin,
                  as_of=stamp.isoformat(),recorded_at=started.isoformat(),completed_at=completed.isoformat(),
                  primary_model=PRIMARY,h0=point,h0_as_of=h0_record['as_of'],h0_run=nowcast_run.relative_to(ROOT).as_posix(),
                  path_input_directory=path_inputs.relative_to(ROOT).as_posix(),nowcast_bundle=bundle.relative_to(ROOT).as_posix(),
                  first_release=h0_record['forecast']['first_release'],available_models=table.model.unique().tolist(),
                  headline_history_end=str(history.index.max()),calendar=calendar_info,
                  source_provenance=provenance,note='Fresh September-origin R27 path; h0 anchored to the separately recorded same-day HARD_BASE run. No accuracy promotion.')
    dump(output/'snapshot.json',snapshot)
    manifest=dict(schema='current-path-r34/manifest-v1',inputs=sources,code=code,
                  outputs={p.name:sha(p) for p in output.iterdir() if p.is_file()})
    dump(output/'manifest.json',manifest)
    return dict(directory=str(output),origin=origin,mode=snapshot['mode'],h0=point,
                h12=float(table[(table.model==PRIMARY)&table.h.eq(12)].yy_exante.iloc[0]))

def load_record(directory):
    directory=Path(directory).resolve();manifest=json.loads((directory/'manifest.json').read_bytes())
    if manifest.get('schema')!='current-path-r34/manifest-v1':raise ValueError('Unsupported path manifest schema')
    files=adapter.checked_files(directory,manifest['outputs'])
    adapter.checked_files(ROOT,manifest['inputs']);adapter.checked_files(ROOT,manifest['code'])
    meta=json.loads(adapter.required(files,'snapshot.json'))
    if meta.get('schema')!='current-path-r34/v1' or meta.get('mode') not in ('prospective','rehearsal'):raise ValueError('Unsupported path record schema/mode')
    as_of,recorded,completed,release=(workflow.clock(meta[k]) for k in ('as_of','recorded_at','completed_at','first_release'))
    if not as_of<=recorded<=completed<=utcnow() or completed>=release:raise ValueError('Invalid, future or reversed path clocks')
    if meta['mode']=='prospective' and as_of!=recorded:raise ValueError('Prospective decision must equal actual recording clock')
    h0_dir=adapter.safe_path(ROOT,meta['h0_run']);bundle=adapter.safe_path(ROOT,meta['nowcast_bundle']);path_inputs=adapter.safe_path(ROOT,meta['path_input_directory'])
    for folder,name in ((h0_dir,'MANIFEST.json'),(bundle,'MANIFEST.json'),(path_inputs,'MANIFEST.json')):
        if (folder/name).relative_to(ROOT).as_posix() not in manifest['inputs']:raise ValueError('Referenced record/input manifest is not pinned')
    h0=workflow.load_run(h0_dir)
    if h0['mode']!='prospective' or h0['target']!=meta['origin'] or h0['forecast']['point']!=meta['h0']:raise ValueError('Path h0 does not match recorded nowcast')
    if h0['as_of']!=meta['h0_as_of'] or workflow.clock(h0['completed_at'])>as_of or workflow.clock(h0['forecast']['first_release'])!=release:raise ValueError('Path and recorded h0 clock/release evidence differ')
    expected=json.loads((h0_dir/'inputs.json').read_bytes())['bundle_manifest_sha256']
    _,_,prov=workflow.bundle_evidence(bundle,expected)
    workflow.check_bundle_availability(dict(mode='prospective',as_of=meta['as_of']),prov)
    from .inputs import load_prepared
    load_prepared(path_inputs,as_of=meta['as_of'])
    levels,available,pump,_,_,_,_=load_inputs(path_inputs,meta['origin'],meta['as_of'])
    calendar,_=adapter.load_calendar(ROOT/'data/release_calendar_cz_cpi.csv',h0_dir/'live_calendar.csv',adapter.decision_clock(meta['as_of']))
    freshness_gate(levels,available,meta['origin'],meta['as_of'],calendar)
    from models.food_drift_r24 import LONG_HISTORY
    if LONG_HISTORY not in manifest['code'] and LONG_HISTORY not in manifest['inputs']:raise ValueError('Long food-history source is not pinned')
    table=pd.read_csv(io.BytesIO(adapter.required(files,'path.csv')),float_precision='round_trip')
    if not table.origin.eq(meta['origin']).all() or 'as_of_utc' not in table or not pd.to_datetime(table.as_of_utc,utc=True).eq(pd.Timestamp(as_of)).all():raise ValueError('Path row origin/clock differs from metadata')
    if set(table.model)!=set(meta['available_models']) or meta['primary_model']!=PRIMARY or PRIMARY not in set(table.model):raise ValueError('Path model identity differs')
    validate_table(table,meta['h0'])
    for b in BLOCKS:
        if not np.allclose(table.loc[table.h.eq(0),'contribution_'+b],h0['forecast']['components'][b],atol=1e-12,rtol=0):raise ValueError('Path h0 contribution differs from recorded nowcast')
    history=adapter.csv_frame(adapter.required(files,'headline_history.csv'),'history').headline_mm
    known=known_history(history,meta['origin'])
    for _,g in table.groupby('model'):
        g=g.sort_values('h');mapping=dict(zip(g.h,g.mm_forecast))
        expected=[compound_path(known,mapping,meta['origin'],h,meta['h0']) for h in range(13)]
        if not np.allclose(g.yy_exante,expected,atol=1e-10,rtol=0):raise ValueError('Recorded annual path does not compound from its history')
    return meta,table,history

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bundle','path-inputs','nowcast-run','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--rehearsal',action='store_true');p.add_argument('--as-of')
    a=p.parse_args();print(json.dumps(record(a.bundle,a.path_inputs,a.nowcast_run,a.output,rehearsal=a.rehearsal,as_of=a.as_of)))
if __name__=='__main__':main()
