"""R14B fixed seasonal-centered monthly-rate pipeline and own-food control."""
import numpy as np
import pandas as pd
from models.food_path_r14 import load_inputs,condition_state,replace_food,_aware

MODELS=('FOOD_STABLE_PIPELINE_R14B','FOOD_STABLE_OWN_AR_R14B')
LAGS=6
WINDOW=96
MIN_TRAIN=36

def released_rates(levels,available,origin,as_of):
    t=pd.Period(origin,'M'); clock=_aware(as_of)
    if not isinstance(levels.index,pd.PeriodIndex) or not levels.index.is_unique or list(levels.columns)!=['agri4','food_ppi','food']:
        raise ValueError('Unique declared monthly level panel required')
    y=levels.loc[levels.index<t].copy()
    if y.empty or not y.index.equals(pd.period_range(y.index.min(),t-1,freq='M')):
        raise ValueError('Contiguous level calendar through t-1 required')
    a=available.reindex(y.index)
    for col in y:
        dates=pd.to_datetime(a[col].map(lambda value:_aware(value) if pd.notna(value) else pd.NaT),utc=True)
        y.loc[~(dates.notna() & dates.le(clock)),col]=np.nan
    return y.diff(),a

def design(rates):
    values=rates.to_numpy(dtype=float); k=len(rates.columns)
    rows=[]; target=[]; dates=[]
    for i in range(LAGS,len(rates)):
        rows.append(np.concatenate([values[i-l] for l in range(1,LAGS+1)]))
        target.append(values[i]); dates.append(rates.index[i])
    return np.asarray(rows).reshape(-1,k*LAGS),np.asarray(target).reshape(-1,k),pd.PeriodIndex(dates,freq='M')

def prior_variance(sigma,equation):
    return np.array([(.2/lag*sigma[equation]/sigma[j]*(1 if j==equation else .5))**2
        for lag in range(1,LAGS+1) for j in range(len(sigma))])

def companion(beta):
    k=beta.shape[1]
    if beta.shape!=(k*LAGS,k):raise ValueError('Exactly six lag blocks required')
    A=np.zeros((k*LAGS,k*LAGS)); A[:k]=beta.T
    A[k:,:-k]=np.eye(k*(LAGS-1))
    return A

def contract(beta):
    rho=float(np.max(np.abs(np.linalg.eigvals(companion(beta)))))
    c=min(1.,.98/rho) if rho>0 else 1.
    result=beta.copy(); k=beta.shape[1]
    for lag in range(1,LAGS+1):result[(lag-1)*k:lag*k]*=c**lag
    final=float(np.max(np.abs(np.linalg.eigvals(companion(result)))))
    if final>.98+1e-9:raise ArithmeticError('Declared root contraction failed')
    return result,c,rho,final

def fit_rate_var(rates,training_dates,shared_means=None,shared_sigma=None):
    dates=pd.PeriodIndex(training_dates,freq='M')
    if len(dates)<MIN_TRAIN or len(dates)>WINDOW or not dates.is_unique:
        raise ValueError('Complete response window must contain 36..96 unique months')
    selected=rates.loc[dates]
    means=selected.groupby(selected.index.month).mean().reindex(range(1,13)).to_numpy()
    if shared_means is not None:means=np.asarray(shared_means).copy()
    if not np.isfinite(means).all():raise ValueError('All destination calendar means required')
    centered=pd.DataFrame(rates.to_numpy()-means[rates.index.month-1],index=rates.index,columns=rates.columns)
    x,y,index=design(centered); mask=index.isin(dates); x,y,index=x[mask],y[mask],index[mask]
    if len(index)!=len(dates) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Training dates need complete response and six actual monthly lags')
    sigma=centered.loc[dates].to_numpy().std(axis=0,ddof=0)
    if shared_sigma is not None:sigma=np.asarray(shared_sigma).copy()
    if not np.isfinite(sigma).all() or (sigma<=0).any():raise ValueError('Invalid training scale')
    k=len(rates.columns); beta=np.empty((k*LAGS,k))
    for equation in range(k):
        precision=1/prior_variance(sigma,equation)
        beta[:,equation]=np.linalg.solve(x.T@x/sigma[equation]**2+np.diag(precision),x.T@y[:,equation]/sigma[equation]**2)
    raw_beta=beta.copy(); beta,c,rho,final=contract(beta)
    residuals=y-x@beta; raw=residuals.T@residuals/len(residuals)
    Q=.9*raw+.1*np.diag(np.diag(raw))+np.eye(k)*1e-10*np.diag(raw).mean()
    return dict(A=companion(beta),beta=beta,raw_beta=raw_beta,Q=Q,residuals=residuals,sigma=sigma,
        seasonal_means=means,n_train=len(index),training_dates=list(map(str,index)),train_start=str(index.min()),
        train_end=str(index.max()),contraction=c,unconstrained_spectral_radius=rho,spectral_radius=final)

