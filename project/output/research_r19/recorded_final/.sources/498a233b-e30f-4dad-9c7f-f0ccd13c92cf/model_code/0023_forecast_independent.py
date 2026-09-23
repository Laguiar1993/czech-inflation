"""Independent nowcast entry point with one decision clock and frozen replay.

Examples:
  python forecast_independent.py --fixture --target 2026-07 --as-of 2026-08-04T23:59:00+02:00
  python forecast_independent.py --live --target 2026-09
  python forecast_independent.py --replay output/runs/<run>

Database/X13 locations are configurable with CZ_CPI_DB and CZ_X13_PATH.
The live loader captures existing local data and refreshes only source loaders
which already do so. It does not promise that every upstream table is current.
"""
from pathlib import Path
import argparse
import hashlib
import json
import uuid
import importlib.metadata
import platform

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
VERSION='independent-r9-2026-09-09'


def decision_clock(as_of):
    ts=pd.Timestamp(as_of)
    if ts.tzinfo is None:
        raise ValueError('as_of must include a timezone')
    return ts.tz_convert('Europe/Prague').tz_localize(None)


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_identity():
    import cz_struct as s
    packages=('numpy','pandas','scipy','scikit-learn','statsmodels','quantile-forest')
    binary=Path(s.la._X13_PATH)
    return {'python':platform.python_version(),
            'packages':{p:importlib.metadata.version(p) for p in packages},
            'x13_sha256':_hash(binary) if binary.is_file() else None}


def verify_points(actual, expected):
    if set(actual)!=set(expected):raise ValueError('replay point names differ')
    for name,value in actual.items():
        if not np.isfinite(value) or not np.isfinite(expected[name]):
            raise ValueError(f'nonfinite replay point: {name}')
        if abs(value-expected[name])>1e-10:raise ValueError(f'replay mismatch: {name}')


def component_edges(series, target, clock):
    import cz_struct as s
    result={}
    for name,values in series.items():
        edge=s._eligible_edge(values.dropna().index,target-1,clock)
        result[name]={'latest_released_value':str(edge) if edge is not None else None,
                      'gap_months':(target-1-edge).n if edge is not None else None}
    return result


def code_inputs():
    paths=[ROOT/'cz_struct.py',ROOT/'config.py',ROOT/'forecast_independent.py',
           ROOT/'independent_path_experiment.py']
    if (ROOT/'independent_bridge_experiment.py').is_file():paths.append(ROOT/'independent_bridge_experiment.py')
    for sub in ('models','data','evaluation'):
        paths+=list((ROOT/sub).glob('*.py'))
    # Announcement/release calendars and legacy comparison history are inputs.
    paths+=list((ROOT/'data').glob('*.csv'))
    paths+=list((ROOT/'data/vintages').glob('*.csv.gz'))
    return {str(p.relative_to(ROOT)).replace('\\','/'):_hash(p) for p in sorted(set(paths))}


def save_snapshot(folder, frames, metadata):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=False)
    hashes={}
    schema={}
    for name,frame in frames.items():
        if not name.replace('_','').isalnum():
            raise ValueError('invalid frame name')
        if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise ValueError(f'frame {name} requires unique chronological observations')
        path=folder/f'{name}.csv'
        frame.to_csv(path,index_label='period')
        hashes[path.name]=_hash(path)
        schema[name]='monthly' if isinstance(frame.index,pd.PeriodIndex) else 'datetime'
    meta={**metadata,'frame_schema':schema,'hashes':hashes}
    (folder/'snapshot.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')


def load_snapshot(folder):
    folder=Path(folder)
    meta=json.loads((folder/'snapshot.json').read_text(encoding='utf-8'))
    frames={}
    for name,sha in meta['hashes'].items():
        path=folder/name
        if path.parent.resolve()!=folder.resolve() or _hash(path)!=sha:
            raise ValueError(f'snapshot hash mismatch: {name}')
        frame=pd.read_csv(path,index_col=0,float_precision='round_trip')
        key=path.stem
        frame.index=(pd.PeriodIndex(frame.index,freq='M') if meta['frame_schema'][key]=='monthly'
                     else pd.to_datetime(frame.index))
        frames[key]=frame
    for name,sha in meta.get('code_and_static_inputs',{}).items():
        path=ROOT/name
        if not path.is_file() or _hash(path)!=sha:
            raise ValueError(f'code/static input hash mismatch: {name}; use the original version to replay')
    if 'runtime' in meta and runtime_identity()!=meta['runtime']:
        raise ValueError('runtime or X13 binary differs from the archived forecast')
    return frames,meta


