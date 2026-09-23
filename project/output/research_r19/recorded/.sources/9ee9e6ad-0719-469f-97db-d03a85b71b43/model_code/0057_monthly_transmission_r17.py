"""R17 shared category forecasts and core residuals on saved generated proxies."""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.core_split import CATEGORIES, weights_at
from models.food_path_r14 import _aware

FAMILIES = ('ar','domestic','imported','both')
CORE_FAMILIES = ('own',*FAMILIES)
CORE_MODELS = {f: f'MONTHLY_{f.upper()}_CORE_R17' for f in CORE_FAMILIES}
DOMESTIC = ('unemployment_change3','ip_growth3','ulc_growth12')
IMPORTED = ('fx3','cost_26_mean3','cost_45_mean3')
MACRO = (*DOMESTIC,*IMPORTED)
GROUPS = {'ar': (), 'domestic':DOMESTIC, 'imported':IMPORTED, 'both':MACRO}
MIN_TRAIN = 24
WINDOW = 96


def released_rates(levels, available, origin, as_of):
    t=pd.Period(origin,'M');clock=_aware(as_of)
    if not isinstance(levels.index,pd.PeriodIndex) or not levels.index.is_unique or list(levels.columns)!=CATEGORIES:
        raise ValueError('Unique declared monthly categories required')
    history=levels.loc[levels.index<t].copy()
    if history.empty or not history.index.equals(pd.period_range(history.index.min(),t-1,freq='M')):
        raise ValueError('Contiguous monthly levels through t-1 required')
    dates=available.reindex(history.index).map(lambda d:_aware(d) if pd.notna(d) else pd.NaT)
    history.loc[~(dates.notna()&dates.le(clock))]=np.nan
    if (history<=0).any().any():raise ValueError('Released category levels must be positive')
    return 100*np.log(history/history.shift(1))


def snapshot(levels, available, weights, macro, origin, as_of):
    t=pd.Period(origin,'M');rates=released_rates(levels,available,t,as_of);history=rates.iloc[-WINDOW:]
    means=history.groupby(history.index.month).mean().reindex(range(1,13)).to_numpy()
    centered=history.to_numpy()-means[history.index.month-1]
    scales=np.maximum(.05,np.nanstd(centered,axis=0,ddof=0))
    lags=pd.period_range(t-3,t-1,freq='M')
    adjusted=rates.reindex(lags).to_numpy()-means[lags.month-1]
    own=np.column_stack([adjusted[-1]/scales,adjusted.mean(axis=0)/scales])
    selected=weights_at(weights,t,as_of)
    return dict(origin=str(t),as_of=_aware(as_of).isoformat(),seasonal=means.tolist(),scales=scales.tolist(),own=own.tolist(),
                macro={name:float(macro[name]) for name in MACRO},weights=selected.to_list(),weight_metadata=selected.attrs,
                coverage_fraction=float(selected.sum()),seasonal_dates=list(map(str,history.dropna().index)),
                last_released_month=str(rates.dropna().index.max()) if len(rates.dropna()) else None,
                last_level_release=str(available.get(t-1,pd.NaT)),previous_level_release=str(available.get(t-2,pd.NaT)),
                status='available' if np.isfinite(means).all() and np.isfinite(scales).all() else 'unavailable_seasonality',
                meaning='Tax-including service-category pressure proxy; not a tax-adjusted core partition')


def pressure(log_rates, weights):
    r=np.asarray(log_rates,dtype=float);w=np.asarray(weights,dtype=float)
    if r.shape!=(5,) or w.shape!=(5,) or not np.isfinite(w).all() or (w<=0).any() or w.sum()>=1:
        raise ValueError('Five positive declared base category fractions required')
    mm=100*np.expm1(r/100)
    p=float(w@mm/w.sum()) if np.isfinite(mm).all() else np.nan
    return dict(pressure_mm=p,pressure_log=float(100*np.log1p(p/100)),contribution_diagnostic=float(w.sum()*p),coverage_fraction=float(w.sum()))


def remainder(core_mm, pressure_mm):
    """Statistical difference in like percentage units, not an uncovered component."""
    return float(core_mm-pressure_mm)


