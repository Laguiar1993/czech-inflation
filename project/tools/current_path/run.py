"""Current independent nowcast plus three h0–h12 paths, with offline replay.

Use --fixture with an explicit historical clock, or --live with an explicitly
refreshed --path-inputs directory. Saved research paths are never live inputs.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,io,json,sys,uuid
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from models.current_path import forecast_current_path,MODELS,aware_clock

PATH_FILES=('pipeline_log_levels.csv','pipeline_available_from.csv','pump_weekly.csv')
PATH_UNITS={'pipeline_log_levels.csv':'100_log_level_points',
            'pipeline_available_from.csv':'publication_timestamps',
            'pump_weekly.csv':'CZK_per_litre_gross_and_net'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc)


def clean_json(value):
    if isinstance(value,dict):return {str(k):clean_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [clean_json(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,(bool,np.bool_)):return bool(value)
    if isinstance(value,np.integer):return int(value)
    if isinstance(value,(pd.Timestamp,pd.Period,datetime,Path)):return str(value)
    return value


def dump(path,value):
    Path(path).write_text(json.dumps(clean_json(value),indent=2,allow_nan=False)+'\n',encoding='utf-8')


def first_release(target):
    calendar=pd.read_csv(ROOT/'data/release_calendar_cz_cpi.csv')
    row=calendar[calendar.target_month.eq(str(target))]
    if len(row)!=1 or not row.first_release_source.notna().all():
        raise ValueError('Missing explicit sourced first-release calendar row for '+str(target))
    return pd.Timestamp(row.iloc[0].first_release_dt).tz_localize('Europe/Prague')+pd.Timedelta(hours=9)


def read_monthly(path):
    data=pd.read_csv(path,index_col=0,float_precision='round_trip')
    data.index=pd.PeriodIndex(data.index,freq='M')
    if not data.index.is_unique or not data.index.is_monotonic_increasing or not data.columns.is_unique:
        raise ValueError('Unique chronological monthly keys required')
    return data


def load_path_inputs(folder):
    folder=Path(folder)
    if not (folder/'manifest.json').is_file():raise ValueError('Explicit path input manifest required')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema')!=1 or manifest.get('units')!=PATH_UNITS:
        raise ValueError('Unsupported path input schema/units')
    if set(manifest.get('files',{}))!=set(PATH_FILES) or not manifest.get('source_notes'):
        raise ValueError('Require exactly declared input files and source notes')
    # Parse precisely the bytes whose hashes were checked, not a second read
    # of paths that an upstream refresh could replace in the meantime.
    payloads={name:(folder/name).read_bytes() for name in PATH_FILES}
    for name,digest in manifest['files'].items():
        if hashlib.sha256(payloads[name]).hexdigest()!=digest:raise ValueError('Path input hash mismatch: '+name)
    levels=read_monthly(io.BytesIO(payloads[PATH_FILES[0]]));available=read_monthly(io.BytesIO(payloads[PATH_FILES[1]]))
    if list(levels)!=['agri4','food_ppi','food'] or list(available)!=list(levels) or not levels.index.equals(available.index):
        raise ValueError('Aligned agri4/food_ppi/food levels and availability required')
    pump=pd.read_csv(io.BytesIO(payloads[PATH_FILES[2]]),index_col=0,parse_dates=True,float_precision='round_trip')
    return levels,available,pump,manifest


def input_freshness(levels,available,target,as_of):
    """Audit normal pipeline lags; a supplied stale frame is never auto-current."""
    from core_split_experiment import publication_dates
    t=pd.Period(target,'M');clock=aware_clock(as_of)
    months=pd.period_range(t-24,t-1,freq='M');exceptions={1:9,3:4,4:4,6:1,12:1}
    food_dates=publication_dates(months);rows=[]
    for col in ('agri4','food_ppi','food'):
        schedule=[]
        for m in months:
            date=(m+1).to_timestamp()+pd.Timedelta(days=25 if col=='agri4' else 15+exceptions.get(m.month,0))
            if col=='food':date=food_dates.get(m,pd.NaT)
            if pd.notna(date) and date.tz_localize('Europe/Prague')<=clock:schedule.append(m)
        expected=max(schedule) if schedule else None
        usable=[]
        for m in levels.index[levels.index<t]:
            stamp=available[col].get(m)
            if pd.notna(stamp) and np.isfinite(levels.loc[m,col]):
                stamp=pd.Timestamp(stamp)
                stamp=stamp.tz_localize('Europe/Prague') if stamp.tzinfo is None else stamp
                if stamp<=clock:usable.append(m)
        # The VAR consumes changes. A recent level is insufficient if its
        # previous-month endpoint is absent or still unpublished.
        rate_months=[m for m in usable if m-1 in usable]
        level_edge=max(usable) if usable else None
        edge=max(rate_months) if rate_months else None
        stale=expected is None or edge is None or edge<expected
        rows.append(dict(series=col,expected_released_month=str(expected),latest_released_month=str(edge),
            latest_released_level_month=str(level_edge),stale=stale))
    return dict(ready=not any(r['stale'] for r in rows),series=rows,
        policy='Existing conservative publication rules; source updater must verify release changes')


def verify_path(actual,expected):
    keys=['origin','model','h'];a=actual.sort_values(keys).reset_index(drop=True);b=expected.sort_values(keys).reset_index(drop=True)
    if a.duplicated(keys).any() or b.duplicated(keys).any() or not a[keys+['target']].equals(b[keys+['target']]):
        raise ValueError('Path replay keys differ')
    if set(a.model)!=set(MODELS) or len(a)!=39 or set(a.columns)!=set(b.columns):raise ValueError('Path replay schema differs')
    columns=['mm_forecast','yy_exante']+[c for c in a if c.startswith(('weight_','value_','contribution_'))]
    for col in columns:
        if not np.allclose(a[col],b[col],rtol=0,atol=1e-10,equal_nan=True):
            raise ValueError('Path replay mismatch: '+col)
    for col in ['as_of_utc','status']:
        if col in a and not a[col].equals(b[col]):raise ValueError('Path replay metadata mismatch: '+col)


def source_hashes():
    import forecast_independent as old
    sources=old.code_inputs()
    for path in (ROOT/'tools/current_path').glob('*.py'):sources[path.relative_to(ROOT).as_posix()]=sha(path)
    sources['core_split_experiment.py']=sha(ROOT/'core_split_experiment.py')
    sources['independent_bridge_experiment.py']=sha(ROOT/'independent_bridge_experiment.py')
    return sources


def calculate(frames,meta):
    import forecast_independent as old
    target=pd.Period(meta['target'],'M');clock=meta['as_of']
    point=old.calculate(frames,target,clock,include_comparison=False)
    path=forecast_current_path(frames,frames['path_food_levels'],frames['path_food_available'],frames['path_pump'],
        target,clock,point['points_mm_pct']['HARD_BASE'],point['main_contributions_pp'])
    fresh=input_freshness(frames['path_food_levels'],frames['path_food_available'],target,clock)
    ready=bool(point['ready_for_first_release'] and path['diagnostics']['all_paths_finite'] and fresh['ready'] and not path['diagnostics']['fuel']['stale'])
    return point,path,dict(ready_at_decision=ready,food_inputs=fresh,path_fuel=path['diagnostics']['fuel'],
        current_path_engine_connected=True,models=MODELS)


def replay(folder):
    import forecast_independent as old
    folder=Path(folder);receipt=json.loads((folder/'receipt.json').read_text())
    required={'snapshot.json','forecast.json','path.csv','path.json','readiness.json'}
    if not required<=set(receipt):raise ValueError('Incomplete current path receipt')
    for name,digest in receipt.items():
        p=(folder/name).resolve()
        if not p.is_relative_to(folder.resolve()) or sha(p)!=digest:raise ValueError('Run receipt hash mismatch')
    frames,meta=old.load_snapshot(folder)
    if meta.get('path_engine')!='current-path-r20':raise ValueError('Not a current path run')
    point,path,ready=calculate(frames,meta)
    expected=json.loads((folder/'forecast.json').read_text())
    old.verify_points(point['points_mm_pct'],expected['points_mm_pct'])
    verify_path(path['monthly'],pd.read_csv(folder/'path.csv',float_precision='round_trip'))
    if clean_json(path['diagnostics'])!=json.loads((folder/'path.json').read_text())['diagnostics']:
        raise ValueError('Path diagnostic replay mismatch')
    saved=json.loads((folder/'readiness.json').read_text())
    if clean_json(ready)!=saved['at_decision']:raise ValueError('Readiness replay mismatch')
    old.load_snapshot(folder)
    return dict(status='replay_matched',models=MODELS,path_rows=39,nowcast_points=len(point['points_mm_pct']),tolerance=1e-10)


def capture(*,target,fixture,as_of=None,path_inputs=None,output=None):
    import forecast_independent as old
    started=now();clock=aware_clock(as_of) if fixture else pd.Timestamp(started)
    release=first_release(target)
    if clock>=release:raise ValueError('Decision must precede target first release')
    if fixture:
        from models.food_path_r14 import load_inputs
        levels,available,meta_food=load_inputs();frames=old.fixture_frames()
        pump_path=ROOT/'data/research_r14/fuel/pump_weekly.csv'
        pump=pd.read_csv(pump_path,index_col=0,parse_dates=True,float_precision='round_trip')
        input_notes=dict(kind='historical_fixture',food_manifest=meta_food,pump_sha256=sha(pump_path))
    else:
        if as_of is not None:raise ValueError('Live captures use the actual current clock')
        if path_inputs is None:raise ValueError('Live requires explicit refreshed --path-inputs')
        levels,available,pump,input_notes=load_path_inputs(path_inputs)
        frames=old.live_frames(pd.Period(target,'M'),old.decision_clock(clock))
    frames.update(path_food_levels=levels,path_food_available=available,path_pump=pump)
    destination=Path(output or ROOT/'output/current_runs')/(started.strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    meta=dict(path_engine='current-path-r20',target=str(target),as_of=clock.isoformat(),captured_at=started.isoformat(),
        capture_kind='historical_fixture' if fixture else 'live_snapshot',runtime=old.runtime_identity(),
        code_and_static_inputs=source_hashes(),include_comparison=False,include_path=True,path_input_provenance=input_notes)
    old.save_snapshot(destination,frames,meta)
    # Preserve the actual source/static bytes as well as their repo-relative
    # hashes. The original version can then be restored on another computer.
    for name,digest in meta['code_and_static_inputs'].items():
        payload=(ROOT/name).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('Source changed during capture')
        target_path=destination/'sources'/name;target_path.parent.mkdir(parents=True,exist_ok=True);target_path.write_bytes(payload)
    frozen,_=old.load_snapshot(destination)
    point,path,ready=calculate(frozen,meta);completed=now()
    prospective=bool(not fixture and ready['ready_at_decision'] and pd.Timestamp(completed)<release)
    point.update(completed_at=completed.isoformat(),completed_before_first_release=pd.Timestamp(completed)<release,
        prospective_eligible=prospective)
    dump(destination/'forecast.json',point)
    path['monthly'].to_csv(destination/'path.csv',index=False)
    dump(destination/'path.json',dict(version='current-path-r20',models=MODELS,diagnostics=path['diagnostics']))
    dump(destination/'readiness.json',dict(at_decision=ready,prospective_eligible=prospective,
        record_type='historical_replay' if fixture else 'prospective_candidate' if prospective else 'live_not_ready',
        completed_at=completed.isoformat(),first_release_at=release.isoformat(),
        limitation='Research models and reconstructed availability; no forecast accuracy promotion'))
    old.load_snapshot(destination)
    names=['snapshot.json','forecast.json','path.csv','path.json','readiness.json']
    names += [p.relative_to(destination).as_posix() for p in (destination/'sources').rglob('*') if p.is_file()]
    dump(destination/'receipt.json',{name:sha(destination/name) for name in names})
    return destination


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture',action='store_true');mode.add_argument('--live',action='store_true');mode.add_argument('--replay',type=Path)
    parser.add_argument('--target');parser.add_argument('--as-of');parser.add_argument('--path-inputs',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--archive-root',type=Path,default=ROOT/'output/current_path_archive')
    args=parser.parse_args(argv)
    if args.replay:print(json.dumps(replay(args.replay),indent=2));return
    if not args.target or args.fixture and not args.as_of:parser.error('target and explicit fixture as-of are required')
    destination=capture(target=args.target,fixture=args.fixture,as_of=args.as_of,path_inputs=args.path_inputs,output=args.output)
    readiness=json.loads((destination/'readiness.json').read_text())
    bundles=[]
    if args.fixture or readiness['prospective_eligible']:
        from tools.current_path.record import record_capture
        bundles=record_capture(destination,args.archive_root,'replay' if args.fixture else 'prospective')
    from tools.current_path.view import build
    view=build(destination)
    print(json.dumps({'run':str(destination),'chart':str(view),'bundles':bundles,'readiness':readiness},indent=2))


if __name__=='__main__':main()