def fixture_frames():
    from independent_nowcast_experiment import read
    names={'headline':'target_headline_cpi_mm.csv','components':'component_food_fuel_mm.csv',
           'core':'cnb_core_mm.csv','regulated':'cnb_regulated_mm.csv','alcohol':'alcohol_tobacco.csv',
           'features':'core_features.csv','food_features':'food_block_features.csv'}
    frames={k:read(v) for k,v in names.items()}
    folder=ROOT/'tests/fixtures/cleanup'
    for name,sha in json.loads((folder/'MANIFEST.json').read_text()).items():
        if _hash(folder/name)!=sha:raise ValueError(f'fixture hash mismatch {name}')
    weekly=pd.read_csv(folder/'fuel_weekly.csv',index_col=0,float_precision='round_trip')
    weekly.index=pd.to_datetime(weekly.index)
    frames['weekly_fuel']=weekly
    return frames


def live_frames(target, as_of):
    import cz_struct as s
    y,comp,core,reg,features,_,food_features,_=s.load_all()
    features=s._mask_row_by_availability(features,target,as_of)
    # The declared fixing rule excludes all call-day fixings.
    mtd=pd.DataFrame(columns=['eurczk_mm','eurczk_mm_x_state'],index=pd.PeriodIndex([],freq='M'),dtype=float)
    if target in features.index and pd.isna(features.loc[target,'eurczk_mm']):
        value,n=s._eurczk_mtd_mm(target,as_of,s.la.load_fx_monthly_levels()['EUR'])
        if np.isfinite(value):
            features.loc[target,'eurczk_mm']=value
            features.loc[target,'eurczk_mm_x_state']=value*features.loc[target,'state']
            mtd.loc[target]=features.loc[target,['eurczk_mm','eurczk_mm_x_state']]
    return {'headline':y.to_frame(),'components':comp,'core':core.to_frame(),
            'regulated':reg.to_frame(),'alcohol':s.load_alc_tobacco_mm().to_frame(),
            'features':features,'food_features':s._mask_row_by_availability(food_features,target,as_of),
            'weekly_fuel':s.la.fetch_weekly_fuels_live(),'gated_mtd_fx':mtd}


