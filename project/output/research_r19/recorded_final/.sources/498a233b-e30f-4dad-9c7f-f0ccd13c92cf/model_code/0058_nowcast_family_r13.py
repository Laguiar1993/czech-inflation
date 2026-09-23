"""R13 fixed own-error corrections, with historical origin weight provenance."""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.core_split import CATEGORIES, REMAINDER, own_features, visible_history
from models.core_tuning import ridge_prediction
from models.independent_nowcast import policy_frame, residual_correction


def category_raw(core, categories, available, origin, as_of, weights, *, core_weight):
    """Only the unchanged TARGET_OWN equations; no other experimental fits."""
    if not np.isfinite(core_weight) or not 0<core_weight<=1:
        raise ValueError('core weight must be in (0,1]')
    if (set(categories.columns)!=set(CATEGORIES) or not categories.columns.is_unique
            or set(weights.index)!=set(CATEGORIES) or not weights.index.is_unique
            or not np.isfinite(weights).all() or (weights<=0).any() or weights.sum()>=1):
        raise ValueError('five valid unique category weights are required')
    c=visible_history(core,origin,as_of,available)
    cat=visible_history(categories.reindex(core.index),origin,as_of,available)
    common=cat.notna().all(axis=1)&c.notna()
    ct=cat.where(common,np.nan)
    remaining=(core_weight*c-ct.mul(weights).sum(axis=1,min_count=5)).where(common)
    identity=ct.mul(weights).sum(axis=1,min_count=5)+remaining-core_weight*c.where(common)
    targets={name:ct[name] for name in CATEGORIES}
    targets[REMAINDER]=remaining
    total=0.; fits=[]
    for block,target in targets.items():
        if origin-1 not in target.index or pd.isna(target.loc[origin-1]):
            fit=dict(prediction=np.nan,fit_status='previous_target_unavailable',n_train=0)
        else:
            fit=ridge_prediction(own_features(target),target,origin,as_of,available)
        weight=weights[block] if block in weights else 1.
        total+=weight*fit['prediction']
        fits.append(dict(block=block,weight=weight,**fit))
    return dict(prediction=total/core_weight,fits=fits,
                reconciliation_error=float(identity.abs().max()))


def category_history(core,categories,available,decisions,weight_provider):
    """Forecast each historical date once using its own weight-provider call.

    Every outcome/error is stored with its DETAIL publication timestamp. It is
    not necessarily known at the forecast clock; eligible_errors gates later use.
    """
    rows=[]; fits=[]
    for origin,clock in decisions.items():
        row=dict(period=str(origin),as_of=clock,target_available_from=available.loc[origin],
                 raw_core=np.nan,error=np.nan,core_weight=np.nan,status='missing_decision')
        if pd.isna(clock):
            rows.append(row); continue
        known=((core.index<origin)&available.le(clock).to_numpy()&core.notna().to_numpy()
               &categories.reindex(core.index).notna().all(axis=1).to_numpy())
        row['n_common_labels']=int(known.sum())
        if known.sum()<48:
            row['status']='insufficient_history'; rows.append(row); continue
        cw,weights=weight_provider(origin,clock)
        result=category_raw(core,categories,available,origin,clock,weights,core_weight=cw)
        prediction=result['prediction']
        row.update(raw_core=prediction,error=float(core.loc[origin]-prediction),core_weight=cw,
            status='estimated' if np.isfinite(prediction) else 'raw_fit_unavailable',
            basket_regime=weights.attrs.get('effective_year'),
            basket_available_from=weights.attrs.get('availability_assumption_date'),
            reconciliation_error=result['reconciliation_error'],
            **{f'weight_{name}':float(weights[name]) for name in CATEGORIES})
        rows.append(row)
        fits.extend(dict(period=str(origin),as_of=clock,**fit) for fit in result['fits'])
    return pd.DataFrame(rows),pd.DataFrame(fits)


def eligible_errors(errors,feature_index,origin,as_of,available):
    if not errors.index.is_unique or not errors.index.is_monotonic_increasing:
        raise ValueError('error history must have unique ordered months')
    clock=pd.Timestamp(as_of)
    if pd.isna(clock):
        raise ValueError('a valid correction clock is required')
    mask=((errors.index<origin)&errors.index.isin(feature_index)&np.isfinite(errors)
          &pd.to_datetime(available.reindex(errors.index)).le(clock).to_numpy())
    return errors.loc[mask]


def matched_histories(base,category):
    common=base[np.isfinite(base)].index.intersection(category[np.isfinite(category)].index)
    return base.reindex(common),category.reindex(common)


def base_history(features,core,decisions):
    """BASE's raw errors at the supplied historical clocks, with no correction."""
    import cz_struct as s
    x=policy_frame(features,'hard')
    rows=[]
    for origin,clock in decisions.items():
        if pd.isna(clock): continue
        masked=s._mask_row_by_availability(x,origin,clock)
        forecast=s._ridge_predict(masked,core,origin,as_of=clock)[0]
        if np.isfinite(forecast):
            rows.append(dict(period=str(origin),as_of=clock,raw_core=forecast,
                             error=float(core.loc[origin]-forecast)))
    audit=pd.DataFrame(rows)
    errors=pd.Series(audit.error.to_numpy(),index=pd.PeriodIndex(audit.period,freq='M'))
    return errors,audit


def correct(features,errors,origin,as_of,available):
    # The fixed production hard frame contains none of these evaluation fields;
    # explicit removal makes that boundary safe for callers supplying extras.
    forbidden=[c for c in features if any(term in c.lower() for term in
               ('survey','consensus','surprise','expectation'))]
    x=policy_frame(features.drop(columns=forbidden),'hard')
    eligible=eligible_errors(errors,x.index,origin,as_of,available)
    value,info=residual_correction(x,eligible,origin,as_of,'hard')
    info.update(error_start=str(eligible.index.min()) if len(eligible) else None,
        validation_rows=min(12,max(info['n_errors']//5,4)) if info['n_errors']>=40 else 0,
        training_last_release=str(available.reindex(eligible.index).max()) if len(eligible) else None,
        eligible_error_months='|'.join(map(str,eligible.index)),feature_columns='|'.join(x.columns))
    return value,info


def family_forecasts(raw,correction,core_weight):
    if not np.isfinite([raw,correction,core_weight]).all() or not 0<core_weight<=1:
        raise ValueError('finite forecasts and core weight in (0,1] required')
    return raw,raw+.5*core_weight*correction,raw+core_weight*correction
