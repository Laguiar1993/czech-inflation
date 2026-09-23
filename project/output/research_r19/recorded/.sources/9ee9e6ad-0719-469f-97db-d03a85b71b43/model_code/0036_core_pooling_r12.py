"""Prespecified partial pooling of R10 category dynamics; no survey inputs.

The sixth rate is a scaled statistical reconciliation, not an official category.
All data preparation, scaling and imputation occur after origin publication masks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.core_split import CATEGORIES, REMAINDER, own_features, visible_history
from models.core_tuning import _monthly

VARIANTS = ('POOL_SEPARATE', 'POOL_12', 'POOL_48')
DYNAMIC = ('own_l1', 'own_l2', 'own_l12', 'common_core_l1')
ALPHA = 3.


def solve_pooled(xs, ys, now, *, deviation_penalty):
    """Solve already centred/scaled panel equations with a shared dynamic slope.

    Four common coefficients and four deviations per equation; the other eleven
    coefficients are equation-specific calendar effects. Loss is an unaveraged
    sum across all equations/observations as fixed in the experiment specification.
    Returns standardised predictions and total dynamic slopes for audit.
    """
    if not np.isfinite(deviation_penalty) or deviation_penalty<=0:
        raise ValueError('deviation penalty must be positive and finite')
    groups = len(xs)
    if not groups or len(ys)!=groups or len(now)!=groups:
        raise ValueError('one target and prediction row per equation required')
    width, shared = 15, len(DYNAMIC)
    ncoef = shared+groups*width
    gram = np.zeros((ncoef,ncoef))
    rhs = np.zeros(ncoef)
    penalty = np.full(ncoef,ALPHA)
    prediction_rows = []
    for j,(x,y,p) in enumerate(zip(xs,ys,now)):
        x,y,p = np.asarray(x,float),np.asarray(y,float),np.asarray(p,float)
        if x.ndim!=2 or x.shape[1]!=width or y.shape!=(len(x),) or p.shape!=(width,):
            raise ValueError('invalid panel dimensions')
        if not all(np.isfinite(v).all() for v in (x,y,p)):
            raise ValueError('panel arrays must be finite')
        start = shared+j*width
        design = np.zeros((len(x),ncoef))
        design[:,:shared] = x[:,:shared]
        design[:,start:start+width] = x
        gram += design.T@design
        rhs += design.T@y
        penalty[start:start+shared] = deviation_penalty
        row = np.zeros(ncoef)
        row[:shared] = p[:shared]
        row[start:start+width] = p
        prediction_rows.append(row)
    beta = np.linalg.solve(gram+np.diag(penalty),rhs)
    coefficients = np.asarray([beta[:shared]+beta[shared+j*width:shared+j*width+shared]
                               for j in range(groups)])
    return np.asarray(prediction_rows)@beta, coefficients


def forecast_origin(core,categories,available,origin,as_of,weights,*,core_weight):
    """Return three fixed core forecasts, origin metadata and block contributions."""
    if not np.isfinite(core_weight) or not 0<core_weight<=1:
        raise ValueError('core weight must be in (0,1]')
    if (not categories.columns.is_unique or not weights.index.is_unique
            or set(categories.columns)!=set(CATEGORIES) or set(weights.index)!=set(CATEGORIES)):
        raise ValueError('the five declared categories and weights are required')
    if not np.isfinite(weights).all() or (weights<=0).any() or weights.sum()>=core_weight:
        raise ValueError('category weights must leave a positive residual weight')
    for values,name in ((core,'core'),(categories,'categories'),(available,'available')):
        _monthly(values,name)
    if origin not in core.index:
        raise ValueError('core history including the forecast origin is required')
    weights = weights.reindex(CATEGORIES)
    c = visible_history(core,origin,as_of,available)
    cat = visible_history(categories.reindex(index=core.index,columns=CATEGORIES),origin,as_of,available)
    common = c.notna() & cat.notna().all(axis=1)
    cat = cat.where(common,np.nan)
    scales = weights.reindex(CATEGORIES).copy()
    scales.loc[REMAINDER] = core_weight-scales.sum()
    remaining = (core_weight*c-cat.mul(weights).sum(axis=1,min_count=5)).where(common)
    targets = cat.reindex(columns=CATEGORIES).copy()
    targets[REMAINDER] = remaining/scales.loc[REMAINDER]
    difference = targets.mul(scales).sum(axis=1,min_count=6)-core_weight*c.where(common)
    train = core.index[common]
    metadata = dict(n_train=len(train),train_start=train.min() if len(train) else None,
        train_end=train.max() if len(train) else None,
        training_last_release=pd.to_datetime(available.reindex(train)).max(),
        as_of=pd.Timestamp(as_of))
    result = dict(predictions={name:np.nan for name in VARIANTS},fits=[],contributions=[],coefficients=[],
        max_reconciliation_error=float(difference.abs().max()),feature_columns=list(DYNAMIC)+[f'mon_{m}' for m in range(2,13)])
    failure = ('previous_target_unavailable' if origin-1 not in targets.index
               or targets.loc[origin-1].isna().any() else
               'insufficient_history' if len(train)<48 else None)
    if failure:
        result['fits'] = [dict(model=name,block='all',fit_status=failure,**metadata) for name in VARIANTS]
        return result
    xs,ys,now,centers,target_scales,dropped = [],[],[],[],[],[]
    for block in targets:
        y = targets[block]
        frame = own_features(y)
        frame.insert(3,'common_core_l1',c.shift(1))
        x,x_now = frame.loc[train].astype(float),frame.loc[origin].astype(float)
        if np.isinf(x.to_numpy()).any() or np.isinf(x_now.to_numpy()).any():
            raise ValueError('predictors must be finite or missing')
        means = x.mean()
        dropped.append(means.index[means.isna()].tolist())
        means = means.fillna(0.)
        x,x_now = x.fillna(means),x_now.fillna(means)
        scale = x.std().replace(0.,1.).fillna(1.)
        # Floating summation can give identical values a tiny nonzero SD.
        # Such a column must not turn roundoff into an economic signal.
        scale.loc[x.nunique()<=1] = 1.
        yy = y.loc[train]
        yc,yscale = float(yy.mean()),float(yy.std())
        if not np.isfinite(yscale) or yscale==0 or yy.nunique()<=1:
            yscale = 1.
        xs.append(((x-means)/scale).to_numpy())
        now.append(((x_now-means)/scale).to_numpy())
        ys.append(((yy-yc)/yscale).to_numpy())
        centers.append(yc)
        target_scales.append(yscale)
    for model in VARIANTS:
        if model=='POOL_SEPARATE':
            beta = [np.linalg.solve(x.T@x+ALPHA*np.eye(x.shape[1]),x.T@y) for x,y in zip(xs,ys)]
            estimates = np.asarray([p@b for p,b in zip(now,beta)])
            dynamics = np.asarray([b[:4] for b in beta])
        else:
            estimates,dynamics = solve_pooled(xs,ys,now,deviation_penalty=float(model.split('_')[1]))
        rates = np.asarray(centers)+np.asarray(target_scales)*estimates
        result['predictions'][model] = float(rates@scales.to_numpy()/core_weight)
        for j,block in enumerate(targets):
            result['fits'].append(dict(model=model,block=block,fit_status='estimated',
                target_center=centers[j],target_scale=target_scales[j],
                dropped_columns='|'.join(dropped[j]),**metadata))
            result['contributions'].append(dict(model=model,block=block,prediction=rates[j],
                weight=scales.loc[block],contribution=rates[j]*scales.loc[block],
                units='headline percentage-point projection'))
            result['coefficients'].append(dict(model=model,block=block,
                                               **dict(zip(DYNAMIC,dynamics[j]))))
    return result
