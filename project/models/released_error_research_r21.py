"""R21 research: learn only from released, saved forecast errors."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import ElasticNet

PRIOR=np.array([.5,.25,.25])


def eligible_rows(rows,origin,as_of):
    dates=pd.to_datetime(rows.available_from)
    months=pd.PeriodIndex(rows.target,freq='M')
    return rows.loc[(months<pd.Period(origin,'M')) & dates.le(pd.Timestamp(as_of))].copy()


def bias_offset(rows,minimum=12):
    z=rows.dropna(subset=['error']).sort_values('target').tail(24)
    if len(z)<minimum:return 0.
    m=pd.PeriodIndex(z.target,freq='M').asi8
    weights=2.**(-(m.max()-m)/12.)
    return float(np.average(z.error,weights=weights)*len(z)/(len(z)+24))


def blend_paths(paths,weights):
    paths=np.asarray(paths,float);weights=np.asarray(weights,float)
    if paths.shape!=(3,12) or weights.shape!=(3,):raise ValueError('Three twelve-month paths required')
    if not np.isfinite(paths).all() or (paths<=-100).any():raise ValueError('Invalid monthly paths')
    if min(weights)<-1e-10 or not np.isclose(sum(weights),1):raise ValueError('Invalid convex weights')
    return weights@paths


def pool_weights(predictions,actual_cumulative,mask,target_age):
    """Exact monthly-rate mixture, cumulative log loss on published prefixes.

    actual_cumulative contains h1..h cumulative log points, NOT monthly rates.
    Mask is the caller's strict prefix-publication and window eligibility test.
    Unmasked outcomes are removed before loss/scaling arithmetic.
    """
    p=np.asarray(predictions,float);mask=np.asarray(mask,bool)
    a=np.asarray(actual_cumulative,float);age=np.asarray(target_age,float)
    if p.ndim!=3 or p.shape[1:]!=(3,12) or mask.shape!=(len(p),12) or a.shape!=mask.shape or age.shape!=mask.shape:
        raise ValueError('Invalid pool array dimensions')
    if not np.isfinite(p).all() or (p<=-100).any():raise ValueError('Invalid training forecasts')
    if not np.isfinite(a[mask]).all():raise ValueError('Missing released outcomes')
    if not len(p) or (mask.sum(axis=0)<6).any():return PRIOR.copy()
    a=np.where(mask,a,0.)
    rw=np.where(mask,2.**(-age/12.),0.);rw/=rw.sum(axis=0)
    def cumulative(w):return 100*np.cumsum(np.log1p(np.einsum('nmh,m->nh',p,w)/100),axis=1)
    scale=np.maximum(np.sum(rw*(cumulative(PRIOR)-a)**2,axis=0),.01**2)
    def loss(w):return float(np.mean(np.sum(rw*(cumulative(w)-a)**2,axis=0)/scale)+.05*np.sum((w-PRIOR)**2))
    result=minimize(loss,PRIOR,method='SLSQP',bounds=[(.25,1.),(0.,.75),(0.,.75)],
                    constraints={'type':'eq','fun':lambda w:sum(w)-1},options={'ftol':1e-12,'maxiter':250})
    if not result.success or not np.isfinite(result.fun):raise RuntimeError('Pool optimizer failed: '+str(result.message))
    w=np.maximum(result.x,0.);w/=w.sum()
    return w


def offset_prediction(features,labels,available,origin,as_of,kind,minimum=24,window=60):
    """Headline actual-minus-BASE target. Consensus is not accepted."""
    dates=pd.to_datetime(available.reindex(labels.index))
    ix=labels.index[(labels.index<origin)&dates.le(pd.Timestamp(as_of)).to_numpy()&labels.notna().to_numpy()]
    ix=ix[-window:];n=len(ix)
    info=dict(correction=0.,n=n,last_release=dates.loc[ix].max().isoformat() if n else None,
              train_origins='|'.join(map(str,ix)),status='warmup')
    if n<minimum:return info
    xx=features.loc[ix].astype(float);now=features.loc[[origin]].astype(float)
    if np.isinf(xx.to_numpy()).any() or np.isinf(now.to_numpy()).any():raise ValueError('Infinite features')
    means=xx.mean().fillna(0.);xx=xx.fillna(means);now=now.fillna(means)
    scale=xx.std().fillna(1.).replace(0.,1.)
    z=(xx-means)/scale;zn=(now-means)/scale
    y=labels.loc[ix].to_numpy(float);weights=2.**(-(origin.ordinal-ix.asi8)/12.)
    intercept=float(np.average(y,weights=weights));shrink=n/(n+24.)
    if kind=='mean':correction=shrink*intercept
    elif kind=='enet':
        model=ElasticNet(alpha=.05,l1_ratio=.5,fit_intercept=False,max_iter=20000,tol=1e-9)
        model.fit(z,y-intercept,sample_weight=weights)
        correction=shrink*intercept+float(model.predict(zn)[0])
    else:raise ValueError('Unknown offset model')
    info.update(correction=float(correction),status='estimated')
    return info
