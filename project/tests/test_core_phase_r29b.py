"""R29B: the level-based phase."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from models import core_phase_r29b as m


def levels(monthly_pct, start='2015-01'):
    index = pd.period_range(start, periods=len(monthly_pct), freq='M')
    return pd.Series(100 * np.exp(np.cumsum(np.asarray(monthly_pct, float)) / 100), index=index)


def test_building_above_two_percent_a_year_and_fading_below():
    fast = levels(np.full(20, .3)); phase, d = m.phase_from_levels(fast)      # 1.8 log points a half-year
    assert phase == 'building' and d['momentum'] > 1. and d['threshold'] == 1.
    slow = levels(np.full(20, .1)); assert m.phase_from_levels(slow)[0] == 'fading'
    near = levels(np.full(20, .16)); assert m.phase_from_levels(near)[0] == 'fading'   # 0.96 log points is below the threshold
    falling_but_high = levels(np.r_[np.full(14, 2.), np.full(6, .5)])   # momentum 3.0: still building on the level rule
    assert m.phase_from_levels(falling_but_high)[0] == 'building'


def test_uses_seven_months_only_and_refuses_gaps():
    assert m.phase_from_levels(levels(np.full(7, .3)))[0] == 'building'
    assert m.phase_from_levels(levels(np.full(6, .3)))[0] is None
    gappy = levels(np.full(12, .3)).drop(pd.Period('2015-09', 'M')); assert m.phase_from_levels(gappy)[1]['status'] == 'gap_or_nonpositive_level'


def test_models_declared():
    assert set(m.FIXED_PAIRS.values()) == {.4, .6, .8} and m.PANEL_MODEL in m.MODELS and len(m.MODELS) == 4