def simulate_rates(A,state,start,steps,seasonal_means):
    rows=[]; current=state.copy(); k=seasonal_means.shape[1]
    for h in range(steps):
        current=A@current
        rows.append(current[:k]+seasonal_means[(pd.Period(start,'M')+h).month-1])
    return np.asarray(rows)

def forecast_origin(levels,available,origin,as_of):
    t=pd.Period(origin,'M'); rates,a=released_rates(levels,available,t,as_of)
    x,target,index=design(rates)
    valid=np.isfinite(x).all(axis=1)&np.isfinite(target).all(axis=1)
    dates=index[valid][-WINDOW:]
    last={col:str(rates[col].last_valid_index()) if rates[col].notna().any() else None for col in rates}
    endpoints={col:{'current':str(a.loc[pd.Period(month,'M'),col]),'previous':str(a.loc[pd.Period(month,'M')-1,col])}
               if month else None for col,month in last.items()}
    diag=dict(status='estimated',as_of=_aware(as_of).isoformat(),last_released_rate=last,last_rate_endpoint_releases=endpoints,
              n_train=len(dates),window_cap=WINDOW,rate_units='100 log points per month')
    empty={name:{h:np.nan for h in range(1,13)} for name in MODELS}
    if len(dates)<MIN_TRAIN:
        diag['status']='insufficient_history'
        return dict(paths=empty,fits=[],forecast_food_rates={},diagnostics=diag)
    candidates=[i for i in range(LAGS-1,len(rates)) if np.isfinite(rates.iloc[i-LAGS+1:i+1].to_numpy()).all()]
    anchor=candidates[-1]; fits=[]; paths={}; foodrates={}; primary=None
    for name,columns in [(MODELS[0],list(rates.columns)),(MODELS[1],['food'])]:
        selected=rates[columns]
        fit=fit_rate_var(selected,dates,primary['seasonal_means'][:,-1:] if primary is not None else None,
                         primary['sigma'][-1:] if primary is not None else None)
        if primary is None:primary=fit
        means=fit['seasonal_means']; k=len(columns)
        state=np.concatenate([selected.iloc[anchor-l].to_numpy()-means[rates.index[anchor-l].month-1] for l in range(LAGS)])
        covariance=np.zeros((k*LAGS,k*LAGS)); process=covariance.copy(); process[:k,:k]=fit['Q']; updates=[]
        for i in range(anchor+1,len(rates)):
            state=fit['A']@state; covariance=fit['A']@covariance@fit['A'].T+process
            observed={j:float(selected.iloc[i,j]-means[rates.index[i].month-1,j]) for j in range(k) if np.isfinite(selected.iloc[i,j])}
            state,covariance=condition_state(state,covariance,observed)
            updates.append(dict(month=str(rates.index[i]),observed_columns=[columns[j] for j in observed],
                state_mean=state[:k].tolist(),state_variance=np.diag(covariance)[:k].tolist()))
        predicted=simulate_rates(fit['A'],state,t,13,means)[:,columns.index('food')]
        path={h:float(100*np.expm1(predicted[h]/100)) for h in range(1,13)}
        if not np.isfinite(list(path.values())).all():path={h:np.nan for h in range(1,13)}
        paths[name]=path; foodrates[name]=predicted.tolist()
        audit={key:fit[key] for key in ('n_train','train_start','train_end','training_dates','contraction','unconstrained_spectral_radius','spectral_radius')}
        audit.update(model=name,columns=columns,status='estimated' if np.isfinite(list(path.values())).all() else 'nonfinite_path',
            sigma=fit['sigma'].tolist(),Q=fit['Q'].tolist(),coefficients=fit['beta'].tolist(),
            unconstrained_coefficients=fit['raw_beta'].tolist(),seasonal_means=means.tolist(),
            anchor_month=str(rates.index[anchor]),conditioning_updates=updates)
        fits.append(audit)
    return dict(paths=paths,fits=fits,forecast_food_rates=foodrates,diagnostics=diag)