def calculate(frames,target,as_of,include_comparison=False):
    """All changing observations supplied in frames; one Prague decision time."""
    import cz_struct as s
    from models.independent_nowcast import policy_frame,sequential_errors,residual_correction
    from models.components import fuel_mm_from_weekly
    clock=decision_clock(as_of)
    y=frames['headline'].iloc[:,0]
    comp=frames['components']
    core=frames['core'].iloc[:,0].rename('core')
    reg=frames['regulated'].iloc[:,0].rename('reg')
    alc=frames['alcohol'].iloc[:,0]
    x=s._mask_row_by_availability(frames['features'],target,clock)
    f=s._mask_row_by_availability(frames['food_features'],target,clock)
    # The live MTD override was already gated at capture time; preserve it.
    if 'gated_mtd_fx' in frames and target in frames['gated_mtd_fx'].index:
        for c in ('eurczk_mm','eurczk_mm_x_state'):x.loc[target,c]=frames['gated_mtd_fx'].loc[target,c]
    if target not in x.index:raise ValueError(f'no feature row for {target}; refresh source data')
    wm=s.solve_weights(y,comp,core,reg,target-1,as_of=clock,alc=alc)
    w=wm[s._regime(target)]
    fp=s.food_forecast(comp.food,f,target,as_of=clock)
    food_diag=dict(s.FOOD_DIAG)
    ap=s.alc_forecast(alc,target,target-1,as_of=clock)
    ad=s.admin_forecast(reg,target,as_of=clock,announce_mode='documented',w_adm=w['administered'])
    wk=s._fuel_inputs_as_of(frames['weekly_fuel'],None,clock)[0]
    fuel,fd=fuel_mm_from_weekly(wk,target,petrol_share=s._petrol_share(target,clock))
    support=pd.concat([y,comp[['food','fuel']],core,reg],axis=1).dropna().iloc[:,0]
    wd=s._wedge_at(s._weighted_wedge(y,comp,alc,core,reg,support,wm,as_of=clock),target,target-1)
    contributions={'food':w['food']*fp,'alcohol_tobacco':w['alc']*ap,
                   'administered':w['administered']*ad,'fuel':w['fuel']*fuel,'wedge':wd}
    rest=sum(contributions.values())
    points,detail={},{}
    for policy in ('hard','sentiment'):
        xp=policy_frame(x,policy)
        cp=s._ridge_predict(xp,core,target,as_of=clock)[0]
        errors=sequential_errors(frames['features'],core,policy,through=target-1)
        corr,diag=residual_correction(xp,errors,target,clock,policy)
        base=rest+w['core']*cp
        points.update({f'{policy.upper()}_BASE':base,f'{policy.upper()}_HALF':base+.5*w['core']*corr,
                       f'{policy.upper()}_FULL':base+w['core']*corr})
        detail[policy]={'core_prediction':cp,'core_correction':corr,
                       'core_contribution':w['core']*cp,'error_history_sha256':hashlib.sha256(errors.to_csv().encode()).hexdigest(),
                       'residual_forest':diag}
    if include_comparison:
        cp=s._ridge_predict(x,core,target,as_of=clock)[0]
        corr=s.restored_pe_correction(x,core,target,clock)
        points.update(OPTIONAL_EXPECTATIONS_BASE=rest+w['core']*cp,
                      OPTIONAL_EXPECTATIONS_HALF=rest+w['core']*(cp+.5*corr),
                      OPTIONAL_EXPECTATIONS_FULL=rest+w['core']*(cp+corr))
    missing=[]
    for block,frame in [('core',policy_frame(x,'hard')),('food',f)]:
        for col in frame.columns:
            if pd.isna(frame.loc[target,col]):
                missing.append({'block':block,'variable':col,'status':s._classify_missing(col,target,clock)})
    edge=s._eligible_edge(y.dropna().index,target-1,clock)
    gap=None if edge is None else (target-1-edge).n
    release=s._first_release_dt(target)
    before=bool(pd.notna(release) and clock<release)
    edges=component_edges({'core':core,'regulated':reg,'food':comp.food,
                           'official_fuel':comp.fuel,'alcohol_tobacco':alc},target,clock)
    latest_due=min(clock-pd.Timedelta(days=7),target.to_timestamp(how='end'))
    mondays=pd.date_range((target-1).to_timestamp(),latest_due,freq='W-MON')
    usable_weekly=wk.loc[wk.index<=target.to_timestamp(how='end'),['petrol95','diesel']].dropna()
    fuel_stale=bool(len(mondays) and (usable_weekly.empty or usable_weekly.index.max().normalize()<mondays[-1].normalize()))
    fd.update(last_observation=str(usable_weekly.index.max()) if len(usable_weekly) else None,
              last_due_observation=str(mondays[-1]) if len(mondays) else None,stale=fuel_stale)
    ready=bool(before and gap==0 and all(z['gap_months']==0 for z in edges.values())
               and not fuel_stale and not any(z['status']=='STALE' for z in missing)
               and all(np.isfinite(v) for v in points.values()))
    return {'version':VERSION,'target':str(target),'as_of':pd.Timestamp(as_of).isoformat(),
            'main_model':'HARD_BASE','points_mm_pct':points,
            'main_contributions_pp':{'core':detail['hard']['core_contribution'],**contributions},
            'weights':w,'diagnostics':detail,'food_diagnostics':food_diag,'fuel_diagnostics':fd,
            'component_history_edges':edges,'missing_inputs':missing,
            'ready_for_first_release':ready,'before_first_release':before,'detailed_CPI_edge_gap':gap,
            'limitations':['latest-vintage inputs with publication rules; prospective archives start with this run',
                           'historical energy mapping remains reconstructed',
                           'no calibrated forecast interval or validated trading position rule']}