def _snapshot_complete(state):
    return (state['status']=='available' and np.isfinite(state['own']).all() and
            np.isfinite([state['macro'][c] for c in MACRO]).all())


def _stage1_training(saved,rates,available,origin,h,family):
    t=pd.Period(origin,'M');eligible=[]
    for s in sorted(saved):
        source=pd.Period(s,'M');target=source+h
        if source>=t or target>=t or not _snapshot_complete(saved[s]):continue
        actual=rates.reindex([target]).to_numpy()[0]
        if not np.isfinite(actual).all():continue
        state=saved[s];offset=np.asarray(state['seasonal'])[target.month-1];scale=np.asarray(state['scales'])
        y=(actual-offset)/scale
        x=np.column_stack([state['own'],np.tile([state['macro'][c] for c in GROUPS[family]],(5,1))])
        eligible.append((x,y,dict(origin=s,target=str(target),feature_as_of=state['as_of'],
                                   current_release=str(available.get(target)),previous_release=str(available.get(target-1)))))
    eligible=eligible[-WINDOW:];k=2+len(GROUPS[family])
    x=np.vstack([v[0] for v in eligible]) if eligible else np.empty((0,k))
    y=np.concatenate([v[1] for v in eligible]) if eligible else np.array([])
    return x,y,[v[2] for v in eligible]


def stage1_training(saved,levels,available,origin,as_of,h,family):
    if h not in range(1,13) or family not in FAMILIES:raise ValueError('Unknown horizon or family')
    return _stage1_training(saved,released_rates(levels,available,origin,as_of),available,origin,h,family)


def ridge(x,y,penalties):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float);p=np.asarray(penalties,dtype=float)
    if not len(y) or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Finite training data required')
    scale=np.sqrt(np.mean(x*x,axis=0));scale[scale<=1e-12]=1.
    z=x/scale;beta=np.linalg.solve(z.T@z/len(y)+np.diag(p),z.T@y/len(y))
    return dict(scale=scale.tolist(),beta=beta.tolist(),penalties=p.tolist())


def first_stage(saved,levels,available,origin,as_of):
    t=pd.Period(origin,'M');state=saved[str(t)]
    if _aware(state['as_of'])!=_aware(as_of):raise ValueError('Current snapshot clock mismatch')
    rates=released_rates(levels,available,t,as_of)
    seasonal=np.asarray([state['seasonal'][(t+h).month-1] for h in range(1,13)])
    if state['status']!='available':seasonal[:]=np.nan
    own3=np.asarray(state['own'])[:,1];scales=np.asarray(state['scales'])
    persistence=seasonal+scales*np.where(np.isfinite(own3),own3,0.)
    control_status='unavailable_seasonality' if state['status']!='available' else 'control' if np.isfinite(own3).all() else 'fallback_seasonal'
    paths={'persistence':persistence};statuses={'persistence':[control_status]*12}
    reasons={'persistence':['' if np.isfinite(own3).all() else 'missing_own3_use_seasonal']*12};fits=[]
    for family in FAMILIES:
        path=[];status=[];why=[]
        for h in range(1,13):
            x,y,audit=_stage1_training(saved,rates,available,t,h,family)
            reason=('unavailable_seasonality' if state['status']!='available' else 'insufficient_training_origins' if len(audit)<MIN_TRAIN else
                    'missing_current_common_feature' if not _snapshot_complete(state) else '')
            row=dict(origin=str(t),family=family,h=h,n_train_origins=len(audit),n_category_rows=len(y),training=audit,
                     feature_names=['own1_normalized','own3_normalized',*GROUPS[family]],reason=reason)
            value=persistence[h-1]
            if not reason:
                fit=ridge(x,y,[.1,.1]+[1.]*len(GROUPS[family]));now=np.column_stack([state['own'],np.tile([state['macro'][c] for c in GROUPS[family]],(5,1))])
                value=seasonal[h-1]+scales*((now/fit['scale'])@fit['beta']);row.update(fit,status='estimated')
            else:row['status']='fallback_persistence' if np.isfinite(value).all() else 'unavailable_seasonality'
            path.append(value);status.append(row['status']);why.append(reason);fits.append(row)
        paths[family]=np.array(path);statuses[family]=status;reasons[family]=why
    signals={f:[pressure(row,state['weights']) for row in path] for f,path in paths.items()}
    return dict(category_log=paths,pressure_log={f:[r['pressure_log'] for r in rows] for f,rows in signals.items()},
                signals=signals,status=statuses,reasons=reasons,fits=fits)


