"""Independent input policies and sequential, policy-specific error forecasts.

All error targets are generated without reading the legacy error cache. Historical
feature snapshots still inherit their declared latest-vintage limitations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EXPECTATION_COLUMNS = ('exp12', 'exp36', 'exp12_x_state', 'household_exp')


def policy_frame(features: pd.DataFrame, policy: str = 'hard') -> pd.DataFrame:
    if policy not in ('hard', 'sentiment', 'legacy'):
        raise ValueError(f'unknown input policy: {policy}')
    remove = () if policy == 'legacy' else EXPECTATION_COLUMNS
    if policy == 'hard':
        remove += ('esi',)
    return features.drop(columns=list(remove), errors='ignore').copy()


def sequential_errors(features: pd.DataFrame, core: pd.Series, policy: str,
                      through: pd.Period) -> pd.Series:
    """Expanding ridge prediction errors, computed at each release eve.

    Availability of the *outcome* is checked by residual_correction when this
    history is consumed. No contemporaneous or later target enters its forecast.
    """
    import cz_struct as s
    x = policy_frame(features, policy)
    errors = {}
    for u in core.dropna().index:
        if u > through or u not in x.index:
            continue
        release = s._first_release_dt(u)
        if pd.isna(release):
            if u >= s._release_calendar().index.min():
                continue  # missing modern release metadata fails closed
            release = (u + 1).to_timestamp() + pd.Timedelta(days=19, hours=9)
        clock = release - pd.Timedelta(days=1)
        # The source frames carry publication shifts; enforce the decision-row
        # rule too, rather than assuming every release eve has identical inputs.
        xu = s._mask_row_by_availability(x, u, clock)
        forecast = s._ridge_predict(xu, core, u, as_of=clock)[0]
        if np.isfinite(forecast):
            errors[u] = float(core.loc[u] - forecast)
    return pd.Series(errors, index=pd.PeriodIndex(list(errors), freq='M'),
                     dtype=float, name=f'{policy}_sequential_core_error')


def residual_correction(features: pd.DataFrame, errors: pd.Series,
                        origin: pd.Period, as_of, policy: str = 'hard',
                        forest_options: dict | None = None) -> tuple[float, dict]:
    """Only released past errors may train the residual forest."""
    import cz_struct as s
    from models.horizon_models import TVWQRF
    x = policy_frame(features, policy)
    eligible = errors.loc[(errors.index < origin) & errors.index.isin(x.index)].dropna()
    eligible = eligible[ [s._cpi_family_released_by(u, as_of) for u in eligible.index] ]
    detail = {'policy': policy, 'n_errors': len(eligible),
              'error_end': str(eligible.index.max()) if len(eligible) else None,
              'status': 'insufficient_errors', 'fallback_used': len(eligible) < 40}
    if len(eligible) < 40:
        return 0., detail
    xp = x.loc[eligible.index].to_numpy(dtype=float)
    mu = pd.DataFrame(xp).mean().fillna(0.).to_numpy()
    xp = np.where(np.isfinite(xp), xp, mu)
    sd = xp.std(axis=0, ddof=1)
    sd = np.where(sd > 0, sd, 1.)
    xr = x.loc[origin].to_numpy(dtype=float)
    xr = (np.where(np.isfinite(xr), xr, mu) - mu) / sd
    opts = {'n_estimators': 200}
    opts.update(forest_options or {})
    try:
        result = TVWQRF(**opts).fit_predict((xp - mu) / sd, eligible.to_numpy(), xr)
        corr = float(result['point'])
        if not np.isfinite(corr):
            raise ValueError('nonfinite forest forecast')
        detail.update(status='ok', fallback_used=False, quantile_weights=result['weights'])
        return corr, detail
    except Exception as exc:
        detail.update(status='forest_failed', fallback_used=True,
                      error=f'{type(exc).__name__}: {exc}')
        return 0., detail
