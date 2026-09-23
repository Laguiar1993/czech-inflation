"""Joint Bayesian-ridge / elastic-net / nonlinear-residual pressure dynamics."""
import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet
from sklearn.ensemble import RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from models.food_path_r14 import condition_state

LAGS=6
FAMILIES={
 'JOINT_OWN_R22':['core'],
 'JOINT_DOMESTIC_R22':['core','services','housing','unemployment','ulc','ip'],
 'JOINT_IMPORTED_R22':['core','goods','imports','ppi','fx','brent','metals'],
 'JOINT_LINEAR_R22':['core','services','housing','goods','unemployment','ulc','ip','imports','ppi','fx','brent','metals'],
}
FAMILIES['JOINT_ENET_R22']=FAMILIES['JOINT_LINEAR_R22']
FAMILIES['JOINT_RF_R22']=FAMILIES['JOINT_LINEAR_R22']
NO_SEASON={'unemployment','ulc','ip'}
SHOCKS={'ulc':2.,'unemployment':.5,'fx':100*np.log1p(.05),'brent':100*np.log1p(.2)}


def local(stamp):
    t=pd.Timestamp(stamp)
    if pd.isna(t):raise ValueError('Known forecast clock required')
    return t.tz_convert('Europe/Prague').tz_localize(None) if t.tzinfo else t


def mask_panel(panel,available,origin,asof):
    t=pd.Period(origin,'M');clock=local(asof)
    y=panel.loc[panel.index<=t].copy()
    for col in y:
        a=pd.to_datetime(available[col].reindex(y.index))
        y.loc[~(a.notna()&a.le(clock)),col]=np.nan
        if col in ['core','services','housing','goods']:y.loc[y.index>=t,col]=np.nan
    return y


def companion(beta):
    k=beta.shape[1]
    if beta.shape!=(1+LAGS*k,k):raise ValueError('Six-lag coefficient matrix required')
    a=np.zeros((LAGS*k,LAGS*k));a[:k]=beta[1:].T;a[k:,:-k]=np.eye((LAGS-1)*k)
    return a


def stabilize(beta):
    rho=float(max(abs(np.linalg.eigvals(companion(beta)))))
    c=min(1.,.98/rho) if rho else 1.;b=beta.copy();k=beta.shape[1]
    for lag in range(1,LAGS+1):b[1+(lag-1)*k:1+lag*k]*=c**lag
    final=float(max(abs(np.linalg.eigvals(companion(b)))))
    if final>.980000001:raise ArithmeticError('Companion stability contraction failed')
    return b,dict(raw_radius=rho,radius=final,contraction=c)


def preprocessing(y,dates,origin):
    history=y.loc[y.index<origin]
    detrended=history-history.rolling(12,min_periods=12).mean()
    seasonal=detrended.loc[dates].groupby(dates.month).mean().reindex(range(1,13))
    seasonal=seasonal-seasonal.mean()
    for col in y:
        if col in NO_SEASON:seasonal[col]=0.
    if not np.isfinite(seasonal.to_numpy()).all():raise ValueError('Incomplete seasonal history')
    adjusted=y.copy()
    for col in y:adjusted[col]-=seasonal[col].reindex(y.index.month).to_numpy()
    center=pd.Series({col:adjusted.loc[adjusted.index<origin,col].dropna().tail(12).mean() for col in y})
    sigma=adjusted.loc[dates].std(ddof=0).clip(lower=.05)
    return (adjusted-center)/sigma,seasonal,center,sigma


def design(z,dates):
    xx=[]
    for t in dates:xx.append(np.r_[1.,*[z.loc[t-lag].to_numpy() for lag in range(1,LAGS+1)]])
    return np.asarray(xx),z.loc[dates].to_numpy()


def fit_system(z,dates,columns,kind='linear'):
    x,y=design(z[columns],dates);k=len(columns)
    prior=np.zeros((1+k*LAGS,k));beta=prior.copy()
    for j,col in enumerate(columns):prior[1+j,j]=.95 if col in NO_SEASON else .8
    if kind=='enet':
        for j in range(k):
            fit=ElasticNet(alpha=.02,l1_ratio=.5,fit_intercept=False,max_iter=20000,tol=1e-8)
            with warnings.catch_warnings():
                warnings.simplefilter('error',ConvergenceWarning);fit.fit(x,y[:,j]-x@prior[:,j])
            beta[:,j]=prior[:,j]+fit.coef_
    else:
        for j in range(k):
            sd=np.r_[.2,[.2/lag*(1. if source==j else .5) for lag in range(1,LAGS+1) for source in range(k)]]
            precision=1/sd**2
            beta[:,j]=np.linalg.solve(x.T@x+np.diag(precision),x.T@y[:,j]+precision*prior[:,j])
    raw=beta.copy();beta,info=stabilize(beta)
    residual=y-x@beta;cov=residual.T@residual/len(y)
    q=.9*cov+.1*np.diag(np.diag(cov))+np.eye(k)*1e-8
    forest=None
    if kind=='forest':
        forest=RandomForestRegressor(n_estimators=200,min_samples_leaf=8,max_features=1.,random_state=42,n_jobs=2)
        forest.fit(x[:,1:],residual[:,columns.index('core')])
        forest.set_params(n_jobs=1)  # Small recursive prediction batches; deterministic tree order.
    return dict(beta=beta,raw_beta=raw,A=companion(beta),Q=q,forest=forest,**info)


