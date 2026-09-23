"""Circular block bootstrap for paired loss differences on consecutive monthly origins.

The R15-R23 evaluator resamples non-circular moving blocks and truncates to n. With 19
observations and blocks of 12 the latest origins are almost never drawn, and point estimates
fell outside their own intervals (R23 review, finding 6). Wrapping the blocks gives every
origin the same inclusion probability. Short panels get no interval at all.
"""
import numpy as np
import pandas as pd


def block_length(n):
    """Declared rule: 12 months from 48 observations, 6 from 24, otherwise no interval."""
    return 12 if n >= 48 else 6 if n >= 24 else None


def circular_block_bootstrap(loss_difference, origins=None, draws=2000, seed=1509, block=None):
    values = np.asarray(loss_difference, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Bootstrap support must be finite before resampling')
    n = len(values)
    block = block_length(n) if block is None else block
    result = dict(n=n, block=block, draws=draws, seed=seed, mean_loss_difference=float(values.mean()) if n else np.nan,
                  bootstrap_mean=np.nan, ci_low=np.nan, ci_high=np.nan, bootstrap_probability_improvement=np.nan, status='ok')
    if origins is not None:
        ordinal = pd.PeriodIndex(pd.Series(origins).astype(str), freq='M').asi8
        if len(ordinal) != n:
            raise ValueError('One origin per loss difference is required')
        if n > 1 and not np.all(np.diff(ordinal) == 1):
            result['status'] = 'noncontiguous_origins'
            return result
    if block is None:
        result['status'] = 'too_few_observations_for_an_interval'
        return result
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(draws, int(np.ceil(n / block))))
    index = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    means = values[index].mean(axis=1)
    result.update(bootstrap_mean=float(means.mean()), ci_low=float(np.quantile(means, .025)), ci_high=float(np.quantile(means, .975)),
                  bootstrap_probability_improvement=float(np.mean(means < 0)))
    return result
