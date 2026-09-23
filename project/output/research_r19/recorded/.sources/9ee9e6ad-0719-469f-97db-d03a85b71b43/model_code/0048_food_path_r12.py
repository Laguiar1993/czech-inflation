"""Prespecified R12 causal food trend and lagged-cost extension; no data loaders."""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.trend_gap import require_monthly_contiguous

MIN_HISTORY = 24
SEASON_WINDOW = 120
TREND_SPAN = 12
RIDGE_PENALTY = 1.0


def log_history(history, origin):
    """Slice before validation so irrelevant future values cannot affect a fit."""
    origin = pd.Period(origin, 'M')
    y = history.loc[history.index < origin].copy()
    y = y.loc[y.first_valid_index():]
    require_monthly_contiguous(y, 'released history')
    if len(y) < MIN_HISTORY or y.index[-1] != origin-1:
        raise ValueError('At least 24 released months ending exactly at origin minus one required')
    if not np.isfinite(y.to_numpy(dtype=float)).all() or (y <= -100).any():
        raise ValueError('Released history contains missing/nonfinite/invalid interior rates')
    return 100*np.log1p(y/100)


def trend_state(history, origin):
    q = log_history(history, origin)
    detrended = (q-q.rolling(12, min_periods=12).mean()).dropna().tail(SEASON_WINDOW)
    seas = detrended.groupby(detrended.index.month).mean().reindex(range(1,13),fill_value=0.)
    seas = seas-seas.mean()
    sa = q-np.array([seas.loc[p.month] for p in q.index])
    trend = float(sa.ewm(span=TREND_SPAN, adjust=False).mean().iloc[-1])
    return dict(trend=trend, seasonal={int(k):float(v) for k,v in seas.items()},
        predictors=np.array([sa.iloc[-1],sa.tail(3).mean(),sa.tail(12).mean()])-trend,
        history_end=str(q.index[-1]), n_history=len(q), n_seasonal=len(detrended))


def prior_log(state, origin, h):
    return float(state['trend']+state['seasonal'][(pd.Period(origin,'M')+h).month])


def cost_features(records, origin, historical_clock, current_clock):
    """All three exact source months must be published at both clocks."""
    source = pd.period_range(pd.Period(origin,'M')-4,pd.Period(origin,'M')-2,freq='M')
    rows = records.reindex(source)
    clocks = [pd.Timestamp(historical_clock),pd.Timestamp(current_clock)]
    if any(pd.isna(c) or c.tzinfo is None for c in clocks):
        raise ValueError('Cost availability requires known timezone-aware clocks')
    result = {}
    for col in ('agri','ppi'):
        stamps = pd.to_datetime(rows[f'{col}_available_at'],utc=True,errors='coerce')
        valid = stamps.notna() & (stamps <= clocks[0]) & (stamps <= clocks[1])
        vals = rows[col].to_numpy(dtype=float)
        result[col] = float(vals.mean()) if valid.all() and np.isfinite(vals).all() else np.nan
    return pd.Series(result)


def ridge_zero_prior(x, target, now, min_rows):
    """Mean-loss ridge, train-only scaling, no fitted residual intercept."""
    valid = np.isfinite(x.to_numpy(dtype=float)).all(axis=1) & np.isfinite(target)
    x, target = x.loc[valid], target.loc[valid]
    diag = dict(n_training=len(x),ridge_penalty=RIDGE_PENALTY,
        last_training_origin=str(x.index[-1]) if len(x) else None,
        fallback_used=len(x)<min_rows or not np.isfinite(now.to_numpy(dtype=float)).all())
    if diag['fallback_used']:
        diag.update(status='prior_fallback',coefficients=[],reason='short_training_or_unavailable_current_predictor')
        return 0.,diag
    center=x.mean(); scale=x.std(ddof=0)
    # A constant decimal column can have a tiny nonzero floating-point SD.
    constant=x.nunique(dropna=False)<=1
    scale=scale.mask(constant|scale.eq(0.),1.)
    xx=((x-center)/scale).to_numpy(dtype=float)
    beta=np.linalg.solve(xx.T@xx+len(x)*RIDGE_PENALTY*np.eye(xx.shape[1]),xx.T@target.to_numpy())
    correction=float(((now-center)/scale).to_numpy()@beta)
    diag.update(status='estimated',coefficients=beta.tolist(),training_center=center.to_dict(),
                training_scale=scale.to_dict())
    return correction,diag


def forecast_food(history, origin, records, historical_clocks, as_of):
    origin=pd.Period(origin,'M'); q=log_history(history,origin)
    released=history.loc[q.index]; state=trend_state(released,origin)
    xrows=[]; targets=[]; ridx=[]
    for r in q.index[MIN_HISTORY:]:
        if r not in historical_clocks:
            continue
        feature=cost_features(records,r,historical_clocks[r],as_of)
        previous=trend_state(released,r)
        xrows.append(feature); targets.append(q.loc[r]-prior_log(previous,r,0)); ridx.append(r)
    index=pd.PeriodIndex(ridx,freq='M')
    x=pd.DataFrame(xrows,index=index,columns=['agri','ppi'])
    yy=pd.Series(targets,index=index,dtype=float)
    now=cost_features(records,origin,as_of,as_of)
    correction,diag=ridge_zero_prior(x,yy,now,24)
    diag.update(last_training_target=diag['last_training_origin'],current_cost_features=now.to_dict(),
        source_start=str(origin-4),source_end=str(origin-2),current_correction=correction,
        half_life_months=3,as_of_utc=pd.Timestamp(as_of).tz_convert('UTC').isoformat())
    paths={key:{} for key in ('FOOD_TREND_R12','FOOD_COST_R12')}
    for h in range(4,13):
        base=prior_log(state,origin,h)
        paths['FOOD_TREND_R12'][h]=float(100*np.expm1(base/100))
        paths['FOOD_COST_R12'][h]=float(100*np.expm1((base+correction*2**(-h/3))/100))
    summary={k:v for k,v in state.items() if k!='predictors'}
    return dict(paths=paths,diagnostics={'FOOD_TREND_R12':dict(summary,status='estimated',fallback_used=False),
        'FOOD_COST_R12':dict(summary,**diag)})
