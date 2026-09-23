"""Bind a current nowcast/path capture to the existing append-only archive."""
from pathlib import Path
import argparse,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from models.current_path import MODELS,BLOCKS,aware_clock
from tools.current_path.run import now,sha,first_release
from tools.research_r18 import forecast_archive as archive


def validate_paths(frame,target,h0):
    if len(frame)!=39 or set(frame.model)!=set(MODELS) or frame.duplicated(['model','h']).any():
        raise ValueError('Complete unique current model/horizon roster required')
    if set(frame.origin)!={target}:raise ValueError('Path origin differs from nowcast target')
    for model,group in frame.groupby('model'):
        if sorted(group.h)!=list(range(13)):raise ValueError('Exactly h0–h12 horizons required')
        expected=[str(pd.Period(target,'M')+int(h)) for h in group.h]
        if list(group.target)!=expected:raise ValueError('Path target/horizon mismatch')
        if not np.isclose(group.loc[group.h.eq(0),'mm_forecast'].iloc[0],h0,atol=1e-10,rtol=0):
            raise ValueError('Path h0 differs from independent nowcast')
    columns=['mm_forecast','yy_exante']+['contribution_'+b for b in BLOCKS]
    if not np.isfinite(frame[columns]).all().all():raise ValueError('Nonfinite path/contribution cannot be issued')
    if not np.allclose(frame[['contribution_'+b for b in BLOCKS]].sum(axis=1),frame.mm_forecast,atol=1e-10,rtol=0):
        raise ValueError('Contribution sum differs from monthly path')


def record_capture(run,archive_root,mode):
    import forecast_independent as old
    if mode not in ('replay','prospective'):raise ValueError('Explicit replay/prospective mode required')
    run=Path(run).resolve();frames,meta=old.load_snapshot(run)
    receipt=json.loads((run/'receipt.json').read_text())
    required={'snapshot.json','forecast.json','path.json','path.csv','readiness.json'}
    if not required<=set(receipt):raise ValueError('Incomplete current capture receipt')
    for name,digest in receipt.items():
        path=(run/name).resolve()
        if not path.is_relative_to(run) or sha(path)!=digest:raise ValueError('Capture receipt mismatch')
    if meta.get('path_engine')!='current-path-r20':raise ValueError('Unsupported path engine')
    point=json.loads((run/'forecast.json').read_text());ready=json.loads((run/'readiness.json').read_text())
    table=pd.read_csv(run/'path.csv',float_precision='round_trip');h0=point['points_mm_pct']['HARD_BASE']
    validate_paths(table,meta['target'],h0)
    if point.get('main_model')!='HARD_BASE' or point['as_of']!=meta['as_of']:
        raise ValueError('Independent nowcast/clock identity mismatch')
    if not pd.to_datetime(table.as_of_utc,utc=True).eq(pd.Timestamp(meta['as_of']).tz_convert('UTC')).all():
        raise ValueError('Path decision clocks differ')
    observed=now();completed=aware_clock(point['completed_at'])
    captured=aware_clock(meta['captured_at']);decision=aware_clock(meta['as_of'])
    if completed<captured or completed<decision or completed>pd.Timestamp(observed):
        raise ValueError('Invalid capture/completion chronology')
    release=first_release(meta['target'])
    if mode=='prospective':
        if decision!=captured:raise ValueError('Live decision must equal actual capture clock')
        if meta['capture_kind']!='live_snapshot' or ready['prospective_eligible'] is not True or ready['at_decision']['ready_at_decision'] is not True:
            raise ValueError('Capture is not a prospective-ready live forecast')
        if (pd.Timestamp(observed)-completed).total_seconds()>120:raise ValueError('Stale capture completion')
        if pd.Timestamp(observed)>=release:raise ValueError('Target has already been released')
    copied=[]
    for name,digest in meta['code_and_static_inputs'].items():
        path=run/'sources'/name
        if sha(path)!=digest:raise ValueError('Retained source differs from engine snapshot')
        copied.append(path)
    artifacts=dict(model_code=[p for p in copied if p.suffix=='.py'],
        inputs=[p for p in copied if p.suffix!='.py']+[run/name for name in meta['hashes']],
        source_manifests=[run/name for name in sorted(required|{'receipt.json'})])
    issued=pd.Timestamp(observed) if mode=='prospective' else pd.Timestamp(meta['as_of'])
    availability={str(p):dict(available_from=issued.isoformat(),actual_observed_at_utc=observed.isoformat(),
        availability_kind='observed_snapshot' if mode=='prospective' else 'historical_rule_assumption')
        for role in ('inputs','source_manifests') for p in artifacts[role]}
    bundles=[]
    for model in MODELS:
        path=table[table.model.eq(model)].sort_values('h')
        bundle=archive.archive_forecast(archive_root,mode=mode,issued_at=issued.to_pydatetime(),target_origin=meta['target'],
            target_first_release_at=release.to_pydatetime(),model=model,point_forecast=h0,
            path_forecasts=[dict(target_month=r.target,point=float(r.mm_forecast)) for r in path.itertuples()],
            artifact_paths=artifacts,data_availability=availability,metadata=dict(path_engine='current-path-r20',
                h0_model='HARD_BASE',point_units='monthly_CPI_percent',path_units='monthly_CPI_percent',
                annual_path_source='path.csv: yy_exante',contribution_units='percentage_points',runtime=meta['runtime'],
                engine_completed_at=point['completed_at'],freshness='120 seconds at handoff; separate 120-second archive issue window',
                caveat='Research model; original historical vintages and upstream refresh completeness not certified'))
        archive.verify_bundle(bundle,verify_artifacts=True);bundles.append(str(bundle))
    return bundles


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--mode',choices=['replay','prospective'],required=True)
    parser.add_argument('--archive-root',type=Path,default=ROOT/'output/current_path_archive')
    args=parser.parse_args();print(json.dumps({'bundles':record_capture(args.run,args.archive_root,args.mode)},indent=2))
