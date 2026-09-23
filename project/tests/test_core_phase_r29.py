"""R29: phase detection, publication gating, phase-split weights and band corrections."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from models import core_phase_r29 as m


def levels(start='2015-01', months=60, monthly_pct=None):
    index = pd.period_range(start, periods=months, freq='M')
    rates = np.full(months, .2) if monthly_pct is None else np.asarray(monthly_pct, float)
    return pd.Series(100 * np.exp(np.cumsum(rates) / 100), index=index)


def test_phase_is_building_when_momentum_rises():
    rising = levels(monthly_pct=np.r_[np.full(54, .1), np.full(6, .6)])   # last six months faster than the six before
    phase, d = m.phase_from_levels(rising)
    assert phase == 'building' and d['momentum'] == pytest.approx(3.6) and d['momentum_before'] == pytest.approx(.6) and d['change'] == pytest.approx(3.)
    falling = levels(monthly_pct=np.r_[np.full(54, .6), np.full(6, .1)])   # last six months slower than the six before
    phase2, d2 = m.phase_from_levels(falling)
    assert phase2 == 'fading' and d2['change'] == pytest.approx(-3.)
    flat = levels(monthly_pct=np.full(60, .3)); assert m.phase_from_levels(flat)[0] == 'fading'   # no change is not building


def test_phase_uses_exactly_thirteen_months_and_refuses_gaps():
    series = levels(months=13); assert m.phase_from_levels(series)[0] in ('building', 'fading')
    short = levels(months=12); assert m.phase_from_levels(short)[0] is None
    gappy = levels(months=20).drop(pd.Period('2016-03', 'M')); assert m.phase_from_levels(gappy)[1]['status'] == 'gap_or_nonpositive_level'


def test_publication_gate_and_last_month():
    series = levels(months=40, monthly_pct=np.r_[np.full(30, .1), np.full(10, .9)])
    published = pd.Series((series.index + 2).to_timestamp() + pd.Timedelta(days=9), index=series.index)   # day 10 of m+2
    early = m.published_levels(series, published, '2018-04', pd.Timestamp('2018-04-05'))    # Feb 2018 published 10 Apr: not yet
    late = m.published_levels(series, published, '2018-04', pd.Timestamp('2018-04-24'))
    assert str(early.index[-1]) == '2018-01' and str(late.index[-1]) == '2018-02'
    aware = m.published_levels(series, published, '2018-04', pd.Timestamp('2018-04-23 22:59', tz='UTC'))
    assert str(aware.index[-1]) == '2018-02'


def test_phase_weights_split_the_rows():
    origins = pd.period_range('2005-03', '2020-12', freq='Q').asfreq('M', 'end'); rows = []
    rng = np.random.default_rng(2)
    for i, o in enumerate(origins):
        for band in (1, 2, 3, 4):
            phase = 'building' if i % 2 == 0 else 'fading'; f = rng.normal(0, 1); lam = .9 if phase == 'building' else .4
            rows.append(dict(geo='XX', origin=o, band=band, label_end=o + 3 * band, f=f, r=lam * f + rng.normal(0, .05), mu=0., phase=phase))
    rows = pd.DataFrame(rows)
    b = m.lambda_phase_at(rows, 1, pd.Period('2021-06', 'M'), 'building', minimum=10); f = m.lambda_phase_at(rows, 1, pd.Period('2021-06', 'M'), 'fading', minimum=10)
    assert abs(b['lam'] - .9) < .05 and abs(f['lam'] - .4) < .05 and b['status'] == f['status'] == 'estimated'
    unpublished = m.lambda_phase_at(rows, 4, pd.Period('2006-01', 'M'), 'building', minimum=10)
    assert unpublished['status'] == 'fallback_too_few_rows' and unpublished['lam'] == 1.


def test_band_corrections_move_toward_the_norm():
    f = np.array([.5, .5, .5, .5]); corr = m.band_corrections(f, .165, [1., .6, .6, .4])
    assert corr[0] == 0. and corr[1] == pytest.approx(-.4 * (.5 - .165)) and corr[3] == pytest.approx(-.6 * (.5 - .165))
    assert m.fixed_name(.6) == 'CORE_PHASE_FIXED060_R29' and m.TARGET_LOG_PER_MONTH == pytest.approx(100 * np.log1p(.02) / 12)
