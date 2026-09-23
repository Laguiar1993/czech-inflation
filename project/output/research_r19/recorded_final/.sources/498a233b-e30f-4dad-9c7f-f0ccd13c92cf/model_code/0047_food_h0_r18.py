"""Fixed incremental food-h0 profiles using only matured saved-origin errors."""
from __future__ import annotations

import numpy as np
import pandas as pd
from models.food_path_r14 import _aware

CONTROL='STATE_FAST_R15'
PROFILES={'FOOD_H0_FAST_R18':.5,'FOOD_H0_SLOW_R18':.9}
SELECT='FOOD_H0_SELECT_R18'
PREFERENCE=(CONTROL,*PROFILES)
MIN_ORIGINS=12
TRAIN_WINDOW=60
VALIDATION_WINDOW=36
RIDGE=1.


def monthly_labels(levels,available,targets,as_of):
    """A monthly log rate needs both actual calendar endpoints published."""
    clock=_aware(as_of);values=[];audit=[]
    for target in targets:
        m=pd.Period(target,'M');dates=[];ends=[]
        for endpoint in (m-1,m):
            release=available.get(endpoint)
            value=levels.get(endpoint,np.nan)
            if pd.isna(release) or not np.isfinite(value):return None
            stamp=_aware(release)
            if stamp>clock:return None
            dates.append(stamp.isoformat());ends.append(float(value))
        values.append(ends[1]-ends[0])
        audit.append(dict(target=str(m),previous_release=dates[0],current_release=dates[1],
                          actual_log=values[-1]))
    return values,audit


def mature_origins(saved,levels,available,origin,as_of,window=TRAIN_WINDOW):
    """Keep complete paths only; target s+12 must be strictly before t."""
    t=pd.Period(origin,'M');eligible=[];audits={}
    for key in sorted(saved):
        s=pd.Period(key,'M')
        if s+12>=t:continue
        row=saved[key]
        if not np.isfinite(row['signal']) or not np.isfinite(row['baseline_log']).all():continue
        labels=monthly_labels(levels,available,pd.period_range(s+1,s+12,freq='M'),as_of)
        if labels is None:continue
        eligible.append(key)
        audits[key]=[dict(origin=key,feature_as_of=row['as_of'],**r) for r in labels[1]]
    chosen=eligible[-window:]
    return chosen,[r for key in chosen for r in audits[key]]


def fit_profile(saved,levels,available,origin,as_of,rho):
    if rho not in PROFILES.values():raise ValueError('Only predeclared decay profiles allowed')
    origins,rows=mature_origins(saved,levels,available,origin,as_of)
    x=[];y=[]
    for row in rows:
        s=row['origin'];h=pd.Period(row['target'],'M').ordinal-pd.Period(s,'M').ordinal
        signal=float(saved[s]['signal']);baseline=float(saved[s]['baseline_log'][h])
        regressor=signal*rho**h;error=row['actual_log']-baseline
        x.append(regressor);y.append(error)
        row.update(h=h,signal=signal,profile=rho**h,x=regressor,baseline_log=baseline,error=error)
    result=dict(beta=0.,beta_unbounded=0.,theta=0.,scale=0.,ridge=RIDGE,
                n_origins=len(origins),n_rows=len(rows),training_origins=origins,training=rows,
                status='fallback',reason='fallback_insufficient_mature_origins')
    if len(origins)<MIN_ORIGINS:return result
    x=np.asarray(x);y=np.asarray(y);scale=float(np.sqrt(np.mean(x*x)))
    result['scale']=scale
    if scale<=1e-12:
        result['reason']='fallback_zero_signal_variance';return result
    z=x/scale;theta=float(z@y/(z@z+len(z)*RIDGE));raw=theta/scale
    beta=float(np.clip(raw,0.,1.));error=y-beta*x
    result.update(beta=beta,beta_unbounded=raw,theta=theta,status='estimated',reason='',
                  training_rmse=float(np.sqrt(np.mean(error*error))))
    return result


def corrected_path(state,beta,rho):
    signal=float(state['signal']);baseline=np.asarray(state['baseline_log'],dtype=float)
    if baseline.shape!=(13,) or len(state['baseline_mm'])!=12:
        raise ValueError('Saved pipeline h0..12 and exact h1..12 control required')
    if not 0<=beta<=1 or rho not in PROFILES.values():raise ValueError('Undeclared coefficient/profile')
    if not np.isfinite(signal) or beta==0:
        return dict(log_rates=baseline[1:].tolist(),mm_rates=list(state['baseline_mm']),
                    reason='fallback_missing_h0_signal' if not np.isfinite(signal) else '')
    rates=baseline[1:]+beta*signal*rho**np.arange(1,13)
    return dict(log_rates=rates.tolist(),mm_rates=(100*np.expm1(rates/100)).tolist(),reason='')


def select_path(history,saved,levels,available,origin,as_of):
    # Select the latest36 valid historical saved candidate paths, not a later refit.
    origins,rows=mature_origins(saved,levels,available,origin,as_of,window=len(saved))
    chosen=[s for s in origins if s in history and all(
        name in history[s] and len(history[s][name])==12 and np.isfinite(history[s][name]).all()
        for name in PREFERENCE)][-VALIDATION_WINDOW:]
    labels={s:[r['actual_log'] for r in rows if r['origin']==s] for s in chosen}
    result=dict(selected=CONTROL,n_origins=len(chosen),training_origins=chosen,losses={},
                status='fallback',reason='fallback_insufficient_mature_validation')
    if len(chosen)<MIN_ORIGINS:return result
    losses={name:float(np.mean([np.mean((np.asarray(history[s][name])-labels[s])**2)
                                for s in chosen])) for name in PREFERENCE}
    winner=CONTROL
    for name in PREFERENCE[1:]:
        if losses[name]<losses[winner]-1e-12:winner=name
    result.update(selected=winner,losses=losses,status='selected',reason='')
    return result
