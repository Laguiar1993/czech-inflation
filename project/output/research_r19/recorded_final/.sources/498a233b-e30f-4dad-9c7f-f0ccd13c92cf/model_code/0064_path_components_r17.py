"""Bounded whole-path combinations and separately declared movement diagnostic."""
import itertools
import numpy as np
import pandas as pd
from models.core_slope_transmission_r16 import _local_clock


def pool_grid():
    result={}
    for flags in itertools.product((0.,.25),repeat=3):
        if sum(flags)<=.5:
            weights=(1-sum(flags),*flags)
            result['POOL_'+''.join(str(round(v*4)) for v in weights)]=weights
    return result


def choose_path(frame,available,origin,clock,configs,default):
    t=pd.Period(origin,'M');cutoff=_local_clock(clock)
    if default not in configs:raise ValueError('Declared default required')
    if frame.duplicated(['origin','h','model']).any():raise ValueError('Duplicate candidate path key')
    selected=frame[frame.model.isin(configs)&frame.h.between(1,12)]
    eligible=[];losses={k:[] for k in configs};last_release={}
    for key,group in selected.groupby('origin',sort=True):
        s=pd.Period(key,'M')
        if s+12>=t:continue
        months=pd.period_range(s+1,s+12,freq='M');release=available.reindex(months)
        if release.isna().any() or release.map(_local_clock).gt(cutoff).any():continue
        grid=group.pivot(index='h',columns='model',values='yy_exante').reindex(index=range(1,13),columns=configs)
        if not np.isfinite(grid).all().all():continue
        if group.groupby('h').yy_actual.nunique().gt(1).any():raise ValueError('Conflicting headline label')
        actual=group.drop_duplicates('h').set_index('h').yy_actual.reindex(range(1,13))
        if not np.isfinite(actual).all():continue
        eligible.append(key);last_release[key]=str(release.max())
        for name in configs:losses[name].append(float(np.mean((grid[name]-actual)**2)))
    keys=eligible[-36:];n=len(keys)
    objectives={name:float(np.mean(values[-36:])+.05*np.sum(np.array(configs[name][1:])**2)) for name,values in losses.items()} if n else {}
    order=list(configs)
    choice=min(configs,key=lambda k:(objectives[k],-configs[k][0],order.index(k))) if n>=12 else default
    return choice,dict(n_validation=n,validation_origins=keys,validation_releases=[last_release[k] for k in keys],
        objectives=objectives,weights=list(configs[choice]),status='selected_mature_paths' if n>=12 else 'default_insufficient_history')


def sustained(values,threshold=.5):
    x=np.asarray(values,dtype=float)
    if x.shape!=(3,):raise ValueError('Three bands required')
    if not np.isfinite(x).all():return np.nan
    delta=x[-1]-x[0];adjacent=np.diff(x)
    if delta>=threshold and not (adjacent<=-threshold).any():return 1
    if delta<=-threshold and not (adjacent>=threshold).any():return -1
    return 0


def blend_native(frames,weights,model):
    weights=np.asarray(weights,float)
    if len(frames)!=len(weights) or not np.isfinite(weights).all() or (weights<0).any() or not np.isclose(weights.sum(),1):
        raise ValueError('Nonnegative normalized mixture required')
    keys=['origin','h'];base=frames[0].sort_values(keys).reset_index(drop=True).copy()
    aligned=[]
    for frame in frames:
        f=frame.sort_values(keys).reset_index(drop=True)
        if not f[keys+['target','as_of_utc']].equals(base[keys+['target','as_of_utc']]):raise ValueError('Mixture source clock/calendar mismatch')
        if not np.array_equal(f.loc[f.h.eq(0),'mm_forecast'],base.loc[base.h.eq(0),'mm_forecast']):raise ValueError('Mixture h0 mismatch')
        for col in (k for k in base if k.startswith('weight_')):
            if not np.allclose(f[col],base[col],atol=0,rtol=0,equal_nan=True):raise ValueError('Origin basket mismatch')
        aligned.append(f)
    value_columns=[col for col in base if col.startswith(('value_','contribution_')) or col=='mm_forecast']
    mask=base.h.gt(0)
    for col in value_columns:
        value=np.zeros(mask.sum())
        for weight,frame in zip(weights,aligned):
            if weight:value+=weight*frame.loc[mask,col].to_numpy(float)
        base.loc[mask,col]=value
    for col in ('yy_exante','yy_conditional','cumulative_log_forecast'):
        if col in base:base.loc[mask,col]=np.nan
    base['model']=model
    return base
