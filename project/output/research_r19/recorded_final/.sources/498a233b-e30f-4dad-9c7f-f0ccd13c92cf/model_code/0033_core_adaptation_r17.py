"""R17 conditional-mean filters; adjusted input rates are monthly log pp.

Origin t observes through t-1. The h0 signal changes the mean only and is not
a Bayesian posterior observation or a calibrated uncertainty update.
"""
import numpy as np
import pandas as pd
from models.core_slope_transmission_r16 import _origin, _seasonal, _monthly_series, _local_clock

F = np.array([[1., .95, 0.], [0., .95, 0.], [0., 0., .8]])
H = np.array([1., 0., 1.])


def innovation_scale(past, initial):
    x = np.asarray(past[-36:] if len(past) >= 12 else initial, dtype=float)
    if not np.isfinite(x).all() or not len(x):
        raise ValueError('Finite past innovations or initialization required')
    return float(max(.05, 1.4826 * np.median(abs(x - np.median(x)))))


def update_settings(mode, previous_z, current_z):
    if mode not in ('fixed', 'robust', 'news') or not np.isfinite(current_z):
        raise ValueError('Unknown mode or nonfinite innovation')
    z = np.asarray([*previous_z[-2:], current_z])
    persistent = mode == 'news' and len(z) == 3 and bool(
        (abs(z) >= .5).all() and ((z > 0).all() or (z < 0).all()))
    return (.20, .01, 1., True) if persistent else (
        .05, .001, 1. if mode == 'fixed' else max(1., (abs(current_z)/2.5)**2), False)


def _path(mean_at_t, transition, observation, t, seasonal):
    result = {}; mean = np.array(mean_at_t, dtype=float)
    for h in range(1, 13):
        mean = transition @ mean
        result[h] = float(observation @ mean + seasonal[(t+h).month])
    return result


def filter_state(adjusted_history, origin, seasonal, mode):
    _monthly_series(adjusted_history, 'adjusted_history')
    t, factors = _origin(origin), _seasonal(seasonal)
    if (adjusted_history.index >= t).any():
        raise ValueError('Core filter received current/future observations')
    history = adjusted_history.sort_index()
    if len(history) < 36 or not history.index.equals(pd.period_range(history.index[0], t-1, freq='M')):
        raise ValueError('At least36 contiguous monthly observations through t-1 required')
    values = history.to_numpy(float)
    if not np.isfinite(values).all(): raise ValueError('Nonfinite core history')
    mean = np.array([values[:12].mean(), 0., 0.]); covariance = np.diag([1., .01, 1.])
    errors = []; zs = []; trace = []
    for month, observed in zip(history.index[12:], values[12:]):
        prior = F @ mean; error = float(observed-H @ prior)
        scale = innovation_scale(errors, values[:12]); z = error/scale
        q, qs, r, persistent = update_settings(mode, zs, z)
        process = np.diag([q, qs, .2]); p = F @ covariance @ F.T + process
        gain = p @ H / (H @ p @ H + r)
        mean = prior + gain * error
        residual = np.eye(3)-np.outer(gain, H)
        covariance = residual @ p @ residual.T + r*np.outer(gain, gain)
        covariance = (covariance+covariance.T)/2
        if np.linalg.eigvalsh(covariance).min() < -1e-10: raise ValueError('Invalid covariance')
        trace.append(dict(month=str(month), innovation=error, prior_scale=scale, z=z,
                          persistent=bool(persistent), level_q=q, slope_q=qs, observation_r=r))
        errors.append(error); zs.append(z)
    return dict(origin=str(t), mean=mean.tolist(), covariance=covariance.tolist(),
                transition=F.tolist(), observation=H.tolist(), process=process.tolist(),
                seasonal=factors, path=_path(F@mean,F,H,t,factors),
                h0_log=float(H@F@mean+factors[t.month]), trace=trace)


def fast_state(saved, origin):
    t = _origin(origin); factors = _seasonal(saved['seasonal'])
    s = saved['filter_states']['fast']; mean = np.array([s['mu'], s['cycle']])
    f = np.diag([1., .8]); obs = np.ones(2)
    return dict(origin=str(t), mean=mean.tolist(), covariance=s['covariance'],
                transition=f.tolist(), observation=obs.tolist(), process=np.diag([.2,.2]).tolist(),
                seasonal=factors, path=_path(f@mean,f,obs,t,factors), h0_log=float(obs@f@mean+factors[t.month]))


def condition_h0(state, delta):
    if not np.isfinite(delta): raise ValueError('Finite h0 correction required')
    f=np.asarray(state['transition']); obs=np.asarray(state['observation']); p=np.asarray(state['covariance'])
    p0=f@p@f.T+np.asarray(state['process']); variance=float(obs@p0@obs)
    if variance <= 0 or not np.isfinite(variance): raise ValueError('Invalid signal covariance')
    direction=p0@obs/variance
    if not np.isclose(obs@direction,1.): raise ValueError('Correction does not reproduce h0 increment')
    mean=f@np.asarray(state['mean'])+direction*delta
    return _path(mean,f,obs,_origin(state['origin']),_seasonal(state['seasonal']))


def h0_coefficient(rows, origin, clock):
    t, cutoff = _origin(origin), _local_clock(clock)
    if rows.origin.duplicated().any(): raise ValueError('Duplicate saved h0 history')
    months=pd.PeriodIndex(rows.origin,freq='M')
    dates=rows.available_from.map(lambda x: pd.NaT if pd.isna(x) else _local_clock(x))
    use=rows.loc[(months<t)&dates.notna()&dates.le(cutoff)].copy().sort_values('origin')
    use=use[np.isfinite(use[['signal','error']]).all(axis=1)].tail(60)
    n=len(use); denom=float(use.signal@use.signal)
    beta=float(np.clip((use.signal@use.error)/denom*n/(n+24),0,1)) if n>=12 and denom>1e-12 else 0.
    meta=dict(n_train=n, training_origins=use.origin.tolist(), training_releases=use.available_from.astype(str).tolist(),
              status='estimated' if n>=12 and denom>1e-12 else 'zero_default',
              residual_rmse=float(np.sqrt(np.mean((use.error-beta*use.signal)**2))) if n else None)
    return beta,meta
