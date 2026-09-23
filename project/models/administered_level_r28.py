"""R28: the level of the administered-price block outside announced events.

Every candidate starts from FAST's own administered path at the origin (a sticky ten-year calendar median with a
January announcement gate) and changes only the level assumed for months the gate did not override. A January
rate above GATE_THRESHOLD percent on the FAST path is a fired gate and is kept as it is in every candidate.
See docs/implementation/R28_ADMINISTERED_LEVEL_SPEC_2026-09-18.md.
"""
import numpy as np
import pandas as pd

from models.benchmarks_r26 import published_before, to_percent

MODELS = ('ADMIN_ZERO_R28', 'ADMIN_JAN_ONLY_R28', 'ADMIN_RECENT_R28', 'ADMIN_HALF_R28')
FACTORS = (0., .25, .5, .75)
GATE_THRESHOLD = 5.
RECENT_YEARS = 3
HORIZONS = range(1, 13)


def factor_name(factor):
    return f'ADMIN_F{int(round(100 * factor)):03d}_R28'


def fired(month, value):
    return bool(pd.Period(month, 'M').month == 1 and np.isfinite(value) and value > GATE_THRESHOLD)


def recent_median_path(rates, published, origin, clock, years=RECENT_YEARS):
    """h -> median of the same calendar month over the latest `years` published observations (percent); NaN if fewer."""
    known = published_before(rates, published, origin, clock)  # log points, published only
    origin = pd.Period(origin, 'M'); path = {}
    for h in HORIZONS:
        same = known[known.index.month == (origin + h).month]
        path[h] = float(to_percent(np.median(same.iloc[-years:].to_numpy()))) if len(same) >= years else np.nan
    return path


def candidate_paths(fast_path, origin, rates=None, published=None, clock=None, factors=FACTORS):
    """{name: {h: percent}} for one origin from FAST's administered path {h: percent}; fired Januaries kept everywhere."""
    origin = pd.Period(origin, 'M'); gates = {h: fired(origin + h, fast_path[h]) for h in HORIZONS}
    out = {}
    out['ADMIN_ZERO_R28'] = {h: fast_path[h] if gates[h] else 0. for h in HORIZONS}
    out['ADMIN_JAN_ONLY_R28'] = {h: fast_path[h] if gates[h] or (origin + h).month == 1 else 0. for h in HORIZONS}
    out['ADMIN_HALF_R28'] = {h: fast_path[h] if gates[h] else .5 * fast_path[h] for h in HORIZONS}
    for factor in factors:
        out[factor_name(factor)] = {h: fast_path[h] if gates[h] else factor * fast_path[h] for h in HORIZONS}
    if rates is not None:
        recent = recent_median_path(rates, published, origin, clock)
        out['ADMIN_RECENT_R28'] = {h: fast_path[h] if gates[h] else recent[h] for h in HORIZONS}
    return out, dict(fired_months=[str(origin + h) for h in HORIZONS if gates[h]], january_horizons=[h for h in HORIZONS if (origin + h).month == 1],
                     fast_january=[fast_path[h] for h in HORIZONS if (origin + h).month == 1], fast_non_january_sum=float(sum(fast_path[h] for h in HORIZONS if (origin + h).month != 1)))