def calculate_path(frames, result):
    """Share the exact independent h0 and clock with all path comparisons."""
    import cz_struct as s
    from independent_path_experiment import forecast_origin
    from independent_bridge_experiment import forecast_bridge
    from models.path_inputs import compound_path
    from evaluation.path_calendar import complete_quarters
    target=pd.Period(result['target'],freq='M')
    clock=decision_clock(result['as_of'])
    h0=result['points_mm_pct']['HARD_BASE']
    y=frames['path_headline'].iloc[:,0]
    y=y[[s._cpi_family_released_by(t,clock) for t in y.index]]
    fx=frames['path_fx'].iloc[:,0]
    fitted=forecast_origin(y,fx,target,result['as_of'],h0)
    bridge=forecast_bridge(frames,target,result['as_of'],h0)
    # Bridge API is a pure monthly path plus its contributions/diagnostics.
    paths={**fitted['paths'],'BRIDGE_HARD':bridge['path']}
    history=fitted['history']
    known_yoy=(1+history/100).rolling(12).apply(np.prod,raw=True).sub(1).mul(100)
    records=[]
    quarters={}
    for model,path in paths.items():
        future={target+h:compound_path(history,path,target,h,h0) for h in range(13)}
        quarters[model]={str(k):v for k,v in complete_quarters(known_yoy,pd.Series(future)).items()}
        for h in range(13):
            records.append({'model':model,'target':str(target+h),'h':h,'mm_pct':path[h],
                            'yoy_pct':future[target+h]})
    return {'status':'research','primary_model':'BRIDGE_HARD','origin':str(target),'as_of':result['as_of'],
            'h0_model':'HARD_BASE','h0':h0,'monthly':records,'complete_quarters_yoy':quarters,
            'diagnostics':fitted['diagnostics'],'bridge_diagnostics':bridge.get('diagnostics',{}),
            'inputs':fitted['inputs'],'production_certified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture',action='store_true')
    mode.add_argument('--live',action='store_true')
    mode.add_argument('--replay',type=Path)
    parser.add_argument('--target');parser.add_argument('--as-of')
    parser.add_argument('--include-expectations-comparison',action='store_true')
    parser.add_argument('--path',action='store_true',help='also calculate the independent research paths from the same archive')
    parser.add_argument('--archive-root',type=Path,default=ROOT/'output/runs')
    args=parser.parse_args()
    started=pd.Timestamp.now(tz='UTC')
    if args.replay:
        frames,meta=load_snapshot(args.replay)
        result=calculate(frames,pd.Period(meta['target'],freq='M'),meta['as_of'],meta.get('include_comparison',False))
        expected=json.loads((args.replay/'forecast.json').read_text())
        receipt=json.loads((args.replay/'receipt.json').read_text())
        for name,sha in receipt.items():
            if _hash(args.replay/name)!=sha:raise ValueError(f'archive receipt hash mismatch: {name}')
        verify_points(result['points_mm_pct'],expected['points_mm_pct'])
        if meta.get('include_path'):
            path=calculate_path(frames,result)
            saved=json.loads((args.replay/'path.json').read_text())
            actual_points={f"{r['model']}_{r['h']}":r['mm_pct'] for r in path['monthly']}
            expected_points={f"{r['model']}_{r['h']}":r['mm_pct'] for r in saved['monthly']}
            verify_points(actual_points,expected_points)
        load_snapshot(args.replay)
        print(json.dumps({'replay':'matched','points_mm_pct':result['points_mm_pct']},indent=2))
        return
    if not args.target:parser.error('--target YYYY-MM is required')
    if args.live and args.as_of:parser.error('--live uses the current capture clock; past dates require an archived snapshot')
    if args.fixture and not args.as_of:parser.error('--fixture requires an explicit historical --as-of with timezone')
    as_of=args.as_of or started.isoformat()
    clock=decision_clock(as_of);target=pd.Period(args.target,freq='M')
    frames=fixture_frames() if args.fixture else live_frames(target,clock)
    if args.path:
        if args.fixture:
            saved=pd.read_csv(ROOT/'output/independent_path_frozen_inputs.csv',index_col=0,float_precision='round_trip')
            saved.index=pd.PeriodIndex(saved.index,freq='M')
            frames['path_headline']=saved[['headline_mm']]
            frames['path_fx']=saved[['eurczk']].dropna()
        else:
            import cz_struct as s
            frames['path_headline']=s.la.load_headline_cpi_mm_extended().to_frame()
            frames['path_fx']=s.la.load_fx_monthly_levels()[['EUR']]
    folder=args.archive_root/(started.strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    meta={'as_of':as_of,'target':str(target),'captured_at':started.isoformat(),
          'capture_kind':'historical_fixture' if args.fixture else 'live_snapshot',
          'include_comparison':args.include_expectations_comparison,'include_path':args.path,'code_and_static_inputs':code_inputs(),
          'runtime':runtime_identity()}
    save_snapshot(folder,frames,meta)
    # Read back the exact serialized inputs so live and offline replay share them.
    frozen,_=load_snapshot(folder)
    result=calculate(frozen,target,as_of,args.include_expectations_comparison)
    verify_points(result['points_mm_pct'],result['points_mm_pct'])
    receipt_files=['forecast.json','snapshot.json']
    if args.path:
        path_result=calculate_path(frozen,result)
    # Refuse a completed receipt if code, data or runtime changed during fitting.
    load_snapshot(folder)
    if args.path:
        (folder/'path.json').write_text(json.dumps(path_result,indent=2,default=str))
        pd.DataFrame(path_result['monthly']).to_csv(folder/'path.csv',index=False)
        receipt_files+=['path.json','path.csv']
    result['completed_at']=pd.Timestamp.now(tz='UTC').isoformat()
    import cz_struct as s
    release=s._first_release_dt(target)
    result['completed_before_first_release']=bool(pd.notna(release) and decision_clock(result['completed_at'])<release)
    result['prospective_eligible']=bool(args.live and result['ready_for_first_release']
                                       and result['completed_before_first_release'])
    (folder/'forecast.json').write_text(json.dumps(result,indent=2,default=str))
    (folder/'receipt.json').write_text(json.dumps({name:_hash(folder/name) for name in receipt_files},indent=2))
    print(json.dumps(result,indent=2,default=str))
    print(f'Archived inputs and result: {folder}')


if __name__=='__main__':main()
