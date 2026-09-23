"""Offline numerical replay: compare saved September inputs with recorded outputs."""
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import numpy as np,pandas as pd
from .runtime import ROOT

def compare_points(actual,reference):
    if actual.get('ready_for_first_release') is not True:raise ValueError('Replay forecast is not ready for first release')
    if actual.get('food_diagnostics',{}).get('method')!='x13':raise ValueError('Replay food adjustment fell back')
    expected={'HARD_BASE','HARD_HALF','HARD_FULL'}
    raw=actual.get('points_mm_pct',{})
    if set(reference)!=expected or not expected<=set(raw):raise ValueError('Nowcast replay production roster differs')
    values={k:raw[k] for k in expected} # R32 records only HARD; legacy calculator also returns SENTIMENT.
    if not np.isfinite(list(values.values())+list(reference.values())).all():raise ValueError('Nonfinite nowcast replay or reference')
    errors={k:abs(values[k]-v) for k,v in reference.items()}
    if max(errors.values())>1e-10:raise ValueError('Nowcast numerical replay differs: '+str(errors))
    return errors

def compare_path(table,saved):
    keys=['model','h'];columns=['mm_forecast','yy_exante']+[c for c in saved if c.startswith('contribution_')]
    if table.empty or saved.empty or table.duplicated(keys).any() or saved.duplicated(keys).any():raise ValueError('Empty or duplicate path comparison rows')
    left=table.set_index(keys).sort_index();right=saved.set_index(keys).sort_index()
    if not left.index.equals(right.index):raise ValueError('Path replay model/horizon roster differs')
    if not np.isfinite(left[columns].to_numpy()).all() or not np.isfinite(right[columns].to_numpy()).all():raise ValueError('Nonfinite path replay or reference')
    error=float(np.max(np.abs(left[columns].to_numpy()-right[columns].to_numpy())))
    if error>1e-9:raise ValueError('Path numerical replay differs: '+str(error))
    return error

def check():
    from tools.current_path_r34.run import load_record,load_inputs,compute
    from tools.live_bundle_r32 import adapter,runner
    from .relocation import relocations
    with relocations(ROOT):
        meta,saved,_=load_record(ROOT/'output/current_path_r34/final')
    run=ROOT/meta['h0_run'];record=json.loads((run/'adapter.json').read_bytes());h0_clock=record['as_of']
    loaded=adapter.load_bundle(ROOT/meta['nowcast_bundle'],ROOT)
    calendar,_=adapter.load_calendar(ROOT/'data/release_calendar_cz_cpi.csv',run/'live_calendar.csv',adapter.decision_clock(h0_clock))
    frames,fx=adapter.prepare_frames(loaded,pd.Period(meta['origin'],'M'),adapter.decision_clock(h0_clock),calendar)
    with redirect_stdout(sys.stderr):actual=runner.calculate(frames,pd.Period(meta['origin'],'M'),h0_clock,calendar)
    errors=compare_points(actual,record['forecast']['points_mm_pct'])
    with relocations(ROOT):
        levels,available,pump,history,_,_,_=load_inputs(ROOT/meta['path_input_directory'],meta['origin'],meta['as_of'])
    frames,_=adapter.prepare_frames(loaded,pd.Period(meta['origin'],'M'),adapter.decision_clock(meta['as_of']),calendar)
    with redirect_stdout(sys.stderr):table,_,_=compute(frames,levels,available,pump,history,meta['origin'],meta['as_of'],meta['h0'],record['forecast']['main_contributions_pp'],calendar)
    error=compare_path(table,saved)
    return {'status':'passed','mode':'offline_reproduction_only','origin':meta['origin'],'nowcast_absolute_errors':errors,'path_max_absolute_error':error,'path_rows':len(table),'forecast_published':False}
