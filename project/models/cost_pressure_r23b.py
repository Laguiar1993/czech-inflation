"""R23B: near-term core corrections from cost pressure, without an intercept.

Two separate band equations (h1-3 and h4-6), each with its own label maturity. Predictors are
scaled by their training root-mean-square and never centered, so zero pressure maps to zero
correction. A correction is applied only when nested chronological validation beats applying
none. Bands h7-12 receive no learned correction.
"""
import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

from data.cost_gaps_r23 import local
from models.cost_gaps_r23 import monthly_correction

DOMESTIC = ['ulc_sameq', 'tightening']
MOMENTUM = ['import_mom', 'ppi_mom', 'fx_news']
FAMILIES = {
    'PRESS_ULC_R23B': (['ulc_sameq'], 'ridge'),
    'PRESS_DOMESTIC_R23B': (DOMESTIC, 'ridge'),
    'PRESS_MOMENTUM_R23B': (MOMENTUM, 'ridge'),
    'PRESS_JOINT_R23B': ([*DOMESTIC, *MOMENTUM], 'ridge'),
    'PRESS_SIGNED_R23B': ([*DOMESTIC, *MOMENTUM], 'positive'),
    'PRESS_LEVELS_R23B': ([*DOMESTIC, 'import_gap', 'ppi_gap', 'fx_news'], 'ridge'),
}
GRID = (.3, 1., 3., 10., 30.)
REFERENCE_ALPHA = 3.          # diagnostic fit only, when validation applies no correction
BANDS = (1, 2)


def fit(x, y, now, alpha, kind):
    """One band. No intercept; RMS scaling without centering; ridge, optionally bounded at zero."""
    target = np.asarray(y, float); current = pd.Series(now)[list(x.columns)].astype(float)
    if not np.isfinite(x.to_numpy(float)).all() or not np.isfinite(target).all() or not np.isfinite(current).all():
        raise ValueError('Nonfinite fitting data')
    scale = np.sqrt((x.astype(float) ** 2).mean()); scale = scale.where(scale > 1e-8, 1.)
    design = (x / scale).to_numpy(float); test = (current / scale).to_numpy(float); n, p = design.shape
    if kind == 'ridge':
        beta = np.linalg.solve(design.T @ design / n + alpha * np.eye(p), design.T @ target / n)
    elif kind == 'positive':
        solved = lsq_linear(np.vstack([design / np.sqrt(n), np.sqrt(alpha) * np.eye(p)]), np.r_[target / np.sqrt(n), np.zeros(p)],
                            bounds=(np.zeros(p), np.full(p, np.inf)), tol=1e-12, max_iter=500)
        if not solved.success:
            raise RuntimeError('Bounded ridge did not converge')
        beta = solved.x
    else:
        raise ValueError('Unknown learner')
    contributions = test * beta
    return dict(prediction=float(contributions.sum()), coefficients=beta.tolist(), scale=scale.to_dict(), columns=list(x.columns),
                contributions=contributions.tolist(), alpha=float(alpha), kind=kind)


def eligible(x, y, available, origin, clock, band, minimum):
    """Latest 40 quarter-end origins whose band label is matured and released by `clock`."""
    t = pd.Period(origin, 'M'); released = pd.to_datetime(available[band].reindex(x.index)); label = y[band].reindex(x.index)
    okay = ((x.index.month % 3 == 0) & ((x.index + 3 * band) < t) & released.notna().to_numpy() & (released <= local(clock)).to_numpy()
            & x.notna().all(axis=1).to_numpy() & label.notna().to_numpy())
    keys = x.index[okay][-40:]
    return keys if len(keys) >= minimum else keys[:0]


def choose(x, y, available, clocks, origin, clock, band, columns, kind):
    """Nested chronological choice of the penalty, with no correction as an explicit option."""
    folds = []
    for v in eligible(x, y, available, origin, clock, band, 24):
        inner = eligible(x, y, available, v, clocks.loc[v], band, 16)
        if len(inner):
            folds.append((v, inner))
    folds = folds[-8:]; scores = {}; audit = []
    if len(folds) < 4:
        return dict(alpha=None, status='no_correction_insufficient_validation', scores=scores, zero_loss=None, validation=audit)
    zero = float(np.mean([y.loc[v, band] ** 2 for v, _ in folds]))
    for alpha in GRID:
        losses = []
        for v, inner in folds:
            result = fit(x.loc[inner, columns], y.loc[inner, band].to_numpy(), x.loc[v, columns], alpha, kind)
            losses.append(float((result['prediction'] - y.loc[v, band]) ** 2))
            audit.append(dict(band=band, alpha=alpha, validation_origin=str(v), validation_clock=str(local(clocks.loc[v])), n_train=len(inner),
                              first_training_origin=str(inner[0]), last_training_origin=str(inner[-1]), last_training_target=str(inner[-1] + 3 * band),
                              max_training_release=str(pd.to_datetime(available.loc[inner, band]).max()), validation_target=str(v + 3 * band),
                              validation_available=str(available.loc[v, band]), loss=losses[-1], zero_loss=float(y.loc[v, band] ** 2)))
        scores[str(alpha)] = float(np.mean(losses))
    best = min(GRID, key=lambda a: (scores[str(a)], -a))
    if scores[str(best)] < zero:
        return dict(alpha=best, status='nested_selected', scores=scores, zero_loss=zero, validation=audit)
    return dict(alpha=None, status='no_correction_validated', scores=scores, zero_loss=zero, validation=audit)


def run_origin(x, y, available, clocks, origin, asof):
    t = pd.Period(origin, 'M'); rows = {b: eligible(x, y, available, t, asof, b, 24) for b in BANDS}
    out = dict(status='insufficient_common_history', n_train={str(b): len(rows[b]) for b in BANDS},
               train_dates={str(b): list(map(str, rows[b])) for b in BANDS}, fits={}, paths={}, selection={})
    if not len(rows[1]):
        return out
    if t not in x.index or not np.isfinite(x.loc[t].to_numpy(float)).all():
        out['status'] = 'missing_current_features'; return out
    for name, (columns, kind) in FAMILIES.items():
        out['fits'][name] = {}; out['selection'][name] = {}; bands = []
        for b in BANDS:
            if not len(rows[b]):
                out['selection'][name][str(b)] = dict(alpha=None, status='no_correction_insufficient_history', scores={}, zero_loss=None, validation=[])
                bands.append(0.); continue
            setting = choose(x, y, available, clocks, t, asof, b, columns, kind)
            applied = setting['alpha'] is not None
            result = fit(x.loc[rows[b], columns], y.loc[rows[b], b].to_numpy(), x.loc[t, columns], setting['alpha'] if applied else REFERENCE_ALPHA, kind)
            out['fits'][name][str(b)] = dict(**result, applied=applied); out['selection'][name][str(b)] = setting
            bands.append(result['prediction'] if applied else 0.)
        out['paths'][name] = monthly_correction([*bands, 0., 0.]).tolist()
    out['status'] = 'estimated'
    return out
