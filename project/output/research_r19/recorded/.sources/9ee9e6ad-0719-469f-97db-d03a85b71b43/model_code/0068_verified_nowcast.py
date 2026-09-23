"""Validate an existing independent nowcast run and bind it to a sealed archive.

No forecast fitting, source refresh or path-model substitution occurs here.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,re,sys
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.research_r18 import forecast_archive as archive

REQUIRED_FRAMES=('headline','components','core','regulated','alcohol','features','food_features','weekly_fuel')
COMPONENTS=('core','regulated','food','official_fuel','alcohol_tobacco')
POINTS=('HARD_BASE','HARD_HALF','HARD_FULL')
CONTRIBUTIONS=('core','food','alcohol_tobacco','administered','fuel','wedge')


def _utc_now():return datetime.now(timezone.utc)
def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def _runtime():
    from forecast_independent import runtime_identity
    return runtime_identity()


def _stamp(value):
    try:stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (AttributeError,TypeError,ValueError) as exc:raise ValueError('Invalid timestamp') from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:raise ValueError('Timestamp requires timezone')
    return stamp.astimezone(timezone.utc)


def _child(root,name):
    if not isinstance(name,str) or not name:raise ValueError('Invalid artifact path')
    root=Path(root).resolve();p=(root/name).resolve()
    if Path(name).is_absolute() or not p.is_relative_to(root):raise ValueError('Unsafe artifact path')
    if not p.is_file():raise ValueError('Missing artifact path: '+name)
    return p


def _verify_map(base,mapping):
    if not isinstance(mapping,dict) or not mapping:raise ValueError('Missing artifact hash map')
    result={}
    for name,digest in mapping.items():
        p=_child(base,name)
        if _sha(p)!=digest:raise ValueError('Artifact hash mismatch: '+name)
        result[str(p)]=digest
    return result


def _finite(value):return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value)


def inspect_run(run,*,mode,root=ROOT):
    if mode not in ('replay','prospective'):raise ValueError('Explicit replay/prospective mode required')
    run=Path(run).resolve();root=Path(root).resolve();now=_utc_now()
    receipt=_json(run/'receipt.json')
    if not {'snapshot.json','forecast.json'}<=set(receipt):raise ValueError('Incomplete engine receipt')
    checked=_verify_map(run,receipt)
    meta=_json(run/'snapshot.json');result=_json(run/'forecast.json')
    for name in REQUIRED_FRAMES:
        if name+'.csv' not in meta['hashes']:raise ValueError('Missing required frame: '+name)
    checked.update(_verify_map(run,meta['hashes']))
    if 'forecast_independent.py' not in meta['code_and_static_inputs']:raise ValueError('Missing independent engine hash')
    checked.update(_verify_map(root,meta['code_and_static_inputs']))
    if not meta.get('runtime') or _runtime()!=meta['runtime']:raise ValueError('Recorded runtime differs')
    target=meta['target']
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',target) or target!=result.get('target'):
        raise ValueError('Inconsistent target')
    calendar=root/'data/release_calendar_cz_cpi.csv'
    with calendar.open(encoding='utf-8-sig',newline='') as f:
        events=[r for r in csv.DictReader(f) if r['target_month']==target]
    if len(events)!=1 or not events[0].get('first_release_source'):raise ValueError('Missing or ambiguous sourced first-release calendar')
    event=events[0]
    release=datetime.fromisoformat(event['first_release_dt']).replace(hour=9,tzinfo=ZoneInfo('Europe/Prague')).astimezone(timezone.utc)
    decision=_stamp(meta['as_of']);completed=_stamp(result['completed_at']);captured=_stamp(meta['captured_at'])
    if decision!=_stamp(result['as_of']):raise ValueError('Inconsistent decision clock')
    if decision>=release:raise ValueError('Decision at/after first release')
    if completed<captured or completed<decision or completed>now:raise ValueError('Invalid completion chronology')
    if result.get('version')!='independent-r9-2026-09-09' or result.get('main_model')!='HARD_BASE':
        raise ValueError('Unsupported independent primary model/version')
    points={k:result.get('points_mm_pct',{}).get(k) for k in POINTS}
    if not all(_finite(v) for v in points.values()):raise ValueError('All three independent points must be finite')
    contrib=result.get('main_contributions_pp',{})
    if set(contrib)!=set(CONTRIBUTIONS) or not all(_finite(v) for v in contrib.values()):raise ValueError('Invalid contribution schema')
    if not math.isclose(math.fsum(contrib.values()),points['HARD_BASE'],rel_tol=0,abs_tol=1e-10):
        raise ValueError('Primary contribution sum differs from point')
    if mode=='prospective':
        if meta.get('capture_kind')!='live_snapshot':raise ValueError('Prospective requires live capture')
        if (now-completed).total_seconds()>120:raise ValueError('Stale completion; run the model again')
        if now>=release:raise ValueError('First release has already occurred')
        for key in ['ready_for_first_release','before_first_release','completed_before_first_release','prospective_eligible']:
            if result.get(key) is not True:raise ValueError('Forecast is not ready: '+key)
        edges=result.get('component_history_edges',{})
        if set(edges)!=set(COMPONENTS) or any(z.get('gap_months')!=0 for z in edges.values()):
            raise ValueError('Stale or missing component history')
        if result.get('detailed_CPI_edge_gap')!=0:raise ValueError('Stale headline history')
        if result.get('fuel_diagnostics',{}).get('stale') is not False:raise ValueError('Stale or unknown fuel input')
        if any(z.get('status')=='STALE' for z in result.get('missing_inputs',[])):raise ValueError('Stale feature input')
    manifest_paths=[run/'snapshot.json',run/'receipt.json',run/'forecast.json']
    static=[root/n for n in meta['code_and_static_inputs']]
    code=[p for p in static if p.suffix=='.py']+[Path(__file__).resolve(),Path(archive.__file__).resolve()]
    data=[p for p in static if p.suffix!='.py']+[run/n for n in meta['hashes']]
    if calendar.resolve() not in [p.resolve() for p in data]:data.append(calendar)
    artifacts={k:sorted(set(str(p.resolve()) for p in items)) for k,items in
               [('model_code',code),('inputs',data),('source_manifests',manifest_paths)]}
    for items in artifacts.values():
        for path in items:checked.setdefault(path,_sha(path))
    return dict(mode=mode,target=target,points=points,contributions=contrib,
        engine_decision_at_utc=decision.isoformat(),engine_completed_at_utc=completed.isoformat(),
        capture_kind=meta['capture_kind'],verified_at_utc=now.isoformat(),first_release_at_utc=release.isoformat(),
        release_kind=event['first_release_kind'],release_source=event['first_release_source'],
        runtime=meta['runtime'],artifacts=artifacts,checked_hashes=checked,
        path_status='latest_audited_path_runtime_not_connected')


def record_run(run,archive_root,*,mode,root=ROOT):
    info=inspect_run(run,mode=mode,root=root)
    # Preserve the exact verified source bytes. Otherwise an unrelated source
    # refresh between validation and hashing could bind the wrong vintage.
    staging=Path(archive_root).resolve()/'.sources'/str(uuid4());staging.mkdir(parents=True,exist_ok=False)
    copied={};source_map={}
    for role,paths in info['artifacts'].items():
        copied[role]=[]
        destination=staging/role;destination.mkdir()
        for i,source in enumerate(paths):
            payload=Path(source).read_bytes()
            if hashlib.sha256(payload).hexdigest()!=info['checked_hashes'][source]:raise ValueError('Source hash changed after validation')
            target=destination/(str(i).zfill(4)+'_'+Path(source).name)
            with target.open('xb') as f:f.write(payload)
            copied[role].append(target);source_map[str(target)]=source
    observed=_utc_now();issued=observed if mode=='prospective' else _stamp(info['engine_decision_at_utc'])
    if mode=='prospective' and (observed-_stamp(info['engine_completed_at_utc'])).total_seconds()>120:
        raise ValueError('Stale completion after source snapshot; no forecast committed')
    availability={str(p):dict(available_from=issued.isoformat(),
        availability_kind='observed_at_verification' if mode=='prospective' else 'historical_rule_assumption',
        actual_observed_at_utc=observed.isoformat(),original_path=source_map[str(p)])
        for role in ('inputs','source_manifests') for p in copied[role]}
    metadata={k:info[k] for k in ['engine_decision_at_utc','engine_completed_at_utc','capture_kind','release_kind','release_source','runtime','path_status']}
    metadata.update(units={'point':'monthly_CPI_percent','contributions':'percentage_points'},
        independent_comparisons=info['points'],main_contributions_pp=info['contributions'],source_path_map=source_map,
        caveat='Verifies recorded bytes and engine receipt; no certification of original historical vintages, data refresh completeness or calibrated trading signals.')
    bundle=archive.archive_forecast(archive_root,mode=mode,issued_at=issued,target_origin=info['target'],
        target_first_release_at=info['first_release_at_utc'],model='HARD_BASE',point_forecast=info['points']['HARD_BASE'],
        artifact_paths=copied,data_availability=availability,metadata=metadata)
    archive.verify_bundle(bundle,verify_artifacts=True)
    return bundle


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path);p.add_argument('--mode',required=True,choices=['replay','prospective'])
    p.add_argument('--archive-root',type=Path,default=ROOT/'output/recorded_forecasts');p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if args.dry_run:
        info=inspect_run(args.run,mode=args.mode)
        print(json.dumps({k:v for k,v in info.items() if k not in ['artifacts','checked_hashes']},indent=2))
    else:print(json.dumps({'bundle':str(record_run(args.run,args.archive_root,mode=args.mode))},indent=2))


if __name__=='__main__':main()
