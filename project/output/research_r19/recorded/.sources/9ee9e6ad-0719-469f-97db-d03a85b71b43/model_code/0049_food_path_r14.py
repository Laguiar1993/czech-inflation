"""R14 fixed log-level food pipeline; no live inputs or fitted future values."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

MODELS=('FOOD_DOMESTIC_PIPELINE_R14','FOOD_OWN_LEVEL_AR_R14')
LAGS=12
MIN_TRAIN=36
ROOT=Path(__file__).resolve().parents[1]


def load_inputs():
    folder=ROOT/'data/research_r14/food'
    manifest=json.loads((folder/'input_manifest.json').read_text(encoding='utf-8'))
    for name,expected in manifest['inputs'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Original food source hash changed: {name}')
    for name,expected in manifest['outputs'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Prepared food input hash changed: {name}')
    levels=pd.read_csv(folder/'pipeline_log_levels.csv',index_col=0,float_precision='round_trip')
    dates=pd.read_csv(folder/'pipeline_available_from.csv',index_col=0)
    levels.index=dates.index=pd.PeriodIndex(levels.index,freq='M')
    if list(levels.columns)!=['agri4','food_ppi','food'] or not np.isfinite(levels).all().all():
        raise ValueError('Exactly three complete declared level series required')
    return levels,dates,manifest


def calendar_terms(month):
    return np.array([1.]+[float(pd.Period(month,'M').month==m) for m in range(2,13)])


def minnesota_prior(sigma,equation):
    k=len(sigma); mean=np.zeros(k*LAGS+12); variance=np.zeros_like(mean)
    mean[equation]=1.
    for lag in range(1,LAGS+1):
        for j in range(k):
            sd=.2/lag*(sigma[equation]/sigma[j])*(1. if j==equation else .5)
            variance[(lag-1)*k+j]=sd**2
    variance[k*LAGS:]=(10*sigma[equation])**2
    return mean,variance


def design(levels):
    values=levels.to_numpy(dtype=float); rows=[]; dates=[]; response=[]
    for i in range(LAGS,len(levels)):
        rows.append(np.concatenate([values[i-l] for l in range(1,LAGS+1)]+[calendar_terms(levels.index[i])]))
        response.append(values[i]); dates.append(levels.index[i])
    return np.asarray(rows),np.asarray(response),pd.PeriodIndex(dates,freq='M')


def fit_level_var(levels,training_dates=None,scale_levels=None):
    x,y,dates=design(levels)
    valid=np.isfinite(x).all(axis=1)&np.isfinite(y).all(axis=1)
    if training_dates is not None:
        valid &= dates.isin(training_dates)
    x,y,dates=x[valid],y[valid],dates[valid]
    if len(x)<MIN_TRAIN:
        raise ValueError('insufficient_history')
    # The caller supplies the same fully observed history for both model scales.
    scale_data=levels if scale_levels is None else scale_levels
    sigma=scale_data.diff().dropna().std(ddof=0).to_numpy(dtype=float)
    if not np.isfinite(sigma).all() or (sigma<=0).any():
        raise ValueError('invalid_training_innovation_scale')
    k=levels.shape[1]; beta=np.empty((x.shape[1],k))
    for equation in range(k):
        mean,variance=minnesota_prior(sigma,equation)
        precision=1/variance
        beta[:,equation]=np.linalg.solve(x.T@x/sigma[equation]**2+np.diag(precision),
            x.T@y[:,equation]/sigma[equation]**2+precision*mean)
    residuals=y-x@beta
    raw=residuals.T@residuals/len(residuals)
    Q=.9*raw+.1*np.diag(np.diag(raw))+np.eye(k)*(1e-10*np.diag(raw).mean())
    A=np.zeros((k*LAGS,k*LAGS)); A[:k]=beta[:k*LAGS].T
    A[k:,:-k]=np.eye(k*(LAGS-1))
    D=np.zeros((k*LAGS,12)); D[:k]=beta[k*LAGS:].T
    return dict(A=A,D=D,Q=Q,beta=beta,sigma=sigma,residuals=residuals,n_train=len(x),
        train_start=str(dates.min()),train_end=str(dates.max()),training_dates=list(map(str,dates)),
        spectral_radius=float(np.max(np.abs(np.linalg.eigvals(A)))))


def condition_state(mean,covariance,observed):
    if not observed:
        return mean.copy(),covariance.copy()
    index=np.array(sorted(observed),dtype=int)
    values=np.array([observed[i] for i in index])
    covariance=(covariance+covariance.T)/2
    measured=covariance[np.ix_(index,index)]
    gain=covariance[:,index]@np.linalg.pinv(measured,hermitian=True)
    result=mean+gain@(values-mean[index])
    variance=covariance-gain@covariance[index,:]
    result[index]=values
    variance[index,:]=0.; variance[:,index]=0.
    return result,(variance+variance.T)/2


def simulate_state(A,D,state,start,steps):
    rows=[]; value=state.copy()
    for step in range(steps):
        value=A@value+D@calendar_terms(pd.Period(start,'M')+step)
        rows.append(value.copy())
    return np.asarray(rows)


def _aware(clock):
    stamp=pd.Timestamp(clock)
    if pd.isna(stamp):
        raise ValueError('Known decision timestamp required')
    return stamp.tz_localize('Europe/Prague') if stamp.tzinfo is None else stamp.tz_convert('Europe/Prague')


def forecast_origin(levels,available,origin,as_of):
    t=pd.Period(origin,'M'); clock=_aware(as_of)
    if not isinstance(levels.index,pd.PeriodIndex) or not levels.index.is_unique or not levels.columns.is_unique:
        raise ValueError('Unique monthly calendar and variable names required')
    y=levels.loc[levels.index<t].copy()
    if not y.index.equals(pd.period_range(y.index.min(),t-1,freq='M')):
        raise ValueError('Contiguous level calendar through t-1 required')
    a=available.reindex(y.index)
    for col in y:
        dates=pd.to_datetime(a[col].map(lambda value: _aware(value) if pd.notna(value) else pd.NaT),utc=True)
        y.loc[~(dates.notna() & dates.le(clock)),col]=np.nan
    x,target,training_index=design(y)
    valid=np.isfinite(x).all(axis=1)&np.isfinite(target).all(axis=1)
    training_dates=training_index[valid]
    last_released={col:str(y[col].last_valid_index()) if y[col].notna().any() else None for col in y}
    diag=dict(status='estimated',as_of=clock.isoformat(),last_released_month=last_released,
        last_release_timestamp={col:str(a.loc[pd.Period(last_released[col],'M'),col]) if last_released[col] else None for col in y},
        target_clock='h0=t, food(t) internal, headline HARD_BASE unchanged')
    empty={name:{h:np.nan for h in range(1,13)} for name in MODELS}
    if len(training_dates)<MIN_TRAIN:
        diag.update(status='insufficient_history',n_train=len(training_dates))
        return dict(paths=empty,fits=[],forecast_food_levels={},diagnostics=diag)
    fits=[]; paths={}; foodlevels={}
    common_scale=y.loc[:training_dates[-1]].where(y.notna().all(axis=1))
    for name,columns in [(MODELS[0],list(y.columns)),(MODELS[1],['food'])]:
        selected=y[columns]; fit=fit_level_var(selected,training_dates,common_scale[columns])
        k=len(columns)
        # Latest fully observed lag state; subsequent partially observed months condition it.
        candidates=[i for i in range(LAGS-1,len(y)) if np.isfinite(y.iloc[i-LAGS+1:i+1].to_numpy()).all()]
        anchor=candidates[-1]
        state=np.concatenate([selected.iloc[anchor-l].to_numpy() for l in range(LAGS)])
        covariance=np.zeros((k*LAGS,k*LAGS)); process=np.zeros_like(covariance); process[:k,:k]=fit['Q']
        updates=[]
        for i in range(anchor+1,len(y)):
            state=fit['A']@state+fit['D']@calendar_terms(y.index[i])
            covariance=fit['A']@covariance@fit['A'].T+process
            observed={j:float(selected.iloc[i,j]) for j in range(k) if np.isfinite(selected.iloc[i,j])}
            state,covariance=condition_state(state,covariance,observed)
            updates.append(dict(month=str(y.index[i]),observed_columns=[columns[j] for j in observed],
                                state_mean=state[:k].tolist(),state_variance=np.diag(covariance)[:k].tolist()))
        predicted=simulate_state(fit['A'],fit['D'],state,t,13)
        food_index=columns.index('food'); fl=predicted[:,food_index]
        path={h:float(100*np.expm1((fl[h]-fl[h-1])/100)) for h in range(1,13)}
        if not np.isfinite(list(path.values())).all():
            path={h:np.nan for h in range(1,13)}
        paths[name]=path; foodlevels[name]=fl.tolist()
        fits.append(dict(model=name,columns=columns,status='estimated' if np.isfinite(list(path.values())).all() else 'nonfinite_path',
            n_train=fit['n_train'],train_start=fit['train_start'],train_end=fit['train_end'],
            training_dates=fit['training_dates'],sigma=fit['sigma'].tolist(),Q=fit['Q'].tolist(),
            coefficients=fit['beta'].tolist(),spectral_radius=fit['spectral_radius'],
            anchor_month=str(y.index[anchor]),conditioning_updates=updates))
    return dict(paths=paths,fits=fits,forecast_food_levels=foodlevels,diagnostics=diag)


def replace_food(frame,path):
    result=frame.copy()
    columns=[f'contribution_{col}' for col in ('core','administered','alcohol_tobacco','fuel','wedge')]
    for h,value in path.items():
        if not 1<=h<=12:
            raise ValueError('Only future food h1..12 may be replaced')
        mask=result.h.eq(h)
        result.loc[mask,'value_food']=value
        result.loc[mask,'contribution_food']=result.loc[mask,'weight_food']*value
        result.loc[mask,'mm_forecast']=result.loc[mask,columns+['contribution_food']].sum(axis=1,min_count=6)
    return result
