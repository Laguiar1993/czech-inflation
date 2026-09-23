"""Small multivariate persistent-pressure filter and chronological smooth ridge."""
import numpy as np
import pandas as pd


def fit_path(history,origin,q_mu):
    t=pd.Period(origin,'M')
    if not isinstance(history.index,pd.PeriodIndex) or history.index.has_duplicates:
        raise ValueError('Unique monthly index required')
    if (history.index>=t).any():raise ValueError('Current/future category observation')
    f=history.sort_index().tail(96)
    if len(f)<48 or not f.index.equals(pd.period_range(f.index[0],t-1,freq='M')):
        raise ValueError('At least48 contiguous months through t-1 required')
    if f.columns[0]!='core' or not np.isfinite(f.to_numpy()).all() or q_mu not in (.0025,.01):
        raise ValueError('Invalid core/measurement matrix or fixed variance')
    seasonal={m:f.loc[f.index.month==m].mean().to_numpy() for m in range(1,13)}
    y=f.to_numpy()-np.array([seasonal[m.month] for m in f.index])
    dy=np.diff(y,axis=0);mad=1.4826*np.median(abs(dy-np.median(dy,axis=0)),axis=0)/np.sqrt(2)
    r=np.maximum(.05,mad)**2;n=y.shape[1];d=n+2
    transition=np.diag([1.,.3,*([.95]*n)])
    obs=np.column_stack([np.ones((n,2)),np.eye(n)])
    process=np.diag([q_mu,.04,*list(.05*r)])
    covariance=np.diag([1.,1.,*r]);mean=np.zeros(d);identity=np.eye(d)
    trace=[]
    for month,value in zip(f.index,y):
        prior=transition@mean;p=transition@covariance@transition.T+process
        innovation=value-obs@prior;s=obs@p@obs.T+np.diag(r)
        gain=np.linalg.solve(s,obs@p).T
        mean=prior+gain@innovation;res=identity-gain@obs
        covariance=res@p@res.T+(gain*r)@gain.T
        covariance=(covariance+covariance.T)/2
        if not np.isfinite(mean).all() or np.linalg.eigvalsh(covariance).min()<-1e-9:
            raise ValueError('Invalid filtered state/covariance')
        trace.append(dict(month=str(month),common=float(mean[0]),temporary=float(mean[1]),core_specific=float(mean[2])))
    path={h:float(seasonal[(t+h).month][0]+mean[0]+.3**(h+1)*mean[1]+.95**(h+1)*mean[2]) for h in range(1,13)}
    breadth=float(np.mean((y[-3:,1:]>.05).mean(axis=1)-(y[-3:,1:]<-.05).mean(axis=1)))
    return dict(origin=str(t),path=path,mean=mean.tolist(),covariance=covariance.tolist(),
                seasonal={m:v.tolist() for m,v in seasonal.items()},observation_variance=r.tolist(),
                columns=f.columns.tolist(),q_mu=q_mu,n_history=len(f),history_start=str(f.index[0]),
                history_end=str(f.index[-1]),trace=trace,breadth3=breadth)


def smooth_correction(features,labels,origin,clock,current):
    t=pd.Period(origin,'M');cutoff=pd.Timestamp(clock);p=len(current)
    if labels.duplicated(['origin','h']).any():raise ValueError('Duplicate saved prediction labels')
    if not np.isfinite(current).all():return dict(status='fallback_missing_features',correction=[0.]*12)
    targets=pd.PeriodIndex(labels.target,freq='M');sources=pd.PeriodIndex(labels.origin,freq='M')
    releases=pd.to_datetime(labels.released)
    use=labels.loc[(targets<t)&(sources<t)&releases.notna()&releases.le(cutoff)].copy()
    groups=[];training=[]
    for h in range(1,13):
        g=use[use.h.eq(h)].sort_values('origin');rows=[]
        for row in g.itertuples():
            x=features.get(row.origin)
            if x is not None and len(x)==p and np.isfinite(x).all() and np.isfinite(row.error):rows.append((x,row.error,row))
        rows=rows[-96:]
        if len(rows)<24:return dict(status='fallback_insufficient_labels',correction=[0.]*12,h=h,n=len(rows))
        groups.append(rows);training.extend(row[2] for row in rows)
    pooled=np.array([x for group in groups for x,y,row in group]);rms=np.sqrt(np.mean(pooled*pooled,axis=0))
    rms=np.where(rms<1e-8,1.,rms);A=np.zeros((12*p,12*p));b=np.zeros(12*p)
    for i,group in enumerate(groups):
        x=np.array([x for x,y,row in group])/rms;y=np.array([y for x,y,row in group]);s=slice(i*p,(i+1)*p)
        A[s,s]=x.T@x/len(y)/12+np.eye(p)/12;b[s]=x.T@y/len(y)/12
    for h in range(1,12):
        a=slice((h-1)*p,h*p);z=slice(h*p,(h+1)*p);pen=np.eye(p)/11
        A[a,a]+=pen;A[z,z]+=pen;A[a,z]-=pen;A[z,a]-=pen
    beta=np.linalg.solve(A,b).reshape(12,p);correction=beta@(np.asarray(current)/rms)
    return dict(status='estimated',correction=correction.tolist(),coefficients=beta.tolist(),rms=rms.tolist(),
        n_by_h=[len(g) for g in groups],training_origins=[r.origin for r in training],
        training_targets=[r.target for r in training],training_h=[int(r.h) for r in training],
        training_releases=[str(r.released) for r in training],normal_equation_error=float(np.max(abs(A@beta.ravel()-b))))
