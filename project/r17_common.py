"""Offline R17 accounting and original-clock input contracts."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from path_improvements_experiment_r12 import sha, dump, add_outcomes_and_compound

ROOT=Path(__file__).resolve().parent
FAST='STATE_FAST_R15'


def read(name): return pd.read_csv(ROOT/name,float_precision='round_trip')


def monthly(name,column=None):
    frame=read(name).set_index(read(name).columns[0]);frame.index=pd.PeriodIndex(frame.index,freq='M')
    if not frame.index.is_unique:raise ValueError('Duplicate month')
    return frame[column] if column else frame


def publication_dates(index,calendar=None):
    cal=read('data/release_calendar_cz_cpi.csv') if calendar is None else calendar.copy()
    cal=cal.set_index('target_month');cal.index=pd.PeriodIndex(cal.index,freq='M')
    if not cal.index.is_unique:raise ValueError('Duplicate release month')
    dates=pd.to_datetime(cal.detail_release_dt).dt.normalize()+pd.Timedelta(hours=9)
    result=dates.reindex(index)
    for m in index[index<cal.index.min()]:result.loc[m]=(m+1).to_timestamp()+pd.Timedelta(days=19,hours=9)
    return result


def adjusted_core(raw,seasonal):
    if (raw<=-100).any() or not np.isfinite(raw).all():raise ValueError('Invalid monthly rates')
    return 100*np.log1p(raw/100)-np.array([seasonal[m.month] for m in raw.index])


def replace_block(frame,block,path):
    out=frame.copy();weight='weight_'+('alc' if block=='alcohol_tobacco' else block)
    if frame.h.duplicated().any():raise ValueError('One origin/model required')
    for h,value in path.items():
        if h not in range(1,13):raise ValueError('Only h1..12 may change')
        mask=out.h.eq(h)
        out.loc[mask,'mm_forecast']+=out.loc[mask,weight]*(value-out.loc[mask,'value_'+block])
        out.loc[mask,'value_'+block]=value
        out.loc[mask,'contribution_'+block]=out.loc[mask,weight]*value
    if path:
        for col in ('yy_exante','yy_conditional','cumulative_log_forecast'):
            if col in out:out.loc[out.h.gt(0),col]=np.nan
    return out


def preserved_hashes():
    result={}
    for directory in ('output/research_r15','output/research_r16'):
        manifest=json.loads((ROOT/directory/'manifest.json').read_text(encoding='utf-8'))
        for name,digest in manifest['inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Old input changed: '+name)
            result[name]=digest
        for name,digest in manifest['outputs'].items():
            path=ROOT/directory/name
            if sha(path)!=digest:raise ValueError('Old output changed: '+str(path))
            result[path.relative_to(ROOT).as_posix()]=digest
    return result


def compound(native):
    headline=monthly('output/independent_path_frozen_inputs.csv','headline_mm')
    stored=read('output/research_r16/forecasts.csv').query("model == 'INDEPENDENT_BRIDGE'")
    columns=['origin','h','target','as_of_utc','model','mm_forecast']
    return add_outcomes_and_compound(native[columns],headline,stored)[0]


def finish(out,hashes,**extra):
    for name,digest in hashes.items():
        if sha(ROOT/name)!=digest:raise ValueError('Input changed during fit: '+name)
    dump(out/'manifest.json',dict(inputs=hashes,**extra,outputs={p.name:sha(p) for p in out.iterdir()
        if p.suffix in ('.csv','.json') and p.name!='manifest.json'}))
