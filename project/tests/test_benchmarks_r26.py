"""R26: the benchmark family and the promotion rule's mechanics."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from models import benchmarks_r26 as b


def series(months=120, start='2010-01', seed=3):
    rng = np.random.default_rng(seed); index = pd.period_range(start, periods=months, freq='M')
    pattern = np.array([.6, .2, .1, .3, .1, 0, -.4, -.3, .2, .1, .0, .1]) - .0833
    return pd.Series(.2 + pattern[index.month - 1] + rng.normal(0, .15, months), index=index)


def published_on(index, delay_days=10):
    return pd.Series((index + 1).to_timestamp() + pd.Timedelta(days=delay_days), index=index)


def test_publication_gate_excludes_months_released_after_the_clock():
    rates = series(); published = published_on(rates.index)
    origin = '2019-12'; clock = pd.Timestamp('2019-12-05')  # November not yet released
    known = b.published_before(rates, published, origin, clock)
    assert str(known.index[-1]) == '2019-10'
    path, d = b.sa_ar_path(rates, published, origin, clock)
    assert d['gap_months'] == 1 and d['last_month'] == '2019-10'
    later = b.sa_ar_path(rates, published, origin, pd.Timestamp('2019-12-20'))[1]
    assert later['gap_months'] == 0 and later['last_month'] == '2019-11'


def test_pattern_is_centred_and_mean_is_the_window_mean():
    rates = series(); window = pd.Series(b.to_log(rates.to_numpy()), index=rates.index).iloc[-96:]
    pattern, mean = b.seasonal_pattern(window)
    assert abs(pattern.sum()) < 1e-12 and abs(mean - window.mean()) < 1e-12


def test_ar_coefficient_is_clipped_and_uses_consecutive_months_only():
    d = pd.Series(np.tile([1., -1.], 30), index=pd.period_range('2000-01', periods=60, freq='M'))
    assert b.ar1(d) == 0.  # strongly negative autocorrelation clips at the lower bound
    persistent = pd.Series(np.ones(40), index=pd.period_range('2000-01', periods=40, freq='M'))
    assert b.ar1(persistent) == pytest.approx(.95)  # slope 1 clipped at .95
    gappy = pd.Series([1., 2.], index=pd.PeriodIndex(['2000-01', '2000-03'], freq='M'))
    assert b.ar1(gappy) == 0.  # no consecutive pairs


def test_forecast_is_pattern_plus_decaying_deviation():
    rates = series(); published = published_on(rates.index)
    path, d = b.sa_ar_path(rates, published, '2019-12', pd.Timestamp('2019-12-20'))
    window = b.published_before(rates, published, '2019-12', pd.Timestamp('2019-12-20')).iloc[-96:]
    pattern, mean = b.seasonal_pattern(window)
    expected_h3 = mean + pattern[pd.Period('2020-03', 'M').month - 1] + d['phi'] ** 3 * d['last_deviation']
    assert path[3] == pytest.approx(float(b.to_percent(expected_h3)))
    assert d['n'] == 96 and d['status'] == 'estimated'


def test_target_override_moves_only_the_level():
    rates = series(); published = published_on(rates.index)
    plain, dp = b.sa_ar_path(rates, published, '2019-12', pd.Timestamp('2019-12-20'))
    anchored, da = b.sa_ar_path(rates, published, '2019-12', pd.Timestamp('2019-12-20'), mean_override=.1)
    shift = b.to_log(anchored[6]) - b.to_log(plain[6])
    assert shift == pytest.approx(.1 - dp['mean_log']) and da['phi'] == dp['phi']


def test_short_window_returns_nan_path():
    rates = series(months=40); published = published_on(rates.index)
    path, d = b.sa_ar_path(rates, published, '2012-06', pd.Timestamp('2012-06-20'))
    assert d['status'] == 'insufficient_window' and all(np.isnan(v) for v in path.values())


def test_family_members_and_zero():
    rates = series(); actual = pd.DataFrame({blk: rates for blk in b.BLOCKS}); published = published_on(rates.index)
    members, diagnostics = b.family_paths(actual, published, '2019-12', pd.Timestamp('2019-12-20'))
    assert set(members) == set(b.MEMBERS) and all(members['ZERO'][blk][h] == 0. for blk in b.BLOCKS for h in b.HORIZONS)
    assert members['SA_AR_TARGET']['food'] == members['SA_AR']['food'] and members['SA_AR_TARGET']['core'] != members['SA_AR']['core']


def test_constant_oracle_is_the_rmse_minimiser():
    y = np.array([3., 5., 4., 8.]); c = b.constant_oracle(y, 12)
    grid = np.linspace(-1, 1, 2001)
    best = grid[np.argmin([np.sqrt(((12 * g - y) ** 2).mean()) for g in grid])]
    assert c == pytest.approx(best, abs=1e-3) and c == pytest.approx(y.mean() / 12)


def test_replace_blocks_changes_only_the_named_block_and_the_total():
    rows = pd.DataFrame(dict(h=range(13), mm_forecast=.3, value_core=.2, value_food=.5, value_fuel=0., value_administered=.1, value_alcohol_tobacco=.1,
                             contribution_core=.1, contribution_food=.08, contribution_fuel=0., contribution_administered=.02, contribution_alcohol_tobacco=.01,
                             weight_core=.5, weight_food=.16, weight_fuel=.03, weight_administered=.2, weight_alc=.1))
    out = b.replace_blocks(rows, {'food': {h: 1.5 for h in b.HORIZONS}})
    assert out.loc[0, 'mm_forecast'] == .3 and out.loc[0, 'value_food'] == .5
    assert out.loc[5, 'value_food'] == 1.5 and out.loc[5, 'mm_forecast'] == pytest.approx(.3 + .16 * 1.)
    assert out.loc[5, 'value_core'] == .2 and out.loc[5, 'contribution_food'] == pytest.approx(.16 * 1.5)
    with pytest.raises(ValueError):
        b.replace_blocks(rows.iloc[1:], {})
