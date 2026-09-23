"""Independent reviewer arithmetic; never imports the R16 engine or runner."""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

LAMBDAS=(.1,1.,10.)
CONFIGS=('p80_q001','p80_q010','p95_q001','p95_q010')
BANDS=((1,3),(4,6),(7,9),(10,12))

def local_clock(value):
    stamp=pd.Timestamp(value)
    return stamp.tz_convert('Europe/Prague').tz_localize(None) if stamp.tzinfo else stamp

def release_dates(index,calendar):
    out={}
    for p in index:
        if p in calendar.index:
            value=pd.Timestamp(calendar.loc[p,'detail_release_dt'])
            out[p]=value.normalize()+pd.Timedelta(hours=9) if pd.notna(value) else pd.NaT
        elif p<calendar.index.min():
            out[p]=(p+1).start_time+pd.Timedelta(days=19,hours=9)
        else:
            out[p]=pd.NaT
    return pd.Series(out)

def labels(series,available,origins,t,clock,band,center=None):
    t=pd.Period(t,'M'); clock=local_clock(clock)
    lo,hi=band; rows=[]
    for r in sorted(origins):
        r=pd.Period(r,'M')
        if r+hi>=t: continue
        months=pd.period_range(r+lo,r+hi,freq='M')
        y=series.reindex(months)
        dates=available.reindex(months)
        if not np.isfinite(y).all() or dates.isna().any() or dates.gt(clock).any(): continue
        value=float(y.mean())
        if center is not None:
            level=center.get(r,np.nan)
            if not np.isfinite(level):continue
            value-=level
        rows.append(dict(origin=str(r),actual=value,last_target=str(months[-1]),available_from=str(dates.max())))
    return pd.DataFrame(rows,columns=['origin','actual','last_target','available_from'])

def ridge(design,outcomes,now,penalty,required=()):
    y=outcomes.set_index('origin').actual
    y.index=pd.PeriodIndex(y.index,freq='M')
    keys=design.index.intersection(y[np.isfinite(y)].index).sort_values()
    if required: keys=keys[np.isfinite(design.loc[keys,list(required)]).all(axis=1)]
    keys=keys[-120:]
    x=design.loc[keys]
    if len(keys)<48 or required and not np.isfinite(now.reindex(required)).all():
        return np.nan,dict(n_train=len(keys),keys=[str(p) for p in keys])
    columns=[c for c in x.columns if x[c].nunique(dropna=True)>1]
    means=x[columns].mean()
    scales=x[columns].fillna(means).std(ddof=0)
    xx=(x[columns].fillna(means)-means)/scales
    current=(now.reindex(columns).fillna(means)-means)/scales
    fitted=Ridge(alpha=len(keys)*penalty,fit_intercept=False,solver='svd')
    fitted.fit(np.column_stack([np.ones(len(keys)),xx]),y.loc[keys].to_numpy())
    result=float(fitted.predict(np.r_[1.,current].reshape(1,-1))[0])
    return result,dict(n_train=len(keys),keys=[str(p) for p in keys],columns=columns,
        intercept=float(fitted.coef_[0]),coefficients=dict(zip(columns,fitted.coef_[1:])),
        means=means.to_dict(),scales=scales.to_dict())

def slope_paths(history,seasonal,t):
    adjusted=history-np.array([seasonal[str(p.month)] for p in history.index])
    paths={}; hobs=np.array([1.,0.,1.])
    for config,(phi,q) in zip(CONFIGS,[(.8,.001),(.8,.01),(.95,.001),(.95,.01)]):
        ff=np.array([[1.,phi,0.],[0.,phi,0.],[0.,0.,.8]])
        mm=np.array([adjusted.iloc[:12].mean(),0.,0.]); pp=np.diag([1.,.01,1.])
        for value in adjusted.iloc[12:]:
            mp=ff@mm; pc=ff@pp@ff.T+np.diag([.05,q,.2])
            kg=pc@hobs/(hobs@pc@hobs+1.)
            mm=mp+kg*(value-hobs@mp)
            residual=np.eye(3)-np.outer(kg,hobs)
            pp=residual@pc@residual.T+np.outer(kg,kg)
        paths[config]={h:float(hobs@np.linalg.matrix_power(ff,h+1)@mm+seasonal[str((t+h).month)]) for h in range(1,13)}
    return paths

def choose(candidates,outcomes,t,clock,configs,default):
    valid=outcomes.copy()
    valid=valid[valid.origin.lt(str(t))&valid.last_target.lt(str(t))&pd.to_datetime(valid.available_from).le(local_clock(clock))]
    wide=candidates.pivot(index='origin',columns='config',values='prediction').reindex(columns=configs)
    joined=wide.join(valid.set_index('origin').actual,how='inner')
    joined=joined.replace([np.inf,-np.inf],np.nan).dropna().sort_index().tail(36)
    if len(joined)<24:return default,list(joined.index),{}
    loss=joined[list(configs)].sub(joined.actual,axis=0).pow(2).mean()
    tied=[c for c in configs if np.isclose(loss[c],loss.min(),rtol=1e-10,atol=1e-12)]
    return default if default in tied else tied[0],list(joined.index),loss.to_dict()