def _core_labels(core,available,origin,as_of):
    t=pd.Period(origin,'M');clock=_aware(as_of);hist=core.loc[core.index<t].copy()
    dates=available.reindex(hist.index).map(lambda d:_aware(d) if pd.notna(d) else pd.NaT)
    hist.loc[~(dates.notna()&dates.le(clock))]=np.nan
    if (hist<=-100).any():raise ValueError('Core simple percentage must exceed -100')
    return 100*np.log1p(hist/100)


def _stage2_training(states,generated,core_log,available,origin,h,family):
    t=pd.Period(origin,'M');eligible=[]
    for s in sorted(states):
        source=pd.Period(s,'M');target=source+h
        if target>=t or source>=t or s not in generated:continue
        state=states[s];g=generated[s]
        values=np.asarray([g[f][h-1] for f in ('persistence',*FAMILIES)],dtype=float)
        all_signals=values[1:]-values[0]
        actual=core_log.get(target,np.nan);baseline=state['fast_log'][h-1]
        if not np.isfinite(all_signals).all() or not np.isfinite(state['own']).all() or not np.isfinite([actual,baseline]).all():continue
        x=[*state['own']]+([] if family=='own' else [all_signals[FAMILIES.index(family)]])
        eligible.append((x,float(actual-baseline),dict(origin=s,target=str(target),feature_as_of=state['as_of'],
                                                       response_release=str(available.get(target)),baseline_fast_log=float(baseline))))
    eligible=eligible[-WINDOW:];k=2 if family=='own' else 3
    return np.asarray([v[0] for v in eligible]).reshape(-1,k),np.array([v[1] for v in eligible]),[v[2] for v in eligible]


def stage2_training(states,generated,core,available,origin,as_of,h,family):
    if h not in range(1,13) or family not in CORE_FAMILIES:raise ValueError('Unknown stage-two horizon or family')
    return _stage2_training(states,generated,_core_labels(core,available,origin,as_of),available,origin,h,family)


def second_stage(states,generated,generated_status,core,available,origin,as_of):
    t=pd.Period(origin,'M');state=states[str(t)];labels=_core_labels(core,available,t,as_of)
    if _aware(state['as_of'])!=_aware(as_of):raise ValueError('Current core clock mismatch')
    paths={};fits=[];status={};reasons={}
    for family in CORE_FAMILIES:
        paths[family]=[];status[family]=[];reasons[family]=[]
        for h in range(1,13):
            x,y,audit=_stage2_training(states,generated,labels,available,t,h,family)
            current=generated[str(t)];values=np.asarray([current[f][h-1] for f in ('persistence',*FAMILIES)],dtype=float)
            signals=values[1:]-values[0]
            now=np.array([*state['own']]+([] if family=='own' else [signals[FAMILIES.index(family)]]))
            why='insufficient_training_origins' if len(y)<MIN_TRAIN else 'missing_current_common_feature' if not np.isfinite([*state['own'],*signals]).all() else ''
            row=dict(origin=str(t),family=family,h=h,n_train=len(y),training=audit,reason=why,
                     n_generated_estimated=sum(all(generated_status[r['origin']][f][h-1]=='estimated' for f in FAMILIES) for r in audit))
            value=state['fast_log'][h-1];correction=0.
            if not why:
                fit=ridge(x,y,[1.,1.]+([] if family=='own' else [10.]));correction=float((now/fit['scale'])@fit['beta'])
                value+=correction;row.update(fit,status='estimated')
            else:row['status']='fallback_fast'
            row['correction_log']=correction;paths[family].append(float(value));status[family].append(row['status']);reasons[family].append(why);fits.append(row)
    return dict(core_log=paths,fits=fits,status=status,reasons=reasons)
