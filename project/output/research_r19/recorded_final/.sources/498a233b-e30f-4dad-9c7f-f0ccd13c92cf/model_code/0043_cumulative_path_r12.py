"""Matched monthly and cumulative direct targets for R12, same causal prior."""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.food_path_r12 import log_history, trend_state, prior_log, ridge_zero_prior, MIN_HISTORY


def state_panel(history,origin):
    q=log_history(history,origin)
    released=history.loc[q.index]
    origins=pd.period_range(q.index[0]+MIN_HISTORY,pd.Period(origin,'M'),freq='M')
    states={r:trend_state(released,r) for r in origins}
    return q,states


def training_data(history,origin,h,mode,panel=None):
    origin=pd.Period(origin,'M')
    if not isinstance(h,int) or not 1<=h<=12 or mode not in ('monthly','cumulative'):
        raise ValueError('h must be 1..12 and mode monthly or cumulative')
    q,states=state_panel(history,origin) if panel is None else panel
    eligible=[r for r in states if r+h<=origin-1]
    x=pd.DataFrame([states[r]['predictors'] for r in eligible],
        index=pd.PeriodIndex(eligible,freq='M'),columns=['last_sa_gap','mean3_sa_gap','mean12_sa_gap'])
    target=[]
    for r in eligible:
        hs=[h] if mode=='monthly' else range(1,h+1)
        target.append(float(np.mean([q.loc[r+k]-prior_log(states[r],r,k) for k in hs])))
    yy=pd.Series(target,index=x.index,dtype=float)
    now=pd.Series(states[origin]['predictors'],index=x.columns)
    return dict(x=x,target=yy,now=now,state=states[origin],
        last_training_target=str(eligible[-1]+h) if eligible else None)


def reconstruct_cumulative(cumulative,h0):
    path={0:float(h0)}; previous=0.
    for h in range(1,13):
        value=float(cumulative[h]); path[h]=float(100*np.expm1((value-previous)/100)); previous=value
    return path


def forecast_targets(history,origin,h0):
    if not np.isfinite(h0) or h0<=-100:
        raise ValueError('Valid finite supplied HARD_BASE h0 required')
    origin=pd.Period(origin,'M'); panel=state_panel(history,origin)
    paths={}; diagnostics={}
    for name,mode in [('DIRECT_MONTHLY_R12','monthly'),('DIRECT_CUMULATIVE_R12','cumulative')]:
        native={0:float(h0)}; detail={}
        for h in range(1,13):
            data=training_data(history,origin,h,mode,panel)
            correction,diag=ridge_zero_prior(data['x'],data['target'],data['now'],60)
            hs=[h] if mode=='monthly' else range(1,h+1)
            forecast=float(np.mean([prior_log(data['state'],origin,k) for k in hs])+correction)
            native[h]=float(100*np.expm1(forecast/100)) if mode=='monthly' else h*forecast
            diag.update(last_training_target=data['last_training_target'],h=h,mode=mode,
                prior_mean_log=float(np.mean([prior_log(data['state'],origin,k) for k in hs])))
            detail[h]=diag
        paths[name]=native if mode=='monthly' else reconstruct_cumulative(native,h0)
        diagnostics[name]=detail
    return dict(paths=paths,diagnostics=diagnostics)