def advance(fit,state):
    out=fit['A']@state;k=fit['beta'].shape[1];out[:k]+=fit['beta'][0]
    return out


def simulate(fit,state,columns,center,sigma,seasonal,origin,steps=12):
    out=[];s=state.copy();k=len(columns);core=columns.index('core')
    for h in range(1,steps+1):
        old=s.copy();s=advance(fit,s)
        if fit['forest'] is not None:s[core]+=.5*float(fit['forest'].predict(old[None,:])[0])
        raw=s[:k]*sigma.to_numpy()+center.to_numpy()+seasonal.loc[(origin+h).month].to_numpy()
        if not np.isfinite(raw).all():raise ArithmeticError('Nonfinite system forecast')
        out.append(raw)
    return np.asarray(out)


def run_origin(panel,available,origin,asof,families=None):
    families=FAMILIES if families is None else families;t=pd.Period(origin,'M');y=mask_panel(panel,available,t,asof)
    if not y.index.equals(pd.period_range(y.index.min(),t,freq='M')):raise ValueError('Complete calendar through origin required')
    history=y.loc[y.index<t];complete=history.notna().all(axis=1)
    good=complete.copy()
    for lag in range(1,LAGS+1):good &= complete.shift(lag,fill_value=False)
    dates=history.index[good][-96:]
    result=dict(paths={},drivers={},fits={},responses=[],status='insufficient_common_history',n_train=len(dates))
    if len(dates)<36:return result
    z,seasonal,center,sigma=preprocessing(y,dates,t)
    anchor=dates[-1]
    result.update(status='estimated',preprocessing=dict(seasonal=seasonal.to_dict(),center=center.to_dict(),sigma=sigma.to_dict()))
    for name,columns in families.items():
        kind='enet' if name=='JOINT_ENET_R22' else 'forest' if name=='JOINT_RF_R22' else 'linear'
        fit=fit_system(z,dates,columns,kind);k=len(columns)
        state=np.concatenate([z.loc[anchor-lag,columns].to_numpy() for lag in range(LAGS)])
        cov=np.zeros((k*LAGS,k*LAGS));process=cov.copy();process[:k,:k]=fit['Q'];updates=[]
        # Linear Kalman update handles both the historical ragged edge and permitted known macro month t.
        for m in pd.period_range(anchor+1,t,freq='M'):
            state=advance(fit,state);cov=fit['A']@cov@fit['A'].T+process
            observed={j:float(z.loc[m,col]) for j,col in enumerate(columns) if np.isfinite(z.loc[m,col])}
            state,cov=condition_state(state,cov,observed)
            if np.linalg.eigvalsh(cov).min() < -1e-7:raise ArithmeticError('Non-PSD conditioned covariance')
            updates.append(dict(month=str(m),observed=[columns[j] for j in observed]))
        selected=(center[columns],sigma[columns],seasonal[columns])
        prediction=simulate(fit,state,columns,*selected,t)
        core_mm=100*np.expm1(prediction[:,columns.index('core')]/100)
        if not np.isfinite(core_mm).all():raise ArithmeticError('Nonfinite core monthly forecast')
        result['paths'][name]=core_mm.tolist();result['drivers'][name]=pd.DataFrame(prediction,index=range(1,13),columns=columns).to_dict()
        result['fits'][name]=dict(columns=columns,kind=kind,train_dates=list(map(str,dates)),n_train=len(dates),
            raw_radius=fit['raw_radius'],radius=fit['radius'],contraction=fit['contraction'],coefficients=fit['beta'].tolist(),
            raw_coefficients=fit['raw_beta'].tolist(),residual_covariance=fit['Q'].tolist(),
            anchor=str(anchor),updates=updates,known_h0=updates[-1]['observed'],state_at_internal_h0=state.tolist(),
            state_covariance=cov.tolist(),forest_importance=fit['forest'].feature_importances_.tolist() if fit['forest'] is not None else None)
        for variable,shock in SHOCKS.items():
            if variable not in columns:continue
            shifted=state.copy();shifted[columns.index(variable)]+=shock/sigma[variable]
            alternative=simulate(fit,shifted,columns,*selected,t)
            difference=np.cumsum(alternative[:,columns.index('core')]-prediction[:,columns.index('core')])
            for h in [3,6,12]:result['responses'].append(dict(model=name,variable=variable,shock=shock,h=h,core_cumulative_log_response=float(difference[h-1])))
    return result
