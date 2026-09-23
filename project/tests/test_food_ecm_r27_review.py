"""R27 review: the three tests the independent reviewer asked for before promotion (clip bound, gap month, returned gap centred)."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from models import food_ecm_r27 as m


def panel(months=130, seed=5, alpha=-.08):
    rng = np.random.default_rng(seed); index = pd.period_range('2015-01', periods=months, freq='M')
    ppi = np.cumsum(rng.normal(.2, .8, months)); agri = np.cumsum(rng.normal(.1, 1.5, months))
    season = np.array([.8, .2, -.3, .1, .4, -.2, -.9, -.6, .3, .5, .0, -.3])[index.month - 1]
    gap = np.zeros(months)
    for i in range(1, months):
        gap[i] = (1 + alpha) * gap[i - 1] + rng.normal(0, .5)
    food = 3 + .05 * np.arange(months) + .9 * ppi + gap + season
    levels = pd.DataFrame(dict(agri4=agri, food_ppi=ppi, food=food), index=index)
    available = pd.DataFrame({col: [(p + 1).to_timestamp() + pd.Timedelta(days=d) for p in index] for col, d in [('agri4', 25), ('food_ppi', 15), ('food', 9)]}, index=index)
    return levels, available


def test_clip_bound_is_the_speed_when_the_raw_estimate_is_faster():
    # A gap that reverts within the month has a raw speed near -1; the candidate must use exactly the clip bound.
    index = pd.period_range('2015-01', periods=120, freq='M'); rng = np.random.default_rng(9)
    gap = pd.Series(rng.normal(0, 1, 120), index=index)                      # white noise: raw speed about -1
    food = pd.Series(50 + .1 * np.arange(120) + gap.to_numpy(), index=index)
    alpha, audit = m.adjustment_speed(pd.DataFrame(dict(food=food)), gap)
    assert audit['alpha_raw'] < -.5 and alpha == m.ALPHA_CLIP[0] == -.25


def test_correction_uses_the_gap_at_the_last_common_month():
    levels, available = panel(); origin = '2024-06'; clock = pd.Timestamp('2024-06-27')
    published = m.published_levels(levels, available, origin, clock); last = m.last_common_month(published)
    gap, _ = m.gap_series(published, ['food_ppi', 'agri4'], last); alpha, _ = m.adjustment_speed(published, gap)
    out = m.candidates_at(levels, available, origin, clock, np.zeros(12), fixed_alphas=())
    expected = m.correction(alpha, float(gap.loc[last]), last, origin)
    wrong_month = m.correction(alpha, float(gap.loc[last - 1]), last, origin)
    assert out['corrections']['FOOD_ECM_R27'] == expected and out['corrections']['FOOD_ECM_R27'] != wrong_month
    assert out['audits']['FOOD_ECM_R27']['gap_last'] == pytest.approx(float(gap.loc[last]))


def test_returned_gap_has_zero_calendar_month_means():
    levels, available = panel(); published = m.published_levels(levels, available, '2024-06', pd.Timestamp('2024-06-27'))
    gap, _ = m.gap_series(published, ['food_ppi', 'agri4'], m.last_common_month(published))
    by_month = gap.groupby(gap.index.month).mean()
    assert np.abs(by_month.to_numpy()).max() < 1e-9 and len(by_month) == 12
