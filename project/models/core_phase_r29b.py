"""R29B: the upstream phase read from the level of six-month producer-price momentum.

Building when the six-month log change of the last published producer-price index exceeds THRESHOLD_LOG_POINTS
(1.0 log point a half-year, 2% a year); fading otherwise. Everything else is the R29 machinery.
See docs/implementation/R29B_CORE_PHASE_LEVEL_SPEC_2026-09-18.md.
"""
import numpy as np
import pandas as pd

from models.core_phase_r29 import MOMENTUM_MONTHS, published_levels

THRESHOLD_LOG_POINTS = 1.0
FIXED_PAIRS = {'CORE_LEVELPHASE_FIXED040_R29B': .4, 'CORE_LEVELPHASE_FIXED060_R29B': .6, 'CORE_LEVELPHASE_FIXED080_R29B': .8}
PANEL_MODEL = 'CORE_LEVELPHASE_PANEL_R29B'
MODELS = (*FIXED_PAIRS, PANEL_MODEL)


def phase_from_levels(known, months=MOMENTUM_MONTHS, threshold=THRESHOLD_LOG_POINTS):
    """(phase, diagnostics) from published index levels; None when fewer than months+1 consecutive months end the series."""
    if len(known) < months + 1:
        return None, dict(status='insufficient_history', n=len(known))
    tail = known.iloc[-(months + 1):]
    if (tail.index[-1] - tail.index[0]).n != months or (tail <= 0).any():
        return None, dict(status='gap_or_nonpositive_level', n=len(known))
    momentum = float(100 * (np.log(tail.iloc[-1]) - np.log(tail.iloc[0])))
    phase = 'building' if momentum > threshold else 'fading'
    return phase, dict(status='estimated', last_month=str(tail.index[-1]), momentum=momentum, threshold=threshold, phase=phase)


def phase_at(levels, published, origin, clock):
    return phase_from_levels(published_levels(levels, published, origin, clock))
