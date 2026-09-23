"""Input gates to run before any path-correction score is read.

Each one would have exposed a defect in R23 before scoring: a seasonal pattern hiding in a
feature, a sign restriction that silently removes a channel, and a learned correction that
arrives out of phase with the correction the baseline needed.
"""
import numpy as np
import pandas as pd


def seasonal_share(values, period_of_year, minimum=8):
    """Share of variance explained by period-of-year means (between-group over total).

    Undefined (NaN) for fewer than `minimum` observations, fewer than two periods, or a
    constant series. A constant feature has no seasonal contamination to measure.
    """
    frame = pd.DataFrame({'value': pd.to_numeric(pd.Series(values).to_numpy(), errors='coerce'),
                          'period': pd.Series(period_of_year).to_numpy()}).dropna()
    if len(frame) < minimum or frame.period.nunique() < 2:
        return np.nan
    total = float(((frame.value - frame.value.mean()) ** 2).sum())
    if total <= 1e-18:
        return np.nan
    within = float(((frame.value - frame.groupby('period').value.transform('mean')) ** 2).sum())
    return 1. - within / total


def _slopes(coefficients):
    frame = pd.DataFrame(coefficients)
    return frame[frame.feature.ne('intercept')]


def binding_share(coefficients, tolerance=1e-10):
    """Per feature: share of fitted cells whose coefficient sits on a zero bound."""
    frame = _slopes(coefficients)
    return frame.coefficient.abs().lt(tolerance).groupby(frame.feature).mean()


def wrong_sign_share(coefficients, expected=1, tolerance=1e-10):
    """Per feature: share of fitted cells whose coefficient contradicts the declared sign."""
    frame = _slopes(coefficients)
    return (np.sign(expected) * frame.coefficient).lt(-tolerance).groupby(frame.feature).mean()


def needed_vs_applied(needed, applied):
    """Did the correction arrive when, and in the direction, the baseline needed it?

    `needed` is realised minus baseline, `applied` is the correction added. Correlation is
    undefined (NaN) when nothing was applied; that is different from a zero correlation.
    """
    frame = pd.concat([pd.Series(needed, name='needed'), pd.Series(applied, name='applied')], axis=1).dropna()
    active = frame[frame.applied.abs().gt(1e-12)]
    varies = len(frame) > 2 and frame.applied.std() > 1e-12 and frame.needed.std() > 1e-12
    return dict(n=len(frame), n_active=len(active),
                correlation=float(frame.needed.corr(frame.applied)) if varies else np.nan,
                mean_needed=float(frame.needed.mean()) if len(frame) else np.nan,
                mean_applied=float(frame.applied.mean()) if len(frame) else np.nan,
                sign_agreement=float((np.sign(active.needed) == np.sign(active.applied)).mean()) if len(active) else np.nan)
