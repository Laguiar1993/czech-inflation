"""Quarterly direct core corrections with nested chronological regularization."""
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear
from sklearn.linear_model import ElasticNet
from sklearn.exceptions import ConvergenceWarning
from data.cost_gaps_r23 import local,COLUMNS

FAMILIES={
 'GAP_CALIBRATION_R23':([], 'ridge'),
 'GAP_DOMESTIC_R23':(['ulc_gap','tightening'],'positive'),
 'GAP_IMPORTED_R23':(['import_gap','ppi_gap','fx_news'],'positive'),
 'GAP_JOINT_R23':(COLUMNS,'positive'),
 'GAP_FREE_R23':(COLUMNS,'ridge'),
 'GAP_ENET_R23':(COLUMNS,'enet')}


def monthly_correction(bands):
    y=np.asarray(bands,float)
    if y.shape!=(4,) or not np.isfinite(y).all():raise ValueError('Four finite band averages required')
    basis=np.column_stack([np.interp(np.arange(1,13),[2,5,8,11],np.eye(4)[:,j]) for j in range(4)])
    mapping=basis.reshape(4,3,4).mean(axis=1)
    return basis@np.linalg.solve(mapping,y)


def fit(x,y,now,alpha,kind):
    if not np.isfinite(x.to_numpy()).all() or not np.isfinite(y).all() or not np.isfinite(now).all():raise ValueError('Nonfinite fitting data')
    mean=x.mean();scale=x.std(ddof=0);scale=scale.where(scale>1e-8,1.)
    design=np.column_stack([np.ones(len(x)),((x-mean)/scale).to_numpy()]);test=np.r_[1.,((now-mean)/scale).to_numpy()]
    target=np.asarray(y,float);p=design.shape[1]
    if kind=='positive':
        xx=np.vstack([design/np.sqrt(len(x)),np.sqrt(alpha)*np.eye(p)])
        yy=np.vstack([target/np.sqrt(len(x)),np.zeros((p,4))])
        lower=np.r_[-np.inf,np.zeros(p-1)];upper=np.full(p,np.inf);columns=[]
        for j in range(4):
            f=lsq_linear(xx,yy[:,j],bounds=(lower,upper),tol=1e-12,max_iter=500)
            if not f.success:raise RuntimeError('Bounded ridge did not converge')
            columns.append(f.x)
        beta=np.column_stack(columns)
    elif kind=='ridge':beta=np.linalg.solve(design.T@design/len(x)+alpha*np.eye(p),design.T@target/len(x))
    elif kind=='enet':
        cols=[]
        for j in range(4):
            f=ElasticNet(alpha=alpha,l1_ratio=.5,fit_intercept=False,max_iter=50000,tol=1e-8)
            with warnings.catch_warnings():warnings.simplefilter('error',ConvergenceWarning);f.fit(design,target[:,j])
            cols.append(f.coef_)
        beta=np.column_stack(cols)
    else:raise ValueError('Unknown learner')
    prediction=test@beta
    return dict(prediction=prediction.tolist(),coefficients=beta.tolist(),mean=mean.to_dict(),scale=scale.to_dict(),columns=list(x),
                contributions=(test[:,None]*beta).tolist(),alpha=float(alpha),kind=kind)


def eligible(x,y,available,origin,clock,minimum):
    t=pd.Period(origin,'M');a=pd.to_datetime(available.reindex(x.index));yy=y.reindex(x.index)
    okay=(x.index.month%3==0)&((x.index+12)<t)&a.notna()&a.le(local(clock))&x.notna().all(axis=1)&yy.notna().all(axis=1)
    keys=x.index[okay][-40:]
    return keys if len(keys)>=minimum else keys[:0]


def choose(x,y,available,clocks,origin,clock,columns,kind):
    grid=(.01,.1,1.) if kind=='enet' else (.1,1.,10.);default=.1 if kind=='enet' else 1.
    keys=eligible(x,y,available,origin,clock,24);folds=[]
    for v in keys:
        inner=eligible(x,y,available,v,clocks.loc[v],16)
        if len(inner):folds.append((v,inner))
    folds=folds[-8:];audit=[];scores={}
    if len(folds)<4:return dict(alpha=default,status='default_insufficient_validation',scores=scores,validation=audit)
    for alpha in grid:
        losses=[]
        for v,inner in folds:
            result=fit(x.loc[inner,columns],y.loc[inner].to_numpy(),x.loc[v,columns],alpha,kind)
            error=3*np.cumsum(np.array(result['prediction'])-y.loc[v].to_numpy())
            losses.append(float(np.mean(error**2)))
            audit.append(dict(alpha=alpha,validation_origin=str(v),validation_clock=str(local(clocks.loc[v])),
                n_train=len(inner),first_training_origin=str(inner[0]),last_training_origin=str(inner[-1]),
                last_training_target=str(inner[-1]+12),max_training_release=str(pd.to_datetime(available.loc[inner]).max()),
                validation_target=str(v+12),validation_available=str(available.loc[v]),loss=losses[-1]))
        scores[str(alpha)]=float(np.mean(losses))
    alpha=min(grid,key=lambda a:(scores[str(a)],-a))
    return dict(alpha=alpha,status='nested_selected',scores=scores,validation=audit)


def run_origin(x,y,available,clocks,origin,asof):
    t=pd.Period(origin,'M');keys=eligible(x,y,available,t,asof,24)
    out=dict(status='insufficient_common_history',n_train=len(keys),train_dates=list(map(str,keys)),fits={},paths={},selection={})
    if len(keys)<24:return out
    if t not in x.index or not np.isfinite(x.loc[t]).all():out['status']='missing_current_features';return out
    for name,(columns,kind) in FAMILIES.items():
        setting=choose(x,y,available,clocks,t,asof,columns,kind) if columns else dict(alpha=1.,status='fixed_intercept_control',scores={},validation=[])
        result=fit(x.loc[keys,columns],y.loc[keys].to_numpy(),x.loc[t,columns],setting['alpha'],kind)
        out['fits'][name]=result;out['paths'][name]=monthly_correction(result['prediction']).tolist();out['selection'][name]=setting
    out['paths']['GAP_HALF_R23']=(.5*np.array(out['paths']['GAP_JOINT_R23'])).tolist();out['status']='estimated'
    return out
