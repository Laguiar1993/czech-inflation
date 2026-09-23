"""Explicit, survey-free long-run anchor; research hypothesis, not a policy model."""
import numpy as np
import pandas as pd


def core_anchor(core,headline,available,origin,asof):
    ix=core.index.union(headline.index).sort_values()
    ix=ix[ix<origin];dates=pd.to_datetime(available.reindex(ix))
    valid=dates.notna()&dates.le(pd.Timestamp(asof))
    cq=100*np.log1p(core.reindex(ix).where(valid)/100)
    hq=100*np.log1p(headline.reindex(ix).where(valid)/100)
    # Reindex to a complete calendar so missing dates cannot shorten a year.
    calendar=pd.period_range(ix.min(),ix.max(),freq='M')
    spread=(cq.reindex(calendar).rolling(12).sum()-hq.reindex(calendar).rolling(12).sum()).dropna().tail(120)
    if len(spread)<60:raise ValueError('Insufficient published annual spreads')
    n=len(spread);annual=100*np.log1p(.02)+spread.median()*n/(n+120.)
    used=pd.period_range(spread.index.min()-11,spread.index.max(),freq='M')
    return dict(anchor_log_monthly=float(annual/12),n=n,median_annual_log_spread=float(spread.median()),
                first_target=str(spread.index.min()),last_target=str(spread.index.max()),
                last_release=dates.reindex(used).max().isoformat())


def anchored_path(state,origin,anchor,half_life):
    if half_life<=0 or not np.isfinite(anchor):raise ValueError('Invalid anchor or half-life')
    t=pd.Period(origin,'M');mu=state['filter_states']['fast']['mu'];cycle=state['filter_states']['fast']['cycle']
    return {h:float(100*np.expm1((anchor+(mu-anchor)*2.**(-(h+1)/half_life)+.8**(h+1)*cycle+
                state['seasonal'][str((t+h).month)])/100)) for h in range(1,13)}
