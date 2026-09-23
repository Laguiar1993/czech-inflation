"""R28: administered-level candidate mechanics."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from models import administered_level_r28 as m


def fast_path(origin, january=.9, other=.1, fired=None):
    t = pd.Period(origin, 'M'); path = {}
    for h in range(1, 13):
        month = t + h
        path[h] = (fired if (fired is not None and str(month) == fired) else january) if month.month == 1 else other
    return path


def test_fired_gate_detection_only_in_january_above_threshold():
    assert m.fired('2023-01', 30.9) and not m.fired('2023-01', 1.5) and not m.fired('2022-09', 6.)


def test_candidates_keep_fired_january_and_change_the_rest():
    path = fast_path('2022-06', fired='2023-01', january=.9)  # 2023-01 is h7
    fired_value = 30.9; path[7] = fired_value
    out, audit = m.candidate_paths(path, '2022-06')
    assert audit['fired_months'] == ['2023-01'] and audit['january_horizons'] == [7]
    for name in ('ADMIN_ZERO_R28', 'ADMIN_JAN_ONLY_R28', 'ADMIN_HALF_R28', m.factor_name(.25)):
        assert out[name][7] == fired_value
    assert all(out['ADMIN_ZERO_R28'][h] == 0. for h in range(1, 13) if h != 7)
    assert all(out['ADMIN_HALF_R28'][h] == pytest.approx(.05) for h in range(1, 13) if h != 7)
    assert out[m.factor_name(.25)][3] == pytest.approx(.025) and out[m.factor_name(0.)][3] == 0.


def test_january_only_keeps_the_pattern_january_when_not_fired():
    path = fast_path('2024-06', january=.65, other=.1)  # 2025-01 is h7, not fired
    out, audit = m.candidate_paths(path, '2024-06')
    assert audit['fired_months'] == [] and out['ADMIN_JAN_ONLY_R28'][7] == .65
    assert all(out['ADMIN_JAN_ONLY_R28'][h] == 0. for h in range(1, 13) if h != 7)
    assert out['ADMIN_ZERO_R28'][7] == 0.
    assert audit['fast_non_january_sum'] == pytest.approx(1.1)


def test_recent_median_uses_published_months_only_and_needs_three_years():
    index = pd.period_range('2015-01', '2026-07', freq='M'); rates = pd.Series(.2, index=index)
    rates[index.month == 1] = [1., 2., 3., 17., 31., 6., 1., .8, -.9, 2., 3., 4.][:sum(index.month == 1)]
    published = pd.Series((index + 1).to_timestamp() + pd.Timedelta(days=10), index=index)
    path = m.recent_median_path(rates, published, '2024-06', pd.Timestamp('2024-07-09'))
    januaries = rates[(index.month == 1) & (index < pd.Period('2024-06', 'M'))].iloc[-3:]  # 2022, 2023, 2024
    assert path[7] == pytest.approx(float(np.median(januaries)))  # the recent window carries the energy Januaries
    assert path[1] == pytest.approx(.2)
    short = m.recent_median_path(rates.iloc[:20], published.iloc[:20], '2016-06', pd.Timestamp('2016-07-09'))
    assert all(np.isnan(v) for v in short.values())  # fewer than three same-month observations


def test_recent_candidate_reads_the_clock():
    index = pd.period_range('2015-01', '2026-07', freq='M'); rates = pd.Series(.3, index=index)
    published = pd.Series((index + 1).to_timestamp() + pd.Timedelta(days=10), index=index)
    rates[pd.Period('2023-05', 'M')] = 9.; rates[pd.Period('2024-05', 'M')] = 9.  # May 2024 is published on 10 June 2024
    early = m.recent_median_path(rates, published, '2024-06', pd.Timestamp('2024-06-05'))   # window 2021-23: .3, .3, 9
    late = m.recent_median_path(rates, published, '2024-06', pd.Timestamp('2024-06-20'))    # window 2022-24: .3, 9, 9
    assert early[11] == pytest.approx(.3) and late[11] == pytest.approx(9.)
    out, _ = m.candidate_paths(fast_path('2024-06'), '2024-06', rates, published, pd.Timestamp('2024-06-20'))
    assert out['ADMIN_RECENT_R28'][11] == pytest.approx(9.) and out['ADMIN_RECENT_R28'][1] == pytest.approx(.3)
