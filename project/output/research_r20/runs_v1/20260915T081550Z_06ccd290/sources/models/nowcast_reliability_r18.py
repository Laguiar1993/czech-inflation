"""Sequential empirical error laws. Consensus is confined to event evaluation."""
import numpy as np
import pandas as pd


def past_scale(errors):
    e=np.asarray(errors,float)
    if not np.isfinite(e).all():raise ValueError('Nonfinite past errors')
    if not len(e):return .25
    short=np.abs(e[-12:]);long=np.abs(e[-36:]);n=len(short)
    return float(max(.05,(n*short.mean()+12*long.mean())/(n+12)))


def _distribution(support,weights):
    x=np.asarray(support,float);w=np.asarray(weights,float)
    if x.ndim!=1 or x.shape!=w.shape or not len(x):raise ValueError('Invalid support shape')
    if not np.isfinite(x).all() or not np.isfinite(w).all() or (w<0).any() or w.sum()<=0:
        raise ValueError('Invalid probability distribution')
    return x,w/w.sum()


def weighted_quantile(support,weights,p):
    if not 0<=p<=1:raise ValueError('Quantile outside unit interval')
    x,w=_distribution(support,weights);order=np.argsort(x,kind='stable')
    j=min(np.searchsorted(np.cumsum(w[order]),p,side='left'),len(x)-1)
    return float(x[order[j]])


def crps(support,weights,actual):
    x,w=_distribution(support,weights)
    return float(w@abs(x-actual)-.5*w@abs(x[:,None]-x[None,:])@w)


def event_probabilities(support,weights,point,consensus):
    x,w=_distribution(support,weights)
    gain=abs(x-consensus)-abs(x-point)
    return dict(p_material_gain=float(w@(gain>=.15-1e-9)),p_big=float(w@(abs(x-consensus)>=.4-1e-9)))


def error_law(history,origin,clock,point,features,family):
    if family not in ('POOLED','SCALE','STATE'):raise ValueError('Unknown error law')
    if history.origin.duplicated().any():raise ValueError('Duplicate error origins')
    t=pd.Period(origin,'M');clock=pd.Timestamp(clock)
    months=pd.PeriodIndex(history.origin,freq='M');release=pd.to_datetime(history.released)
    use=history.loc[(months<t)&release.notna()&release.le(clock)].sort_values('origin').copy()
    if not np.isfinite(use[['error','own_scale','full_gap','category_gap']].to_numpy(float)).all():
        raise ValueError('Nonfinite eligible history')
    scale=past_scale(use.error.to_numpy());use=use.tail(60);n=len(use)
    meta=dict(n=n,current_scale=scale,training_origins=use.origin.tolist(),
              training_releases=use.released.astype(str).tolist(),kernel_fallback=False)
    if n<24:return dict(status='insufficient_history',**meta)
    if not np.isfinite(point) or not np.isfinite(features).all() or (use.own_scale<=0).any():
        raise ValueError('Invalid current point/features or own-origin scale')
    if family=='POOLED':
        x=point+use.error.to_numpy();w=np.ones(n)/n
    else:
        x=point+scale*use.error.to_numpy()/use.own_scale.to_numpy()
        age=t.ordinal-pd.PeriodIndex(use.origin,freq='M').asi8
        w=np.exp(-np.log(2)*age/24);w/=w.sum()
        if family=='STATE':
            f=use[['full_gap','category_gap']].to_numpy(float)
            rms=np.maximum(.05,np.sqrt(np.mean(f*f,axis=0)))
            kernel=np.exp(-.5*np.sum(((f-np.asarray(features))/rms)**2,axis=1))*w
            if kernel.sum()>1e-250:w=.5*w+.5*kernel/kernel.sum()
            else:meta['kernel_fallback']=True
    w/=w.sum()
    return dict(status='estimated',support=x.tolist(),weights=w.tolist(),ess=float(1/(w@w)),**meta)
