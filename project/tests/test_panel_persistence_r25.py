import numpy as np
import pandas as pd
import pytest

from data.hicp_panel_r25 import parse_jsonstat, load, MEMBERS
from models.panel_persistence_r25 import (robust_norm, estimate_lambda, lambda_at, two_regime_at, country_rows, czech_correction,
                                          MIN_PANEL_ROWS, BANDS)


def test_jsonstat_cube_is_unpacked_by_geo_and_month():
    payload = dict(id=['freq', 'unit', 'coicop', 'geo', 'time'], size=[1, 1, 1, 2, 3],
                   dimension=dict(geo=dict(category=dict(index={'AT': 0, 'BE': 1})), time=dict(category=dict(index={'2020-01': 0, '2020-02': 1, '2020-03': 2}))),
                   value={'0': 100., '1': 101., '3': 90., '5': 92.})
    table = parse_jsonstat(payload)
    assert table.loc['2020-02', 'AT'] == 101. and table.loc['2020-03', 'BE'] == 92. and np.isnan(table.loc['2020-03', 'AT']) and np.isnan(table.loc['2020-02', 'BE'])


def test_frozen_panel_excludes_czechia_and_verifies_its_hashes():
    rates, published, manifest = load()
    assert list(rates.columns) == MEMBERS and 'CZ' not in rates.columns and len(MEMBERS) == 26
    assert rates.index.max() == pd.Period('2025-12', 'M') and published.loc['2025-12'] == pd.Timestamp('2026-01-20')
    assert rates['DE'].loc['2001-01':].notna().all() and abs(rates['DE'].loc['2010-01':'2019-12'].mean() * 12 - 1.2) < .6


def test_robust_norm_ignores_an_extreme_year_and_needs_five_years():
    ix = pd.period_range('2000-01', '2019-12', freq='M'); logs = pd.Series(.2, index=ix); logs.loc['2010-01':'2010-12'] = 1.5
    assert robust_norm(logs) == pytest.approx(.2) and logs.mean() > .25
    assert np.isnan(robust_norm(logs.iloc[:59])) and robust_norm(logs.iloc[:72]) == pytest.approx(.2)
    holed = logs.copy(); holed.loc['2005-06'] = np.nan
    assert robust_norm(holed) == pytest.approx(.2)


def test_lambda_is_recovered_and_clipped():
    x = np.linspace(-1, 1, 101)
    assert estimate_lambda(x, .6 * x) == pytest.approx(.6)
    assert estimate_lambda(x, 1.4 * x) == 1. and estimate_lambda(x, -.3 * x) == 0.
    assert np.isnan(estimate_lambda(np.zeros(10), np.zeros(10)))


def panel_fixture(small=.2, large=.9, seed=4):
    rng = np.random.default_rng(seed); rows = []
    for geo in range(8):
        for k, origin in enumerate(pd.period_range('2005-03', '2024-12', freq='Q').asfreq('M', 'end')):
            for b in BANDS:
                x = rng.normal(scale=.3); persistence = small if abs(x) <= .2 else large
                rows.append(dict(geo=f'G{geo}', origin=origin, band=b, label_end=origin + 3 * b, f=.2 + x, mu=.2, r=.2 + persistence * x + rng.normal(scale=.005)))
    return pd.DataFrame(rows)


def test_lambda_at_uses_only_rows_matured_by_the_clock_and_falls_back_when_thin():
    rows = panel_fixture(small=.7, large=.7); t = pd.Period('2016-05', 'M')
    out = lambda_at(rows, 2, t, MIN_PANEL_ROWS)
    assert out['status'] == 'estimated' and out['lam'] == pytest.approx(.7, abs=.02)
    assert out['n'] == int(((rows.band == 2) & (rows.label_end <= t - 1)).sum())
    poisoned = rows.copy(); poisoned.loc[poisoned.label_end > t - 1, 'r'] = 1e9
    assert lambda_at(poisoned, 2, t, MIN_PANEL_ROWS) == out
    thin = lambda_at(rows, 2, pd.Period('2006-01', 'M'), MIN_PANEL_ROWS)
    assert thin['status'] == 'fallback_too_few_rows' and thin['lam'] == 1.


def test_two_regimes_split_on_the_real_time_median_and_recover_both_values():
    rows = panel_fixture(small=.2, large=.9); t = pd.Period('2022-01', 'M')
    out = two_regime_at(rows, 4, t, MIN_PANEL_ROWS)
    used = rows[(rows.band == 4) & (rows.label_end <= t - 1)]
    assert out['threshold'] == pytest.approx(float((used.f - used.mu).abs().median()))
    assert out['lam_large'] == pytest.approx(.9, abs=.03) and out['lam_small'] < .6 and out['n_small'] + out['n_large'] == len(used)
    poisoned = rows.copy(); poisoned.loc[poisoned.label_end > t - 1, ['f', 'r']] = 1e9
    assert two_regime_at(poisoned, 4, t, MIN_PANEL_ROWS) == out


def test_country_rows_align_bands_and_never_look_past_the_origin():
    ix = pd.period_range('2000-01', '2015-12', freq='M'); rng = np.random.default_rng(2)
    rates = pd.Series(.2 + rng.normal(scale=.05, size=len(ix)), index=ix)
    published = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=19), index=ix)
    origins = pd.PeriodIndex(['2012-03', '2015-09'], freq='M')
    rows = pd.DataFrame(country_rows(rates, published, 'XX', origins))
    first = rows[rows.origin == origins[0]].set_index('band')
    assert list(first.index) == list(BANDS) and (first.label_end == [origins[0] + 3 * b for b in BANDS]).all()
    assert abs(first.f.iloc[0] - .2) < .1 and first.mu.iloc[0] == pytest.approx(robust_norm(100 * np.log1p(rates.loc[:'2012-02'] / 100)))
    last = rows[rows.origin == origins[1]].set_index('band')
    assert np.isfinite(last.r.loc[1]) and np.isnan(last.r.loc[2])                 # October-December 2015 exist; January 2016 does not
    poisoned = rates.copy(); poisoned.loc['2012-03':] = 50.
    again = pd.DataFrame(country_rows(poisoned, published, 'XX', origins[:1])).set_index('band')
    np.testing.assert_allclose(again.f, first.f, atol=0, rtol=0); np.testing.assert_allclose(again.mu, first.mu, atol=0, rtol=0)


def test_czech_correction_is_zero_without_shrinkage_or_without_a_deviation():
    f = np.array([.30, .28, .27, .27])
    np.testing.assert_allclose(czech_correction(f, .2, np.ones(4)), 0.)
    np.testing.assert_allclose(czech_correction(np.full(4, .2), .2, np.array([.9, .8, .6, .5])), 0.)
    np.testing.assert_allclose(czech_correction(f, .2, np.array([.9, .8, .6, .5])), (np.array([.9, .8, .6, .5]) - 1) * (f - .2))
