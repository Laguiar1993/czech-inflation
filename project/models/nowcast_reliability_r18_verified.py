"""R18 error laws with a roundoff-safe inverse empirical CDF.

Only the quantile implementation changes. The original frozen engine is an
explicit dependency so distributions, event probabilities and points stay exact.
"""
import numpy as np
from models.nowcast_reliability_r18 import (
    _distribution, past_scale, crps, event_probabilities, error_law,
)


def weighted_quantile(support, weights, p):
    if not 0 <= p <= 1:
        raise ValueError('Quantile outside unit interval')
    x, w = _distribution(support, weights)
    positive = w > 0
    x, w = x[positive], w[positive]
    order = np.argsort(x, kind='stable')
    cdf = np.cumsum(w[order], dtype=np.longdouble)
    cdf /= cdf[-1]
    # Up to eight binary64 ulps in probability space are treated as the
    # intended exact boundary. No interpolation or statistically chosen offset.
    tolerance = 8 * np.finfo(float).eps
    j = min(int(np.searchsorted(cdf, p - tolerance, side='left')), len(x)-1)
    return float(x[order[j]])
