"""R27: gap, speed and correction mechanics of the food error-correction candidate."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from models import food_ecm_r27 as m


def panel(months=130, seed=5, alpha=-.08):
    """Synthetic log levels: producer prices random walk, retail = 0.9*ppi + trend + a mean-reverting margin with a seasonal."""
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


def test_last_common_month_respects_each_series_release():
    levels, available = panel()
    published = m.published_levels(levels, available, '2024-06', pd.Timestamp('2024-06-12'))  # May food out (9 Jun), May ppi not (15 Jun)
    assert str(published.food.last_valid_index()) == '2024-05' and str(published.food_ppi.last_valid_index()) == '2024-04'
    assert str(m.last_common_month(published)) == '2024-04'
    later = m.published_levels(levels, available, '2024-06', pd.Timestamp('2024-06-27'))
    assert str(m.last_common_month(later)) == '2024-05'


def test_gap_is_centred_and_trend_absorbs_drift():
    levels, available = panel()
    published = m.published_levels(levels, available, '2024-06', pd.Timestamp('2024-06-27'))
    gap, audit = m.gap_series(published, ['food_ppi', 'agri4'], m.last_common_month(published))
    assert audit['status'] == 'estimated' and audit['n'] == 96 and abs(gap.mean()) < 1e-9
    assert abs(audit['trend_per_month'] - .05) < .03 and abs(audit['coef_food_ppi'] - .9) < .15 and abs(audit['coef_agri4']) < .1
    assert audit['gap_seasonal_share_raw'] > .1 and audit['gap_seasonal_share_centred'] < 1e-9


def test_speed_recovers_the_sign_and_is_clipped():
    levels, available = panel(alpha=-.08)
    published = m.published_levels(levels, available, '2024-06', pd.Timestamp('2024-06-27'))
    gap, _ = m.gap_series(published, ['food_ppi', 'agri4'], m.last_common_month(published))
    alpha, audit = m.adjustment_speed(published, gap)
    assert -.25 <= alpha < 0 and not audit['wrong_sign']
    flipped = -gap  # a gap with the wrong sign convention gives a positive raw speed and no correction
    alpha2, audit2 = m.adjustment_speed(published, flipped)
    assert alpha2 == 0. and audit2['wrong_sign'] and audit2['alpha_raw'] > 0


def test_speed_on_the_true_gap_is_the_ar_coefficient_up_to_small_sample_bias():
    rng = np.random.default_rng(11); months = 130; index = pd.period_range('2015-01', periods=months, freq='M'); gap = np.zeros(months)
    for i in range(1, months):
        gap[i] = .92 * gap[i - 1] + rng.normal(0, .5)
    food = 10 + .1 * np.arange(months) + gap; published = pd.DataFrame(dict(food=food), index=index)
    alpha, audit = m.adjustment_speed(published, pd.Series(gap, index=index))
    assert audit['status'] == 'estimated' and -.20 < alpha < -.03  # true -.08; the in-sample regression on a detrended gap runs faster than the truth


def test_estimated_gap_runs_faster_than_the_true_gap():
    # Documented bias: detrending and projecting on a random-walk regressor makes the residual mean-revert in sample.
    levels, available = panel(alpha=-.08)
    published = m.published_levels(levels, available, '2024-06', pd.Timestamp('2024-06-27'))
    gap, _ = m.gap_series(published, ['food_ppi', 'agri4'], m.last_common_month(published))
    alpha, _ = m.adjustment_speed(published, gap)
    assert alpha <= -.08


def test_correction_decays_from_the_last_gap_month_and_stops_at_h6():
    corr = m.correction(-.1, 2., '2024-04', '2024-06')
    assert corr[1] == pytest.approx(-.1 * 2. * .9 ** 2) and corr[2] == pytest.approx(-.1 * 2. * .9 ** 3)
    assert corr[6] == pytest.approx(-.1 * 2. * .9 ** 7) and all(corr[h] == 0. for h in range(7, 13))


def test_candidates_reproduce_baseline_when_speed_is_zero_and_shift_only_h1_to_h6():
    levels, available = panel()
    base = np.full(12, .25)
    out = m.candidates_at(levels, available, '2024-06', pd.Timestamp('2024-06-27'), base, fixed_alphas=(0., -.05))
    assert out['status'] == 'estimated' and set(out['paths']) >= {'FOOD_ECM_R27', 'FOOD_ECM_PPI_R27', 'FOOD_ECM_A000_R27', 'FOOD_ECM_A005_R27'}
    zero = np.asarray(out['log_rates']['FOOD_ECM_A000_R27']); assert np.allclose(zero, base)
    est = np.asarray(out['log_rates']['FOOD_ECM_R27']); assert np.allclose(est[6:], base[6:]) and not np.allclose(est[:6], base[:6])
    assert out['paths']['FOOD_ECM_A000_R27'][3] == pytest.approx(float(100 * np.expm1(.25 / 100)))


def test_short_history_is_reported_not_forced():
    levels, available = panel(months=34)
    out = m.candidates_at(levels, available, '2017-11', pd.Timestamp('2017-11-27'), np.zeros(12))
    assert out['status'] == 'insufficient_window' and not out['paths']
