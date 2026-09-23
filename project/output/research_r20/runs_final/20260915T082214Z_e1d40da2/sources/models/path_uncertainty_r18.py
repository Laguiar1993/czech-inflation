"""Joint historical path-error scenarios, preserving cross-month dependence."""
import numpy as np
import pandas as pd


def joint_pool(rows,origin,clock):
    t=pd.Period(origin,'M');clock=pd.Timestamp(clock)
    if rows.duplicated(['origin','h']).any():raise ValueError('Duplicate path keys')
    # Select origins whose final reference month is strictly before t first.
    sources=pd.PeriodIndex(rows.origin,freq='M')
    eligible=rows.loc[(sources+12<t)].copy();groups=[]
    for key,g in eligible.groupby('origin',sort=True):
        g=g.sort_values('h')
        if list(g.h)!=list(range(13)):continue
        expected=pd.period_range(key,periods=13,freq='M')
        if not expected.equals(pd.PeriodIndex(g.target,freq='M')):raise ValueError('Incorrect horizon labels')
        dates=pd.to_datetime(g.released)
        if dates.isna().any() or dates.gt(clock).any():continue
        f=g.forecast.to_numpy(float);a=g.actual.to_numpy(float)
        if not np.isfinite([f,a]).all() or (f<=-100).any() or (a<=-100).any():continue
        errors=100*(np.log1p(a/100)-np.log1p(f/100))
        groups.append((key,errors,str(dates.max())))
    groups=groups[-60:]
    return dict(origins=[x[0] for x in groups],errors=np.array([x[1] for x in groups]).reshape(-1,13),
                final_releases=[x[2] for x in groups],n_pool=len(groups))


def annual_scenarios(points,errors,known,origin):
    t=pd.Period(origin,'M');points=np.asarray(points,float);errors=np.asarray(errors,float)
    if points.shape!=(13,) or errors.ndim!=2 or errors.shape[1]!=13:raise ValueError('Complete h0..12 required')
    if not np.isfinite(points).all() or (points<=-100).any() or not np.isfinite(errors).all():raise ValueError('Invalid rate')
    if known.index.has_duplicates or (known.index>=t).any():raise ValueError('Known history contains current/future months')
    log=100*np.log1p(points/100)[None,:]+errors;result=np.full((len(errors),13),np.nan)
    for h in range(13):
        begin=t+h-11;end=t-1
        hist=known.reindex(pd.period_range(begin,end,freq='M')).to_numpy(float) if begin<=end else np.array([])
        if not np.isfinite(hist).all() or (hist<=-100).any():continue
        fixed=100*np.log1p(hist/100).sum();future=log[:,max(0,h-11):h+1].sum(axis=1)
        result[:,h]=100*np.expm1((fixed+future)/100)
    return result
